"""
Plan Merge Routes — Snapshot Only
ExF vs ETD vs Packout vs CTB — only snapshot import.
"""
import io
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from flask import jsonify, request, send_file, send_from_directory

from app import config
from app.modules.plan_merge import plan_merge_bp
from app.modules.plan_merge.engine import generate_excel, process_snapshot_data
from app.modules.plan_merge.snapshot_parser import detect_snapshot_files

MODULE_DIR = os.path.dirname(__file__)
TEMPLATE_DIR = os.path.join(MODULE_DIR, "templates")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data")
SNAPSHOT_DEMO_DIR = os.path.join(DEFAULT_DATA_DIR, "gated.ungated.ctb")

# ---------- Snapshot Target Map (like IO's TARGET_MAP, but 7 files) ----------
SNAPSHOT_TARGET_MAP = {
    "item": "料号快照.xlsx",
    "bom": "BOM快照.xlsx",
    "gated": "gated排产结果表.xlsx",
    "ungated": "ungated排产结果表.xlsx",
    "fcst_main": "FCST主表.xlsx",
    "fcst_detail": "FCST明细表.xlsx",
    "ctb": "CTB.xlsx",
}

# For backward compat of old demo/template endpoint names
LEGACY_TEMPLATE_FILES = ("input_template.xlsx", "input_demo.xlsx", "schema.json")

def _classify_snapshot_upload(filename: str, field: str) -> str | None:
    """
    Classify uploaded file into snapshot key (item/bom/gated/ungated/fcst_main/fcst_detail/ctb)
    Returns target filename (the value in SNAPSHOT_TARGET_MAP) or None.
    Like IO's _classify_upload but for 7 snapshot types.
    """
    fn_low = (filename or "").lower()
    field_low = (field or "").lower()
    # Check exact keywords
    # IMPORTANT: check ungated before gated because ungated contains gated substring
    if "料号" in filename or "item" in fn_low or "料号" in field or "item" in field_low:
        # Prefer filled version but still map to item
        return SNAPSHOT_TARGET_MAP["item"]
    if "bom" in fn_low or "bom" in field_low:
        return SNAPSHOT_TARGET_MAP["bom"]
    if "ungated" in fn_low or "ungated" in field_low or "ungated排产" in filename:
        return SNAPSHOT_TARGET_MAP["ungated"]
    if "gated" in fn_low or "gated" in field_low or "gated排产" in filename:
        # ensure not ungated (already handled)
        if "ungated" not in fn_low:
            return SNAPSHOT_TARGET_MAP["gated"]
    # fcst main vs detail
    if "fcst" in fn_low or "fcst" in field_low:
        if "主表" in filename or "main" in fn_low:
            return SNAPSHOT_TARGET_MAP["fcst_main"]
        if "明细" in filename or "detail" in fn_low:
            return SNAPSHOT_TARGET_MAP["fcst_detail"]
        # fallback: try to infer by other keywords, if filename has 主表 -> main else detail
        # If ambiguous, return None and let detection handle later
    if "fcst主表" in filename or "fcst_main" in fn_low:
        return SNAPSHOT_TARGET_MAP["fcst_main"]
    if "fcst明细" in filename or "fcst_detail" in fn_low:
        return SNAPSHOT_TARGET_MAP["fcst_detail"]
    if "ctb" in fn_low or "ctb" in field_low:
        return SNAPSHOT_TARGET_MAP["ctb"]
    # Additional heuristic for FCST files named with 主表 / 明细 without fcst keyword
    if "主表" in filename:
        return SNAPSHOT_TARGET_MAP["fcst_main"]
    if "明细表" in filename:
        return SNAPSHOT_TARGET_MAP["fcst_detail"]
    return None

def _classify_to_key(filename: str, field: str) -> str | None:
    """Return logical key (item/bom/gated/ungated/fcst_main/fcst_detail/ctb)"""
    target = _classify_snapshot_upload(filename, field)
    if not target:
        return None
    for k, v in SNAPSHOT_TARGET_MAP.items():
        if v == target:
            return k
    return None

def _is_zip_file(filename: str) -> bool:
    return filename.lower().endswith(".zip")

def _is_valid_xlsx_by_content(file_path: str) -> bool:
    """Check if file is xlsx by reading magic number PK"""
    try:
        if not os.path.exists(file_path):
            return False
        if os.path.getsize(file_path) < 10:
            return False
        with open(file_path, 'rb') as fh:
            head = fh.read(4)
            # xlsx is zip file, starts with PK
            return head[:2] == b'PK'
    except Exception:
        return False

def _extract_zip_to_tmp(zip_path: str, tmp_dir: str):
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                # Be more permissive: extract all files, not just .xlsx, and let later filtering decide
                # But still skip obvious non-data files
                raw_name = info.filename
                # Try to handle encoding issues: zipfile may have cp437 encoded filenames
                # os.path.basename handles both / and \
                base = os.path.basename(raw_name)
                # Skip hidden files and temp files
                if not base or base.startswith('.') or base.startswith('~$'):
                    continue
                # If file doesn't look like xlsx and not in our target list, we still extract if size reasonable
                # We'll check content later, but for now extract if name contains our keywords or ends with xlsx
                low = base.lower()
                # Extract if it ends with xlsx or contains known keywords (for files without extension due to encoding)
                should_extract = low.endswith('.xlsx') or any(kw in low for kw in ["料号", "bom", "gated", "ungated", "fcst", "ctb"]) or any(kw in raw_name.lower() for kw in ["料号", "bom", "gated", "ungated", "fcst", "ctb"])
                # Also extract if file has no extension but size > 1KB (could be xlsx with garbled name)
                if not should_extract:
                    # Check if file size > 1KB and maybe is xlsx
                    try:
                        # We need to peek without extracting fully – just check file size from ZipInfo
                        if info.file_size > 1024:
                            # If file name has no extension but is in our expected set, still extract
                            # For safety, extract all files >1KB that are not obviously non-excel (like .txt, .docx etc)
                            # We'll extract and later validate by content
                            if '.' not in low or low.endswith(('.xls', '.xlsx')):
                                should_extract = True
                    except:
                        pass
                if not should_extract:
                    # As fallback, extract any file that might be xlsx by content? We can't know without extracting.
                    # We'll extract all files with size > 1KB to be safe, except known non-excel
                    if info.file_size > 1024 and not low.endswith(('.txt', '.csv', '.pdf', '.png', '.jpg', '.docx')):
                        should_extract = True

                if not should_extract:
                    continue

                target_path = os.path.join(tmp_dir, base)
                # Sanitize base to avoid path traversal and strip spaces
                base = base.strip()
                if not base:
                    continue
                target_path = os.path.join(tmp_dir, base)
                # avoid overwrite
                c = 1
                b, e = os.path.splitext(target_path)
                while os.path.exists(target_path):
                    target_path = f"{b}_{c}{e}"
                    c += 1
                try:
                    with zf.open(info) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    # Validate content is xlsx (PK header)
                    if _is_valid_xlsx_by_content(target_path):
                        extracted.append(target_path)
                    else:
                        # If not valid xlsx, keep but mark? For now, if file is small and not PK, maybe still try to keep if name matches
                        # Check if name matches expected snapshot names, keep even if content not PK (could be old xls)
                        if any(kw in base.lower() for kw in ["料号", "bom", "gated", "ungated", "fcst", "ctb"]):
                            extracted.append(target_path)
                        else:
                            # Remove invalid
                            try:
                                os.remove(target_path)
                            except:
                                pass
                except Exception as ex:
                    print(f"[PlanMerge] extract file {base} failed: {ex}")
                    continue
    except Exception as e:
        print(f"[PlanMerge] zip extract failed {e}")
        import traceback
        traceback.print_exc()
    return extracted

def _json_error(msg, code=400):
    return jsonify({"error": msg}), code

# ---------- Helpers for template/demo generation (like IO) ----------
def _xlsx_buf(header, rows=None, sheet_name="Sheet1"):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(header)
    for r in rows or []:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

def _zip_snapshot_templates(empty=True):
    """
    Create zip of 7 snapshot templates.
    If empty=True, only headers. If False, with sample rows.
    """
    if empty:
        item_header = ["ITEM_NO", "STYLE", "COLOR", "PURPOSE", "PRODUCT_STYLE", "TYPE", "PRODUCT_CATEGORY"]
        bom_header = ["PARENT_PN_CODE", "ITEM_NO"]
        plan_header = ["LINE_CODE", "SHIFT_NAME", "PLAN_ITEM", "SKU", "PLAN_DATE", "PLAN_VALUE"]
        fcst_main_header = ["ID", "PN_CODE"]
        fcst_detail_header = ["MAIN_ID", "ACTUALFIRSTDAYOFWEEK", "ACTUALWEEKVALUE", "ID"]
        ctb_header_sku = ["SKU", "2026-06-02", "2026-06-09"]
        ctb_header_gb = ["PN", "2026-06-02", "2026-06-09"]
        sample_item = []
        sample_bom = []
        sample_gated = []
        sample_ungated = []
        sample_fcst_main = []
        sample_fcst_detail = []
        sample_ctb_sku = []
        sample_ctb_gb = []
    else:
        item_header = ["ITEM_NO", "STYLE", "COLOR", "PURPOSE", "PRODUCT_STYLE", "TYPE", "PRODUCT_CATEGORY"]
        bom_header = ["PARENT_PN_CODE", "ITEM_NO"]
        plan_header = ["LINE_CODE", "SHIFT_NAME", "PLAN_ITEM", "SKU", "PLAN_DATE", "PLAN_VALUE"]
        fcst_main_header = ["ID", "PN_CODE"]
        fcst_detail_header = ["MAIN_ID", "ACTUALFIRSTDAYOFWEEK", "ACTUALWEEKVALUE", "ID"]
        ctb_header_sku = ["SKU", "2026-06-02", "2026-06-09"]
        ctb_header_gb = ["PN", "2026-06-02", "2026-06-09"]
        sample_item = [
            ["SK-1001879-01", "Rectangle M", "BLACK", "MP", "Rectangle M", "FG", "成品"],
            ["GB-Rec M-BLACK", "Rectangle M", "BLACK", "MP", "Rectangle M", "GB", "GB"],
        ]
        sample_bom = [
            ["SK-1001879-01", "GB-Rec M-BLACK"],
        ]
        sample_gated = [
            ["AL1-PKG", "白班", "OUTPUT", "SK-1001879-01", "2026-06-02", 864],
            ["AL1-PKG", "白班", "OUTPUT", "GB-Rec M-BLACK", "2026-06-02", 864],
        ]
        sample_ungated = [
            ["AL1-PKG", "白班", "OUTPUT", "SK-1001879-01", "2026-06-02", 800],
            ["AL1-PKG", "白班", "OUTPUT", "GB-Rec M-BLACK", "2026-06-02", 800],
        ]
        sample_fcst_main = [
            ["1", "SK-1001879-01"],
        ]
        sample_fcst_detail = [
            ["1", "2026-06-02", 1000, "1"],
            ["1", "2026-06-09", 1200, "2"],
        ]
        sample_ctb_sku = [
            ["SK-1001879-01", 1000, 2200],
        ]
        sample_ctb_gb = [
            ["GB-Rec M-BLACK", 1000, 2200],
        ]

    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(SNAPSHOT_TARGET_MAP["item"], _xlsx_buf(item_header, sample_item).getvalue())
        zf.writestr(SNAPSHOT_TARGET_MAP["bom"], _xlsx_buf(bom_header, sample_bom).getvalue())
        zf.writestr(SNAPSHOT_TARGET_MAP["gated"], _xlsx_buf(plan_header, sample_gated).getvalue())
        zf.writestr(SNAPSHOT_TARGET_MAP["ungated"], _xlsx_buf(plan_header, sample_ungated).getvalue())
        zf.writestr(SNAPSHOT_TARGET_MAP["fcst_main"], _xlsx_buf(fcst_main_header, sample_fcst_main).getvalue())
        zf.writestr(SNAPSHOT_TARGET_MAP["fcst_detail"], _xlsx_buf(fcst_detail_header, sample_fcst_detail).getvalue())
        # CTB has 2 sheets
        import openpyxl
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "ctb_sku_cum"
        ws1.append(ctb_header_sku)
        for r in sample_ctb_sku:
            ws1.append(r)
        ws2 = wb.create_sheet("ctb_gb_cum")
        ws2.append(ctb_header_gb)
        for r in sample_ctb_gb:
            ws2.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        zf.writestr(SNAPSHOT_TARGET_MAP["ctb"], buf.getvalue())
    zb.seek(0)
    return zb

def _zip_local_snapshot_demo():
    """
    If data/gated.ungated.ctb exists, zip its files as demo.
    Returns BytesIO or None.
    """
    if not os.path.isdir(SNAPSHOT_DEMO_DIR):
        return None
    files = []
    for fn in SNAPSHOT_TARGET_MAP.values():
        # also check _filled variant for item
        primary = os.path.join(SNAPSHOT_DEMO_DIR, fn)
        if os.path.exists(primary):
            files.append((fn, primary))
        # fallback for item_filled
        if fn == SNAPSHOT_TARGET_MAP["item"]:
            filled = os.path.join(SNAPSHOT_DEMO_DIR, "料号快照_filled.xlsx")
            if os.path.exists(filled) and not os.path.exists(primary):
                files.append((fn, filled))
            # also include filled as extra? Keep primary only
    if not files:
        # try any xlsx in dir
        for f in os.listdir(SNAPSHOT_DEMO_DIR):
            if f.lower().endswith(".xlsx"):
                files.append((f, os.path.join(SNAPSHOT_DEMO_DIR, f)))
    if not files:
        return None
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, fp in files:
            zf.write(fp, arcname=arc)
    zb.seek(0)
    return zb

# ---------- Schema ----------
SNAPSHOT_SCHEMA = {
    "item_snapshot": {
        "file": "料号快照.xlsx",
        "fields": [
            ["ITEM_NO", "String", "Material/ SKU number", "SK-1001879-01"],
            ["STYLE", "String", "Style", "Rectangle M"],
            ["COLOR", "String", "Color", "BLACK"],
            ["PURPOSE", "String", "Usage MP/Dummy", "MP"],
            ["PRODUCT_STYLE", "String", "Style alias", "Rectangle M"],
            ["TYPE", "String", "Type", "FG"],
        ],
        "note": "At least ITEM_NO + STYLE/COLOR/PURPOSE. Used to build sku_attrs.",
    },
    "bom_snapshot": {
        "file": "BOM快照.xlsx",
        "fields": [
            ["PARENT_PN_CODE", "String", "Parent PN (SKU)", "SK-1001879-01"],
            ["ITEM_NO", "String", "Child PN (GB)", "GB-Rec M-BLACK"],
        ],
        "note": "Builds SKU -> GB mapping via BFS.",
    },
    "gated_plan": {
        "file": "gated排产结果表.xlsx",
        "fields": [
            ["LINE_CODE", "String", "Line", "AL1-PKG"],
            ["SHIFT_NAME", "String", "Shift", "白班"],
            ["PLAN_ITEM", "String", "INPUT/OUTPUT/CHECKIN/CHECKOUT, filter OUTPUT", "OUTPUT"],
            ["SKU", "String", "SKU/GB", "SK-1001879-01"],
            ["PLAN_DATE", "Date", "Date", "2026-06-02"],
            ["PLAN_VALUE", "Number", "Qty", "864"],
        ],
        "note": "Filtered PLAN_ITEM=OUTPUT, grouped by SKU+date sum.",
    },
    "ungated_plan": {
        "file": "ungated排产结果表.xlsx",
        "fields": [
            ["LINE_CODE", "String", "Line", "AL1-PKG"],
            ["SHIFT_NAME", "String", "Shift", "白班"],
            ["PLAN_ITEM", "String", "OUTPUT", "OUTPUT"],
            ["SKU", "String", "SKU/GB", "SK-1001879-01"],
            ["PLAN_DATE", "Date", "Date", "2026-06-02"],
            ["PLAN_VALUE", "Number", "Qty", "800"],
        ],
        "note": "Same as gated.",
    },
    "fcst_main": {
        "file": "FCST主表.xlsx",
        "fields": [
            ["ID", "String", "Main ID", "1"],
            ["PN_CODE", "String", "SKU", "SK-1001879-01"],
        ],
        "note": "Groups by ID -> PN_CODE list.",
    },
    "fcst_detail": {
        "file": "FCST明细表.xlsx",
        "fields": [
            ["MAIN_ID", "String", "Link to FCST主表 ID", "1"],
            ["ACTUALFIRSTDAYOFWEEK", "Date", "Week start date", "2026-06-02"],
            ["ACTUALWEEKVALUE", "Number", "Forecast qty", "1000"],
            ["ID", "String", "Detail ID (order matters, sorted desc)", "1"],
        ],
        "note": "For each MAIN_ID+week, rows sorted ID desc assigned to SKUs in main order.",
    },
    "ctb": {
        "file": "CTB.xlsx",
        "fields": [
            ["SKU / PN", "String", "First column SKU or GB PN", "SK-1001879-01"],
            ["2026-06-02", "Number", "Date column cumulative value", "1000"],
        ],
        "note": "2 sheets: ctb_sku_cum and ctb_gb_cum, matrix form, weekly cum values.",
    },
}

# ---------- Template / Demo Routes (IO-style) ----------
@plan_merge_bp.route("/templates/<name>")
def download_template(name):
    # Only schema.json remains as legacy, others redirect to snapshot zip
    if name == "schema.json":
        fp = os.path.join(TEMPLATE_DIR, "schema.json")
        if os.path.exists(fp):
            return send_from_directory(TEMPLATE_DIR, name, as_attachment=True)
        # fallback to generated snapshot schema
        return jsonify(SNAPSHOT_SCHEMA)
    if name in ("input_template.xlsx", "input_demo.xlsx", "snapshot_template.xlsx"):
        # Return snapshot template zip for compatibility
        zb = _zip_snapshot_templates(empty=True)
        return send_file(zb, mimetype="application/zip", as_attachment=True, download_name="snapshot_templates.zip")
    return "Not found", 404

@plan_merge_bp.route("/demo")
@plan_merge_bp.route("/api/demo")
@plan_merge_bp.route("/templates/input_demo.xlsx")
def download_demo():
    # Snapshot demo only
    zb = _zip_local_snapshot_demo()
    if zb:
        return send_file(zb, mimetype="application/zip", as_attachment=True, download_name="snapshot_demo.zip")
    # fallback to sample
    zb = _zip_snapshot_templates(empty=False)
    return send_file(zb, mimetype="application/zip", as_attachment=True, download_name="snapshot_demo.zip")

@plan_merge_bp.route("/api/schema")
def get_schema():
    # Return snapshot schema (like IO)
    legacy_path = os.path.join(TEMPLATE_DIR, "schema.json")
    if os.path.exists(legacy_path):
        try:
            import json
            with open(legacy_path, "r", encoding="utf-8") as f:
                legacy = json.load(f)
            # Merge with snapshot schema for backward compat, but prioritize snapshot
            return jsonify({**SNAPSHOT_SCHEMA, "_legacy": legacy})
        except:
            pass
    return jsonify(SNAPSHOT_SCHEMA)

@plan_merge_bp.route("/templates/zip")
@plan_merge_bp.route("/api/templates/zip")
@plan_merge_bp.route("/api/plan_merge/templates/zip")
def download_all_templates():
    # Snapshot templates zip (empty)
    zb = _zip_snapshot_templates(empty=True)
    return send_file(zb, mimetype="application/zip", as_attachment=True, download_name="snapshot_templates.zip")

@plan_merge_bp.route("/api/plan_merge/templates/template")
def api_template_empty():
    zb = _zip_snapshot_templates(empty=True)
    return send_file(zb, mimetype="application/zip", as_attachment=True, download_name="snapshot_templates.zip")

@plan_merge_bp.route("/api/plan_merge/templates/demo")
@plan_merge_bp.route("/api/plan_merge/templates/snapshot_demo")
def api_demo_zip():
    zb = _zip_local_snapshot_demo()
    if zb:
        return send_file(zb, mimetype="application/zip", as_attachment=True, download_name="snapshot_demo.zip")
    zb = _zip_snapshot_templates(empty=False)
    return send_file(zb, mimetype="application/zip", as_attachment=True, download_name="snapshot_demo.zip")

@plan_merge_bp.route("/api/plan_merge/templates/schema")
def api_schema_new():
    return jsonify(SNAPSHOT_SCHEMA)

@plan_merge_bp.route("/api/plan_merge/templates/input_template.xlsx")
def api_input_template_xlsx():
    # For compatibility, return demo zip with single combined? Keep returning zip
    zb = _zip_snapshot_templates(empty=True)
    return send_file(zb, mimetype="application/zip", as_attachment=True, download_name="snapshot_templates.zip")

# ---------- Core Process Endpoint — Snapshot Only (IO-style upload) ----------
@plan_merge_bp.route("/api/process", methods=["POST"])
def process():
    """
    Snapshot-only upload, IO-report style:
    - Accepts: multiple xlsx, zip, folder (webkitdirectory)
    - Auto-classify by filename keywords (like IO)
    - Validates at least item + bom
    - Processes via process_snapshot_data
    """
    upload_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    work_dir = os.path.join(config.UPLOAD_FOLDER, upload_id)
    os.makedirs(work_dir, exist_ok=True)
    tmp_extract_dir = tempfile.mkdtemp(prefix="pm_extract_")
    try:
        saved_files = []
        # Collect all uploaded files (including multiple under same key)
        all_files = []
        for key in request.files:
            all_files.extend([(key, f) for f in request.files.getlist(key)])

        if not all_files:
            return _json_error("No files uploaded. Expected snapshot files: 料号快照, BOM快照, gated/ungated排产, FCST主表, FCST明细, CTB or zip containing them.", 400)

        pending_regular = []
        for field_key, f in all_files:
            if not f.filename:
                continue
            fname = f.filename
            if _is_zip_file(fname):
                zip_tmp = os.path.join(work_dir, f"_upload_{field_key}_{os.path.basename(fname)}")
                f.save(zip_tmp)
                extracted = _extract_zip_to_tmp(zip_tmp, tmp_extract_dir)
                for ep in extracted:
                    target_name = _classify_snapshot_upload(os.path.basename(ep), os.path.basename(ep))
                    if target_name:
                        dest = os.path.join(tmp_extract_dir, target_name)
                        if os.path.abspath(ep) != os.path.abspath(dest):
                            # avoid overwrite? Keep first
                            if not os.path.exists(dest):
                                shutil.copyfile(ep, dest)
                            # remove temp duplicate
                            try:
                                if os.path.exists(ep) and os.path.abspath(ep) != os.path.abspath(dest):
                                    os.remove(ep)
                            except:
                                pass
                        # will collect later
                    else:
                        pending_regular.append((field_key, ep, True))
                try:
                    os.remove(zip_tmp)
                except:
                    pass
            else:
                # Save to tmp first for classification
                safe_name = os.path.basename(fname)
                if not safe_name:
                    continue
                temp_path = os.path.join(tmp_extract_dir, f"_raw_{field_key}_{safe_name}")
                # handle duplicate
                c = 1
                b, e = os.path.splitext(temp_path)
                while os.path.exists(temp_path):
                    temp_path = f"{b}_{c}{e}"
                    c += 1
                f.save(temp_path)
                pending_regular.append((field_key, temp_path, True))

        # Second pass: classify remaining regular files into work_dir with target names
        for field_key, f_or_path, is_path in pending_regular:
            src_path = f_or_path
            if not os.path.exists(src_path):
                continue
            fname = os.path.basename(src_path)
            # Try classification
            target_filename = _classify_snapshot_upload(fname, field_key)
            # Also try from original field key if not classified
            if not target_filename:
                # If field_key itself is a logical key like item/bom/gated...
                fk_low = (field_key or "").lower()
                if fk_low in SNAPSHOT_TARGET_MAP:
                    target_filename = SNAPSHOT_TARGET_MAP[fk_low]
                elif fk_low in ("master", "schedule", "balance"):
                    # old IO field names, ignore
                    pass

            # Also try detect via content of raw name without _raw_ prefix
            raw_base = fname
            if raw_base.startswith("_raw_"):
                # extract original basename after _raw_<key>_
                parts = raw_base.split("_", 2)
                # Actually _raw_{key}_{orig}
                # We saved as _raw_{field_key}_{safe_name}, so original is after second _
                # For simplicity, try classify original safe_name
                orig = "_".join(raw_base.split("_")[2:]) if "_" in raw_base else raw_base
                if not target_filename:
                    target_filename = _classify_snapshot_upload(orig, field_key)

            if target_filename:
                dest = os.path.join(tmp_extract_dir, target_filename)
                # If dest exists, keep existing (first wins) unless it's a _raw_ file
                if not os.path.exists(dest):
                    shutil.copyfile(src_path, dest)
                # else merge? For now keep first

        # Also collect loose files that were already classified in first loop (they are in tmp_extract_dir with target names)
        # Build file list for detection
        final_files = []
        for root, _, files in os.walk(tmp_extract_dir):
            for fn in files:
                if fn.startswith("_raw_") or fn.startswith("_upload_"):
                    continue
                fp = os.path.join(root, fn)
                if os.path.isfile(fp):
                    final_files.append(fp)

        if not final_files:
            existing = os.listdir(tmp_extract_dir)
            return _json_error(f"Missing snapshot files. Got {existing}. Need at least 料号快照.xlsx and BOM快照.xlsx, plus gated/ungated/CTB/FCST. Hint: upload 7 files or zip.", 400)

        # Detect mapping using existing helper (supports both naming)
        file_map = detect_snapshot_files(final_files)

        # If detection still misses some because filename is target name, ensure we map by target name
        for fp in final_files:
            base = os.path.basename(fp)
            for key, target in SNAPSHOT_TARGET_MAP.items():
                if base == target and key not in file_map:
                    file_map[key] = fp

        # Validation: at least item + bom
        missing_required = []
        if "item" not in file_map:
            missing_required.append(SNAPSHOT_TARGET_MAP["item"])
        if "bom" not in file_map:
            missing_required.append(SNAPSHOT_TARGET_MAP["bom"])

        if missing_required:
            existing_names = [f"{os.path.basename(p)} ({os.path.getsize(p)} bytes, {round(os.path.getsize(p)/1024,1)}KB)" for p in final_files]
            detected_list = []
            for k, v in file_map.items():
                try:
                    sz = os.path.getsize(v)
                    detected_list.append(f"{k}:{os.path.basename(v)}({round(sz/1024,1)}KB)")
                except:
                    detected_list.append(f"{k}:{os.path.basename(v)}")
            return _json_error(
                f"Missing required files {missing_required}. Detected {len(file_map)} files: {', '.join(detected_list)}. All uploaded files: {existing_names}. Need at least 料号快照.xlsx and BOM快照.xlsx. Optional: gated/ungated/FCST/CTB will be empty if not provided. Tip: Ensure filenames contain keywords like 料号, BOM, gated, ungated, FCST, CTB or use exact names {list(SNAPSHOT_TARGET_MAP.values())}.",
                400,
            )

        # Additional validation: ensure each file in file_map is valid xlsx (PK header) and readable by openpyxl
        invalid_files = []
        for key, fp in file_map.items():
            if not os.path.exists(fp):
                invalid_files.append(f"{key}={os.path.basename(fp)} not found")
                continue
            sz = os.path.getsize(fp)
            if sz == 0:
                invalid_files.append(f"{key}={os.path.basename(fp)} empty 0 bytes")
                continue
            if not _is_valid_xlsx_by_content(fp):
                # Try to see if it's actually a zip containing xlsx (user uploaded zip with .xlsx extension)
                try:
                    with zipfile.ZipFile(fp, 'r') as zf:
                        # If it's a zip, try to extract its xlsx files into tmp dir and update file_map
                        print(f"[PlanMerge] {key} file {os.path.basename(fp)} is actually a zip, extracting...")
                        extra = _extract_zip_to_tmp(fp, tmp_extract_dir)
                        # Re-classify extracted
                        for ep in extra:
                            tname = _classify_snapshot_upload(os.path.basename(ep), os.path.basename(ep))
                            if tname:
                                dest = os.path.join(tmp_extract_dir, tname)
                                if not os.path.exists(dest):
                                    shutil.copyfile(ep, dest)
                        # After extraction, try to find the real file for this key
                        # For simplicity, if we extracted and file_map key still points to zip, we need to replace
                        # Look for file with same key in tmp_extract_dir
                        for root, _, files in os.walk(tmp_extract_dir):
                            for fn in files:
                                if fn.startswith("_raw_") or fn.startswith("_upload_"):
                                    continue
                                full = os.path.join(root, fn)
                                if _classify_to_key(fn, fn) == key or os.path.basename(full) == SNAPSHOT_TARGET_MAP.get(key, ''):
                                    file_map[key] = full
                                    break
                except Exception as ze:
                    invalid_files.append(f"{key}={os.path.basename(fp)} not valid xlsx (size {sz} bytes, not PK header, zip check failed: {ze})")
                    continue
            # Try openpyxl open to validate – if fails, it's definitely not a valid xlsx
            try:
                import openpyxl
                wb = openpyxl.load_workbook(fp, read_only=True, data_only=True)
                wb.close()
            except Exception as oe:
                # If openpyxl fails, treat as invalid xlsx
                oe_str = str(oe)
                if "no item named '[Content_Types].xml'" in oe_str.lower() or "file is not a zip file" in oe_str.lower() or "not a zip file" in oe_str.lower():
                    invalid_files.append(f"{key}={os.path.basename(fp)} invalid xlsx (openpyxl: {oe}) – file may be a zip containing non-xlsx, or corrupted, or .xls old format. Try re-saving as .xlsx")
                else:
                    invalid_files.append(f"{key}={os.path.basename(fp)} failed openpyxl validation: {oe}")
                continue

        if invalid_files:
            all_files_info = [f"{os.path.basename(p)} ({os.path.getsize(p)} bytes, {round(os.path.getsize(p)/1024,1)}KB) – {p}" for p in final_files]
            detected_info = [f"{k}:{os.path.basename(v)} ({round(os.path.getsize(v)/1024,1)}KB)" for k, v in file_map.items() if os.path.exists(v)]
            return _json_error(
                f"Invalid snapshot files detected: {invalid_files}. Detected files: {detected_info}. All uploaded: {all_files_info}. Please ensure all files are valid .xlsx (not 0 bytes, not corrupted, not .xls, not truncated). If you uploaded a zip, ensure it contains xlsx files. Tip: Try re-saving files as .xlsx in Excel, check file sizes, or upload via zip. For truncated files (EOFError), re-upload and ensure network completes.",
                400,
            )

        cfg = {}
        for cfg_key in ["exf_cut", "etd_cut", "output_cut", "gb_cut", "etd_packout_offset"]:
            val = request.form.get(cfg_key)
            if val:
                cfg[cfg_key] = val

        # Process snapshot
        try:
            result = process_snapshot_data(file_map, cfg)
            warnings = result.get("warnings", [])
            warnings.insert(
                0,
                f"✅ Snapshot mode: detected {len(file_map)} files — {', '.join([os.path.basename(v) for v in file_map.values()])}",
            )
            result["warnings"] = warnings
            result["mode"] = "snapshot"
            result["files"] = {k: f"{os.path.basename(v)} ({os.path.getsize(v)} bytes)" for k, v in file_map.items()}
            return jsonify(result)
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            print(f"[PlanMerge] Processing failed: {e}\n{tb_str}")
            # Return detailed error with file list for debugging
            file_info = {k: f"{os.path.basename(v)} ({os.path.getsize(v)} bytes)" for k, v in file_map.items()}
            return _json_error(f"Processing failed: {e}\nFiles: {file_info}\nTrace: {tb_str[:2000]}", 500)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(str(e), 500)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        shutil.rmtree(tmp_extract_dir, ignore_errors=True)


@plan_merge_bp.route("/api/process/snapshot", methods=["POST"])
def process_snapshot():
    # Same as /api/process, snapshot only (for explicit endpoint)
    return process()


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


@plan_merge_bp.route("/api/plan_merge/clear", methods=["POST", "DELETE"])
@plan_merge_bp.route("/api/clear", methods=["POST", "DELETE"])
def api_clear():
    """Clear Packout (ExF vs ETD vs Packout vs CTB) cache — frontend will reset UI, backend is stateless"""
    return jsonify(
        {
            "ok": True,
            "message": "Cleared Packout data — now Not Ready, re-upload supported (snapshot only)",
        }
    )


@plan_merge_bp.route("/api/plan_merge/export/static", methods=["GET", "POST"])
@plan_merge_bp.route("/api/export/static", methods=["GET", "POST"])
def api_export_static():
    """Export current Packout dashboard as static HTML with embedded data and flexible filtering"""
    try:
        import json
        import datetime

        data = None
        if request.method == "POST":
            data = request.get_json()
        # If no data posted, try to use snapshot demo folder to generate data
        if not data or not data.get("rows"):
            # Try to process snapshot demo if available
            demo_dir = Path(SNAPSHOT_DEMO_DIR)
            if demo_dir.exists():
                # Collect files
                demo_files = []
                for fn in SNAPSHOT_TARGET_MAP.values():
                    fp = demo_dir / fn
                    if fp.exists():
                        demo_files.append(str(fp))
                if demo_files:
                    from app.modules.plan_merge.snapshot_parser import detect_snapshot_files as _detect
                    from app.modules.plan_merge.engine import process_snapshot_data as _proc_snap
                    file_map = _detect(demo_files)
                    if "item" in file_map and "bom" in file_map:
                        try:
                            data = _proc_snap(file_map, {})
                        except Exception as e:
                            print(f"Export static: failed to process demo snapshot: {e}")
            # Fallback to empty? Return error if still no data
            if not data or not data.get("rows"):
                return jsonify({"error": "No data to export. Upload snapshot files first or POST rows/weeks"}), 404

        rows = data.get("rows", [])[:2000]
        weeks = data.get("weeks", [])
        week_labels = data.get("week_labels", {}) or data.get("weekLabels", {})
        config = data.get("config", {})

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        static_json = json.dumps(
            {"rows": rows, "weeks": weeks, "week_labels": week_labels, "config": config},
            ensure_ascii=False,
            default=str,
        ).replace("<", "\\u003c")

        html_content = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Packout Report - Static BI - {now_str}</title>
<style>
body{{font-family:Arial,sans-serif;margin:16px;background:#f8fafc}}
h1{{font-size:18px;color:#1e293b}}
.sub{{font-size:11px;color:#64748b;margin-bottom:8px}}
.status{{margin:10px 0;padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px}}
.tabs{{display:flex;gap:6px;margin:10px 0;flex-wrap:wrap}}
.tab{{padding:6px 12px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;cursor:pointer;font-size:12px}}
.tab.active{{background:#3b82f6;color:#fff;border-color:#3b82f6}}
.filters{{background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px;margin:10px 0;display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}}
.filter-group{{display:flex;flex-direction:column;gap:4px;min-width:140px}}
.filter-group label{{font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase}}
.filter-group input{{padding:5px 8px;border:1px solid #cbd5e1;border-radius:5px;font-size:12px}}
.btn{{padding:5px 12px;border:1px solid #3b82f6;background:#3b82f6;color:#fff;border-radius:5px;font-size:12px;cursor:pointer}}
.btn-outline{{background:#fff;color:#64748b;border-color:#cbd5e1}}
.table-wrapper{{overflow:auto;border:1px solid #e2e8f0;border-radius:6px;background:#fff;max-height:80vh}}
table{{border-collapse:collapse;font-size:12px;white-space:nowrap;width:max-content;min-width:100%}}
th{{background:#1e293b;color:#fff;padding:6px 8px;position:sticky;top:0;z-index:2}}
td{{padding:4px 6px;border-bottom:1px solid #e2e8f0;border-right:1px solid #f1f5f9;text-align:right;min-width:70px}}
td.frozen{{position:sticky;left:0;background:#fff;z-index:1;text-align:left;font-weight:500}}
</style></head><body>
<h1>📦 ExF vs ETD vs Packout vs CTB — Static BI Report (Snapshot Only)</h1>
<div class="sub">Generated: {now_str} | Export via /api/plan_merge/export/static | Rows: {len(rows)} | Weeks: {len(weeks)} | Flexible filtering works offline | Snapshot-only mode</div>
<div class="status" id="static-status">✅ Ready: {len(rows)} rows | Config: {config}</div>
<div class="tabs" id="dimTabs"><button class="tab active" data-dim="FG">FG (SKU)</button><button class="tab" data-dim="GB">GB</button><button class="tab" data-dim="ALL">All</button></div>
<div class="filters">
  <div class="filter-group"><label>Search PN / Usage / Style / Color / Type / Detail</label><input type="text" id="f-search" placeholder="e.g. PN123, Usage..."></div>
  <div class="filter-group"><label>Version-Type</label><input type="text" id="f-vtype" placeholder="ExF, Gated, Ungated, CTB"></div>
  <div class="filter-group"><label>&nbsp;</label><div><button class="btn" id="f-apply">Apply</button> <button class="btn btn-outline" id="f-clear">Clear</button> <span id="f-count" style="font-size:11px;color:#64748b"></span></div></div>
</div>
<div class="table-wrapper" id="static-wrapper"></div>
<div style="margin-top:12px;font-size:10px;color:#94a3b8">Static BI report from Packout dashboard (snapshot-only). All format and filtering preserved. Data embedded at export time. Open directly and share.</div>
<script>
const STATIC_DATA = {static_json};
let curDim = 'FG';
function esc(s){{ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }}
function renderTable(){{
  const rows = STATIC_DATA.rows || [];
  const weeks = STATIC_DATA.weeks || [];
  const weekLabels = STATIC_DATA.week_labels || {{}};
  let filtered = rows;
  const search = (document.getElementById('f-search').value||'').toLowerCase();
  const vtype = (document.getElementById('f-vtype').value||'').toLowerCase();
  if(curDim!=='ALL'){{ filtered = filtered.filter(r=> (r._dim||'').toUpperCase()===curDim); }}
  if(search){{ filtered = filtered.filter(r=> JSON.stringify(r).toLowerCase().includes(search)); }}
  if(vtype){{ filtered = filtered.filter(r=> (r['Version-Type']||'').toLowerCase().includes(vtype) || JSON.stringify(r).toLowerCase().includes(vtype)); }}
  let html = '<table><thead><tr>';
  const fixed = ['_dim','PN','Usage','Style','Color','Version-Type','Version-Detail','Cut Day','Pallet_Qty'];
  fixed.forEach(k=>{{ html += '<th class="frozen" style="min-width:80px">'+esc(k)+'</th>'; }});
  weeks.forEach(w=>{{ html += '<th>'+esc(weekLabels[w]||w)+'</th>'; }});
  html += '</tr></thead><tbody>';
  filtered.slice(0,1000).forEach(r=>{{
    html += '<tr>';
    fixed.forEach(k=>{{ html += '<td class="frozen">'+esc(String(r[k]||''))+'</td>'; }});
    weeks.forEach(w=>{{ const v=r[w]; html += '<td>'+(v!=null?Number(v).toLocaleString():'')+'</td>'; }});
    html += '</tr>';
  }});
  if(filtered.length>1000) html += '<tr><td colspan="999" style="text-align:center;color:#94a3b8">... '+filtered.length+' total rows, showing first 1000 ...</td></tr>';
  html += '</tbody></table>';
  document.getElementById('static-wrapper').innerHTML = html;
  document.getElementById('f-count').textContent = filtered.length+' / '+rows.length+' rows';
}}
document.querySelectorAll('#dimTabs .tab').forEach(b=>{{ b.addEventListener('click', ()=>{{ document.querySelectorAll('#dimTabs .tab').forEach(x=>x.classList.remove('active')); b.classList.add('active'); curDim=b.dataset.dim; renderTable(); }}); }});
document.getElementById('f-apply')?.addEventListener('click', renderTable);
document.getElementById('f-clear')?.addEventListener('click', ()=>{{ document.getElementById('f-search').value=''; document.getElementById('f-vtype').value=''; curDim='ALL'; document.querySelectorAll('#dimTabs .tab').forEach(b=>b.classList.remove('active')); document.querySelector('#dimTabs .tab[data-dim="ALL"]')?.classList.add('active'); renderTable(); }});
document.getElementById('f-search')?.addEventListener('input', renderTable);
document.getElementById('f-vtype')?.addEventListener('input', renderTable);
renderTable();
</script>
</body></html>"""

        from flask import Response

        return Response(
            html_content,
            mimetype="text/html",
            headers={
                "Content-Disposition": f"attachment; filename=packout_static_BI_snapshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            },
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"error": f"Export static failed: {e}"}), 500


# ---------- Extended status for snapshot (optional) ----------
@plan_merge_bp.route("/api/plan_merge/status", methods=["GET"])
def api_status():
    # Stateless, but report if demo data exists
    demo_exists = os.path.isdir(SNAPSHOT_DEMO_DIR)
    count = 0
    if demo_exists:
        count = sum(1 for fn in os.listdir(SNAPSHOT_DEMO_DIR) if fn.lower().endswith(".xlsx"))
    return jsonify(
        {
            "loaded": False,
            "mode": "snapshot-only",
            "snapshot_target_map": SNAPSHOT_TARGET_MAP,
            "demo_dir_exists": demo_exists,
            "demo_files": count,
            "note": "Snapshot-only: upload 7 files (料号快照, BOM快照, gated, ungated, FCST主, FCST明细, CTB) or zip",
        }
    )
