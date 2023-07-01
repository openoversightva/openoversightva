import datetime
import hashlib
import imghdr as imghdr
import mimetypes
import os
import sys
from io import BytesIO
from traceback import format_exc
from urllib.request import urlopen

import boto3
import botocore
from botocore.exceptions import ClientError
from flask import current_app
from flask_login import current_user
from PIL import Image as Pimage
from PIL.PngImagePlugin import PngImageFile

from ..models import Image, Document, Sheet, db


def compute_hash(data_to_hash):
    return hashlib.sha256(data_to_hash).hexdigest()


def crop_image(image, crop_data=None, department_id=None):
    """Crops an image to given dimensions and shrinks it to fit within a configured
    bounding box if the cropped image is still too big.
    """
    # Cropped officer face image size
    THUMBNAIL_SIZE = 1000, 1000

    if "http" in image.filepath:
        with urlopen(image.filepath) as response:
            image_buf = BytesIO(response.read())
    else:
        image_buf = open(os.path.abspath(current_app.root_path) + image.filepath, "rb")

    pimage = Pimage.open(image_buf)

    if (
        not crop_data
        and pimage.size[0] < THUMBNAIL_SIZE[0]
        and pimage.size[1] < THUMBNAIL_SIZE[1]
    ):
        return image

    # Crops image to face and resizes to bounding box if still too big
    if crop_data:
        pimage = pimage.crop(crop_data)
    if pimage.size[0] > THUMBNAIL_SIZE[0] or pimage.size[1] > THUMBNAIL_SIZE[1]:
        pimage.thumbnail(THUMBNAIL_SIZE)

    # JPEG doesn't support alpha channel, convert to RGB
    if pimage.mode in ("RGBA", "P"):
        pimage = pimage.convert("RGB")

    # Save preview image as JPEG to save bandwidth for mobile users
    cropped_image_buf = BytesIO()
    pimage.save(cropped_image_buf, "jpeg", quality=95, optimize=True, progressive=True)

    return upload_image_to_s3_and_store_in_db(
        cropped_image_buf, current_user.get_id(), department_id
    )

"""The legacy version of crop_image from before refactoring utils. Please review then remove"""
def crop_image_legacy(image, crop_data=None, department_id=None):
    if 'http' in image.filepath:
        with urlopen(image.filepath) as response:
            image_buf = BytesIO(response.read())
    else:
        image_buf = open(os.path.abspath(current_app.root_path) + image.filepath, 'rb')

    image_buf.seek(0)
    image_type = imghdr.what(image_buf)
    if not image_type:
        image_type = os.path.splitext(image.filepath)[1].lower()[1:]
        if image_type in ('jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2'):
            image_type = 'jpeg2000'
        elif image_type in ('jpg', 'jpeg', 'jpe', 'jif', 'jfif', 'jfi'):
            image_type = 'jpeg'
        elif image_type in ('tif', 'tiff'):
            image_type = 'tiff'
    pimage = Pimage.open(image_buf)

    SIZE = 300, 300
    if not crop_data and pimage.size[0] < SIZE[0] and pimage.size[1] < SIZE[1]:
        return image

    if crop_data:
        pimage = pimage.crop(crop_data)
    if pimage.size[0] > SIZE[0] or pimage.size[1] > SIZE[1]:
        pimage = pimage.copy()
        pimage.thumbnail(SIZE)

    cropped_image_buf = BytesIO()
    pimage.save(cropped_image_buf, image_type)

    return upload_image_to_s3_and_store_in_db(cropped_image_buf, current_user.get_id(), department_id)



def find_date_taken(pimage):
    if isinstance(pimage, PngImageFile):
        return None

    exif = hasattr(pimage, "_getexif") and pimage._getexif()
    if exif:
        # 36867 in the exif tags holds the date and the original image was taken
        # https://www.awaresystems.be/imaging/tiff/tifftags/privateifd/exif.html
        if 36867 in exif:
            return exif[36867]
    else:
        return None


def upload_obj_to_s3(file_obj, dest_filename):
    s3_client = boto3.client("s3")

    # Folder to store files in on S3 is first two chars of dest_filename
    s3_folder = dest_filename[0:2]
    s3_filename = dest_filename[2:]
    file_ending = imghdr.what(None, h=file_obj.read())
    file_obj.seek(0)
    s3_content_type = "image/%s" % file_ending
    s3_path = "{}/{}".format(s3_folder, s3_filename)
    s3_client.upload_fileobj(
        file_obj,
        current_app.config["S3_BUCKET_NAME"],
        s3_path,
        ExtraArgs={"ContentType": s3_content_type, "ACL": "public-read"},
    )

    config = s3_client._client_config
    config.signature_version = botocore.UNSIGNED
    url = boto3.resource("s3", config=config).meta.client.generate_presigned_url(
        "get_object",
        Params={"Bucket": current_app.config["S3_BUCKET_NAME"], "Key": s3_path},
    )

    return url


def upload_doc_to_s3(file_obj, dest_filename, content_type):
    s3_client = boto3.client('s3')

    # Folder to store files in on S3 is first two chars of dest_filename
    s3_folder = dest_filename[0:2]
    s3_filename = dest_filename[2:]
    s3_content_type = content_type
    s3_path = '{}/{}'.format(s3_folder, s3_filename)
    s3_client.upload_fileobj(file_obj,
                             current_app.config['S3_BUCKET_NAME'],
                             s3_path,
                             ExtraArgs={'ContentType': s3_content_type, 'ACL': 'public-read'})

    config = s3_client._client_config
    config.signature_version = botocore.UNSIGNED
    url = boto3.resource(
        's3', config=config).meta.client.generate_presigned_url(
        'get_object',
        Params={'Bucket': current_app.config['S3_BUCKET_NAME'],
                'Key': s3_path})

    return url

def upload_document_to_s3_and_store_in_db(doc_buf, user_id, department_id, title, description, content_type):
    doc_type = "Document"
    guess_type = mimetypes.guess_extension(content_type, strict=False)
    if guess_type:
        doc_type = guess_type[1:]
    doc_data = BytesIO(doc_buf)
    hash_doc = compute_hash(doc_buf)
    existing_doc = Document.query.filter_by(hash_doc=hash_doc).first()
    if existing_doc:
        return existing_doc
    try:
        new_filename = '{}.{}'.format(hash_doc, doc_type)
        url = upload_doc_to_s3(doc_data, new_filename, content_type)
        new_doc = Document(filepath=url, hash_doc=hash_doc,
                          url=url,
                          date_inserted=datetime.datetime.now(),
                          department_id=department_id,
                          title=title,
                          description=description,
                          user_id=user_id
                          )
        db.session.add(new_doc)
        db.session.commit()
        return new_doc
    except ClientError:
        exception_type, value, full_tback = sys.exc_info()
        current_app.logger.error('Error uploading to S3: {}'.format(
            ' '.join([str(exception_type), str(value),
                      format_exc()])
        ))
        return None

def upload_image_to_s3_and_store_in_db(image_buf, user_id, department_id=None):
    """
    Just a quick explaination of the order of operations here...
    we have to scrub the image before we do anything else like hash it
    but we also have to get the date for the image before we scrub it.
    """
    image_buf.seek(0)
    image_type = imghdr.what(image_buf)
    if image_type not in current_app.config["ALLOWED_EXTENSIONS"]:
        raise ValueError("Attempted to pass invalid data type: {}".format(image_type))
    image_buf.seek(0)
    pimage = Pimage.open(image_buf)
    date_taken = find_date_taken(pimage)
    if date_taken:
        date_taken = datetime.datetime.strptime(date_taken, "%Y:%m:%d %H:%M:%S")
    pimage.getexif().clear()
    scrubbed_image_buf = BytesIO()
    pimage.save(scrubbed_image_buf, image_type)
    pimage.close()
    scrubbed_image_buf.seek(0)
    image_data = scrubbed_image_buf.read()
    hash_img = compute_hash(image_data)
    existing_image = Image.query.filter_by(hash_img=hash_img).first()
    if existing_image:
        return existing_image
    try:
        new_filename = "{}.{}".format(hash_img, image_type)
        scrubbed_image_buf.seek(0)
        url = upload_obj_to_s3(scrubbed_image_buf, new_filename)
        new_image = Image(
            filepath=url,
            hash_img=hash_img,
            date_image_inserted=datetime.datetime.now(),
            department_id=department_id,
            date_image_taken=date_taken,
            user_id=user_id,
        )
        db.session.add(new_image)
        db.session.commit()
        return new_image
    except ClientError:
        exception_type, value, full_tback = sys.exc_info()
        current_app.logger.error(
            "Error uploading to S3: {}".format(
                " ".join([str(exception_type), str(value), format_exc()])
            )
        )
        return None

""" Legacy version. Please review then delete """

def upload_image_to_s3_and_store_in_db_legacy(image_buf, user_id, department_id=None):
    image_buf.seek(0)
    image_type = imghdr.what(image_buf)
    image_data = image_buf.read()
    image_buf.seek(0)
    hash_img = compute_hash(image_data)
    existing_image = Image.query.filter_by(hash_img=hash_img).first()
    if existing_image:
        return existing_image
    date_taken = None
    if image_type in current_app.config['ALLOWED_EXTENSIONS']:
        image_buf.seek(0)
        pimage = Pimage.open(image_buf)
        date_taken = find_date_taken(pimage)
        if date_taken:
            date_taken = datetime.datetime.strptime(date_taken, '%Y:%m:%d %H:%M:%S')
    else:
        raise ValueError('Attempted to pass invalid data type: {}'.format(image_type))
    try:
        new_filename = '{}.{}'.format(hash_img, image_type)
        url = upload_obj_to_s3(image_buf, new_filename)
        new_image = Image(filepath=url, hash_img=hash_img,
                          date_image_inserted=datetime.datetime.now(),
                          department_id=department_id,
                          date_image_taken=date_taken,
                          user_id=user_id
                          )
        db.session.add(new_image)
        db.session.commit()
        return new_image
    except ClientError:
        exception_type, value, full_tback = sys.exc_info()
        current_app.logger.error('Error uploading to S3: {}'.format(
            ' '.join([str(exception_type), str(value),
                      format_exc()])
        ))
        return None

