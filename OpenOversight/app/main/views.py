import base64
import boto3
import csv
import datetime
import io
import os
import re
import sys
import requests
from xml.etree import ElementTree # for PACER get
from datetime import datetime
from http import HTTPMethod, HTTPStatus
from traceback import format_exc
from werkzeug.utils import secure_filename

from flask import (
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    send_from_directory,
)
from flask_login import current_user, login_required, login_user
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename

from sqlalchemy import select, func, distinct, literal_column, case, union_all, desc, literal_column, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased, contains_eager, joinedload, selectinload
from sqlalchemy.orm.exc import NoResultFound


from OpenOversight.app import limiter, sitemap
from OpenOversight.app.auth.forms import LoginForm
from OpenOversight.app.main import main
from OpenOversight.app.main.downloads import (
    assignment_record_maker,
    descriptions_record_maker,
    incidents_record_maker,
    links_record_maker,
    make_downloadable_csv,
    officer_record_maker,
    salary_record_maker,
)
from OpenOversight.app.main.forms import (
    AddImageForm,
    AddOfficerForm,
    AddUnitForm,
    AssignmentForm,
    BrowseForm,
    DepartmentForm,
    EditDepartmentForm,
    EditOfficerForm,
    EditTextForm,
    FaceTag,
    FindOfficerForm,
    IncidentForm,
    IncidentListForm,
    OfficerLinkForm,
    SalaryForm,
    TextForm,
    # OOVA
    AddDocumentForm, 
    AddMultiDocumentForm,
    EditDocumentForm,
    DocumentsForm, 
    SearchFaceForm, 
    SearchTagForm, 
    EditTagForm, 
    MergeTagForm, 
    PostForm,
    AddSheetForm, 
    SheetMapForm, 
    SheetMatchForm,
    LawsuitListForm,
    LawsuitEditForm,
    DupOfficerForm,
    DupMergeForm,
)
from OpenOversight.app.main.model_view import ModelView
from OpenOversight.app.models.database import (
    Assignment,
    Department,
    Description,
    Face,
    Image,
    Incident,
    Job,
    LicensePlate,
    Link,
    Location,
    Note,
    Officer,
    Salary,
    Unit,
    User,
    db,
    # OOVA
    Document,
    Post,
    Sheet,
    SheetDetail,
    Tag,
    Lawsuit,
    DupOfficerMatches,
    officer_links
)
from OpenOversight.app.models.database_cache import (
    get_database_cache_entry,
    put_database_cache_entry,
)
from OpenOversight.app.utils.auth import ac_or_admin_required, admin_required, edit_required
from OpenOversight.app.utils.choices import AGE_CHOICES, GENDER_CHOICES, RACE_CHOICES
from OpenOversight.app.utils.cloud import (
    crop_image,
    upload_document_to_s3_and_store_in_db,
    save_image_to_s3_and_db,
)
from OpenOversight.app.utils.constants import (
    ENCODING_UTF_8,
    FLASH_MSG_PERMANENT_REDIRECT,
    KEY_DEPT_ALL_ASSIGNMENTS,
    KEY_DEPT_ALL_INCIDENTS,
    KEY_DEPT_ALL_LINKS,
    KEY_DEPT_ALL_NOTES,
    KEY_DEPT_ALL_OFFICERS,
    KEY_DEPT_ALL_SALARIES,
    KEY_DEPT_TOTAL_ASSIGNMENTS,
    KEY_DEPT_TOTAL_OFFICERS,
    KEY_OFFICERS_PER_PAGE,
    KEY_TIMEZONE,
)
from OpenOversight.app.utils.db import (
    add_department_query,
    add_unit_query,
    compute_leaderboard_stats,
    dept_choices,
    unit_choices,
    unsorted_dept_choices,
)
from OpenOversight.app.utils.forms import (
    add_new_assignment,
    add_officer_profile,
    create_description,
    create_incident,
    create_note,
    edit_existing_assignment,
    edit_officer_profile,
    filter_by_form,
    roster_lookup,
    set_dynamic_default,
)
from OpenOversight.app.utils.general import (
    AVAILABLE_TIMEZONES,
    ac_can_edit_officer,
    allowed_file,
    allowed_doc_file,
    get_or_create,
    get_random_image,
    replace_list,
    serve_image,
    validate_redirect_url,
)

# OOVA
from OpenOversight.app.sheet_import import (
    upload_sheet,
    insert_sheet_details,
    prep_ref_data,
    match_officers,
    load_sheet,
    bulk_expire_officers,
    load_incident_sheet
)

from OpenOversight.app.officer_matching import (
    duplicate_officer_bulk_search,
    merge_officers,
)

# Ensure the file is read/write by the creator only
SAVED_UMASK = os.umask(0o077)

sitemap_endpoints = []


def sitemap_include(view):
    sitemap_endpoints.append(view.__name__)
    return view


@sitemap.register_generator
def static_routes():
    for endpoint in sitemap_endpoints:
        yield "main." + endpoint, {}


def redirect_url(default="main.index"):
    return (
        validate_redirect_url(session.get("next"))
        or request.referrer
        or url_for(default)
    )


@sitemap_include
@main.route("/")
@main.route("/index")
def index():
    return render_template("index.html")
    
@main.route("/robots.txt")
def static_from_root():
    return send_from_directory(current_app.static_folder, request.path[1:])


@main.route("/timezone", methods=[HTTPMethod.POST])
def set_session_timezone():
    if KEY_TIMEZONE not in session:
        timezone = request.data.decode(ENCODING_UTF_8)
        if timezone != "" and timezone in AVAILABLE_TIMEZONES:
            session[KEY_TIMEZONE] = timezone
        else:
            session[KEY_TIMEZONE] = current_app.config.get(KEY_TIMEZONE)
    return Response("User timezone saved", status=HTTPStatus.OK)


@sitemap_include
@main.route("/browse", methods=[HTTPMethod.GET])
def browse():
    departments = Department.query.order_by(
        Department.state.asc(), Department.name.asc()
    )
    stats_q = select(Department.id,
                   func.count(distinct(Officer.id)).label("num_officers"),
                   func.count(distinct(Incident.id)).label("num_incidents"),
                   func.count(distinct(Document.id)).label("num_documents")
    ).join(Officer, isouter=True).join(Incident, isouter=True).join(Document, isouter=True)\
    .group_by(Department.id)
    dept_stats = db.session.execute(stats_q).all()
    dept_stats = {x[0]: x[1:] for x in dept_stats}
    return render_template("browse.html", departments=departments, stats=dept_stats)


@sitemap_include
@main.route("/find", methods=[HTTPMethod.GET, HTTPMethod.POST])
def get_officer():
    form = FindOfficerForm()

    # TODO: Figure out why this test is failing when the departments are sorted using
    #  the dept_choices function.
    departments_dict = [
        dept_choice.to_custom_dict() for dept_choice in unsorted_dept_choices()
    ]

    if getattr(current_user, "dept_pref_rel", None):
        set_dynamic_default(form.dept, current_user.dept_pref_rel)

    if form.validate_on_submit():
        return redirect(
            url_for(
                "main.list_officer",
                department_id=form.data["dept"].id,
                race=form.data["race"] if form.data["race"] != "Not Sure" else None,
                gender=form.data["gender"]
                if form.data["gender"] != "Not Sure"
                else None,
                rank=form.data["rank"] if form.data["rank"] != "Not Sure" else None,
                unit=form.data["unit"] if form.data["unit"] != "Not Sure" else None,
                current_job=form.data["current_job"] or None,
                # set to None if False
                min_age=form.data["min_age"],
                max_age=form.data["max_age"],
                first_name=form.data["first_name"],
                last_name=form.data["last_name"],
                badge=form.data["badge"],
                unique_internal_identifier=form.data["unique_internal_identifier"],
            ),
            code=HTTPStatus.FOUND,
        )
    else:
        current_app.logger.info(form.errors)
    return render_template(
        "input_find_officer.html",
        form=form,
        depts_dict=departments_dict,
        jsloads=["js/find_officer.js"],
    )


@main.route("/label", methods=[HTTPMethod.GET, HTTPMethod.POST])
def redirect_get_started_labeling():
    return redirect(
        url_for("main.get_started_labeling"), code=HTTPStatus.PERMANENT_REDIRECT
    )


@sitemap_include
@main.route("/labels", methods=[HTTPMethod.GET, HTTPMethod.POST])
def get_started_labeling():
    if not current_user.is_authenticated:
        return redirect(url_for("main.volunteer"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.by_email(form.email.data).first()
        if user is not None and user.verify_password(form.password.data):
            login_user(user, form.remember_me.data)
            return redirect(url_for("main.get_started_labeling"))
        flash("Invalid username or password.")
    else:
        current_app.logger.info(form.errors)

    # fast way to list all departments with (a) unclassified images (is there any cop), (b) untagged images (cop with unknown id)
    dept_images = db.session.execute(
            select(Department)
                .join(Image.department)
                .where(
                    or_(Image.contains_cops == None, 
                        and_(Image.contains_cops == True,
                             Image.is_tagged==False)
                        )
                    ).distinct()
        ).scalars().all()

    return render_template("label_data.html", departments=dept_images, form=form)

@sitemap_include
@main.route("/volunteer", methods=[HTTPMethod.GET])
def volunteer():
    return render_template("volunteer.html")

@sitemap_include
@main.route("/information", methods=[HTTPMethod.GET])
def information():
    return render_template("information.html")

@main.route(
    "/sort/department/<int:department_id>", methods=[HTTPMethod.GET, HTTPMethod.POST]
)
@login_required
def redirect_sort_images(department_id: int):
    return redirect(
        url_for("main.sort_images", department_id=department_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/sort/departments/<int:department_id>", methods=[HTTPMethod.GET, HTTPMethod.POST]
)
@login_required
def sort_images(department_id: int):
    # Select a random unsorted image from the database
    image_query = Image.query.filter_by(contains_cops=None).filter_by(
        department_id=department_id
    )
    image = get_random_image(image_query)

    if image:
        proper_path = serve_image(image.filepath)
    else:
        proper_path = None
    return render_template(
        "sort.html", image=image, path=proper_path, department_id=department_id
    )


@sitemap_include
@main.route("/tutorial")
def get_tutorial():
    return render_template("tutorial.html")


@main.route("/user/<username>")
@login_required
def profile(username: str):
    if re.search("^[A-Za-z][A-Za-z0-9_.]*$", username):
        user = User.by_username(username).one()
    else:
        abort(HTTPStatus.NOT_FOUND)
    try:
        pref = User.query.filter_by(id=current_user.id).one().dept_pref
        department = Department.query.filter_by(id=pref).one().name
    except NoResultFound:
        department = None
    return render_template("profile.html", user=user, department=department)


@main.route("/officer/<int:officer_id>", methods=[HTTPMethod.GET, HTTPMethod.POST])
def redirect_officer_profile(officer_id: int):
    return redirect(
        url_for("main.officer_profile", officer_id=officer_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/officers/<int:officer_id>", methods=[HTTPMethod.GET, HTTPMethod.POST])
def officer_profile(officer_id: int):
    form = AssignmentForm()
    try:
        officer = Officer.query.filter_by(id=officer_id).one()
        #officer.incidents.query.order_by(Incident.date.desc(), Incident.time.desc())
    except NoResultFound:
        abort(HTTPStatus.NOT_FOUND)
    except:  # noqa: E722
        exception_type, value, full_traceback = sys.exc_info()
        error_str = " ".join([str(exception_type), str(value), format_exc()])
        current_app.logger.error(f"Error finding officer: {error_str}")
    form.job_title.query = (
        Job.query.filter_by(department_id=officer.department_id)
        .order_by(Job.order.asc())
        .all()
    )

    # OOVA
    form.unit.query = Unit.query\
                              .filter_by(department_id=officer.department_id)\
                              .all()

    set_dynamic_default(form.dept, officer.department)
    
    try:
        faces = (
            Face.query.filter_by(officer_id=officer_id)
            .order_by(Face.featured.desc())
            .all()
        )
        assignments = (Assignment.query
            .filter_by(officer_id=officer_id)
            .order_by(Assignment.resign_date.desc().nulls_first(), Assignment.start_date.desc().nulls_last())
            .all())
        face_paths = [(face, serve_image(face.image.filepath)) for face in faces]
        if not face_paths:
            # Add in the placeholder image if no faces are found
            face_paths = [(None, url_for("static", filename="images/placeholder.png"))]
    except:  # noqa: E722
        exception_type, value, full_traceback = sys.exc_info()
        error_str = " ".join([str(exception_type), str(value), format_exc()])
        current_app.logger.error(f"Error loading officer profile: {error_str}")
    if faces:
        officer.image_url = faces[0].image.filepath
        if not officer.image_url.startswith("http"):
            officer.image_url = url_for(
                "static",
                filename=faces[0].image.filepath.replace("/static/", ""),
            )
        if faces[0].face_width and faces[0].face_height:
            officer.image_width = faces[0].face_width
            officer.image_height = faces[0].face_height

    return render_template(
        "officer.html",
        officer=officer,
        face_paths=face_paths,
        assignments=assignments,
        form=form,
        jsloads=['js/dynamic_lists.js', 'js/add_assignment.js'],
    )


@sitemap.register_generator
def sitemap_officers():
    for officer in Officer.query.all():
        yield "main.officer_profile", {"officer_id": officer.id}


@main.route(
    "/officer/<int:officer_id>/assignment/new",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@ac_or_admin_required
def redirect_add_assignment(officer_id: int):
    return redirect(
        url_for("main.add_assignment", officer_id=officer_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/officers/<int:officer_id>/assignments/new", methods=[HTTPMethod.POST])
@ac_or_admin_required
def add_assignment(officer_id: int):
    form = AssignmentForm()
    officer = Officer.query.filter_by(id=officer_id).first()
    # specifically not filtering by officer.department_id bc it breaks job_title validation
    form.job_title.query = (
        Job.query
        .order_by(Job.order.asc())
        .all()
        #.filter_by(department_id=officer.department_id)
    )
    if not officer:
        flash("Officer not found")
        abort(HTTPStatus.NOT_FOUND)

    if form.validate_on_submit():
        if current_user.is_administrator or (
            current_user.is_area_coordinator
            and officer.department_id == current_user.ac_department_id
        ):
            try:
                add_new_assignment(officer_id, form, current_user)
                Department(id=officer.department_id).remove_database_cache_entries(
                    [KEY_DEPT_ALL_ASSIGNMENTS, KEY_DEPT_TOTAL_ASSIGNMENTS],
                )
                flash("Added new assignment!")
            except IntegrityError:
                flash("Assignment already exists")
            return redirect(
                url_for("main.officer_profile", officer_id=officer_id),
                code=HTTPStatus.FOUND,
            )
        elif (
            current_user.is_area_coordinator
            and not officer.department_id == current_user.ac_department_id
        ):
            abort(HTTPStatus.FORBIDDEN)
    else:
        current_app.logger.info(form.errors)
        flash("Error: " + str(form.errors))

        return redirect(url_for("main.officer_profile", officer_id=officer_id))


@main.route(
    "/officer/<int:officer_id>/assignment/<int:assignment_id>",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@login_required
@ac_or_admin_required
def redirect_edit_assignment(officer_id: int, assignment_id: int):
    return redirect(
        url_for(
            "main.edit_assignment", officer_id=officer_id, assignment_id=assignment_id
        ),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/officers/<int:officer_id>/assignments/<int:assignment_id>",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@login_required
@ac_or_admin_required
def edit_assignment(officer_id: int, assignment_id: int):
    officer = Officer.query.filter_by(id=officer_id).one()

    if current_user.is_area_coordinator and not current_user.is_administrator:
        if not ac_can_edit_officer(officer, current_user):
            abort(HTTPStatus.FORBIDDEN)

    
    assignment = Assignment.query.filter_by(id=assignment_id).one()
    form = AssignmentForm(obj=assignment)
    form.job_title.query = (
        Job.query
        .order_by(Job.order.asc())
        .all()
        #.filter_by(department_id=assignment.department_id) # oova; see add_assignment
    )
    # OOVA
    form.unit.query = (
        Unit.query.filter_by(department_id=assignment.department_id)
        .all()
    )
    form.job_title.data = Job.query.filter_by(id=assignment.job_id).one()
    form.dept.data = Department.query.filter_by(id=assignment.department_id).one()
    form.is_edit = True
    if form.unit.data and type(form.unit.data) == int:
        form.unit.data = Unit.query.filter_by(id=form.unit.data).one()
    if form.dept.data and type(form.dept.data) == int:
        form.dept.data = Department.query.filter_by(id=form.unit.data).one()
    if form.validate_on_submit():
        form.job_title.data = Job.query.filter_by(
            id=int(form.job_title.raw_data[0])
        ).one()
        assignment = edit_existing_assignment(assignment, form)
        Department(id=officer.department_id).remove_database_cache_entries(
            [KEY_DEPT_ALL_ASSIGNMENTS],
        )
        flash(f"Edited officer assignment ID {assignment.id}")
        return redirect(url_for("main.officer_profile", officer_id=officer_id))
    else:
        current_app.logger.info(form.errors)
    return render_template("edit_assignment.html",
        form=form,
        jsloads=['js/dynamic_lists.js', 'js/add_assignment.js'],
        )

# OOVA added
@main.route("/officer/<int:officer_id>/assignment/<int:assignment_id>/delete", methods=[HTTPMethod.GET])
@login_required
@ac_or_admin_required
def delete_assignment(officer_id, assignment_id):
    assignment = Assignment.query.filter_by(id=assignment_id).first()
    if not assignment:
        flash("Assignment not found")
        abort(HTTPStatus.NOT_FOUND)
    if not current_user.is_administrator and current_user.is_area_coordinator:
        if current_user.ac_department_id != assignment.officer.department_id:
            abort(HTTPStatus.FORBIDDEN)
    try:
        db.session.delete(assignment)
        db.session.commit()
        flash("Deleted this assignment")
    except:  # noqa
        flash("Unknown error occurred")
        exception_type, value, full_tback = sys.exc_info()
        current_app.logger.error("Error deleting assignment: {}".format(
            " ".join([str(exception_type), str(value),
                      format_exc()])
        ))
    return redirect(url_for("main.officer_profile", officer_id=officer_id))


@main.route(
    "/officer/<int:officer_id>/salary/new", methods=[HTTPMethod.GET, HTTPMethod.POST]
)
@edit_required
def redirect_add_salary(officer_id: int):
    return redirect(
        url_for("main.add_salary", officer_id=officer_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/officers/<int:officer_id>/salaries/new", methods=[HTTPMethod.GET, HTTPMethod.POST]
)
@edit_required
def add_salary(officer_id: int):
    form = SalaryForm()
    officer = Officer.query.filter_by(id=officer_id).first()
    if not officer:
        flash("Officer not found")
        abort(HTTPStatus.NOT_FOUND)

    if form.validate_on_submit() and (
        current_user.can_edit()
    ):
        try:
            new_salary = Salary(
                officer_id=officer_id,
                salary=form.salary.data,
                overtime_pay=form.overtime_pay.data,
                year=form.year.data,
                is_fiscal_year=form.is_fiscal_year.data,
                created_by=current_user.id,
                last_updated_by=current_user.id,
            )
            db.session.add(new_salary)
            db.session.commit()
            Department(id=officer.department_id).remove_database_cache_entries(
                [KEY_DEPT_ALL_SALARIES],
            )
            flash("Added new salary!")
        except IntegrityError as e:
            db.session.rollback()
            flash(f"Error adding new salary: {e}")
        return redirect(
            url_for("main.officer_profile", officer_id=officer_id),
            code=HTTPStatus.FOUND,
        )
    else:
        return render_template("add_edit_salary.html", form=form)


@main.route(
    "/officer/<int:officer_id>/salary/<int:salary_id>",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@login_required
@ac_or_admin_required
def redirect_edit_salary(officer_id: int, salary_id: int):
    return redirect(
        url_for("main.edit_salary", officer_id=officer_id, salary_id=salary_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/officers/<int:officer_id>/salaries/<int:salary_id>",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@login_required
@ac_or_admin_required
def edit_salary(officer_id: int, salary_id: int):
    officer = Officer.query.filter_by(id=officer_id).one()
    if current_user.is_area_coordinator and not current_user.is_administrator:
        if not ac_can_edit_officer(officer, current_user):
            abort(HTTPStatus.FORBIDDEN)

    salary = Salary.query.filter_by(id=salary_id).one()
    form = SalaryForm(obj=salary)
    if form.validate_on_submit():
        form.populate_obj(salary)
        db.session.add(salary)
        db.session.commit()
        Department(id=officer.department_id).remove_database_cache_entries(
            [KEY_DEPT_ALL_SALARIES],
        )
        flash(f"Edited officer salary ID {salary.id}")
        return redirect(url_for("main.officer_profile", officer_id=officer_id))
    else:
        current_app.logger.info(form.errors)
    return render_template("add_edit_salary.html", form=form, update=True)


@main.route("/image/<int:image_id>")
@login_required
def redirect_display_submission(image_id: int):
    return redirect(
        url_for("main.display_submission", image_id=image_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/images/<int:image_id>")
@login_required
def display_submission(image_id: int):
    try:
        image = Image.query.filter_by(id=image_id).one()
        proper_path = serve_image(image.filepath)
    except NoResultFound:
        abort(HTTPStatus.NOT_FOUND)
    return render_template("image.html", image=image, path=proper_path)


@main.route("/tag/<int:tag_id>")
def redirect_display_tag(tag_id: int):
    return redirect(
        url_for("main.display_tag", tag_id=tag_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/tags/<int:tag_id>")
def display_tag(tag_id: int):
    try:
        tag = Face.query.filter_by(id=tag_id).one()
        proper_path = serve_image(tag.image.filepath) # upstream changed from image to original_image
    except NoResultFound:
        abort(HTTPStatus.NOT_FOUND)
    return render_template(
        "tag.html", face=tag, path=proper_path, jsloads=["js/tag.js"]
    )


@main.route(
    "/image/classify/<int:image_id>/<int:contains_cops>", methods=[HTTPMethod.POST]
)
@login_required
def redirect_classify_submission(image_id: int, contains_cops: int):
    return redirect(
        url_for(
            "main.classify_submission", image_id=image_id, contains_cops=contains_cops
        ),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/images/classify/<int:image_id>/<int:contains_cops>", methods=[HTTPMethod.POST]
)
@login_required
def classify_submission(image_id: int, contains_cops: int):
    try:
        image = Image.query.filter_by(id=image_id).one()
        if image.contains_cops is not None and not current_user.is_administrator:
            flash("Only administrator can re-classify image")
            return redirect(redirect_url())
        if contains_cops == 1:
            image.contains_cops = True
        elif contains_cops == 0:
            image.contains_cops = False
        image.last_updated_by = current_user.id
        db.session.commit()
        flash("Updated image classification")
    except:  # noqa: E722
        flash("Unknown error occurred")
        exception_type, value, full_traceback = sys.exc_info()
        error_str = " ".join([str(exception_type), str(value), format_exc()])
        current_app.logger.error(f"Error classifying image: {error_str}")
    return redirect(redirect_url())


@main.route("/department/new", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@admin_required
def redirect_add_department():
    return redirect(
        url_for("main.add_department"),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/departments/new", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@admin_required
def add_department():
    form = DepartmentForm()
    if form.validate_on_submit():
        department_does_not_exist = (
            Department.query.filter_by(
                name=form.name.data, state=form.state.data
            ).count()
            == 0
        )

        if department_does_not_exist:
            department = Department(
                name=form.name.data,
                short_name=form.short_name.data,
                state=form.state.data,
                created_by=current_user.id,
                last_updated_by=current_user.id,
            )
            db.session.add(department)
            db.session.flush()
            db.session.add(
                Job(job_title="Not Sure", order=0, department_id=department.id)
            )
            db.session.flush()
            if form.jobs.data:
                order = 1
                for job in form.data["jobs"]:
                    if job:
                        db.session.add(
                            Job(
                                job_title=job,
                                order=order,
                                is_sworn_officer=True,
                                department_id=department.id,
                            )
                        )
                        order += 1
                db.session.commit()
            flash(
                f"New department {department.name} in {department.state} added"
            )
        else:
            flash(f"Department {form.name.data} in {form.state.data} already exists")
        return redirect(url_for("main.get_started_labeling"))
    else:
        current_app.logger.info(form.errors)
        return render_template(
            "department_add_edit.html",
            form=form,
            jsloads=["js/jquery-ui.min.js", "js/deptRanks.js"],
        )


@main.route(
    "/department/<int:department_id>/edit", methods=[HTTPMethod.GET, HTTPMethod.POST]
)
@login_required
@admin_required
def redirect_edit_department(department_id: int):
    return redirect(
        url_for("main.edit_department", department_id=department_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/departments/<int:department_id>/edit", methods=[HTTPMethod.GET, HTTPMethod.POST]
)
@login_required
@admin_required
def edit_department(department_id: int):
    department = Department.query.get_or_404(department_id)
    previous_name = department.name
    form = EditDepartmentForm(obj=department)
    original_ranks = department.jobs
    if form.validate_on_submit():
        if form.name.data != previous_name:
            does_already_department_exist = (
                Department.query.filter_by(
                    name=form.name.data, state=form.state.data
                ).count()
                > 0
            )

            if does_already_department_exist:
                flash(
                    f"Department {form.name.data} in {form.state.data} already exists"
                )
                return redirect(
                    url_for("main.edit_department", department_id=department_id)
                )

        department.name = form.name.data
        department.short_name = form.short_name.data
        department.state = form.state.data
        department.last_updated_by = current_user.id
        db.session.flush()
        if form.jobs.data:
            new_ranks = []
            order = 1
            for rank in form.data["jobs"]:
                if rank:
                    new_ranks.append((rank, order))
                    order += 1
            updated_ranks = form.jobs.data
            if len(updated_ranks) < len(original_ranks):
                deleted_ranks = [
                    rank
                    for rank in original_ranks
                    if rank.job_title not in updated_ranks
                ]
                if (
                    Assignment.query.filter(
                        Assignment.job_id.in_([rank.id for rank in deleted_ranks])
                    ).count()
                    == 0
                ):
                    for rank in deleted_ranks:
                        db.session.delete(rank)
                else:
                    failed_deletions = []
                    for rank in deleted_ranks:
                        if (
                            Assignment.query.filter(
                                Assignment.job_id.in_([rank.id])
                            ).count()
                            != 0
                        ):
                            failed_deletions.append(rank)
                    for rank in failed_deletions:
                        flash(
                            f"You attempted to delete a rank, {rank}, that is still in use"
                        )
                    return redirect(
                        url_for("main.edit_department", department_id=department_id)
                    )

            for new_rank, order in new_ranks:
                existing_rank = Job.query.filter_by(
                    department_id=department_id, job_title=new_rank
                ).one_or_none()
                if existing_rank:
                    existing_rank.is_sworn_officer = True
                    existing_rank.order = order
                else:
                    db.session.add(
                        Job(
                            job_title=new_rank,
                            order=order,
                            is_sworn_officer=True,
                            department_id=department_id,
                        )
                    )
            db.session.commit()

        flash(f"Department {department.name} in {department.state} edited")
        return redirect(url_for("main.list_officer", department_id=department.id))
    else:
        current_app.logger.info(form.errors)
        return render_template(
            "department_add_edit.html",
            form=form,
            update=True,
            jsloads=["js/jquery-ui.min.js", "js/deptRanks.js"],
        )

@main.route("/departments/<int:department_id>/")
def department_profile(department_id: int):
    try:
        dept = Department.query.filter_by(id=department_id).one()
    except NoResultFound:
        abort(HTTPStatus.NOT_FOUND)
    except:  # noqa: E722
        exception_type, value, full_traceback = sys.exc_info()
        error_str = " ".join([str(exception_type), str(value), format_exc()])
        current_app.logger.error(f"Error finding department: {error_str}")
    return render_template(
        "department.html",
        dept=dept,
    )

@sitemap.register_generator
def sitemap_departments():
    for dept in Department.query.all():
        yield "main.department_profile", {"department_id": dept.id}

@main.route("/department/<int:department_id>")
def redirect_list_officer(
    department_id: int,
    page: int = 1,
    race=None,
    gender=None,
    rank=None,
    min_age: str = "16",
    max_age: str = "100",
    last_name=None,
    first_name=None,
    badge=None,
    unique_internal_identifier=None,
    unit=None,
    current_job=None,
    require_photo: bool = False,
):
    return redirect(
        url_for(
            "main.list_officer",
            department_id=department_id,
            page=page,
            race=race,
            gender=gender,
            rank=rank,
            min_age=min_age,
            max_age=max_age,
            last_name=last_name,
            first_name=first_name,
            badge=badge,
            unique_internal_identifier=unique_internal_identifier,
            unit=unit,
            current_job=current_job,
            require_photo=require_photo,
        ),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/departments/<int:department_id>/officers/")
def list_officer(
    department_id: int,
    page: int = 1,
    race=None,
    gender=None,
    rank=None,
    min_age=None,
    max_age=None,
    last_name=None,
    first_name=None,
    badge=None,
    unique_internal_identifier=None,
    unit=None,
    current_job=False,
    require_photo: bool = False,
):
    form = BrowseForm()
    form.rank.query = (
        Job.query.filter_by(department_id=department_id, is_sworn_officer=True)
        .order_by(Job.order.asc())
        .all()
    )
    form_data = form.data
    form_data["race"] = race or []
    form_data["gender"] = gender or []
    form_data["rank"] = rank or []
    form_data["min_age"] = min_age
    form_data["max_age"] = max_age
    form_data["last_name"] = last_name
    form_data["first_name"] = first_name
    form_data["badge"] = badge
    form_data["unit"] = unit or []
    form_data["current_job"] = current_job or False
    form_data["unique_internal_identifier"] = unique_internal_identifier
    form_data["require_photo"] = require_photo

    department = Department.query.filter_by(id=department_id).first()
    if not department:
        abort(HTTPStatus.NOT_FOUND)

    age_range = {ac[0] for ac in AGE_CHOICES}

    # Set form data based on URL
    if (min_age_arg := request.args.get("min_age")) and min_age_arg in age_range:
        form_data["min_age"] = min_age_arg
    if (max_age_arg := request.args.get("max_age")) and max_age_arg in age_range:
        form_data["max_age"] = max_age_arg
    if page_arg := request.args.get("page"):
        page = int(page_arg)
    if last_name_arg := request.args.get("last_name"):
        form_data["last_name"] = last_name_arg
    if first_name_arg := request.args.get("first_name"):
        form_data["first_name"] = first_name_arg
    if badge_arg := request.args.get("badge"):
        form_data["badge"] = badge_arg
    if uid := request.args.get("unique_internal_identifier"):
        form_data["unique_internal_identifier"] = uid
    if (races := request.args.getlist("race")) and all(
        race in [rc[0] for rc in RACE_CHOICES] for race in races
    ):
        form_data["race"] = races
    if (genders := request.args.getlist("gender")) and all(
        # Every time you complain we add a new gender
        gender in [gc[0] for gc in GENDER_CHOICES]
        for gender in genders
    ):
        form_data["gender"] = genders
    if require_photo_arg := request.args.get("require_photo"):
        form_data["require_photo"] = (require_photo_arg.lower() in ('y','true'))

    unit_selections = ["Not Sure"] + [
        uc[0]
        for uc in db.session.query(Unit.description)
        .filter_by(department_id=department_id)
        .order_by(Unit.description.asc())
        .all()
    ]
    rank_selections = [
        jc[0]
        for jc in db.session.query(Job.job_title, Job.order)
        .filter_by(department_id=department_id)
        .order_by(Job.job_title)
        .all()
    ]
    if (units := request.args.getlist("unit")) and all(
        unit in unit_selections for unit in units
    ):
        form_data["unit"] = units
    if (ranks := request.args.getlist("rank")) and all(
        rank in rank_selections for rank in ranks
    ):
        form_data["rank"] = ranks
    if current_job_arg := request.args.get("current_job") :
        form_data["current_job"] = (current_job_arg.lower() in ('y','true'))
    

    #if len(form_data["unit"]) == 1 and "Not Sure" in form_data["unit"]:
    #    form_data["unit"].remove("Not Sure")
    
    # pass short name for acab/wandering filter
    form_data["dept_short_name"] = department.short_name

    officers = filter_by_form(form_data, Officer.query, department_id).filter(
        Officer.department_id == department_id
    )

    # Filter officers by presence of a photo
    if form_data["require_photo"]:
        officers = officers.join(Face)
    else:
        officers = officers.options(selectinload(Officer.face))

    officers = officers.order_by(Officer.last_name, Officer.first_name, Officer.id)

    officers = officers.paginate(
        page=page, per_page=current_app.config[KEY_OFFICERS_PER_PAGE], error_out=False
    )

    for officer in officers.items:
        officer_face = sorted(officer.face, key=lambda x: x.featured, reverse=True)

        # Could do some extra work to not lazy load images but load them all together.
        # To do that properly we would want to ensure to only load the first picture of
        # each officer.
        if officer_face and officer_face[0].image:
            officer.image = officer_face[0].image.filepath

    choices = {
        "race": RACE_CHOICES,
        "gender": GENDER_CHOICES,
        "rank": [(rc, rc) for rc in rank_selections],
        "unit": [(uc, uc) for uc in unit_selections],
    }

    next_url = url_for(
        "main.list_officer",
        department_id=department.id,
        page=officers.next_num,
        race=form_data["race"],
        gender=form_data["gender"],
        rank=form_data["rank"],
        min_age=form_data["min_age"],
        max_age=form_data["max_age"],
        last_name=form_data["last_name"],
        first_name=form_data["first_name"],
        badge=form_data["badge"],
        unique_internal_identifier=form_data["unique_internal_identifier"],
        unit=form_data["unit"],
        current_job='Y' if form_data["current_job"] else None,
        require_photo='Y' if form_data["require_photo"] else None,
    )
    prev_url = url_for(
        "main.list_officer",
        department_id=department.id,
        page=officers.prev_num,
        race=form_data["race"],
        gender=form_data["gender"],
        rank=form_data["rank"],
        min_age=form_data["min_age"],
        max_age=form_data["max_age"],
        last_name=form_data["last_name"],
        first_name=form_data["first_name"],
        badge=form_data["badge"],
        unique_internal_identifier=form_data["unique_internal_identifier"],
        unit=form_data["unit"],
        current_job='Y' if form_data["current_job"] else None,
        require_photo='Y' if form_data["require_photo"] else None,
    )

    return render_template(
        "list_officer.html",
        form=form,
        department=department,
        officers=officers,
        form_data=form_data,
        choices=choices,
        next_url=next_url,
        prev_url=prev_url,
        jsloads=["js/select2.min.js", "js/list_officer.js"],
    )


@main.route("/department/<int:department_id>/ranks")
def redirect_get_dept_ranks(department_id: int = 0, is_sworn_officer: bool = False):
    return redirect(
        url_for(
            "main.get_dept_ranks",
            department_id=department_id,
            is_sworn_officer=is_sworn_officer,
        ),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/departments/<int:department_id>/ranks")
@main.route("/ranks")
def get_dept_ranks(department_id: int = 0, is_sworn_officer: bool = False):
    if not department_id:
        department_id = request.args.get("department_id")
    if request.args.get("is_sworn_officer"):
        is_sworn_officer = request.args.get("is_sworn_officer")

    if department_id:
        ranks = Job.query.filter_by(department_id=department_id)
        if is_sworn_officer:
            ranks = ranks.filter_by(is_sworn_officer=True)
        ranks = ranks.order_by(Job.job_title).all()
        rank_list = [(rank.id, rank.job_title) for rank in ranks]
    else:
        # Not filtering by is_sworn_officer
        ranks = Job.query.all()
        # Prevent duplicate ranks
        rank_list = sorted(
            set((rank.id, rank.job_title) for rank in ranks),
            key=lambda x: x[1],
        )

    return jsonify(rank_list)


@main.route("/department/<int:department_id>/units")
def redirect_get_dept_units(department_id: int = 0):
    return redirect(
        url_for("main.get_dept_ranks", department_id=department_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/departments/<int:department_id>/units")
@main.route("/units")
def get_dept_units(department_id: int = 0):
    if not department_id:
        department_id = request.args.get("department_id")

    if department_id:
        units = Unit.query.filter_by(department_id=department_id)
        units = units.order_by(Unit.description).all()
        unit_list = [(unit.id, unit.description) for unit in units]
    else:
        units = Unit.query.all()
        # Prevent duplicate units
        unit_list = sorted(
            set((unit.id, unit.description) for unit in units),
            key=lambda x: x[1],
        )

    return jsonify(unit_list)


@main.route("/officer/new", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@ac_or_admin_required
def redirect_add_officer():
    return redirect(
        url_for("main.add_officer"),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/officers/new", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@ac_or_admin_required
def add_officer():
    form = AddOfficerForm()
    add_unit_query(form, current_user)
    add_department_query(form, current_user)
    set_dynamic_default(form.department, current_user.dept_pref_rel)

    if (
        form.validate_on_submit()
        and not current_user.is_administrator
        and form.department.data.id != current_user.ac_department_id
    ):
        abort(HTTPStatus.FORBIDDEN)
    if form.validate_on_submit():
        # Work around for WTForms limitation with boolean fields in FieldList
        new_form_data = request.form.copy()
        for key in new_form_data.keys():
            if re.fullmatch(r"salaries-\d+-is_fiscal_year", key):
                new_form_data[key] = "y"
        form = AddOfficerForm(new_form_data)
        officer = add_officer_profile(form, current_user)
        Department(id=officer.department_id).remove_database_cache_entries(
            [KEY_DEPT_ALL_OFFICERS, KEY_DEPT_TOTAL_OFFICERS]
        )
        flash(f"New Officer {officer.last_name} added")
        return redirect(url_for("main.submit_officer_images", officer_id=officer.id))
    else:
        current_app.logger.info(form.errors)
        return render_template(
            "add_officer.html",
            form=form,
            jsloads=["js/dynamic_lists.js", "js/add_officer.js"],
        )


@main.route("/officer/<int:officer_id>/edit", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@ac_or_admin_required
def redirect_edit_officer(officer_id: int):
    return redirect(
        url_for("main.edit_officer", officer_id=officer_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/officers/<int:officer_id>/edit", methods=[HTTPMethod.GET, HTTPMethod.POST]
)
@login_required
@ac_or_admin_required
def edit_officer(officer_id: int):
    officer = Officer.query.filter_by(id=officer_id).one()
    form = EditOfficerForm(obj=officer)

    if request.method == HTTPMethod.GET:
        if officer.race is None:
            form.race.data = "Not Sure"
        if officer.gender is None:
            form.gender.data = "Not Sure"

    if current_user.is_area_coordinator and not current_user.is_administrator:
        if not ac_can_edit_officer(officer, current_user):
            abort(HTTPStatus.FORBIDDEN)

    add_department_query(form, current_user)

    form.tags = request.form.getlist("tags[]")

    if form.validate_on_submit():
        officer = edit_officer_profile(officer, form)
        Department(id=officer.department_id).remove_database_cache_entries(
            [KEY_DEPT_TOTAL_OFFICERS]
        )
        new_tags = form.tags
        del form.tags
        tags = []
        for new_tag in new_tags:
            if (new_tag.isdigit()):
                tag = Tag.query.filter_by(id=new_tag).first()
                if tag is not None:
                    tags.append(tag)
            else:
                tag = db.session.add(Tag(
                            tag=new_tag
                        ))
                db.session.commit()
                tag = Tag.query.filter_by(tag=new_tag).first()
                tags.append(tag)
        officer.tags = tags
        db.session.commit()

        flash(f"Officer {officer.last_name} edited")
        return redirect(url_for("main.officer_profile", officer_id=officer.id))
    else:
        current_app.logger.info(form.errors)
        return render_template(
            "edit_officer.html", form=form, officer=officer, jsloads=["js/dynamic_lists.js"]
        )


@main.route("/unit/new", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@ac_or_admin_required
def redirect_add_unit():
    return redirect(
        url_for("main.add_unit"),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/units/new", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@ac_or_admin_required
def add_unit():
    form = AddUnitForm()
    add_department_query(form, current_user)
    set_dynamic_default(form.department, current_user.dept_pref_rel)

    if form.validate_on_submit():
        unit = Unit(
            description=form.description.data, department_id=form.department.data.id
        )
        db.session.add(unit)
        db.session.commit()
        flash(f"New unit {unit.description} added")
        return redirect(url_for("main.get_started_labeling"))
    else:
        current_app.logger.info(form.errors)
        return render_template("add_unit.html", form=form)


@main.route("/tag/delete/<int:tag_id>", methods=[HTTPMethod.POST])
@login_required
@ac_or_admin_required
def redirect_delete_tag(tag_id: int):
    return redirect(
        url_for("main.delete_tag", tag_id=tag_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/tags/delete/<int:tag_id>", methods=[HTTPMethod.POST])
@login_required
@ac_or_admin_required
def delete_tag(tag_id: int):
    tag = Face.query.filter_by(id=tag_id).first()

    if not tag:
        flash("Tag not found")
        abort(HTTPStatus.NOT_FOUND)

    if not current_user.is_administrator and current_user.is_area_coordinator:
        if current_user.ac_department_id != tag.officer.department_id:
            abort(HTTPStatus.FORBIDDEN)

    officer_id = tag.officer_id
    try:
        db.session.delete(tag)
        db.session.commit()
        flash("Deleted this tag")
    except:  # noqa: E722
        flash("Unknown error occurred")
        exception_type, value, full_tback = sys.exc_info()
        current_app.logger.error("Error classifying image: {}".format(
            " ".join([str(exception_type), str(value),
                      format_exc()])
        ))
    return redirect(url_for("main.officer_profile", officer_id=officer_id))


@main.route("/tag/set_featured/<int:tag_id>", methods=[HTTPMethod.POST])
@login_required
@edit_required
def redirect_set_featured_tag(tag_id: int):
    return redirect(
        url_for("main.set_featured_tag", tag_id=tag_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/tags/set_featured/<int:tag_id>", methods=[HTTPMethod.POST])
@login_required
@edit_required
def set_featured_tag(tag_id: int):
    tag = Face.query.filter_by(id=tag_id).first()

    if not tag:
        flash("Tag not found")
        abort(HTTPStatus.NOT_FOUND)

    if not current_user.can_edit:
        abort(HTTPStatus.FORBIDDEN)

    # Set featured=False on all other tags for the same officer
    for face in Face.query.filter_by(officer_id=tag.officer_id).all():
        face.featured = False
    # Then set this tag as featured
    tag.featured = True

    try:
        db.session.commit()
        flash("Successfully set this tag as featured")
    except:  # noqa: E722
        flash("Unknown error occurred")
        exception_type, value, full_traceback = sys.exc_info()
        error_str = " ".join([str(exception_type), str(value), format_exc()])
        current_app.logger.error(f"Error setting featured tag: {error_str}")
    return redirect(url_for("main.officer_profile", officer_id=tag.officer_id))


@main.route("/leaderboard")
@login_required
def leaderboard():
    top_sorters, top_taggers = compute_leaderboard_stats()
    return render_template(
        "leaderboard.html", top_sorters=top_sorters, top_taggers=top_taggers
    )


@main.route(
    "/cop_face/department/<int:department_id>/images/<int:image_id>",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@main.route("/cop_face/image/<int:image_id>", methods=[HTTPMethod.GET, HTTPMethod.POST])
@main.route(
    "/cop_face/department/<int:department_id>",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@main.route("/cop_face/", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
def redirect_label_data(department_id: int = 0, image_id: int = 0):
    return redirect(
        url_for("main.label_data", department_id=department_id, image_id=image_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/cop_faces/departments/<int:department_id>/images/<int:image_id>",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@main.route(
    "/cop_faces/images/<int:image_id>", methods=[HTTPMethod.GET, HTTPMethod.POST]
)
@main.route(
    "/cop_faces/departments/<int:department_id>",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@main.route("/cop_faces/", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
def label_data(department_id: int = 0, image_id: int = 0):
    if department_id:
        department = Department.query.filter_by(id=department_id).one()
        if image_id:
            image = (
                Image.query.filter_by(id=image_id)
                .filter_by(department_id=department_id)
                .first()
            )
        else:  # Get a random image from that department
            image_query = (
                Image.query.filter_by(contains_cops=True)
                .filter_by(department_id=department_id)
                .filter_by(is_tagged=False)
            )
            image = get_random_image(image_query)
    else:
        department = None
        if image_id:
            image = Image.query.filter_by(id=image_id).one()
        else:
            # Select a random untagged image from the entire database
            image_query = Image.query.filter_by(contains_cops=True).filter_by(
                is_tagged=False
            )
            image = get_random_image(image_query)

    if image:
        if image.is_tagged and not current_user.is_administrator:
            flash("This image cannot be tagged anymore")
            return redirect(url_for("main.label_data"))
        proper_path = serve_image(image.filepath)
    else:
        proper_path = None

    form = FaceTag()
    if form.validate_on_submit():
        officer_exists = Officer.query.filter_by(id=form.officer_id.data).first()
        existing_tag = (
            db.session.query(Face)
            .filter(Face.officer_id == form.officer_id.data)
            .filter(Face.original_image_id == form.image_id.data)
            .first()
        )
        if not officer_exists:
            flash("Invalid officer ID. Please select a valid OpenOversight ID!")
        elif department and officer_exists.department_id != department_id:
            flash(
                f"The officer is not in {department.name}, {department.state}. "
                "Are you sure that is the correct OpenOversight ID?"
            )
        elif not existing_tag:
            left = form.dataX.data
            upper = form.dataY.data
            right = left + form.dataWidth.data
            lower = upper + form.dataHeight.data

            cropped_image = crop_image(
                image,
                crop_data=(left, upper, right, lower),
                department_id=department_id,
            )
            cropped_image.contains_cops = True
            cropped_image.is_tagged = True

            if cropped_image:
                new_tag = Face(
                    officer_id=form.officer_id.data,
                    img_id=cropped_image.id,
                    original_image_id=image.id,
                    face_position_x=left,
                    face_position_y=upper,
                    face_width=form.dataWidth.data,
                    face_height=form.dataHeight.data,
                    created_by=current_user.id,
                    last_updated_by=current_user.id,
                )
                db.session.add(new_tag)
                db.session.commit()
                flash("Tag added to database")
            else:
                flash("There was a problem saving this tag. Please try again later.")
        else:
            flash("Tag already exists between this officer and image! Tag not added.")
    else:
        current_app.logger.info(form.errors)

    return render_template(
        "cop_face.html",
        form=form,
        image=image,
        path=proper_path,
        department=department,
        jsloads=["js/cropper.js", "js/tagger.js"],
    )


@main.route("/image/tagged/<int:image_id>")
@login_required
def redirect_complete_tagging(image_id: int):
    return redirect(
        url_for("main.complete_tagging", image_id=image_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/images/tagged/<int:image_id>")
@login_required
def complete_tagging(image_id: int):
    # Select a random untagged image from the database
    image = Image.query.filter_by(id=image_id).first()
    if not image:
        abort(HTTPStatus.NOT_FOUND)
    image.is_tagged = True
    image.last_updated_by = current_user.id
    db.session.commit()
    flash("Marked image as completed.")
    department_id = request.args.get("department_id")
    if department_id:
        return redirect(url_for("main.label_data", department_id=department_id))
    else:
        return redirect(url_for("main.label_data"))


@main.route("/tagger_gallery/<int:page>", methods=[HTTPMethod.GET, HTTPMethod.POST])
@main.route("/tagger_gallery", methods=[HTTPMethod.GET, HTTPMethod.POST])
def get_tagger_gallery(page=1):
    form = FindOfficerIDForm()
    if form.validate_on_submit():
        OFFICERS_PER_PAGE = int(current_app.config[KEY_OFFICERS_PER_PAGE])
        form_data = form.data
        officers = roster_lookup(form_data).paginate(page=page, per_page=OFFICERS_PER_PAGE, error_out=False)
        return render_template("tagger_gallery.html",
                               officers=officers,
                               form=form,
                               form_data=form_data)
    else:
        current_app.logger.info(form.errors)
        return redirect(url_for("main.get_ooid"), code=307)

@main.route("/complaint", methods=[HTTPMethod.GET, HTTPMethod.POST])
def redirect_submit_complaint():
    return redirect(
        url_for("main.submit_complaint"),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/complaints", methods=[HTTPMethod.GET, HTTPMethod.POST])
def submit_complaint():
    return render_template(
        "complaint.html",
        officer_first_name=request.args.get("officer_first_name", ""),
        officer_last_name=request.args.get("officer_last_name", ""),
        officer_middle_initial=request.args.get("officer_middle_name", ""),
        officer_star=request.args.get("officer_star", ""),
        officer_image=request.args.get("officer_image", ""),
    )


@sitemap_include
@main.route("/submit", methods=[HTTPMethod.GET, HTTPMethod.POST])
@limiter.limit("5/minute")
def submit_data():
    preferred_dept_id = Department.query.first().id
    # try to use preferred department if available
    try:
        if User.query.filter_by(id=current_user.id).one().dept_pref:
            preferred_dept_id = User.query.filter_by(id=current_user.id).one().dept_pref
            form = AddImageForm()
        else:
            form = AddImageForm()
        return render_template(
            "submit_image.html", form=form, preferred_dept_id=preferred_dept_id
        )
    # that is, an anonymous user has no id attribute
    except (AttributeError, NoResultFound):
        preferred_dept_id = Department.query.first().id
        form = AddImageForm()
        return render_template(
            "submit_image.html", form=form, preferred_dept_id=preferred_dept_id
        )


@main.route(
    "/download/department/<int:department_id>/officers", methods=[HTTPMethod.GET]
)
def redirect_download_dept_officers_csv(department_id: int):
    return redirect(
        url_for("main.download_dept_officers_csv", department_id=department_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/download/departments/<int:department_id>/officers", methods=[HTTPMethod.GET]
)
@limiter.limit("5/minute")
def download_dept_officers_csv(department_id: int):
    cache_params = (Department(id=department_id), KEY_DEPT_ALL_OFFICERS)
    officers = get_database_cache_entry(*cache_params)
    if officers is None:
        officers = (
            db.session.query(Officer)
            .options(joinedload(Officer.assignments).joinedload(Assignment.job))
            .options(joinedload(Officer.salaries))
            .filter_by(department_id=department_id)
            .all()
        )
        put_database_cache_entry(*cache_params, officers)

    field_names = [
        "id",
        "unique identifier",
        "last name",
        "first name",
        "middle initial",
        "suffix",
        "gender",
        "race",
        "birth year",
        "employment date",
        "badge number",
        "job title",
        "most recent salary",
    ]
    return make_downloadable_csv(
        officers, department_id, "Officers", field_names, officer_record_maker
    )


@main.route(
    "/download/department/<int:department_id>/assignments", methods=[HTTPMethod.GET]
)
def redirect_download_dept_assignments_csv(department_id: int):
    return redirect(
        url_for("main.download_dept_assignments_csv", department_id=department_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/download/departments/<int:department_id>/assignments", methods=[HTTPMethod.GET]
)
@limiter.limit("5/minute")
def download_dept_assignments_csv(department_id: int):
    cache_params = Department(id=department_id), KEY_DEPT_ALL_ASSIGNMENTS
    assignments = get_database_cache_entry(*cache_params)
    if assignments is None:
        assignments = (
            db.session.query(Assignment)
            .join(Assignment.base_officer)
            .filter(Officer.department_id == department_id)
            .options(contains_eager(Assignment.base_officer))
            .options(joinedload(Assignment.unit))
            .options(joinedload(Assignment.job))
            .all()
        )
        put_database_cache_entry(*cache_params, assignments)

    field_names = [
        "id",
        "officer id",
        "officer unique identifier",
        "badge number",
        "job title",
        "start date",
        "end date",
        "unit id",
        "unit description",
    ]
    return make_downloadable_csv(
        assignments,
        department_id,
        "Assignments",
        field_names,
        assignment_record_maker,
    )


@main.route(
    "/download/department/<int:department_id>/incidents", methods=[HTTPMethod.GET]
)
def redirect_download_incidents_csv(department_id: int):
    return redirect(
        url_for("main.download_incidents_csv", department_id=department_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/download/departments/<int:department_id>/incidents", methods=[HTTPMethod.GET]
)
@limiter.limit("5/minute")
def download_incidents_csv(department_id: int):
    cache_params = (Department(id=department_id), KEY_DEPT_ALL_INCIDENTS)
    incidents = get_database_cache_entry(*cache_params)
    if incidents is None:
        incidents = Incident.query.filter_by(department_id=department_id).all()
        put_database_cache_entry(*cache_params, incidents)

    field_names = [
        "id",
        "report_num",
        "date",
        "time",
        "description",
        "location",
        "licenses",
        "links",
        "officers",
    ]
    return make_downloadable_csv(
        incidents,
        department_id,
        "Incidents",
        field_names,
        incidents_record_maker,
    )


@main.route(
    "/download/department/<int:department_id>/salaries", methods=[HTTPMethod.GET]
)
def redirect_download_dept_salaries_csv(department_id: int):
    return redirect(
        url_for("main.download_dept_salaries_csv", department_id=department_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/download/departments/<int:department_id>/salaries", methods=[HTTPMethod.GET]
)
@limiter.limit("5/minute")
def download_dept_salaries_csv(department_id: int):
    cache_params = (Department(id=department_id), KEY_DEPT_ALL_SALARIES)
    salaries = get_database_cache_entry(*cache_params)
    if salaries is None:
        salaries = (
            db.session.query(Salary)
            .join(Salary.officer)
            .filter(Officer.department_id == department_id)
            .options(contains_eager(Salary.officer))
            .all()
        )
        put_database_cache_entry(*cache_params, salaries)

    field_names = [
        "id",
        "officer id",
        "first name",
        "last name",
        "salary",
        "overtime_pay",
        "year",
        "is_fiscal_year",
    ]
    return make_downloadable_csv(
        salaries, department_id, "Salaries", field_names, salary_record_maker
    )


@main.route("/download/department/<int:department_id>/links", methods=[HTTPMethod.GET])
def redirect_download_dept_links_csv(department_id: int):
    return redirect(
        url_for("main.download_dept_links_csv", department_id=department_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/download/departments/<int:department_id>/links", methods=[HTTPMethod.GET])
@limiter.limit("5/minute")
def download_dept_links_csv(department_id: int):
    cache_params = (Department(id=department_id), KEY_DEPT_ALL_LINKS)
    links = get_database_cache_entry(*cache_params)
    if links is None:
        links = (
            db.session.query(Link)
            .join(Link.officers)
            .filter(Officer.department_id == department_id)
            .options(contains_eager(Link.officers))
            .all()
        )
        put_database_cache_entry(*cache_params, links)

    field_names = [
        "id",
        "title",
        "url",
        "link_type",
        "description",
        "author",
        "officers",
        "incidents",
    ]
    return make_downloadable_csv(
        links, department_id, "Links", field_names, links_record_maker
    )


@main.route(
    "/download/department/<int:department_id>/descriptions", methods=[HTTPMethod.GET]
)
def redirect_download_dept_descriptions_csv(department_id: int):
    return redirect(
        url_for("main.download_dept_descriptions_csv", department_id=department_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/download/departments/<int:department_id>/descriptions", methods=[HTTPMethod.GET]
)
@limiter.limit("5/minute")
def download_dept_descriptions_csv(department_id: int):
    cache_params = (Department(id=department_id), KEY_DEPT_ALL_NOTES)
    notes = get_database_cache_entry(*cache_params)
    if notes is None:
        notes = (
            db.session.query(Description)
            .join(Description.officer)
            .filter(Officer.department_id == department_id)
            .options(contains_eager(Description.officer))
            .all()
        )
        put_database_cache_entry(*cache_params, notes)

    field_names = [
        "id",
        "text_contents",
        "created_by",
        "officer_id",
        "created_at",
        "last_updated_at",
    ]
    return make_downloadable_csv(
        notes, department_id, "Notes", field_names, descriptions_record_maker
    )


@sitemap_include
@main.route("/download/all", methods=[HTTPMethod.GET])
def all_data():
    departments = Department.query.filter(Department.officers.any()).order_by(Department.name)
    return render_template("departments_all.html", departments=departments)


@main.route(
    "/submit_officer_images/officer/<int:officer_id>",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@login_required
@edit_required
def redirect_submit_officer_images(officer_id: int):
    return redirect(
        url_for("main.submit_officer_images", officer_id=officer_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route(
    "/submit_officer_images/officers/<int:officer_id>",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@login_required
@edit_required
def submit_officer_images(officer_id: int):
    officer = Officer.query.get_or_404(officer_id)
    return render_template("submit_officer_image.html", officer=officer)


@main.route("/upload/department/<int:department_id>", methods=[HTTPMethod.POST])
@main.route(
    "/upload/department/<int:department_id>/officer/<int:officer_id>",
    methods=[HTTPMethod.POST],
)
@login_required
def redirect_upload(department_id: int = 0, officer_id: int = 0):
    return redirect(
        url_for("main.upload", department_id=department_id, officer_id=officer_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@main.route("/upload/departments/<int:department_id>", methods=[HTTPMethod.POST])
@main.route(
    "/upload/departments/<int:department_id>/officers/<int:officer_id>",
    methods=[HTTPMethod.POST],
)
@login_required
@limiter.limit("250/minute")
def upload(department_id: int = 0, officer_id: int = 0):
    if officer_id:
        officer = Officer.query.filter_by(id=officer_id).first()
        if not officer:
            return jsonify(error="This officer does not exist."), HTTPStatus.NOT_FOUND
        if not (
            current_user.can_edit()
            or
            current_user.is_administrator
            or (
                current_user.is_area_coordinator
                and officer.department_id == current_user.ac_department_id
            )
        ):
            return (
                jsonify(
                    error="You are not authorized to upload photos of this officer."
                ),
                HTTPStatus.FORBIDDEN,
            )
    file_to_upload = request.files["file"]
    if not allowed_file(file_to_upload.filename):
        return (
            jsonify(error="File type not allowed!"),
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
        )

    try:
        image = save_image_to_s3_and_db(
            file_to_upload, current_user.id, department_id=department_id
        )
    except ValueError:
        # Raised if MIME type not allowed
        return jsonify(error="Invalid data type!"), HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    if image:
        db.session.add(image)
        if officer_id:
            image.is_tagged = True
            image.contains_cops = True
            face = Face(
                officer_id=officer_id,
                # Assuming photos uploaded with an officer ID are already cropped,
                # we set both images to the uploaded one
                img_id=image.id,
                original_image_id=image.id,
                created_by=current_user.id,
                last_updated_by=current_user.id,
            )
            db.session.add(face)
            db.session.commit()
        return jsonify(success="Success!"), HTTPStatus.OK
    else:
        return (
            jsonify(error="Server error encountered. Try again later."),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@sitemap_include
@main.route("/about")
def about_oo():
    return render_template("about.html")


@sitemap_include
@main.route("/privacy")
def privacy_oo():
    return render_template("privacy.html")


@sitemap_include
@main.route("/donate")
def donate_oo():
    return render_template("donate.html")


@main.route("/shutdown")  # pragma: no cover
def server_shutdown():  # pragma: no cover
    if not current_app.testing:
        abort(HTTPStatus.NOT_FOUND)
    shutdown = request.environ.get("werkzeug.server.shutdown")
    if not shutdown:
        abort(HTTPStatus.INTERNAL_SERVER_ERROR)
    shutdown()
    return "Shutting down..."


class IncidentApi(ModelView):
    model = Incident
    model_name = "incident"
    order_by = "date"
    descending = True
    form = IncidentForm
    create_function = create_incident
    department_check = True

    def get(self, obj_id: int):
        if obj_id:
            # Single-item view
            return super(IncidentApi, self).get(obj_id)

        # List view
        page = int(request.args.get("page", 1))

        form = IncidentListForm()
        incidents = self.model.query

        if report_number := request.args.get("report_number"):
            form.report_number.data = report_number
            incidents = incidents.filter(
                Incident.report_number.contains(report_number.strip())
            )

        dept = None
        if (department_id := request.args.get("department_id")) and request.args.get("department_id") != '__None':
            dept = Department.query.get_or_404(department_id)
            form.department_id.data = dept
            incidents = incidents.filter_by(department_id=dept.id)

        if occurred_before := request.args.get("occurred_before"):
            before_date = datetime.strptime(occurred_before, "%Y-%m-%d").date()
            form.occurred_before.data = before_date
            incidents = incidents.filter(self.model.date < before_date)

        if occurred_after := request.args.get("occurred_after"):
            after_date = datetime.strptime(occurred_after, "%Y-%m-%d").date()
            form.occurred_after.data = after_date
            incidents = incidents.filter(self.model.date > after_date)

        if desc_search := request.args.get("desc_search"):
            form.desc_search.data = desc_search
            # just a simple exact-match search (case insensitive)
            incidents = incidents.filter(Incident.description.ilike(f"%{desc_search}%"))

        incidents = incidents.order_by(
            Incident.date.desc(), Incident.time.desc()
        ).paginate(page=page, per_page=self.per_page, error_out=False)

        url = f"main.{self.model_name}_api"
        next_url = url_for(
            url,
            page=incidents.next_num,
            department_id=department_id,
            report_number=report_number,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
        )
        prev_url = url_for(
            url,
            page=incidents.prev_num,
            department_id=department_id,
            report_number=report_number,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
        )

        return render_template(
            f"{self.model_name}_list.html",
            form=form,
            incidents=incidents,
            url=url,
            next_url=next_url,
            prev_url=prev_url,
            department=dept,
        )

    def get_new_form(self):
        form = self.form()
        if request.args.get("officer_id"):
            form.officers[0].oo_id.data = request.args.get("officer_id")

        form.tags = request.form.getlist("tags[]")
        return form

    def get_edit_form(self, obj: Incident):
        form = super(IncidentApi, self).get_edit_form(obj=obj)

        #no_license_plates = len(obj.license_plates)
        no_links = len(obj.links)
        no_officers = len(obj.officers)
        tags = obj.tags

        for officer_idx, officer in enumerate(obj.officers):
            form.officers[officer_idx].oo_id.data = officer.id

        # set the form to have fields for all the current model's items
        #form.license_plates.min_entries = no_license_plates
        form.links.min_entries = no_links
        form.officers.min_entries = no_officers
        form.incident_id = obj.id
        form.tags = tags
        if not form.date_field.data and obj.date:
            form.date_field.data = obj.date
        if not form.time_field.data and obj.time:
            form.time_field.data = obj.time
        return form

    def populate_obj(self, form: FlaskForm, obj: Incident):
        # remove all fields not directly on the Incident model
        # use utils to add them to the current object
        address = form.data.pop("address")
        del form.address
        if address["city"]:
            new_address, _ = get_or_create(db.session, Location, **address)
            obj.address = new_address
        else:
            obj.address = None

        links = form.data.pop("links")
        del form.links
        if links and links[0]["url"]:
            replace_list(links, obj, "links", Link, db)

        new_tags = request.form.getlist("tags[]")
        tags = []
        for new_tag in new_tags:
            if (new_tag.isdigit()):
                tag = Tag.query.filter_by(id=new_tag).first()
                if tag is not None:
                    tags.append(tag)
            else:
                tag = db.session.add(Tag(
                            tag=new_tag
                        ))
                db.session.commit()
                tag = Tag.query.filter_by(tag=new_tag).first()
                tags.append(tag)

        obj.tags = tags
        officers = form.data.pop("officers")
        del form.officers
        if officers:
            for officer in officers:
                if officer["oo_id"]:
                    try:
                        of = Officer.query.filter_by(id=int(officer["oo_id"])).first()
                    # Sometimes we get a string in officer["oo_id"], this parses it
                    except ValueError:
                        our_id = officer["oo_id"].split('value="')[1][:-2]
                        of = Officer.query.filter_by(id=int(our_id)).first()
                    if of and of not in obj.officers:
                        obj.officers.append(of)

        #license_plates = form.data.pop("license_plates")
        #del form.license_plates
        #if license_plates and license_plates[0]["number"]:
        #    replace_list(license_plates, obj, "license_plates", LicensePlate, db)

        obj.date = form.date_field.data
        if form.time_field.raw_data and form.time_field.raw_data != [""]:
            obj.time = form.time_field.data
        else:
            obj.time = None
        super(IncidentApi, self).populate_obj(form, obj)


incident_view = IncidentApi.as_view("incident_api")
main.add_url_rule(
    "/incidents/",
    defaults={"obj_id": None},
    endpoint="incident_api",
    view_func=incident_view,
    methods=[HTTPMethod.GET],
)
main.add_url_rule(
    "/incidents/new",
    endpoint="incident_api_new",
    view_func=incident_view,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/incidents/<int:obj_id>",
    endpoint="incident_api",
    view_func=incident_view,
    methods=[HTTPMethod.GET],
)
main.add_url_rule(
    "/incidents/<int:obj_id>/edit",
    endpoint="incident_api_edit",
    view_func=incident_view,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/incidents/<int:obj_id>/delete",
    endpoint="incident_api_delete",
    view_func=incident_view,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)


@sitemap.register_generator
def sitemap_incidents():
    for incident in Incident.query.all():
        yield "main.incident_api", {"obj_id": incident.id}

# This is the page to upload a new spreadsheet containing incidents
@main.route("/incidents/bulk", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@admin_required
@limiter.limit("5/minute")
def submit_incident_sheet():
    form = AddSheetForm()
    if form.validate_on_submit():
        try:
            file_data = form.file.data
            filename = secure_filename(file_data.filename)
            sheet = upload_sheet(file_data, current_user.id, filename)
            flash("Sheet was successfully uploaded")
        except Exception as e:
            import traceback
            flash(f"An error occurred while uploading {file_data} {filename}")
            flash(traceback.format_exc())
            return redirect("/incidents/bulk")
        # actually read the csv and create incidents
        load_incident_sheet(sheet)
        return redirect(url_for("main.incident_api"))
    else:
        return render_template("import/import_incidents.html", form=form)


class TextApi(ModelView):
    order_by = "created_at"
    descending = True
    department_check = True
    form = TextForm

    def get_new_form(self):
        form = self.form()
        form.officer_id.data = self.officer_id
        return form

    def get_redirect_url(self, *args, **kwargs):
        return redirect(url_for("main.officer_profile", officer_id=self.officer_id))

    def get_post_delete_url(self, *args, **kwargs):
        return self.get_redirect_url()

    def get_department_id(self, obj: TextForm):
        return self.department_id

    def get_edit_form(self, obj: TextForm):
        form = EditTextForm(obj=obj)
        return form

    def dispatch_request(self, *args, **kwargs):
        if "officer_id" in kwargs:
            officer = Officer.query.get_or_404(kwargs["officer_id"])
            self.officer_id = kwargs.pop("officer_id")
            self.department_id = officer.department_id
        return super(TextApi, self).dispatch_request(*args, **kwargs)


class NoteApi(TextApi):
    model = Note
    model_name = "note"
    form = TextForm
    create_function = create_note

    def dispatch_request(self, *args, **kwargs):
        return super(NoteApi, self).dispatch_request(*args, **kwargs)


class DescriptionApi(TextApi):
    model = Description
    model_name = "description"
    form = TextForm
    create_function = create_description

    def dispatch_request(self, *args, **kwargs):
        return super(DescriptionApi, self).dispatch_request(*args, **kwargs)


@login_required
@edit_required
def redirect_new_note(officer_id: int):
    return redirect(
        url_for("main.note_api", officer_id=officer_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


def redirect_get_notes(officer_id: int, obj_id=None):
    return redirect(
        url_for("main.note_api", officer_id=officer_id, obj_id=obj_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@login_required
@ac_or_admin_required
def redirect_edit_note(officer_id: int, obj_id=None):
    return redirect(
        url_for("main.note_api_edit", officer_id=officer_id, obj_id=obj_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@login_required
@ac_or_admin_required
def redirect_delete_note(officer_id: int, obj_id=None):
    return redirect(
        url_for("main.note_api_delete", officer_id=officer_id, obj_id=obj_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


note_view = NoteApi.as_view("note_api")
main.add_url_rule(
    "/officers/<int:officer_id>/notes/new",
    endpoint="note_api",
    view_func=note_view,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officer/<int:officer_id>/note/new",
    view_func=redirect_new_note,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officers/<int:officer_id>/notes/<int:obj_id>",
    endpoint="note_api",
    view_func=note_view,
    methods=[HTTPMethod.GET],
)
main.add_url_rule(
    "/officer/<int:officer_id>/note/<int:obj_id>",
    view_func=redirect_get_notes,
    methods=[HTTPMethod.GET],
)
main.add_url_rule(
    "/officers/<int:officer_id>/notes/<int:obj_id>/edit",
    endpoint="note_api_edit",
    view_func=note_view,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officer/<int:officer_id>/note/<int:obj_id>/edit",
    view_func=redirect_edit_note,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officers/<int:officer_id>/notes/<int:obj_id>/delete",
    endpoint="note_api_delete",
    view_func=note_view,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officer/<int:officer_id>/note/<int:obj_id>/delete",
    view_func=redirect_delete_note,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)


@login_required
@ac_or_admin_required
def redirect_new_description(officer_id: int):
    return redirect(
        url_for("main.description_api_new", officer_id=officer_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


def redirect_get_description(officer_id: int, obj_id=None):
    return redirect(
        url_for("main.description_api", officer_id=officer_id, obj_id=obj_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@login_required
@ac_or_admin_required
def redirect_edit_description(officer_id: int, obj_id=None):
    return redirect(
        url_for("main.description_api_edit", officer_id=officer_id, obj_id=obj_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@login_required
@ac_or_admin_required
def redirect_delete_description(officer_id: int, obj_id=None):
    return redirect(
        url_for("main.description_api_delete", officer_id=officer_id, obj_id=obj_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


description_view = DescriptionApi.as_view("description_api")
main.add_url_rule(
    "/officers/<int:officer_id>/descriptions/new",
    endpoint="description_api_new",
    view_func=description_view,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officer/<int:officer_id>/description/new",
    view_func=redirect_new_description,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officers/<int:officer_id>/descriptions/<int:obj_id>",
    endpoint="description_api",
    view_func=description_view,
    methods=[HTTPMethod.GET],
)
main.add_url_rule(
    "/officer/<int:officer_id>/description/<int:obj_id>",
    view_func=redirect_get_description,
    methods=[HTTPMethod.GET],
)
main.add_url_rule(
    "/officers/<int:officer_id>/descriptions/<int:obj_id>/edit",
    endpoint="description_api_edit",
    view_func=description_view,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officer/<int:officer_id>/description/<int:obj_id>/edit",
    view_func=redirect_edit_description,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officers/<int:officer_id>/descriptions/<int:obj_id>/delete",
    endpoint="description_api_delete",
    view_func=description_view,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officer/<int:officer_id>/description/<int:obj_id>/delete",
    view_func=redirect_delete_description,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)


class OfficerLinkApi(ModelView):
    """
    This API only applies to links attached to officer profiles, not links attached to
    incidents.
    """

    model = Link
    model_name = "link"
    form = OfficerLinkForm
    department_check = True

    @property
    def officer(self):
        if not hasattr(self, "_officer"):
            self._officer = (
                db.session.query(Officer).filter_by(id=self.officer_id).one()
            )
        return self._officer

    @login_required
    @edit_required
    def new(self, form: FlaskForm = None):
        if (
            not current_user.can_edit()
        ):
            abort(HTTPStatus.FORBIDDEN)
        if not form:
            form = self.get_new_form()

        if form.validate_on_submit():
            link = Link(
                title=form.title.data,
                url=form.url.data,
                link_type=form.link_type.data,
                description=form.description.data,
                author=form.author.data,
                created_by=current_user.id,
                last_updated_by=current_user.id,
            )
            self.officer.links.append(link)
            db.session.add(link)
            db.session.commit()
            Department(id=self.officer.department_id).remove_database_cache_entries(
                [KEY_DEPT_ALL_LINKS]
            )
            flash(f"{self.model_name} created!")
            return self.get_redirect_url(obj_id=link.id)

        return render_template(f"{self.model_name}_new.html", form=form)

    @login_required
    @ac_or_admin_required
    def delete(self, obj_id: int):
        obj = self.model.query.get_or_404(obj_id)
        if (
            not current_user.is_administrator
            and current_user.ac_department_id != self.get_department_id(obj)
        ):
            abort(HTTPStatus.FORBIDDEN)

        if request.method == HTTPMethod.POST:
            db.session.delete(obj)
            db.session.commit()
            Department(id=self.officer.department_id).remove_database_cache_entries(
                [KEY_DEPT_ALL_LINKS]
            )
            flash(f"{self.model_name} successfully deleted!")
            return self.get_post_delete_url()

        return render_template(
            f"{self.model_name}_delete.html",
            obj=obj,
            officer_id=self.officer_id,
        )

    def get_new_form(self):
        form = self.form()
        form.officer_id.data = self.officer_id
        return form

    def get_edit_form(self, obj):
        form = self.form(obj=obj)
        form.officer_id.data = self.officer_id
        return form

    def get_redirect_url(self, *args, **kwargs):
        return redirect(url_for("main.officer_profile", officer_id=self.officer_id))

    def get_post_delete_url(self, *args, **kwargs):
        return self.get_redirect_url()

    def get_department_id(self, obj):
        return self.officer.department_id

    def dispatch_request(self, *args, **kwargs):
        if "officer_id" in kwargs:
            officer = Officer.query.get_or_404(kwargs["officer_id"])
            self.officer_id = kwargs.pop("officer_id")
            self.department_id = officer.department_id
        return super(OfficerLinkApi, self).dispatch_request(*args, **kwargs)


@login_required
@edit_required
def redirect_new_link(officer_id: int):
    return redirect(
        url_for("main.link_api_new", officer_id=officer_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@login_required
@edit_required
def redirect_edit_link(officer_id: int, obj_id=None):
    return redirect(
        url_for("main.link_api_edit", officer_id=officer_id, obj_id=obj_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


@login_required
@ac_or_admin_required
def redirect_delete_link(officer_id: int, obj_id=None):
    return redirect(
        url_for("main.link_api_delete", officer_id=officer_id, obj_id=obj_id),
        code=HTTPStatus.PERMANENT_REDIRECT,
    )


main.add_url_rule(
    "/officers/<int:officer_id>/links/new",
    view_func=OfficerLinkApi.as_view("link_api_new"),
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officer/<int:officer_id>/link/new",
    view_func=redirect_new_link,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officers/<int:officer_id>/links/<int:obj_id>/edit",
    view_func=OfficerLinkApi.as_view("link_api_edit"),
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officer/<int:officer_id>/link/<int:obj_id>/edit",
    view_func=redirect_edit_link,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officers/<int:officer_id>/links/<int:obj_id>/delete",
    view_func=OfficerLinkApi.as_view("link_api_delete"),
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
main.add_url_rule(
    "/officer/<int:officer_id>/link/<int:obj_id>/delete",
    view_func=redirect_delete_link,
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)

## OOVA additions
@sitemap_include
@main.route("/search")
def search_officer(page=1, race=[], gender=[], min_age="16", max_age="100", last_name=None,
                   badge=None, unique_internal_identifier=None, department=[],
                   first_name=None):
    form = BrowseForm()
    form_data = form.data
    form_data["race"] = race
    form_data["gender"] = gender
    form_data["min_age"] = min_age
    form_data["max_age"] = max_age
    form_data["last_name"] = last_name
    form_data["first_name"] = first_name
    form_data["badge"] = badge
    form_data["department"] = department
    form_data["unique_internal_identifier"] = unique_internal_identifier

    OFFICERS_PER_PAGE = int(current_app.config[KEY_OFFICERS_PER_PAGE])

    # Set form data based on URL
    if request.args.get("min_age") and request.args.get("min_age") in [ac[0] for ac in AGE_CHOICES]:
        form_data["min_age"] = request.args.get("min_age")
    if request.args.get("max_age") and request.args.get("max_age") in [ac[0] for ac in AGE_CHOICES]:
        form_data["max_age"] = request.args.get("max_age")
    if request.args.get("page"):
        page = int(request.args.get("page"))
    if request.args.get("last_name"):
        form_data["last_name"] = request.args.get("last_name")
    if request.args.get("first_name"):
        form_data["first_name"] = request.args.get("first_name")
    if request.args.get("badge"):
        form_data["badge"] = request.args.get("badge")
    if request.args.get("unique_internal_identifier"):
        form_data["unique_internal_identifier"] = request.args.get("unique_internal_identifier")
    if request.args.get("race") and all(race in [rc[0] for rc in RACE_CHOICES] for race in request.args.getlist("race")):
        form_data["race"] = request.args.getlist("race")
    if request.args.get("gender") and all(gender in [gc[0] for gc in GENDER_CHOICES] for gender in request.args.getlist("gender")):
        form_data["gender"] = request.args.getlist("gender")
    if request.args.get("department"):
        form_data["department"] = request.args.getlist("department")

    officers = filter_by_form(
        form_data, Officer.query
    )
    if request.args.get("department") and request.args.get("department") != "-1":
        officers = officers.filter(
            Officer.department_id == request.args.get("department")
        )
    officers = officers.options(selectinload(Officer.face))
    officers = officers.order_by(Officer.last_name, Officer.first_name, Officer.id)
    officers = officers.paginate(page=page, per_page=OFFICERS_PER_PAGE, error_out=False)
    for officer in officers.items:
        officer_face = sorted(officer.face, key=lambda x: x.featured, reverse=True)

        # could do some extra work to not lazy load images but load them all together
        # but we would want to ensure to only load the first picture of each officer
        if officer_face and officer_face[0].image:
            officer.image = officer_face[0].image.filepath

    departments = Department.query.order_by(Department.name.asc())
    departmentlist = [(department.id, department.name) for department in departments]

    choices = {
        "department": departmentlist,
        "race": RACE_CHOICES,
        "gender": GENDER_CHOICES
    }

    next_url = url_for("main.search_officer",
                       page=officers.next_num, race=form_data["race"], gender=form_data["gender"],
                       min_age=form_data["min_age"], max_age=form_data["max_age"], last_name=form_data["last_name"], badge=form_data["badge"],
                       unique_internal_identifier=form_data["unique_internal_identifier"], department=form_data["department"],
                       first_name=form_data["first_name"])
    prev_url = url_for("main.search_officer",
                       page=officers.prev_num, race=form_data["race"], gender=form_data["gender"],
                       min_age=form_data["min_age"], max_age=form_data["max_age"], last_name=form_data["last_name"], badge=form_data["badge"],
                       unique_internal_identifier=form_data["unique_internal_identifier"], department=form_data["department"],
                       first_name=form_data["first_name"])

    return render_template(
        "search.html",
        form=form,
        officers=officers,
        form_data=form_data,
        choices=choices,
        next_url=next_url,
        prev_url=prev_url)

@main.route("/search_tags/<int:tag_id>")
def search_tags(tag_id=None):
    form = SearchTagForm()
    form_data = form.data

    tag = Tag.query.filter_by(id=tag_id).first()
    documents = tag.documents
    incidents = tag.incidents

    return render_template(
        "search_tags.html",
        form=form,
        tag=tag,
        documents=documents,
        incidents=incidents,
        form_data=form_data,
        tag_id=tag_id,)

@main.route("/tags", methods=[HTTPMethod.GET])
def get_tags(term=""):
    args = request.args
    term = args["q"]
    tags = Tag.query.filter(Tag.tag.ilike("%%{}%%".format(term)))
    
    tag_list = list({"id":tag.id,"text":tag.tag} for tag in tags)
    results = {"results":tag_list}
    return jsonify(results)

@main.route("/tags/documents/<int:document_id>", methods=[HTTPMethod.GET])
def get_document_tags(document_id=None):
    document = Document.query.filter_by(id=document_id).one()
    tags = document.tags
    
    tag_list = list({"id":tag.id,"text":tag.tag} for tag in tags)
    results = {"results":tag_list}
    return jsonify(results)

@main.route("/tags/incidents/<int:incident_id>", methods=[HTTPMethod.GET])
def get_incident_tags(incident_id=None):
    incident = Incident.query.filter_by(id=incident_id).one()
    tags = incident.tags
    
    tag_list = list({"id":tag.id,"text":tag.tag} for tag in tags)
    results = {"results":tag_list}
    return jsonify(results)

@main.route("/tags/officers/<int:officer_id>", methods=[HTTPMethod.GET])
def get_officer_tags(officer_id=None):
    officer = Officer.query.filter_by(id=officer_id).one()
    tags = officer.tags
    
    tag_list = list({"id":tag.id,"text":tag.tag} for tag in tags)
    results = {"results":tag_list}
    return jsonify(results)

@main.route("/tagger_find", methods=[HTTPMethod.GET, HTTPMethod.POST])
def get_ooid():
    form = FindOfficerIDForm()
    if form.validate_on_submit():
        return redirect(url_for("main.get_tagger_gallery"), code=307)
    else:
        current_app.logger.info(form.errors)
    return render_template("input_find_ooid.html", form=form)

@sitemap_include
@main.route("/documents")
def show_documents(page=1, department=[], title=None):
    form = DocumentsForm()
    form_data = form.data
    form_data["department"] = department
    form_data["title"] = title

    DOCUMENTS_PER_PAGE = int(current_app.config[KEY_OFFICERS_PER_PAGE])

    # Set form data based on URL
    if request.args.get("page"):
        page = int(request.args.get("page"))
    if request.args.get("title"):
        form_data["title"] = request.args.get("title")
    if request.args.get("department"):
        form_data["department"] = request.args.getlist("department")

    documents =  Document.query
    if request.args.get("title"):
        documents = documents.filter(db.or_(Document.title.ilike("%%{}%%".format(form_data["title"])),
            Document.description.ilike("%%{}%%".format(form_data["title"])))
        )
    if request.args.get("department") and request.args.get("department") != "-1":
        documents = documents.filter(
            Document.department_id == request.args.get("department")
        )
    documents = documents.order_by(Document.last_updated_at.desc())
    documents = documents.paginate(page=page, per_page=DOCUMENTS_PER_PAGE, error_out=False)
    departments = Department.query.order_by(Department.name.asc())

    departmentlist = [(department.id, department.name) for department in departments]

    choices = {
        "department": departmentlist,
    }

    next_url = url_for("main.show_documents",
                       page=documents.next_num, department=form_data["department"], title=form_data["title"])
    prev_url = url_for("main.show_documents",
                       page=documents.prev_num, department=form_data["department"], title=form_data["title"])

    return render_template(
        "documents.html",
        form=form,
        documents=documents,
        form_data=form_data,
        choices=choices,
        next_url=next_url,
        prev_url=prev_url)

@main.route("/documents/delete/<int:document_id>", methods=[HTTPMethod.GET])
@login_required
@ac_or_admin_required
def delete_document(document_id):
    document = Document.query.filter_by(id=document_id).first()

    if not document:
        flash("Document not found")
        abort(HTTPStatus.NOT_FOUND)

    if not current_user.is_administrator and current_user.is_area_coordinator:
        if current_user.ac_department_id != document.department.department_id:
            abort(HTTPStatus.FORBIDDEN)

    try:
        db.session.delete(document)
        db.session.commit()
        flash("Deleted the document")
    except:  # noqa
        flash("Unknown error occurred")
        exception_type, value, full_tback = sys.exc_info()
        current_app.logger.error("Error deleting document: {}".format(
            " ".join([str(exception_type), str(value),
                      format_exc()])
        ))
    return redirect(url_for("main.show_documents"))

@main.route("/documents/<int:document_id>/edit", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@admin_required
def edit_document(document_id):
    document = Document.query.filter_by(id=document_id).one()

    dept = Department.query.order_by(Department.name.asc())

    form = EditDocumentForm(obj=document)

    if form.validate_on_submit():
        new_tags = request.form.getlist("tags[]")
        tags = []
        for new_tag in new_tags:
            if (new_tag.isdigit()):
                tag = Tag.query.filter_by(id=new_tag).first()
                if tag is not None:
                    tags.append(tag)
            else:
                tag = db.session.add(Tag(
                            tag=new_tag
                        ))
                db.session.commit()
                tag = Tag.query.filter_by(tag=new_tag).first()
                tags.append(tag)

        document.tags = tags
        document.title = form.title.data
        document.description = form.description.data
        document.department_id = form.department.data.id
        db.session.commit()
        flash("Edited document ID {}".format(document_id))
        return redirect(url_for("main.edit_document", document_id=document_id))
    else:
        current_app.logger.info(form.errors)
    return render_template("edit_document.html", form=form, document_id=document_id)

@main.route("/documents/new", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@edit_required
@limiter.limit("5/minute")
def submit_document():
    form = AddDocumentForm()
    if form.validate_on_submit():
        try:
            file_parts = form.file.data.split(",")
            file_data = file_parts[1]
            data_parts = file_parts[0].split(";")
            content_type = data_parts[0].split(":")[1]
            file_to_upload = base64.b64decode(file_data)
            title = form.title.data
            description = form.description.data
            department_id = form.department.data.id
            document = upload_document_to_s3_and_store_in_db(file_to_upload, current_user.get_id(), 
                                department_id=department_id, title=title, description=description,
                                content_type=content_type)
            new_tags = request.form.getlist("tags[]")
            tags = []
            for new_tag in new_tags:
                if (new_tag.isdigit()):
                    tag = Tag.query.filter_by(id=new_tag).first()
                    if tag is not None:
                        tags.append(tag)
                else:
                    tag = db.session.add(Tag(
                                tag=new_tag
                            ))
                    db.session.commit()
                    tag = Tag.query.filter_by(tag=new_tag).first()
                    tags.append(tag)

            document.tags = tags
            db.session.commit()
            flash("Document was successfully uploaded")
        except Exception:
            flash("An error occurred while uploading")
            exception_type, value, full_tback = sys.exc_info()
            current_app.logger.error("Error deleting tag: {}".format(
                " ".join([str(exception_type), str(value),
                          format_exc()])
            ))
        return redirect("/documents/new")
    else:
        preferred_dept_id = Department.query.first().id
        # try to use preferred department if available
        try:
            if User.query.filter_by(id=current_user.id).one().dept_pref:
                preferred_dept_id = User.query.filter_by(id=current_user.id).one().dept_pref
            return render_template("submit_document.html", form=form, preferred_dept_id=preferred_dept_id)
        # that is, an anonymous user has no id attribute
        except (AttributeError, NoResultFound):
            preferred_dept_id = Department.query.first().id
            return render_template("submit_document.html", form=form, preferred_dept_id=preferred_dept_id)

@main.route("/documents/multi", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@edit_required
def submit_documents():
    form = AddMultiDocumentForm()
    if form.validate_on_submit(): # called as XHR
        department_id = form.department.data.id
        files = request.files.keys()
        success = 0
        total = len(files)
        for fname in files:
            try:
                file = request.files.get(fname)
                title = file.filename
                content_type = file.content_type
                document = upload_document_to_s3_and_store_in_db(file.read(), current_user.get_id(), 
                                    department_id=department_id, title=title, description='',
                                    content_type=content_type)
                db.session.commit()
                success += 1
            except Exception:
                exception_type, value, full_tback = sys.exc_info()
                current_app.logger.error("Error uploading file: {}".format(
                    " ".join([str(exception_type), str(value),
                              format_exc()])
                ))
                db.session.rollback()
        flash(f"{success}/{total} documents uploaded")
        return 'OK'
    #else:
    preferred_dept_id = Department.query.first().id
    # try to use preferred department if available
    try:
        if User.query.filter_by(id=current_user.id).one().dept_pref:
            preferred_dept_id = User.query.filter_by(id=current_user.id).one().dept_pref
    # that is, an anonymous user has no id attribute
    except (AttributeError, NoResultFound):
        preferred_dept_id = Department.query.first().id 
    return render_template("submit_multi_document.html", form=form, preferred_dept_id=preferred_dept_id)

@sitemap_include
@main.route("/faces", methods=[HTTPMethod.GET, HTTPMethod.POST])
# @limiter.limit("1/minute")
def submit_face():
    form = SearchFaceForm()
    officer_faces = None
    officers = None
    if form.validate_on_submit():
        try:
            file_parts = form.file.data.split(",")
            file_data = file_parts[1]
            data_parts = file_parts[0].split(";")
            content_type = data_parts[0].split(":")[1]
            file_to_upload = base64.b64decode(file_data)
            
            image = {"Bytes": io.BytesIO(file_to_upload).read()}

            session = boto3.Session(aws_access_key_id=os.environ.get("FACE_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("FACE_SECRET_ACCESS_KEY"),
                region_name="us-east-1")
            client = session.client("rekognition")

            collection_id = "lol"

            response=client.search_faces_by_image(CollectionId=collection_id,
                                    Image=image,
                                    FaceMatchThreshold=70,
                                    MaxFaces=1)
            
            officer_faces = []
            matches = response["FaceMatches"]
            if not matches or len(matches) == 0:
                flash("No mtches could be found")
                officer_faces = None
            else:
                for face in matches:
                    external = face.get("Face")
                    officer_face = Face.query.filter(Face.img_id == external.get("ExternalImageId")).first()
                    officer_faces.append(officer_face)

                officers = []
                for officer_face in officer_faces:
                    officer = Officer.query.filter(Officer.id == officer_face.officer_id).first()
                    
                    officer_image = sorted(officer.face, key=lambda x: x.featured, reverse=True)

                    # could do some extra work to not lazy load images but load them all together
                    # but we would want to ensure to only load the first picture of each officer
                    if officer_image and officer_image[0].image:
                        officer.image = officer_image[0].image.filepath
                    officers.append(officer)
        except Exception:
            flash("An error occurred while uploading")
 
    return render_template("submit_face.html", form=form, officer_faces=officer_faces, officers=officers)

def check_input(str_input):
    if str_input is None or str_input == "Not Sure":
        return ""
    else:
        return str(str_input).replace(",", " ")  # no commas allowed

@main.route("/admin", methods=[HTTPMethod.GET])
@login_required
@admin_required
def admin_page():
    return render_template(
        "admin.html")

# List all sheets which have been uploaded (whether imported successfully or not)
@main.route("/sheets/", methods=[HTTPMethod.GET])
@login_required
@admin_required
def list_sheets():
    sheets_q = (select(Sheet.id,
                Sheet.filepath,
                Sheet.date_inserted,
                User.username,
                func.count(distinct(SheetDetail.row_id)).label("num_rows"),
                func.string_agg(distinct(SheetDetail.agency_name), ", ").label("agencies"),
                func.sum(case((SheetDetail.status == 'OK - inserted', 1), else_=0)).label("inserted"),
                func.sum(case((SheetDetail.status == 'OK - updated', 1), else_=0)).label("updated"),
                func.sum(case((SheetDetail.status.like('ERROR%'), 1), else_=0)).label("errors")
                )
            .join(SheetDetail, isouter=True)
            .join(User, isouter=True)
            .group_by(Sheet.id, User.username)
            .order_by(Sheet.id.desc())
            )
    sheets = db.session.execute(sheets_q).all()

    return render_template(
        "import/list.html",
        sheets=sheets)

# This is the page to upload a new spreadsheet containing a roster
# It just uploads it to s3, nothing fancy.
@main.route("/sheets/new", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@admin_required
@limiter.limit("5/minute")
def submit_sheet():
    form = AddSheetForm()
    if form.validate_on_submit():
        try:
            file_data = form.file.data
            filename = secure_filename(form.file.data.filename)
            sheet = upload_sheet(file_data, current_user.id, filename)
            flash("Sheet was successfully uploaded")
            return redirect(url_for("main.sheet_map", sheet_id=sheet.id))
        except Exception as e:
            import traceback
            flash("An error occurred while uploading")
            flash(traceback.format_exc())
        return redirect("/sheets/new")
    else:
        return render_template("import/import_csv.html", form=form)

# Step 2 - insert the spreadsheet columns to database fields
@main.route("/sheets/mapping/<int:sheet_id>", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@admin_required
def sheet_map(sheet_id):
    form = SheetMapForm()

    if form.errors:
        flash(form.errors)

    try:
        sheet = Sheet.query.filter_by(id=sheet_id).one()
    except NoResultFound:
        abort(HTTPStatus.NOT_FOUND)
    #except:
    #    abort(500)
    form.id = sheet_id

    if form.validate_on_submit():
        try:
            #sheet_id = form.id
            #column_mapping = form.column_mapping
            #flash("trying to insert")
            insert_sheet_details(sheet)
            flash("Sheet details inserted")
            return redirect(url_for("main.sheet_match", sheet_id=sheet_id))
        except Exception:
            import traceback
            flash("An error occurred while uploading")
            flash(traceback.format_exc())
        return redirect(url_for("main.sheet_map", sheet_id=sheet_id))
    else:
        return render_template("import/mapping.html", form=form, sheet=sheet)

# Step 3 - Identification - for each record, try to figure out if it"s
# an insert (new officer) or update (existing officer in that department)
# ie, we just need to know if there"s an existing OFFICER.ID or not
@main.route("/sheets/match/<int:sheet_id>", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@admin_required
def sheet_match(sheet_id):
    form = SheetMatchForm()
    form.id = sheet_id

    if form.validate_on_submit():
        if "submit" in request.form:
            try:
                # clean data, insert ref data (depts, units, jobs)
                prep_ref_data(sheet_id)
                flash("Cleaned data. Created any new departments, unit, jobs needed.")
                # try to look up officer_ids for updates instead of inserts
                match_officers(sheet_id)
                flash("Attempted to find best officer matches. Please verify.")
            except Exception:
                import traceback
                flash("Match error:")
                flash(traceback.format_exc())
        elif "load" in request.form:
            try:
                load_sheet(sheet_id)
                flash("Records inserted/updated in database. Check status column for more details")
            except Exception:
                import traceback
                flash("Load error:")
                flash(traceback.format_exc())
            bulk_expire = form.data["bulk_expire"]
            if bulk_expire:
                bulk_expire_officers(sheet_id)
        else:
            flash("Unknown button pressed. Ignoring")
        return redirect(url_for("main.sheet_match", sheet_id=sheet_id))
    else:
        try:
            sheet = Sheet.query.filter_by(id=sheet_id).one()
        except NoResultFound:
            abort(HTTPStatus.NOT_FOUND)
        details = SheetDetail.query.filter_by(sheet_id=sheet_id)\
            .order_by(SheetDetail.row_id).all()
        return render_template("import/match.html", form=form, sheet=sheet, details=details)

# ??
def check_output(output_str):
    if output_str == "Not Sure":
        return ""
    return output_str


@main.route("/upload/documents", methods=[HTTPMethod.POST])
@limiter.limit("250/minute")
def doc_upload(department_id):
 
    file_to_upload = request.files["file"]
    if not allowed_doc_file(file_to_upload.filename):
        return jsonify(error="File type not allowed!"), 415
    image = upload_document_to_s3_and_store_in_db(file_to_upload, current_user.get_id(), department_id=department_id)

    if image:
        db.session.add(image)
        return jsonify(success="Success!"), 200
    else:
        return jsonify(error="Server error encountered. Try again later."), 500


@main.route("/process_faces",
            methods=[HTTPMethod.GET])
@login_required
@admin_required
def process_faces():

    session = boto3.Session(aws_access_key_id=os.environ.get("FACE_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("FACE_SECRET_ACCESS_KEY"),
                region_name="us-east-1")
    client = session.client("rekognition")

    collection_id = "lol"
    # Create a collection
    try:
        flash("Creating collection:" + collection_id)
        response = client.create_collection(CollectionId=collection_id)
        flash("Status code: " + str(response["StatusCode"]))
    except Exception as e:
        flash(collection_id + " already created")
        pass;
    
    faces_to_process = Face.query.filter_by(recognition_ready=False).limit(100)
    for face in faces_to_process:
        #get the image
        image = Image.query.filter_by(id=face.img_id).first()
        if not "/static" in image.filepath:
            img_response = requests.get(image.filepath)
            image = {"Bytes": io.BytesIO(img_response.content).read()}
            try:
                response = client.index_faces(
                    CollectionId=collection_id, Image=image,
                    ExternalImageId=str(face.img_id),
                    DetectionAttributes=["ALL"])
                flash(response)
            except Exception as e:
                pass

            face.recognition_ready= True
            db.session.commit()
        """response = client.index_faces(CollectionId=collection_id,
                                  Image={"S3Object": {"Bucket": bucket, "Name": photo}},
                                  ExternalImageId=photo,
                                  MaxFaces=1,
                                  QualityFilter="AUTO",
                                  DetectionAttributes=["ALL"])
        """
        # print("Results for " + photo)
        # print("Faces indexed:")
        # for faceRecord in response["FaceRecords"]:
        #     print("  Face ID: " + faceRecord["Face"]["FaceId"])
        #     print("  Location: {}".format(faceRecord["Face"]["BoundingBox"]))

    flash(faces_to_process.count())

    return render_template("process_faces.html")

@main.route("/manage_tags", methods=[HTTPMethod.GET])
@login_required
@admin_required
def manage_tags():
    tags = Tag.query.order_by(Tag.tag.asc())
    return render_template("manage_tags.html", tags=tags)

@main.route("/manage_tags/<int:tag_id>/edit", methods=[HTTPMethod.GET,HTTPMethod.POST])
@login_required
@admin_required
def edit_tags(tag_id=None):
    tag = Tag.query.filter_by(id=tag_id).one()
    form = EditTagForm(obj=tag)

    if form.validate_on_submit():
        tag.tag = form.tag.data
        db.session.commit()
        flash("The tag was updated successfully")
        return redirect(url_for("main.manage_tags"))
    return render_template("edit_tag.html", form=form, tag_id=tag_id)

@main.route("/manage_tags/<int:tag_id>/merge", methods=[HTTPMethod.GET,HTTPMethod.POST])
@login_required
@admin_required
def merge_tag(tag_id=None):
    tag = Tag.query.filter_by(id=tag_id).one()
    form = MergeTagForm(obj=tag)

    if form.validate_on_submit():
        merge_id = form.merge_tags.data.id
        new_tag = Tag.query.filter_by(id=merge_id).one()
        documents = tag.documents
        for document in documents:
            document.tags.append(new_tag)
        incidents = tag.incidents
        for incident in incidents:
            incident.tags.append(new_tag)
        db.session.delete(tag)
        db.session.commit()
        
        return redirect(url_for("main.manage_tags"))
    return render_template("merge_tag.html", form=form, tag_id=tag_id, tag=tag)

@main.route("/manage_tags/<int:tag_id>/delete", methods=[HTTPMethod.GET])
@login_required
@admin_required
def delete_docinc_tag(tag_id):
    tag = Tag.query.filter_by(id=tag_id).first()
    if not tag:
        flash("Tag not found")
        abort(HTTPStatus.NOT_FOUND)

    try:
        db.session.delete(tag)
        db.session.commit()
        flash("Deleted the tag")
    except:  # noqa
        flash("Unknown error occurred")
        exception_type, value, full_tback = sys.exc_info()
        current_app.logger.error("Error deleting tag: {}".format(
            " ".join([str(exception_type), str(value),
                      format_exc()])
        ))
    return redirect(url_for("main.manage_tags"))


## News/Blog posts
@sitemap_include
@main.route("/news/")
def show_posts(page=1):

    POSTS_PER_PAGE = int(current_app.config[KEY_OFFICERS_PER_PAGE])

    # Set form data based on URL
    if request.args.get("page"):
        page = int(request.args.get("page"))

    posts =  Post.query
    posts = posts.order_by(Post.created_at.desc())
    posts = posts.paginate(page=page, per_page=POSTS_PER_PAGE, error_out=False)

    next_url = url_for("main.show_posts",
                       page=posts.next_num)
    prev_url = url_for("main.show_posts",
                       page=posts.prev_num)

    return render_template(
        "news/index.html",
        posts=posts,
        next_url=next_url,
        prev_url=prev_url)

@main.route("/news/<int:post_id>")
def show_post(post_id):
    post =  Post.query.filter_by(id=post_id).first()
    if not post:
        flash("Post not found")
        abort(HTTPStatus.NOT_FOUND)
    return render_template(
        "news/view.html",
        post=post)

@main.route("/news/latest")
def show_latest_post():
    posts =  Post.query
    post = posts.order_by(Post.created_at.desc()).first()
    return render_template(
        "news/view_raw.html",
        post=post)

@main.route("/news/<int:post_id>/delete", methods=[HTTPMethod.GET])
@login_required
@ac_or_admin_required
def delete_post(post_id):
    post = Post.query.filter_by(id=post_id).first()

    if not post:
        flash("Post not found")
        abort(HTTPStatus.NOT_FOUND)

    if not current_user.is_administrator:
        if current_user.id != post.created_by:
            abort(HTTPStatus.FORBIDDEN)

    try:
        db.session.delete(post)
        db.session.commit()
        flash("Deleted the post")
    except:  # noqa
        flash("Unknown error occurred")
        exception_type, value, full_tback = sys.exc_info()
        current_app.logger.error("Error deleting post: {}".format(
            " ".join([str(exception_type), str(value),
                      format_exc()])
        ))
    return redirect(url_for("main.show_posts"))

@main.route("/news/<int:post_id>/edit", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@ac_or_admin_required
def edit_post(post_id):
    post = Post.query.filter_by(id=post_id).one()

    form = PostForm(obj=post)

    if form.validate_on_submit():
        post.title = form.title.data
        post.body = form.body.data
        db.session.commit()
        flash("Edited post ID {}".format(post_id))
        return redirect(url_for("main.show_posts"))
    else:
        current_app.logger.info(form.errors)
    return render_template("news/edit.html", form=form, post=post)

@main.route("/news/new", methods=[HTTPMethod.GET, HTTPMethod.POST])
@login_required
@ac_or_admin_required
def submit_post():
    form = PostForm()
    if form.validate_on_submit():
        title = form.title.data
        body = form.body.data
        user_id = current_user.id
        new_post = Post(title = title,
                            body = body)
        db.session.add(new_post)
        db.session.commit()
        flash("Post created")
        return redirect("/news/")
    else:
        return render_template("news/create.html", form=form)

# map 
@main.route("/map/")
def show_map():

    fips_q = select(
        func.substr(Department.locality_fips, 1, 5).label("county_fips"),
        Department.id,
        Department.name,
        )
    dept_fips = db.session.execute(fips_q).all()
    ukeys = list(set([r[0] for r in dept_fips]))    # get unique counties
    agencies = {k: [{'id': c[1], 'name': c[2]} for c in dept_fips if c[0] == k] for k in ukeys if k is not None}

    return render_template(
        "map.html", agencies=agencies)

@sitemap_include
@main.route("/lawsuits")
def show_lawsuits(page=1,
        case_number=None,
        ):
    CASES_PER_PAGE = int(current_app.config[KEY_OFFICERS_PER_PAGE])

    form = LawsuitListForm()
    disp_choices = [("","")]+[(i[0], f"{i[0]} ({i[1]})") for i in db.session.query(Lawsuit.disposition, db.func.count()).group_by(Lawsuit.disposition).order_by(Lawsuit.disposition.asc()).all() if i[0] != ""]
    form.disposition.choices = disp_choices

    lawsuits = Lawsuit.query
    # Set form data based on URL
    if request.args.get("page"):
        page = int(request.args.get("page"))
    if request.args.get("case_number"):
        form.case_number.data = request.args.get("case_number")
    if form.case_number.data:
        lawsuits = lawsuits.filter(
            Lawsuit.case_number.ilike(f"%{form.case_number.data.strip()}%")
        )
    if request.args.get("party"):
        form.party.data = request.args.get("party")
    if form.party.data:
        lawsuits = lawsuits.filter(
            (Lawsuit.plaintiff.ilike(f"%{form.party.data}%"))
            |
            (Lawsuit.defendant.ilike(f"%{form.party.data}%"))
        )
    if request.args.get('disposition'):
        form.disposition.data = request.args.get('disposition')
    if form.disposition.data:
        lawsuits = lawsuits.filter(Lawsuit.disposition == form.disposition.data)
    if request.args.get('judgment'):
        form.judgment.data = request.args.get('judgment')
    if form.judgment.data:
        lawsuits = lawsuits.filter(Lawsuit.judgment == form.judgment.data)
    if "include_pending" in request.args and request.args.get("include_pending") == 'y':
        form.include_pending.data = True
    else:
        form.include_pending.data = False
    if (not form.include_pending.data):
        # by default, hide null end dates
        lawsuits = lawsuits.filter(
            Lawsuit.end_date.isnot(None)
        )


    lawsuits = lawsuits.order_by(Lawsuit.filed_date.desc())
    lawsuits = lawsuits.paginate(page=page, per_page=CASES_PER_PAGE, error_out=False)

    next_url = url_for("main.show_lawsuits",
                       page=lawsuits.next_num,
                       case_number=form.case_number.data,
                       party=form.party.data,
                       disposition=form.disposition.data,
                       include_pending=form.include_pending.data)
    prev_url = url_for("main.show_lawsuits",
                       page=lawsuits.prev_num,
                       case_number=form.case_number.data,
                       party=form.party.data,
                       disposition=form.disposition.data,
                       include_pending=form.include_pending.data)

    return render_template(
        "lawsuit_list.html",
        lawsuits=lawsuits,
        form=form,
        next_url=next_url,
        prev_url=prev_url)

@main.route("/lawsuits/<int:lawsuit_id>")
def show_lawsuit(lawsuit_id):
    lawsuit = Lawsuit.query.filter_by(id=lawsuit_id).first()
    if not lawsuit:
        flash("Lawsuit not found")
        abort(HTTPStatus.NOT_FOUND)
    return render_template(
        "lawsuit_detail.html",
        lawsuit=lawsuit)
        
@sitemap.register_generator
def sitemap_lawsuits():
    for lawsuit in Lawsuit.query.all():
        yield "main.show_lawsuit", {"lawsuit_id": lawsuit.id}

@login_required
@edit_required
@main.route("/lawsuits/new", methods=[HTTPMethod.GET, HTTPMethod.POST])
def add_lawsuit():
    return edit_lawsuit(None)

@main.route("/lawsuits/<int:lawsuit_id>/edit",
    methods=[HTTPMethod.GET, HTTPMethod.POST],
)
@login_required
@edit_required
def edit_lawsuit(lawsuit_id=None):
    lawsuit = Lawsuit.query.filter_by(id=lawsuit_id).first()
    if (lawsuit and
            not current_user.is_administrator
            and current_user.ac_department_id != self.get_department_id(lawsuit)
            and lawsuit.created_by != current_user.id # users can only edit things they created
        ):
        abort(HTTPStatus.FORBIDDEN)
    form = LawsuitEditForm(obj=lawsuit)
    form.departments = request.form.getlist("departments[]")
    form.officers = request.form.getlist("officers[]")

    if form.validate_on_submit():
        if not lawsuit: # add new
            lawsuit = Lawsuit()
            db.session.add(lawsuit)
        departments = form.departments
        del form.departments
        lawsuit.departments = []
        if departments:
            for dept in departments:
                d = Department.query.filter_by(id=int(dept)).first()
                if d and d not in lawsuit.departments:
                    lawsuit.departments.append(d)
        officers = form.officers
        del form.officers
        lawsuit.officers = []
        if officers:
            for off in officers:
                o = Officer.query.filter_by(id=int(off)).first()
                if o and o not in lawsuit.officers:
                    lawsuit.officers.append(o)
        lawsuit.case_number = form.case_number.data
        lawsuit.court_code = form.court_code.data
        lawsuit.location = form.location.data
        lawsuit.filed_date = form.filed_date.data
        lawsuit.filing_nature = form.filing_nature.data
        lawsuit.code_section = form.code_section.data
        lawsuit.plaintiff = form.plaintiff.data
        lawsuit.defendant = form.defendant.data
        lawsuit.disposition = form.disposition.data
        lawsuit.judgment = form.judgment.data
        lawsuit.end_date = form.end_date.data
        lawsuit.case_link = form.case_link.data
        lawsuit.narrative = form.narrative.data
        db.session.commit()
        flash(f"Lawsuit {lawsuit.id} edited")
        return redirect(url_for("main.show_lawsuit", lawsuit_id=lawsuit.id))

    if lawsuit:
        form.departments = lawsuit.departments
        form.officers = lawsuit.officers

    if form.errors:
        current_app.logger.info(form.errors)
        flash("Error: " + str(form.errors))

    return render_template(
        "lawsuit_edit.html",
        lawsuit=lawsuit,
        form=form)

# departments associated with a specific lawsuit
@main.route("/lawsuits/<int:lawsuit_id>/departments", methods=[HTTPMethod.GET])
def get_lawsuit_depts(lawsuit_id):
    lawsuit = Lawsuit.query.filter_by(id=lawsuit_id).first()
    depts = lawsuit.departments
    dept_list = list({"id":dept.id,"text":dept.name} for dept in depts)
    return jsonify({"results":dept_list})

# officers associated with a specific lawsuit
@main.route("/lawsuits/<int:lawsuit_id>/officers", methods=[HTTPMethod.GET])
def get_lawsuit_officers(lawsuit_id):
    lawsuit = Lawsuit.query.filter_by(id=lawsuit_id).first()
    officers = lawsuit.officers
    off_list = list({"id":officer.id,"text":officer.full_name()} for officer in officers)
    return jsonify({"results":off_list})

@login_required
@ac_or_admin_required
@main.route("/lawsuits/<int:lawsuit_id>/delete", methods=[HTTPMethod.GET])
def delete_lawsuit(lawsuit_id):
    lawsuit = Lawsuit.query.filter_by(id=lawsuit_id).first()
    db.session.delete(lawsuit)
    db.session.commit()
    flash("Lawsuit deleted")
    return redirect(url_for("main.show_lawsuits"))

# utility function to load PACER URL
# not working yet; needs login
@main.route("/lawsuits/<int:lawsuit_id>/pacer", methods=[HTTPMethod.GET])
def get_pacer_link(lawsuit_id):
    lawsuit = Lawsuit.query.filter_by(id=lawsuit_id).first()
    if (not lawsuit) or (lawsuit.court_code not in ('vaed','vawd')):
        return {'status': 'not_pacer'}

    url = f"https://ecf.{lawsuit.court_code}.uscourts.gov/cgi-bin/possible_case_numbers.pl?{lawsuit.case_number}"
    resp = requests.get(url)
    if resp.status_code != 200:
        return {'status': 'pacer_api_error'}
    # parse xml response
    try:
        root = ElementTree.fromstring(resp.text)
        pacer_id = root.find("./case").attrib['id'] # get id attrib of first case
        if pacer_id:
            lawsuit.pacer_link = f"https://ecf.{lawsuit.court_code}.uscourts.gov/cgi-bin/DktRpt.pl?{pacer_id}"
            db.session.commit()
            return {'status': 'ok'}
    except Exception as inst:
        current_app.logger.error(inst)
        return {'status': 'error', 'message': str(inst), 'resp': resp.text}
    return {'status': 'no_case_found', 'message': resp.content}

@login_required
@ac_or_admin_required
@main.route("/duplicates", methods=[HTTPMethod.GET, HTTPMethod.POST])
def dup_officer_list(): # todo: filter by department?
    form = DupOfficerForm()
    if form.validate_on_submit():
        # run a new search to refresh the underlying Matches table 
        duplicate_officer_bulk_search()
    matches = DupOfficerMatches.query
    # Set form data based on URL
    if request.args.get("include_all"):
        form.include_all.data = request.args.get("include_all")
    if not form.include_all.data:
        # by default, hide matches with the Excluded flag on
        matches = matches.filter_by(excluded=False)

    matches = matches.order_by(DupOfficerMatches.match_score.desc())

    return render_template(
        "matching/dup_list.html",
        matches=matches,
        form=form)

@login_required
@ac_or_admin_required
@main.route("/duplicates/details", methods=[HTTPMethod.GET, HTTPMethod.POST])
def dup_officer_details(id_1=None,id2=None): 
    form = DupMergeForm()
    try:
        id_1 = int(request.args.get("id1"))
        id_2 = int(request.args.get("id2"))
        officer1 = Officer.query.filter_by(id=id_1).one()
        officer2 = Officer.query.filter_by(id=id_2).one()
    except Exception:
        flash("Invalid Officer IDs")
        return redirect(url_for("main.dup_officer_list"))

    if form.validate_on_submit():
        # merge one of the records into the other one
        if "merge1" in request.form:
            merge_officers(keep_me=officer2, delete_me=officer1)
            flash(f"Officer {id_1} merged into {id_2} and deleted")
        elif "merge2" in request.form:
            merge_officers(keep_me=officer1, delete_me=officer2)
            flash(f"Officer {id_2} merged into {id_1} and deleted")
        elif "exclude" in request.form:
            nomatch = DupOfficerMatches.query.filter_by(id_1=id_1,id_2=id_2).one_or_none()
            if nomatch:
                nomatch.excluded = True
                db.session.add(nomatch)
                db.session.commit()
            flash(f"Match excluded and hidden from view")
        return redirect(url_for("main.dup_officer_list"))

    return render_template(
        "matching/dup_details.html",
        officer1=officer1,
        officer2=officer2,
        form=form)

@main.route("/recent", methods=[HTTPMethod.GET])
def recent_updates(page: int=1): 
    if page_arg := request.args.get("page"):
        page = int(page_arg)
    officer_q = (
        select(literal_column("'/officers/' || cast(officers.id as text)").label("url"),
            literal_column("'Officer ' || officers.first_name || ' ' || officers.last_name").label("label"),
            Officer.last_updated_at, 
            User.username,
            literal_column("''").label("value")
            )
        .join(User, User.id == Officer.last_updated_by, isouter=True)
        )
    incident_q = (
        select(literal_column("'/incidents/' || cast(incidents.id as text)").label("url"),
            literal_column("'Incident ' || incidents.report_number").label("label"),
            Incident.last_updated_at, 
            User.username,
            literal_column("''").label("value")
            )
        .join(User, User.id == Incident.last_updated_by, isouter=True)
        )
    link_q = (
        select(literal_column("'/officers/' || cast(officers.id as text)").label("url"),
            literal_column("'Link ' || cast(links.id as text) || ', Officer ' || officers.first_name || ' ' || officers.last_name").label("label"),
            Link.last_updated_at, 
            User.username,
            (Link.url).label("value")
            )
        .select_from(Link)
        .join(officer_links)
        .join(Officer)
        .join(User, User.id == Link.last_updated_by, isouter=True)
        )

    recent_q = (
        union_all(officer_q, incident_q, link_q)
        .order_by(desc("last_updated_at"))
        .offset((page-1)*50)
        .limit(50)
        )
    recent_objs = db.session.execute(recent_q).all()

    return render_template(
        "recent.html",
        objs=recent_objs, page=page)

# return JSON list of all (optionally filtered) departments. copied from tags
@main.route("/api/departments",
    methods=[HTTPMethod.GET])
def get_departments(term=""):
    term = request.args["q"]
    depts = Department.query.filter(Department.name.ilike("%%{}%%".format(term))).limit(10)
    
    dept_list = list({"id":dept.id,"text":dept.name} for dept in depts)
    return jsonify({"results":dept_list})

# return JSON list of all (optionally filtered) officers. copied from tags
@main.route("/api/officers",
    methods=[HTTPMethod.GET])
def get_officers(term=""):
    term = request.args["q"]
    full_name = Officer.first_name + ' ' + Officer.middle_initial + ' ' + Officer.last_name
    officers = Officer.query.filter(
    	full_name.ilike("%%{}%%".format(term))
        ).limit(10)
    
    officer_list = list({"id":officer.id,"text":officer.full_name()} for officer in officers)
    return jsonify({"results":officer_list})

