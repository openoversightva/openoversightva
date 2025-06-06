import hashlib
import os
import sys
from datetime import datetime
from io import BytesIO
from traceback import format_exc
from urllib.request import urlopen
import mimetypes

import boto3
import botocore
from botocore.exceptions import ClientError
from flask import current_app
from flask_login import current_user
from PIL import Image as Pimage
from PIL import UnidentifiedImageError
from PIL.PngImagePlugin import PngImageFile

from OpenOversight.app.models.database import Image, Document, Sheet, db
from OpenOversight.app.utils.constants import KEY_ALLOWED_EXTENSIONS, KEY_S3_BUCKET_NAME


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

    return save_image_to_s3_and_db(cropped_image_buf, current_user.id, department_id)


# 36867 in the exif tags holds the date and the original image was taken
# https://www.awaresystems.be/imaging/tiff/tifftags/privateifd/exif.html
EXIF_KEY_DATE_TIME_ORIGINAL = 36867


def get_date_taken(pimage):
    if isinstance(pimage, PngImageFile):
        return None

    exif = hasattr(pimage, "_getexif") and pimage._getexif()
    return exif.get(EXIF_KEY_DATE_TIME_ORIGINAL, None) if exif else None


def upload_file_to_s3(file_obj, dest_filename: str):
    s3_client = boto3.client("s3")

    # Folder to store files in on S3 is first two chars of dest_filename
    s3_folder = dest_filename[0:2]
    s3_filename = dest_filename[2:]
    pimage = Pimage.open(file_obj)
    file_obj.seek(0)
    s3_content_type = f"image/{pimage.format.lower()}"
    s3_path = f"{s3_folder}/{s3_filename}"
    s3_client.upload_fileobj(
        file_obj,
        current_app.config[KEY_S3_BUCKET_NAME],
        s3_path,
        ExtraArgs={"ContentType": s3_content_type, "ACL": "public-read"},
    )

    config = s3_client._client_config
    config.signature_version = botocore.UNSIGNED
    url = boto3.resource("s3", config=config).meta.client.generate_presigned_url(
        "get_object",
        Params={"Bucket": current_app.config[KEY_S3_BUCKET_NAME], "Key": s3_path},
    )

    return url

# OOVA
def upload_doc_to_s3(file_obj, dest_filename, content_type):
    s3_client = boto3.client('s3')

    # Folder to store files in on S3 was first two chars of dest_filename - is not documents
    s3_folder = 'documents'
    s3_filename = dest_filename
    s3_content_type = content_type
    s3_path = f"{s3_folder}/{s3_filename}"
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

# OOVA
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
                          department_id=department_id,
                          title=title,
                          description=description
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

def save_image_to_s3_and_db(image_buf, user_id, department_id=None):
    """
    Just a quick explanation of the order of operations here...
    we have to scrub the image before we do anything else like hash it,
    but we also have to get the date for the image before we scrub it.
    """
    image_buf.seek(0)
    try:
        pimage = Pimage.open(image_buf)
    except UnidentifiedImageError:
        raise ValueError("Attempted to pass an invalid image.")
    image_format = pimage.format.lower()
    if image_format not in current_app.config[KEY_ALLOWED_EXTENSIONS]:
        raise ValueError(f"Attempted to pass invalid data type: {image_format}")
    image_buf.seek(0)

    date_taken = get_date_taken(pimage)
    if date_taken:
        date_taken = datetime.strptime(date_taken, "%Y:%m:%d %H:%M:%S")
    pimage.getexif().clear()
    scrubbed_image_buf = BytesIO()
    pimage.save(scrubbed_image_buf, image_format)
    pimage.close()
    scrubbed_image_buf.seek(0)
    image_data = scrubbed_image_buf.read()
    hash_img = compute_hash(image_data)
    existing_image = Image.query.filter_by(hash_img=hash_img).first()
    if existing_image:
        return existing_image
    try:
        new_filename = f"{hash_img}.{image_format}"
        scrubbed_image_buf.seek(0)
        url = upload_file_to_s3(scrubbed_image_buf, new_filename)
        new_image = Image(
            filepath=url,
            hash_img=hash_img,
            department_id=department_id,
            taken_at=date_taken,
            created_by=user_id,
            last_updated_by=user_id,
        )
        db.session.add(new_image)
        db.session.commit()
        return new_image
    except ClientError:
        exception_type, value, full_traceback = sys.exc_info()
        error_str = " ".join([str(exception_type), str(value), format_exc()])
        current_app.logger.error(f"Error uploading to S3: {error_str}")
        return None
