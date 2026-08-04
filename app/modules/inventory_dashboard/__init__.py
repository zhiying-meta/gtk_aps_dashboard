from flask import Blueprint
inventory_bp = Blueprint("inventory_dashboard", __name__)
from app.modules.inventory_dashboard import routes  # noqa
