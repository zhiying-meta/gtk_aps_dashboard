import io
import os
import shutil
import zipfile
from datetime import datetime

from flask import jsonify, request, send_file, send_from_directory

from app import config
from app.modules.plan_merge import plan_merge_bp
from app.modules.plan_merge.engine import generate_excel, process_uploaded_data

MODULE_DIR = os.path.dirname(__file__)
TEMPLATE_DIR = os.path.join(MODULE_DIR, "templates")


@plan_merge_bp.route("/templates/<name>")
def download_template(name):
    allowed = {"input_template.xlsx", "schema.json"}
    if name not in allowed:
        return "Not found", 404
    return send_from_directory(TEMPLATE_DIR, name, as_attachment=True)


@plan_merge_bp.route("/demo")
def download_demo():
    fp = os.path.join(TEMPLATE_DIR, "input_demo.xlsx")
    if not os.path.exists(fp):
        return "Not found", 404
    return send_file(fp, as_attachment=True, download_name="input_demo.xlsx")


@plan_merge_bp.route("/api/schema")
def get_schema():
    fp = os.path.join(TEMPLATE_DIR, "schema.json")
    if not os.path.exists(fp):
        return jsonify({})
    return send_from_directory(TEMPLATE_DIR, "schema.json")


@plan_merge_bp.route("/templates/zip")
def download_all_templates():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in ("input_template.xlsx", "input_demo.xlsx"):
            fp = os.path.join(TEMPLATE_DIR, fname)
            if os.path.exists(fp):
                zf.write(fp, fname)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="input_files.zip")


@plan_merge_bp.route("/api/process", methods=["POST"])
def process():
    upload_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    work_dir = os.path.join(config.UPLOAD_FOLDER, upload_id)
    os.makedirs(work_dir, exist_ok=True)
    try:
        xlsx_path = None
        for f in request.files.values():
            if f.filename and f.filename.lower().endswith(".xlsx"):
                xlsx_path = os.path.join(work_dir, f.filename)
                f.save(xlsx_path)
                break

        if not xlsx_path:
            return jsonify({"error": "No xlsx file uploaded"}), 400

        cfg = {k: v for k in ("exf_cut", "etd_cut", "output_cut", "gb_cut") if (v := request.form.get(k))}

        result = process_uploaded_data({"main": xlsx_path}, cfg)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@plan_merge_bp.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400
    buf = generate_excel(data)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="report.xlsx",
    )
