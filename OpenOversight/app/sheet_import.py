from flask import current_app, url_for, flash
from flask_login import current_user

from OpenOversight.app.models.database import (db, Officer, Assignment, Job, Face, User, Unit, Department,
                     Incident, Link, Note, Description, Salary,
                     Document, Tag, Sheet, SheetDetail)
from OpenOversight.app.utils.cloud import (compute_hash, upload_doc_to_s3)

from io import BytesIO
from botocore.exceptions import ClientError
import datetime
import uuid
import traceback
import numpy as np
import pandas as pd
from sqlalchemy.sql import text
from sqlalchemy import exc

def upload_sheet(sheet_buf, user_id, file_ext='csv'):
    file = sheet_buf.read()
    sheet_data = BytesIO(file)
    hash_sheet = compute_hash(file)
    existing_doc = Sheet.query.filter_by(hash_sheet=hash_sheet).first()
    if existing_doc:
        return existing_doc
    try:
        new_filename = '{}.{}'.format(hash_sheet, file_ext)
        url = upload_doc_to_s3(sheet_data, new_filename, 'text/csv')
        new_sheet = Sheet(filepath=url, hash_sheet=hash_sheet,
                          date_inserted=datetime.datetime.now(),
                          date_loaded=None,
                          user_id=user_id,
                          column_mapping='[]'
                          )
        db.session.add(new_sheet)
        db.session.commit()
        return new_sheet
    except ClientError:
        exception_type, value, full_tback = sys.exc_info()
        current_app.logger.error('Error uploading to S3: {}'.format(
            ' '.join([str(exception_type), str(value),
                      format_exc()])
        ))
        return None

def insert_sheet_details(sheet):
    df = pd.read_csv(sheet.filepath, dtype='str')
    df = df.reset_index()    # create an index column for row_id
    df.columns = ['row_id', 'last_name', 'first_name', 'middle_initial',
                  'suffix', 'badge_number', 'rank_title', 'unit_name',
                  'gender', 'race', 'employment_date', 'salary',
                  'salary_overtime', 'salary_year', 'salary_is_fy',
                  'agency_name']
    df['sheet_id'] = sheet.id
    df['badge_number'] = df['badge_number'] # if all numbers, print as string
    df['salary_year'] = df['salary_year'].astype('Int64').astype('str') # no floats
    # required fields: sheet_id, row_id
    df.to_sql(name='import_sheet_details', con=db.engine, index=False,
              if_exists='append')


def prep_ref_data(sheet_id):
    engine = db.engine
    with engine.connect() as connection:
        # step 1 - tidy up the data a bit
        s = text("""update import_sheet_details
set last_name = trim(last_name),
first_name = trim(first_name),
middle_initial = trim(middle_initial),
suffix = replace(suffix,'.',''),
badge_number = trim(badge_number),
rank_title = trim(rank_title),
unit_name = trim(unit_name),
gender = case substr(upper(gender),1,1) when 'M' then 'M' when 'F' then 'F' else null end,
race = trim(race),
salary = replace(replace(replace(trim(salary),',',''),'$',''),' ',''),
salary_overtime = replace(trim(salary_overtime),',',''),
salary_year = trim(salary_year),
salary_is_fy = case substr(upper(salary_is_fy),1,1) when 'Y' then 'Y' when 'T' then 'Y' else 'N' end,
agency_name = trim(agency_name)
where sheet_id = :sid""")
        result = connection.execute(statement=s, parameters={"sid":sheet_id})
        connection.commit()
        # insert any missing departments
        # edit KF 12/23 - not doing this anymore, keeps creating duplicate departments
#        s = text("""insert into departments (name, short_name)
#select agency_name, agency_name
#from import_sheet_details
#where sheet_id = :sid
#and agency_name not in (select name from departments union all select short_name from departments)
#group by agency_name""")
#        result = connection.execute(statement=s, parameters={"sid":sheet_id})
        # update the sheet
        s = text("""update import_sheet_details d
set department_id = (select id from departments s where s.name = d.agency_name)
where sheet_id = :sid""")
        result = connection.execute(statement=s, parameters={"sid":sheet_id})
        connection.commit()
        # insert any missing units 
        s = text("""insert into unit_types (description, department_id)
select distinct d.unit_name, d.department_id
from import_sheet_details d
left join unit_types ut
    on ut.department_id = d.department_id 
    and ut.description = d.unit_name
where sheet_id = :sid
and ut.id is null
""")
        result = connection.execute(s, parameters={"sid":sheet_id})
        connection.commit()
        # once more with job_title
        s = text("""insert into jobs (job_title, \"order\", department_id)
select coalesce(rank_title,'Not Sure'), row_number() over (order by count(1) asc), d.department_id
from import_sheet_details d
left join jobs j
    on j.department_id = d.department_id
    and j.job_title = d.rank_title
where sheet_id = :sid
and j.id is null
group by d.rank_title, d.department_id""")
        try:
            result = connection.execute(s, parameters={"sid":sheet_id})
            connection.commit()
        except exc.IntegrityError:
            connection.rollback()
        # also add a 'Not Sure' entry for each dept if it doesn't already exist
        s = text("""insert into jobs (job_title, \"order\", department_id)
select 'Not Sure', coalesce(max(j.\"order\")+1,0), d.department_id 
from import_sheet_details d
left join jobs j
    on j.department_id = d.department_id
where d.sheet_id = :sid
  and not exists (select 1 from jobs where department_id = d.department_id and job_title = 'Not Sure')
group by d.department_id""")
        try:
            result = connection.execute(s, parameters={"sid":sheet_id})
            connection.commit()
        except exc.IntegrityError:
            connection.rollback()
        # update the import sheet with those details
        s = text("""update import_sheet_details d
    set unit_id = (select max(id) from unit_types u where u.department_id = d.department_id and description = d.unit_name),
        job_id = (select max(id) from jobs j where j.department_id = d.department_id and j.job_title = d.rank_title)
where sheet_id = :sid""")
        result = connection.execute(s, parameters={"sid":sheet_id})
        connection.commit()
    return None

"""match_officers tries to look up the best match of an existing officer ID 
for each row in the import_sheet_details list.
"""
def match_officers(sheet_id):
    engine = db.engine
    with engine.connect() as connection:
        # step 1 - normalize nulls/blank strings?
        # step 2 - update sheet rows with exact matches
        trans = connection.begin()
        s = text("""
with off_info as
    (select o.*, a.star_no,
    j.job_title,
    a.unit_id
    from officers o
    left join (select a2.*,
                min(a2.id) over (partition by a2.officer_id) as minaid
                from assignments a2) a
        on a.officer_id = o.id and a.id = minaid
    left join jobs j
    on j.id = a.job_id
    and j.department_id = o.department_id)
update import_sheet_details sd
    set officer_id = (select min(i.id) from off_info i
        where sd.department_id = i.department_id
        and lower(sd.last_name) = lower(i.last_name)
        and coalesce(lower(sd.first_name),'n/a') = coalesce(lower(i.first_name),'n/a')
        and replace(lower(sd.middle_initial),'.','') = replace(lower(i.middle_initial),'.','')
        and coalesce(lower(sd.suffix),'') = coalesce(lower(i.suffix),'')
        and (coalesce(sd.badge_number,'') = i.star_no or i.star_no = '')
        )
where sd.sheet_id = :sid
and sd.officer_id is null;""")
        result = connection.execute(statement=s, parameters={"sid":sheet_id})
        trans.commit()
        # step 3 - try again but fuzzier - only match on last, first, mi (1 c)
        trans = connection.begin()
        s = text("""
with off_info as
    (select o.*, a.star_no,
    j.job_title,
    a.unit_id
    from officers o
    left join (select a2.*,
                min(a2.id) over (partition by a2.officer_id) as minaid
                from assignments a2) a
        on a.officer_id = o.id and a.id = minaid
    left join jobs j
    on j.id = a.job_id
    and j.department_id = o.department_id)
update import_sheet_details sd
    set officer_id = (select min(i.id) from off_info i
        where sd.department_id = i.department_id
        and lower(sd.last_name) = lower(i.last_name)
        and coalesce(lower(sd.first_name),'n/a') = coalesce(lower(i.first_name),'n/a')
        and substr(lower(sd.middle_initial),1,1) = substr(lower(i.middle_initial),1,1)
        )
where sd.sheet_id = :sid
and sd.officer_id is null;""")
        result = connection.execute(statement=s, parameters={"sid":sheet_id})
        trans.commit()       # this shouldn't be needed, but apparently it is?
        # step 4 - getting desperate - last name, first initial
        trans = connection.begin()
        s = text("""
with off_info as
    (select o.*, a.star_no,
    j.job_title,
    a.unit_id
    from officers o
    left join (select a2.*,
                min(a2.id) over (partition by a2.officer_id) as minaid
                from assignments a2) a
        on a.officer_id = o.id and a.id = minaid
    left join jobs j
    on j.id = a.job_id
    and j.department_id = o.department_id)
update import_sheet_details sd
    set officer_id = (select min(i.id) from off_info i
        where sd.department_id = i.department_id
        and lower(sd.last_name) = lower(i.last_name)
        and (substr(lower(sd.first_name),1,1) = substr(lower(i.first_name),1,1)
            or i.first_name is null or i.first_name = '')
        )
where sd.sheet_id = :sid
and sd.officer_id is null;""")
        result = connection.execute(statement=s, parameters={"sid":sheet_id})
        trans.commit()
    return 'ok'

"""
Final stage! Insert/update records into the database!

"""
def load_sheet(sheet_id):
    details = SheetDetail.query.filter_by(sheet_id=sheet_id)\
            .order_by(SheetDetail.row_id).all()
    for row in details:
        if (row.status is not None) and (row.status[0:2] == 'OK'):
            continue     #skip this row
        if row.officer_id is None:
            create_officer(row)
        else:
            update_officer(row)
    return 'ok'

"""
Expire all officer assignments in this department which weren't on this roster
"""
def bulk_expire_officers(sheet_id):
    engine = db.engine
    with engine.connect() as connection:
       trans = connection.begin()
       s = text("""
update assignments a
  set resign_date = date_trunc('year',current_date)
where department_id = (select distinct department_id from import_sheet_details where sheet_id = :sid)
  and officer_id not in (select officer_id from import_sheet_details where sheet_id = :sid and department_id = a.department_id)
;
       """)
       try:
          result = connection.execute(statement=s, parameters={"sid":sheet_id})
          trans.commit() 
       except exc.ProgrammingError:
          flash("Error: Can only bulk expire roster sheets with ONE department on them. No officers were expired.")
          trans.rollback();
    return 'ok'
"""
Create a single officer, based on an ImportSheetDetails row
"""
def create_officer(row):
    uid = None
    try:
        if row.badge_number is None:
            # no badge number - you get a uuid
            uid = str(uuid.uuid4()) 
        officer = Officer(first_name=row.first_name,
                          last_name=row.last_name,
                          middle_initial=row.middle_initial,
                          suffix=row.suffix,
                          race=row.race,
                          gender=row.gender,
                          employment_date=row.employment_date,
                          department_id=row.department_id,
                          unique_internal_identifier=uid)
        db.session.add(officer)
        db.session.commit()
        row.officer_id = officer.id
        #db.session.commit()

        add_aux_data(officer, row)

        row.officer_id = officer.id
        row.status = 'OK - inserted'
    except Exception:
        db.session.rollback()
        row.status = f"ERROR - {traceback.format_exc()}"
    db.session.commit()
    return 'ok'

def add_aux_data(officer, row):
    assignment = Assignment(officer_id=officer.id,
                            star_no=row.badge_number,
                            job_id=row.job_id,
                            unit_id=row.unit_id,
                            start_date=row.employment_date,
                            department_id=row.department_id)
    db.session.add(assignment)

    if row.salary is not None:
        new_salary = Salary(
                    officer_id=officer.id,
                    salary=row.salary,
                    overtime_pay=row.salary_overtime,
                    year=row.salary_year,
                    is_fiscal_year=(True if row.salary_is_fy == 'Y' else False))
        db.session.add(new_salary)


"""
Update a single officer, based on an ImportSheetDetails row
"""
def update_officer(row):
    try:
        officer = Officer.query.filter_by(id=row.officer_id).one()
        setattr(officer, 'last_name', row.last_name)
        # for first,mi,etc use whichever one is longer
        setattr(officer, 'first_name', max(officer.first_name, row.first_name, key=lambda x: len(str(x))))
        setattr(officer, 'middle_initial', max(officer.middle_initial, row.middle_initial, key=lambda x: len(str(x))))
        setattr(officer, 'suffix', max(officer.suffix, row.suffix, key=lambda x: len(str(x))))

        add_aux_data(officer, row)

        db.session.add(officer)
        row.status = 'OK - updated'
    except Exception:
        db.session.rollback()
        row.status = f"ERROR - {traceback.format_exc()}"
    db.session.commit()
    return 'ok'
