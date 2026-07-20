from flask import Blueprint

v2v_bp = Blueprint('v2v', __name__)

from app.modules.v2v import routes
