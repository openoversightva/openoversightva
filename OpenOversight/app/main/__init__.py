from flask import Blueprint
import os

os.environ['wsgi.url_scheme'] = 'https'

main = Blueprint('main', __name__)  # noqa

from . import views  # noqa
