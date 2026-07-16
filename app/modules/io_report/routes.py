import os
import tempfile
import shutil
import io
import zipfile
from flask import request, jsonify, Blueprint, send_file

from app.modules.io_report.engine import (
    load_data,
    get_cache,
    reload_cache,
    get_meta,
    build_reports_for_group,
    _resolve_data_dir,
)

io_bp = Blueprint("io_report", __name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# global flag
_data_loaded = False

def _ensure_cache():
    global _data_loaded
    try:
        get_cache(DEFAULT_DATA_DIR)
        _data_loaded = True
        return True
    except Exception as e:
        print(f"[IO] cache not loaded: {e}")
        _data_loaded = False
        return False

# try load at import time
_ensure_cache()

def _json_error(msg, code=500):
    return jsonify({"error": msg}), code

# ---------- status ----------
@io_bp.route("/api/io/status", methods=["GET"])
def api_status():
    # compatible with Go /api/status
    loaded = _ensure_cache()
    return jsonify({"loaded": loaded, "ok": loaded})

@io_bp.route("/api/status", methods=["GET"])
def api_status_compat():
    # Go frontend calls /api/status
    loaded = _ensure_cache()
    return jsonify({"loaded": loaded})

# ---------- meta ----------
@io_bp.route("/api/io/meta", methods=["GET"])
def api_meta():
    try:
        cache = get_cache(DEFAULT_DATA_DIR)
    except Exception as e:
        return _json_error(f"no data: {e}", 404)
    group = request.args.get("group", "成品")
    # also support cat param
    cat = request.args.get("cat")
    if cat:
        group = "成品" if cat in ("FG", "成品") else "GB"
    col_dim = request.args.get("col_dim", "shift")
    if col_dim in ("col_mode",):
        col_dim = request.args.get("col_mode", "shift")
    col_dim = request.args.get("col_dim") or request.args.get("col_mode") or "shift"
    try:
        meta = get_meta(cache, group, col_dim)
        return jsonify(meta)
    except Exception as e:
        return _json_error(str(e))

@io_bp.route("/api/meta", methods=["GET"])
def api_meta_compat():
    """Compat for Go frontend /api/meta?group=&col_dim="""
    return api_meta()

# ---------- reports ----------
@io_bp.route("/api/io/reports", methods=["GET"])
def api_reports():
    """Build 5 reports: ?group=成品&dim=ITEM_NO|LINE_CODE|STYLE|detail&col_dim=shift/day/week/month&line_code=&item_no=&style="""
    try:
        cache = get_cache(DEFAULT_DATA_DIR)
    except Exception as e:
        return _json_error(f"no data: {e}", 404)

    q = request.args
    group = q.get("group", "成品")
    # compat: cat=FG/GB
    cat = q.get("cat")
    if cat:
        group = "成品" if cat in ("FG", "成品") else "GB"
    dim = q.get("dim", "")
    col_dim = q.get("col_dim") or q.get("col_mode") or "shift"
    line_code = q.get("line_code", "")
    item_no = q.get("item_no", "")
    style = q.get("style", "")

    # legacy support for older frontend dim values
    if dim in ("ITEM", "SKU"):
        dim = "ITEM_NO"
    if dim == "LINE":
        dim = "LINE_CODE"

    if not dim:
        # if no dim chosen, return empty but still meta
        return jsonify({})

    try:
        reports, col_defs = build_reports_for_group(cache, dim, col_dim, group, line_code, item_no, style)
        return jsonify(reports)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(str(e))

@io_bp.route("/api/reports", methods=["GET"])
def api_reports_compat():
    return api_reports()

@io_bp.route("/api/report", methods=["GET"])
def api_single_report():
    """Single report endpoint: ?group=&type=daily_input&dim=&col_dim=&line_code=&item_no="""
    try:
        cache = get_cache(DEFAULT_DATA_DIR)
    except Exception as e:
        return _json_error(f"no data: {e}", 404)

    q = request.args
    group = q.get("group", "成品")
    rtype = q.get("type", "daily_input")
    dim = q.get("dim", "ITEM_NO")
    col_dim = q.get("col_dim", "shift")
    line_code = q.get("line_code", "")
    item_no = q.get("item_no", "")
    style = q.get("style", "")

    # map single type to build
    reports, _ = build_reports_for_group(cache, dim, col_dim, group, line_code, item_no, style)
    data = reports.get(rtype, {"columns": [], "rows": []})
    return jsonify({
        "columns": data.get("columns", []),
        "rows": data.get("rows", []),
        "dim": dim,
    })

# ---------- legacy /api/io/load (kept for backward compat) ----------
@io_bp.route("/api/io/load", methods=["POST", "GET"])
def api_load_compat():
    """Legacy endpoint expecting POST JSON {dim, col_mode, cat, dim_filter}. Convert to new logic."""
    try:
        cache = get_cache(DEFAULT_DATA_DIR)
    except Exception as e:
        return _json_error(f"no data: {e}", 404)

    if request.method == "GET":
        # delegate to reports
        return api_reports()

    body = request.get_json() or {}
    dim = body.get("dim", "ITEM_NO")
    col_mode = body.get("col_mode", body.get("col_dim", "shift"))
    cat = body.get("cat", "FG")
    group = "成品" if cat in ("FG", "成品") else "GB"
    dim_filter = body.get("dim_filter")  # legacy single filter list

    line_code = ""
    item_no = ""
    style = ""
    if dim_filter:
        # dim_filter was list of single value for old filter dropdown
        # We try to infer: if dim is ITEM_NO then it's item filter
        if isinstance(dim_filter, list) and len(dim_filter) > 0:
            v = dim_filter[0]
            if dim == "ITEM_NO":
                item_no = v
            elif dim == "LINE_CODE":
                line_code = v
            elif dim == "STYLE":
                style = v
            else:
                item_no = v

    # also support separate filters in body
    line_code = body.get("line_code", line_code)
    item_no = body.get("item_no", body.get("item_code", item_no))
    style = body.get("style", style)

    reports, _ = build_reports_for_group(cache, dim, col_mode, group, line_code, item_no, style)
    # Build meta similar to old
    meta = get_meta(cache, group, col_mode)
    # adapt to old expected shape? Old frontend expects reports keyed by INPUT etc
    # Our new reports are keyed by daily_input etc, but keep as is
    # Also provide meta
    return jsonify({"meta": meta, "reports": reports})

# ---------- upload ----------
@io_bp.route("/api/io/upload", methods=["POST"])
def api_upload():
    """
    Upload 3 files: master=料号主表, schedule=排产结果表, balance=结存表
    Compatible with Go's /api/upload (multipart keys: master, schedule, balance)
    """
    # Check multipart
    if request.content_type and "multipart/form-data" in request.content_type:
        files = request.files
        # support both Go keys and generic
        file_map = {
            "master": ["master", "料号", "item", "sku_master"],
            "schedule": ["schedule", "排产", "plan"],
            "balance": ["balance", "结存"],
        }
        tmp_dir = tempfile.mkdtemp(prefix="io_upload_")
        try:
            found = {}
            # iterate uploaded files
            for field_key in files:
                f = files.get(field_key)
                if not f or not f.filename:
                    continue
                # decide type by field name
                lower_field = field_key.lower()
                target = None
                # direct mapping
                if "master" in lower_field or "料号" in field_key or "item" in lower_field:
                    target = "料号主表.xlsx"
                    found["master"] = True
                elif "sched" in lower_field or "排产" in field_key or "plan" in lower_field:
                    target = "排产结果表.xlsx"
                    found["schedule"] = True
                elif "bal" in lower_field or "结存" in field_key:
                    target = "结存表.xlsx"
                    found["balance"] = True
                else:
                    # try guess by filename
                    fn = f.filename
                    if "料号" in fn:
                        target = "料号主表.xlsx"
                        found["master"] = True
                    elif "排产" in fn:
                        target = "排产结果表.xlsx"
                        found["schedule"] = True
                    elif "结存" in fn:
                        target = "结存表.xlsx"
                        found["balance"] = True
                    else:
                        continue
                if target:
                    f.save(os.path.join(tmp_dir, target))

            # Also allow three files with exact names uploaded under any field
            # If not found enough, try second loop mapping by provided fileKeys exactly as Go
            required = {"料号主表.xlsx": False, "排产结果表.xlsx": False, "结存表.xlsx": False}
            for fn in os.listdir(tmp_dir):
                if fn in required:
                    required[fn] = True
            # If missing, try to get from files named exactly
            if not all(required.values()):
                # check if upload used keys master/schedule/balance as in Go
                for key, expected in [("master","料号主表.xlsx"),("schedule","排产结果表.xlsx"),("balance","结存表.xlsx")]:
                    if expected in required and required[expected]:
                        continue
                    f = files.get(key)
                    if f and f.filename:
                        f.save(os.path.join(tmp_dir, expected))
                        required[expected] = True

            if not all(required.values()):
                # also allow uploading 3 files with any field names but we try to auto-detect remaining
                # list all files uploaded
                for field_key in files:
                    f = files.get(field_key)
                    if not f or not f.filename:
                        continue
                    # if already saved, skip
                    # attempt to save any missing
                    # reuse saved already logic
                    pass
                # final check
                missing = [k for k,v in required.items() if not v]
                # If still missing but we have 3 files, try to map by order
                uploaded_files = list(files.values())
                if len(uploaded_files) >= 3 and missing:
                    # best effort: user uploaded 3 files, we already saved some, save rest
                    pass

            # Validate
            for fn in ["料号主表.xlsx","排产结果表.xlsx","结存表.xlsx"]:
                if not os.path.exists(os.path.join(tmp_dir, fn)):
                    # try to find any xlsx in tmp and rename if only one missing
                    # we already attempted
                    pass

            # Check existence
            if not os.path.exists(os.path.join(tmp_dir, "料号主表.xlsx")) or \
               not os.path.exists(os.path.join(tmp_dir, "排产结果表.xlsx")) or \
               not os.path.exists(os.path.join(tmp_dir, "结存表.xlsx")):
                # Allow partial if user uploaded folder? Return error with what we have
                existing = os.listdir(tmp_dir)
                return jsonify({"error": f"missing files, got {existing}. Need 料号主表.xlsx, 排产结果表.xlsx, 结存表.xlsx"}), 400

            # Copy to DEFAULT_DATA_DIR
            os.makedirs(DEFAULT_DATA_DIR, exist_ok=True)
            for fn in ["料号主表.xlsx","排产结果表.xlsx","结存表.xlsx"]:
                src = os.path.join(tmp_dir, fn)
                dst = os.path.join(DEFAULT_DATA_DIR, fn)
                shutil.copyfile(src, dst)

            # reload cache
            try:
                cache = reload_cache(DEFAULT_DATA_DIR)
                global _data_loaded
                _data_loaded = True
                return jsonify({"ok": True, "fg": len(cache.fg_items), "gb": len(cache.gb_items)})
            except Exception as e:
                import traceback
                traceback.print_exc()
                return _json_error(f"load after upload failed: {e}")

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # JSON folder upload fallback?
    body = request.get_json(silent=True) or {}
    if body.get("action") == "reload":
        ok = _ensure_cache()
        return jsonify({"ok": ok})

    return jsonify({"error": "invalid upload, expected multipart with master/schedule/balance"}), 400

@io_bp.route("/api/upload", methods=["POST"])
def api_upload_compat():
    return api_upload()


# ---------- templates & demo ----------
IO_SCHEMA = {
    "item_master": {
        "file": "料号主表.xlsx / Item Master",
        "fields": [
            ["ITEM_NO", "String", "Material number / PN, key for FG/GB", "FG001, GB001"],
            ["PRODUCT_CATEGORY", "String", "Category: FG (finished) or GB (component)", "FG / GB"],
            ["PRODUCT_STYLE", "String", "Style grouping", "Style-A"],
        ],
        "note": "PRODUCT_CATEGORY must be '成品' or 'GB' (or FG/GB in English version). Used to split FG vs GB."
    },
    "schedule_result": {
        "file": "排产结果表.xlsx / Schedule Result",
        "fields": [
            ["LINE_CODE", "String", "Production line", "Line01"],
            ["SHIFT_NAME", "String", "Shift, e.g., Day/Night or 白班/夜班", "Day Shift"],
            ["PLAN_ITEM", "String", "INPUT (Checkin) or OUTPUT (Checkout)", "INPUT"],
            ["SKU", "String", "Material number, must exist in master", "FG001"],
            ["PLAN_DATE", "Date", "Plan date YYYY-MM-DD or YYYY/MM/DD", "2024-06-01"],
            ["PLAN_VALUE", "Number", "Plan quantity", "100"],
        ],
        "note": "PLAN_ITEM: INPUT = checkin (production input), OUTPUT = checkout (output). Aggregated by date+shift."
    },
    "balance": {
        "file": "结存表.xlsx / BOH Balance",
        "fields": [
            ["PLAN_DATE", "Date", "Balance date", "2024-06-01"],
            ["SHIFT_NAME", "String", "Shift", "Day Shift"],
            ["ITEM_CODE", "String", "Material number", "FG001"],
            ["BALANCE_QTY", "Number", "Balance quantity (BOH)", "500"],
        ],
        "note": "BOH = Balance on Hand. No LINE_CODE dimension."
    }
}

def _create_xlsx_with_header(header, rows=None):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    if rows:
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

def _zip_three_templates(empty=True):
    """
    Create zip containing 3 xlsx files.
    empty=True -> only headers
    empty=False -> include sample rows from existing data/ if available
    """
    import openpyxl

    # Headers
    master_header = ["ITEM_NO", "PRODUCT_CATEGORY", "PRODUCT_STYLE"]
    sched_header = ["LINE_CODE", "SHIFT_NAME", "PLAN_ITEM", "SKU", "PLAN_DATE", "PLAN_VALUE"]
    bal_header = ["PLAN_DATE", "SHIFT_NAME", "ITEM_CODE", "BALANCE_QTY"]

    sample_master = [
        ["FG001", "成品", "Style-A"],
        ["FG002", "成品", "Style-B"],
        ["GB001", "GB", "Style-A"],
    ] if not empty else []

    sample_sched = [
        ["Line01", "白班", "INPUT", "FG001", "2024-06-01", 100],
        ["Line01", "白班", "OUTPUT", "FG001", "2024-06-01", 90],
        ["Line01", "夜班", "INPUT", "GB001", "2024-06-01", 50],
    ] if not empty else []

    sample_bal = [
        ["2024-06-01", "白班", "FG001", 500],
        ["2024-06-01", "白班", "GB001", 200],
    ] if not empty else []

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # master
        b1 = _create_xlsx_with_header(master_header, sample_master)
        zf.writestr("料号主表.xlsx", b1.getvalue())
        # schedule
        b2 = _create_xlsx_with_header(sched_header, sample_sched)
        zf.writestr("排产结果表.xlsx", b2.getvalue())
        # balance
        b3 = _create_xlsx_with_header(bal_header, sample_bal)
        zf.writestr("结存表.xlsx", b3.getvalue())

        # also include English named copies for clarity
        if empty:
            # empty english copies are same content, different name inside zip for reference
            pass

    zip_buf.seek(0)
    return zip_buf

@io_bp.route("/api/io/templates/template", methods=["GET"])
def api_io_template():
    """Download empty templates as zip"""
    zip_buf = _zip_three_templates(empty=True)
    return send_file(zip_buf, mimetype='application/zip', as_attachment=True, download_name='io_templates.zip')

@io_bp.route("/api/io/templates/demo", methods=["GET"])
@io_bp.route("/api/io/templates/zip", methods=["GET"])
def api_io_demo():
    """Download demo: if data/ has files, zip them, otherwise return sample"""
    # Try to use existing data files
    existing_files = []
    for fn in ["料号主表.xlsx", "排产结果表.xlsx", "结存表.xlsx"]:
        fp = os.path.join(DEFAULT_DATA_DIR, fn)
        if os.path.exists(fp):
            existing_files.append((fn, fp))

    if len(existing_files) == 3:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name, path in existing_files:
                zf.write(path, arcname=name)
        zip_buf.seek(0)
        return send_file(zip_buf, mimetype='application/zip', as_attachment=True, download_name='io_demo.zip')
    else:
        # fallback sample
        zip_buf = _zip_three_templates(empty=False)
        return send_file(zip_buf, mimetype='application/zip', as_attachment=True, download_name='io_demo.zip')

@io_bp.route("/api/io/templates/schema", methods=["GET"])
def api_io_schema():
    return jsonify(IO_SCHEMA)

@io_bp.route("/api/io/templates/input_template.xlsx", methods=["GET"])
def api_io_single_template():
    """Single combined template with 3 sheets (for compatibility)"""
    import openpyxl
    wb = openpyxl.Workbook()
    # Remove default sheet and create 3
    ws0 = wb.active
    ws0.title = "Item Master"
    ws0.append(["ITEM_NO", "PRODUCT_CATEGORY", "PRODUCT_STYLE"])

    ws1 = wb.create_sheet("Schedule Result")
    ws1.append(["LINE_CODE", "SHIFT_NAME", "PLAN_ITEM", "SKU", "PLAN_DATE", "PLAN_VALUE"])

    ws2 = wb.create_sheet("BOH Balance")
    ws2.append(["PLAN_DATE", "SHIFT_NAME", "ITEM_CODE", "BALANCE_QTY"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='io_template.xlsx')
