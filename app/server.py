"""
Flask server: upload xlsx → configure Cut Days → generate report → download
"""
import os, sys, json, io, zipfile, tempfile, shutil
from flask import Flask, request, jsonify, send_from_directory, send_file
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from backend_v2 import process_uploaded_data

app = Flask(__name__, static_folder="static")
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
DATA_REF_XLSX = os.path.join(os.path.dirname(__file__), "..", "data-ref-xlsx")

@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

# --- Template downloads ---
TEMPLATE_FILES = ["input_template.xlsx"]

@app.route("/templates/<name>")
def download_template(name):
    if name not in TEMPLATE_FILES and name != "schema.json":
        return "Not found", 404
    return send_from_directory(TEMPLATE_DIR, name, as_attachment=True)

@app.route("/demo")
def download_demo():
    # Try templates/ first (tracked), fallback to data-ref-xlsx
    fp = os.path.join(TEMPLATE_DIR, "input_demo.xlsx")
    if not os.path.exists(fp):
        fp = os.path.join(DATA_REF_XLSX, "input_demo.xlsx")
    if not os.path.exists(fp): return "Not found", 404
    return send_file(fp, as_attachment=True, download_name="input_demo.xlsx")

@app.route("/api/schema")
def get_schema():
    fp = os.path.join(TEMPLATE_DIR, "schema.json")
    if not os.path.exists(fp): return jsonify({})
    return send_from_directory(TEMPLATE_DIR, "schema.json")

@app.route("/templates/zip")
def download_all_templates():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        fp = os.path.join(TEMPLATE_DIR, "input_template.xlsx")
        if os.path.exists(fp): zf.write(fp, "input_template.xlsx")
        fp2 = os.path.join(TEMPLATE_DIR, "input_demo.xlsx")
        if os.path.exists(fp2): zf.write(fp2, "input_demo.xlsx")
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name='input_files.zip')

@app.route("/templates/schema/<name>")
def download_schema(name):
    """Download just the Schema sheet from a template"""
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

# --- Upload & Process ---
@app.route("/api/process", methods=["POST"])
def process():
    upload_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    work_dir = os.path.join(UPLOAD_DIR, upload_id)
    os.makedirs(work_dir)
    try:
        # Save uploaded file(s)
        uploaded = False
        for key in request.files:
            f = request.files[key]
            if f.filename:
                f.save(os.path.join(work_dir, f.filename))
                uploaded = True

        if not uploaded:
            return jsonify({"error": "未上传文件"}), 400

        # Get Cut Day config
        config = {}
        for cfg_key in ['exf_cut', 'etd_cut', 'output_cut', 'gb_cut']:
            val = request.form.get(cfg_key)
            if val: config[cfg_key] = val

        # Detect files
        files = os.listdir(work_dir)
        file_map = {}
        for fn in files:
            fl = fn.lower()
            # Single xlsx with 6 sheets or individual files
            if fl.endswith('.xlsx'):
                file_map['main'] = os.path.join(work_dir, fn)
                break

        if not file_map:
            return jsonify({"error": "未找到xlsx文件"}), 400

        result = process_uploaded_data(file_map, config)
        shutil.rmtree(work_dir, ignore_errors=True)
        return jsonify(result)

    except Exception as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/download", methods=["POST"])
def api_download():
    """Generate Excel from processed data"""
    data = request.get_json()
    if not data: return jsonify({"error": "no data"}), 400
    import backend_v2
    buf = backend_v2.generate_excel(data)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='report.xlsx')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8501))
    print(f"🌐 http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
