from typing import Optional
from io import BytesIO

import boto3
from botocore.exceptions import ClientError
import botocore
import datetime
import hashlib
import os
import io
import random
import sys
from traceback import format_exc
from distutils.util import strtobool

from sqlalchemy import func, or_
from sqlalchemy.sql.expression import cast
from sqlalchemy.orm import selectinload
import imghdr as imghdr
from flask import current_app, url_for, flash
from flask_login import current_user
from PIL import Image as Pimage
from PIL.PngImagePlugin import PngImageFile

from .models import (db, Officer, Assignment, Job, Image, Face, User, Unit, Department,
                     Incident, Location, LicensePlate, Link, Note, Description, Salary,
                     Document)


def create_collection(collection_id):
    session = boto3.Session(profile_name='profile-name')
    client = session.client('rekognition')

    # Create a collection
    print('Creating collection:' + collection_id)
    response = client.create_collection(CollectionId=collection_id)
    print('Collection ARN: ' + response['CollectionArn'])
    print('Status code: ' + str(response['StatusCode']))
    print('Done...')

def main():
    # collection_id = "collection-id"
    # create_collection(collection_id)
    print(config.FACE_ACCESS_KEY_ID)

if __name__ == "__main__":
    main()