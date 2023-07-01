from flask import Blueprint
import os

os.environ['wsgi.url_scheme'] = 'https'

main = Blueprint("main", __name__)

from . import views  # noqa: E402,F401
