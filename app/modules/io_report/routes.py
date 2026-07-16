import io
import os
import shutil
import tempfile
import zipfile

from flask import Blueprint, jsonify, request, send_file

from app.modules.io_report.engine import build_reports_for_group, get_cache, get_meta, reload_cache

io_bp = Blueprint("io_report", __name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def _ensure_cache():
    try:
        get_cache(DEFAULT_DATA_DIR)
        return True
    except Exception as e:
        print(f"[IO] cache not ready: {e}")
        return False


_ensure_cache()


def _json_error(msg, code=500):
    return jsonify({"error": msg}), code


# ---------- status ----------
@io_bp.route("/api/io/status", methods=["GET"])
def api_status():
    loaded = _ensure_cache()
    return jsonify({"loaded": loaded, "ok": loaded})


# ---------- meta ----------
@io_bp.route("/api/io/meta", methods=["GET"])
def api_meta():
    try:
        cache = get_cache(DEFAULT_DATA_DIR)
    except Exception as e:
        return _json_error(f"no data: {e}", 404)
    group = request.args.get("group", "成品")
    if cat := request.args.get("cat"):
        group = "成品" if cat in ("FG", "成品") else "GB"
    col_dim = request.args.get("col_dim") or request.args.get("col_mode") or "shift"
    try:
        return jsonify(get_meta(cache, group, col_dim))
    except Exception as e:
        return _json_error(str(e))


# ---------- reports ----------
@io_bp.route("/api/io/reports", methods=["GET"])
def api_reports():
    try:
        cache = get_cache(DEFAULT_DATA_DIR)
    except Exception as e:
        return _json_error(f"no data: {e}", 404)

    q = request.args
    group = q.get("group", "成品")
    if cat := q.get("cat"):
        group = "成品" if cat in ("FG", "成品") else "GB"

    dim = q.get("dim", "")
    if dim in ("ITEM", "SKU"):
        dim = "ITEM_NO"
    if dim == "LINE":
        dim = "LINE_CODE"
    if not dim:
        return jsonify({})

    try:
        reports, _ = build_reports_for_group(
            cache,
            dim,
            q.get("col_dim") or q.get("col_mode") or "shift",
            group,
            q.get("line_code", ""),
            q.get("item_no", ""),
            q.get("style", ""),
        )
        return jsonify(reports)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return _json_error(str(e))


# ---------- upload ----------
TARGET_MAP = {
    "master": "料号主表.xlsx",
    "schedule": "排产结果表.xlsx",
    "balance": "结存表.xlsx",
}


def _classify_upload(filename: str, field: str) -> str | None:
    fn_low = (filename or "").lower()
    field_low = (field or "").lower()
    if "master" in field_low or "料号" in field or "master" in fn_low or "料号" in filename:
        return TARGET_MAP["master"]
    if "sched" in field_low or "排产" in field or "sched" in fn_low or "排产" in filename:
        return TARGET_MAP["schedule"]
    if "bal" in field_low or "结存" in field or "bal" in fn_low or "结存" in filename:
        return TARGET_MAP["balance"]
    return None


@io_bp.route("/api/io/upload", methods=["POST"])
def api_upload():
    if not request.files:
        return _json_error("expected multipart with master/schedule/balance", 400)

    tmp_dir = tempfile.mkdtemp(prefix="io_upload_")
    try:
        # save with classification
        for field_key, f in request.files.items():
            if not f.filename:
                continue
            target = _classify_upload(f.filename, field_key)
            # direct field name fallback
            if not target and field_key in TARGET_MAP:
                target = TARGET_MAP[field_key]
            if target:
                f.save(os.path.join(tmp_dir, target))

        # ensure all 3 present
        missing = [fn for fn in TARGET_MAP.values() if not os.path.exists(os.path.join(tmp_dir, fn))]
        if missing:
            existing = os.listdir(tmp_dir)
            return _json_error(f"missing files {missing}, got {existing}", 400)

        os.makedirs(DEFAULT_DATA_DIR, exist_ok=True)
        for fn in TARGET_MAP.values():
            shutil.copyfile(os.path.join(tmp_dir, fn), os.path.join(DEFAULT_DATA_DIR, fn))

        cache = reload_cache(DEFAULT_DATA_DIR)
        return jsonify({"ok": True, "fg": len(cache.fg_items), "gb": len(cache.gb_items)})
    except Exception as e:
        import traceback

        traceback.print_exc()
        return _json_error(f"upload failed: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------- templates ----------
IO_SCHEMA = {
    "item_master": {
        "file": "料号主表.xlsx",
        "fields": [
            ["ITEM_NO", "String", "Material number / PN", "FG001"],
            ["PRODUCT_CATEGORY", "String", "Category: 成品/GB", "成品 / GB"],
            ["PRODUCT_STYLE", "String", "Style", "Style-A"],
        ],
        "note": "PRODUCT_CATEGORY must be 成品 or GB",
    },
    "schedule_result": {
        "file": "排产结果表.xlsx",
        "fields": [
            ["LINE_CODE", "String", "Production line", "Line01"],
            ["SHIFT_NAME", "String", "Shift", "白班 / 夜班 / Day / Night"],
            ["PLAN_ITEM", "String", "INPUT / OUTPUT / CHECKIN / CHECKOUT", "INPUT"],
            ["SKU", "String", "Material number", "FG001"],
            ["PLAN_DATE", "Date", "Plan date", "2024-06-01"],
            ["PLAN_VALUE", "Number", "Quantity", "100"],
        ],
        "note": "Aggregated by date+shift",
    },
    "balance": {
        "file": "结存表.xlsx",
        "fields": [
            ["PLAN_DATE", "Date", "Balance date", "2024-06-01"],
            ["SHIFT_NAME", "String", "Shift", "白班"],
            ["ITEM_CODE", "String", "Material number", "FG001"],
            ["BALANCE_QTY", "Number", "BOH quantity", "500"],
        ],
        "note": "BOH = Balance on Hand",
    },
}


def _xlsx_buf(header, rows=None):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows or []:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _zip_io(empty=True):
    master_header = ["ITEM_NO", "PRODUCT_CATEGORY", "PRODUCT_STYLE"]
    sched_header = ["LINE_CODE", "SHIFT_NAME", "PLAN_ITEM", "SKU", "PLAN_DATE", "PLAN_VALUE"]
    bal_header = ["PLAN_DATE", "SHIFT_NAME", "ITEM_CODE", "BALANCE_QTY"]

    sample_master = [["FG001", "成品", "Style-A"], ["GB001", "GB", "Style-A"]] if not empty else []
    sample_sched = [["Line01", "白班", "INPUT", "FG001", "2024-06-01", 100]] if not empty else []
    sample_bal = [["2024-06-01", "白班", "FG001", 500]] if not empty else []

    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("料号主表.xlsx", _xlsx_buf(master_header, sample_master).getvalue())
        zf.writestr("排产结果表.xlsx", _xlsx_buf(sched_header, sample_sched).getvalue())
        zf.writestr("结存表.xlsx", _xlsx_buf(bal_header, sample_bal).getvalue())
    zb.seek(0)
    return zb


@io_bp.route("/api/io/templates/template", methods=["GET"])
def api_io_template():
    return send_file(_zip_io(empty=True), mimetype="application/zip", as_attachment=True, download_name="io_templates.zip")


@io_bp.route("/api/io/templates/demo", methods=["GET"])
@io_bp.route("/api/io/templates/zip", methods=["GET"])
def api_io_demo():
    local = [(fn, os.path.join(DEFAULT_DATA_DIR, fn)) for fn in TARGET_MAP.values()]
    if all(os.path.exists(p) for _, p in local):
        zb = io.BytesIO()
        with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, path in local:
                zf.write(path, arcname=name)
        zb.seek(0)
        return send_file(zb, mimetype="application/zip", as_attachment=True, download_name="io_demo.zip")
    return send_file(_zip_io(empty=False), mimetype="application/zip", as_attachment=True, download_name="io_demo.zip")


@io_bp.route("/api/io/templates/schema", methods=["GET"])
def api_io_schema():
    return jsonify(IO_SCHEMA)


@io_bp.route("/api/io/templates/input_template.xlsx", methods=["GET"])
def api_io_single_template():
    import openpyxl

    wb = openpyxl.Workbook()
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
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name="io_template.xlsx")
