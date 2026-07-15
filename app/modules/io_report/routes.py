import os, json, io
from flask import request, jsonify, send_file, Blueprint
from app.modules.io_report.engine import load_and_build, load_data

io_bp = Blueprint("io_report", __name__)

MODULE_DIR = os.path.dirname(__file__)
DATA_DIR = MODULE_DIR  # data files are bundled alongside the module


@io_bp.route("/api/io/load", methods=["POST"])
def api_load():
    """Load data and build reports."""
    body = request.get_json() or {}
    dim = body.get("dim", "ITEM_NO")
    col_mode = body.get("col_mode", "shift")
    cat = body.get("cat", "FG")
    dim_filter = body.get("dim_filter")

    try:
        result = load_and_build(DATA_DIR, dim, col_mode, cat, dim_filter)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@io_bp.route("/api/io/meta", methods=["GET"])
def api_meta():
    """Return metadata (dimension values) only."""
    try:
        cache = load_data(DATA_DIR)
        return jsonify({
            "lines_fg": cache.line_fg,
            "lines_gb": cache.line_gb,
            "items_fg": cache.fg_items,
            "items_gb": cache.gb_items,
            "styles_fg": cache.style_fg,
            "styles_gb": cache.style_gb,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
