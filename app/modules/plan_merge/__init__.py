from flask import Blueprint

plan_merge_bp = Blueprint('plan_merge', __name__)

from app.modules.plan_merge import routes
