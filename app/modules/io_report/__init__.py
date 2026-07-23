from flask import Blueprint
io_bp = Blueprint("io_report", __name__)
from app.modules.io_report import routes  # noqa
