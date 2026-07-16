import os, sys, json, io, zipfile, tempfile, shutil
from flask import request, jsonify, send_from_directory, send_file
from datetime import datetime

from app import config
from app.modules.plan_merge import plan_merge_bp
from app.modules.plan_merge.engine import process_uploaded_data, generate_excel

MODULE_DIR = os.path.dirname(__file__)
TEMPLATE_DIR = os.path.join(MODULE_DIR, "templates")


@plan_merge_bp.route("/templates/<name>")
def download_template(name):
    TEMPLATE_FILES = ["input_template.xlsx"]
    if name not in TEMPLATE_FILES and name != "schema.json":
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
    if not os.path.exists(fp): return jsonify({})
    return send_from_directory(TEMPLATE_DIR, "schema.json")


@plan_merge_bp.route("/templates/zip")
def download_all_templates():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        fp = os.path.join(TEMPLATE_DIR, "input_template.xlsx")
        if os.path.exists(fp): zf.write(fp, "input_template.xlsx")
        fp2 = os.path.join(TEMPLATE_DIR, "input_demo.xlsx")
        if os.path.exists(fp2): zf.write(fp2, "input_demo.xlsx")
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name='input_files.zip')


@plan_merge_bp.route("/templates/schema/<name>")
def download_schema(name):
    import openpyxl
    fn = name if name.endswith('.xlsx') else name + '.xlsx'
    fp = os.path.join(TEMPLATE_DIR, fn)
    if not os.path.exists(fp):
        return "Not found", 404
    wb = openpyxl.load_workbook(fp)
    if 'Schema' not in wb.sheetnames:
        return "No schema", 404
    ws = wb['Schema']
    out = io.BytesIO()
    wb2 = openpyxl.Workbook()
    for row in ws.iter_rows(values_only=True):
        wb2.active.append(row)
    wb2.save(out)
    out.seek(0)
    return send_file(out, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=f'schema_{fn}')


@plan_merge_bp.route("/api/process", methods=["POST"])
def process():
    upload_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    work_dir = os.path.join(config.UPLOAD_FOLDER, upload_id)
    os.makedirs(work_dir)
    try:
        uploaded = False
        for key in request.files:
            f = request.files[key]
            if f.filename:
                f.save(os.path.join(work_dir, f.filename))
                uploaded = True

        if not uploaded:
            return jsonify({"error": "No file uploaded"}), 400

        cfg = {}
        for cfg_key in ['exf_cut', 'etd_cut', 'output_cut', 'gb_cut', 'etd_packout_offset']:
            val = request.form.get(cfg_key)
            if val: cfg[cfg_key] = val

        files = os.listdir(work_dir)
        file_map = {}
        for fn in files:
            fl = fn.lower()
            if fl.endswith('.xlsx'):
                file_map['main'] = os.path.join(work_dir, fn)
                break

        if not file_map:
            return jsonify({"error": "No xlsx file found"}), 400

        result = process_uploaded_data(file_map, cfg)
        shutil.rmtree(work_dir, ignore_errors=True)
        return jsonify(result)

    except Exception as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500


@plan_merge_bp.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json()
    if not data: return jsonify({"error": "no data"}), 400
    buf = generate_excel(data)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='report.xlsx')
