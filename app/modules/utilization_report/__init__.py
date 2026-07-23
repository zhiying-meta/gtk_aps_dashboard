from flask import Blueprint
util_bp = Blueprint("utilization_report", __name__)
from app.modules.utilization_report import routes  # noqa
