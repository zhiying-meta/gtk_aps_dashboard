import io
import os
import shutil
import tempfile
import zipfile

from flask import jsonify, request, send_file

from app.modules.io_report.engine import build_reports_for_group, get_cache, get_meta, reload_cache
from app.modules.io_report import io_bp
from app.common.zip_handler import is_zip_file as _common_is_zip, extract_all_xlsx as _common_extract_all
from app.common.template_builder import xlsx_buf as _common_xlsx_buf, zip_files as _common_zip_files
from app.common.xlsx_validator import is_valid_xlsx_by_content

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
    try:
        cache = get_cache(DEFAULT_DATA_DIR)
        base = {
            "loaded": loaded,
            "ok": loaded,
            "fg": len(cache.fg_items) if loaded else 0,
            "gb": len(cache.gb_items) if loaded else 0,
            "fg_sched": len(cache.sched_fg) if loaded else 0,
            "gb_sched": len(cache.sched_gb) if loaded else 0,
        }
        # extended cats
        if loaded and getattr(cache, 'cats', None):
            for cat in cache.cats:
                safe = cat.replace('成品', 'FG')
                base[f"count_{safe}"] = len(cache.items_by_cat.get(cat, []))
                base[f"sched_{safe}"] = len(cache.sched_by_cat.get(cat, []))
                base[f"bal_{safe}"] = len(cache.bal_by_cat.get(cat, []))
            base["cats"] = cache.cats
            base["items_by_cat"] = {k: len(v) for k, v in cache.items_by_cat.items()}
        return jsonify(base)
    except Exception:
        return jsonify({"loaded": loaded, "ok": loaded, "fg": 0, "gb": 0})


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


def _is_zip_file(filename: str) -> bool:
    return _common_is_zip(filename)


def _extract_zip_to_tmp(zip_path: str, tmp_dir: str):
    return _common_extract_all(zip_path, tmp_dir)


def _try_split_combined_xlsx(xlsx_path: str, tmp_dir: str) -> bool:
    """
    If xlsx is a combined file with 3 sheets (Item Master / Schedule / Balance),
    split into 3 separate files matching TARGET_MAP.
    Returns True if split succeeded.
    """
    try:
        import openpyxl

        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        sheet_names = [s.lower() for s in wb.sheetnames]
        # Map possible sheet name patterns to target
        # Look for sheets that contain relevant keywords
        def find_sheet(keywords):
            for idx, sn in enumerate(wb.sheetnames):
                low = sn.lower()
                for kw in keywords:
                    if kw in low or kw in sn:
                        return sn
            return None

        master_sheet = find_sheet(["item master", "料号主表", "master", "item_master", "料号"])
        sched_sheet = find_sheet(["schedule", "排产结果", "排产", "schedule_result", "sched"])
        bal_sheet = find_sheet(["balance", "boh", "结存", "结存表", "boh_balance", "balance_qty"])

        # If we found at least 2 of them, or if file has exactly 3 sheets and we can guess, split
        # Heuristic: if we have 3 sheets, assume order = master, schedule, balance
        if not (master_sheet and sched_sheet and bal_sheet):
            if len(wb.sheetnames) >= 3:
                # try to use sheet order as fallback
                # Check if sheets have expected headers
                # For now, if we have 3 sheets, try to map by header
                for sn in wb.sheetnames:
                    try:
                        ws = wb[sn]
                        headers = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
                        # print(f"sheet {sn} headers {headers}")
                        if "ITEM_NO" in headers and "PRODUCT_CATEGORY" in headers:
                            master_sheet = sn
                        elif "LINE_CODE" in headers and "PLAN_ITEM" in headers:
                            sched_sheet = sn
                        elif "ITEM_CODE" in headers and "BALANCE_QTY" in headers:
                            bal_sheet = sn
                    except Exception:
                        continue
        wb.close()

        if not (master_sheet and sched_sheet and bal_sheet):
            return False

        # Now split - reopen to copy sheets
        wb = openpyxl.load_workbook(xlsx_path, data_only=False)
        # Master
        if master_sheet in wb.sheetnames:
            ws = wb[master_sheet]
            out_wb = openpyxl.Workbook()
            out_ws = out_wb.active
            for row in ws.iter_rows(values_only=True):
                out_ws.append(list(row) if row else [])
            out_wb.save(os.path.join(tmp_dir, TARGET_MAP["master"]))
        # Schedule
        if sched_sheet in wb.sheetnames:
            ws = wb[sched_sheet]
            out_wb = openpyxl.Workbook()
            out_ws = out_wb.active
            for row in ws.iter_rows(values_only=True):
                out_ws.append(list(row) if row else [])
            out_wb.save(os.path.join(tmp_dir, TARGET_MAP["schedule"]))
        # Balance
        if bal_sheet in wb.sheetnames:
            ws = wb[bal_sheet]
            out_wb = openpyxl.Workbook()
            out_ws = out_wb.active
            for row in ws.iter_rows(values_only=True):
                out_ws.append(list(row) if row else [])
            out_wb.save(os.path.join(tmp_dir, TARGET_MAP["balance"]))
        wb.close()
        return True
    except Exception as e:
        print(f"[IO] split combined xlsx failed: {e}")
        import traceback
        traceback.print_exc()
        return False


@io_bp.route("/api/io/upload", methods=["POST"])
def api_upload():
    if not request.files:
        return _json_error("expected multipart with master/schedule/balance", 400)

    tmp_dir = tempfile.mkdtemp(prefix="io_upload_")
    try:
        # Collect all files (including multiple under same key)
        all_files = []
        for key in request.files:
            all_files.extend([(key, f) for f in request.files.getlist(key)])

        # First pass: handle zip and combined xlsx
        pending_regular = []
        for field_key, f in all_files:
            if not f.filename:
                continue
            fname = f.filename
            if _is_zip_file(fname):
                # save zip to tmp and extract
                zip_tmp = os.path.join(tmp_dir, f"_upload_{field_key}_{fname}")
                f.save(zip_tmp)
                extracted = _extract_zip_to_tmp(zip_tmp, tmp_dir)
                # classify extracted files
                for ep in extracted:
                    target = _classify_upload(os.path.basename(ep), os.path.basename(ep))
                    if target:
                        # already in tmp_dir with basename, need to move to target name
                        dest = os.path.join(tmp_dir, target)
                        if os.path.abspath(ep) != os.path.abspath(dest):
                            shutil.copyfile(ep, dest)
                    else:
                        # try to keep as is, will be classified later
                        pending_regular.append((field_key, ep, True))  # True = is path
                # remove zip tmp
                try:
                    os.remove(zip_tmp)
                except:
                    pass
            else:
                # check if it's a potential combined xlsx
                # save to temp first
                temp_path = os.path.join(tmp_dir, f"_raw_{field_key}_{fname}")
                f.save(temp_path)
                # Try to detect combined - if it has 3 sheets with expected headers, split
                # Only attempt if file hasn't been classified yet or if it's named as combined
                is_combined = False
                # Heuristic: filename contains "combined" or "io_template" or has more than 2 sheets with matching headers
                # We'll try split for any xlsx that hasn't been classified as one of the 3
                # Try split first
                if _try_split_combined_xlsx(temp_path, tmp_dir):
                    is_combined = True
                    # remove raw temp
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                if not is_combined:
                    pending_regular.append((field_key, temp_path, True))

        # Second pass: classify remaining regular files
        for field_key, f_or_path, is_path in pending_regular:
            if is_path:
                # f_or_path is a path
                src_path = f_or_path
                fname = os.path.basename(src_path)
                target = _classify_upload(fname, field_key)
                if not target and field_key in TARGET_MAP:
                    target = TARGET_MAP[field_key]
                if target:
                    dest = os.path.join(tmp_dir, target)
                    if os.path.abspath(src_path) != os.path.abspath(dest):
                        shutil.copyfile(src_path, dest)
                else:
                    # if still not classified, keep file as is and try to guess later
                    # Leave it, will be counted as existing if matches target name already
                    pass
            else:
                # Should not happen, but handle file object
                f = f_or_path
                target = _classify_upload(f.filename, field_key)
                if not target and field_key in TARGET_MAP:
                    target = TARGET_MAP[field_key]
                if target:
                    f.save(os.path.join(tmp_dir, target))

        # Also handle any files that were directly saved with target names via classification in first loop
        # Ensure we have the 3 required files (try to find any file that matches keywords even if not exactly named)
        for existing_file in os.listdir(tmp_dir):
            if existing_file.startswith("_raw_") or existing_file.startswith("_upload_"):
                continue
            full = os.path.join(tmp_dir, existing_file)
            if not os.path.isfile(full):
                continue
            # If file is already one of target names, keep
            if existing_file in TARGET_MAP.values():
                continue
            # Try to classify loose files
            target = _classify_upload(existing_file, existing_file)
            if target and not os.path.exists(os.path.join(tmp_dir, target)):
                shutil.copyfile(full, os.path.join(tmp_dir, target))

        # ensure all 3 present
        missing = [fn for fn in TARGET_MAP.values() if not os.path.exists(os.path.join(tmp_dir, fn))]
        if missing:
            existing = [f for f in os.listdir(tmp_dir) if not f.startswith("_raw_") and not f.startswith("_upload_")]
            return _json_error(f"missing files {missing}, got {existing}. Hint: upload 3 separate files, or a zip containing them, or a single combined xlsx with 3 sheets (Item Master/Schedule Result/BOH Balance).", 400)

        # validate data before overwriting real data dir
        try:
            from app.modules.io_report.engine import load_data as _load_tmp

            tmp_cache = _load_tmp(tmp_dir)
            total_items = len(tmp_cache.fg_items) + len(tmp_cache.gb_items)
            total_sched = len(tmp_cache.sched_fg) + len(tmp_cache.sched_gb)
            if total_items == 0:
                return _json_error(
                    f"validation failed: 0 FG/GB items found. Check 料号主表.xlsx has PRODUCT_CATEGORY=成品/GB and ITEM_NO column.",
                    400,
                )
            if total_sched == 0:
                return _json_error(
                    f"validation failed: 0 schedule rows. Check 排产结果表.xlsx has LINE_CODE, PLAN_ITEM (INPUT/OUTPUT/CHECKIN/CHECKOUT), SKU, PLAN_DATE, PLAN_VALUE and SKU exists in master.",
                    400,
                )
        except Exception as ve:
            import traceback

            traceback.print_exc()
            return _json_error(f"validation failed: {ve}", 400)

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


# ---------- clear ----------
@io_bp.route("/api/io/clear", methods=["POST", "DELETE"])
def api_clear():
    """Clear IO report cache and data files — similar to utilization clear, supports re-upload"""
    try:
        import pathlib
        base_path = pathlib.Path(DEFAULT_DATA_DIR)
        cleared = []
        for fn in TARGET_MAP.values():
            fp = base_path / fn
            if fp.exists():
                try:
                    fp.unlink()
                    cleared.append(fn)
                except Exception as e:
                    print(f"[IO] clear file failed {fp}: {e}")
        # Also clear any cache files if present
        for cache_file in base_path.glob("*.pkl"):
            try:
                cache_file.unlink()
            except:
                pass
        # Clear in-memory cache — _global_cache is the main cache
        try:
            import app.modules.io_report.engine as eng
            eng._global_cache = None
            eng._global_data_dir = None
        except Exception as ce:
            print(f"[IO] clear cache failed: {ce}")

        return jsonify({
            "ok": True,
            "cleared": cleared,
            "message": f"Cleared {', '.join(cleared) if cleared else 'no files (already empty)'} — now Not Ready, re-upload supported"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(f"Clear failed: {e}")


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
    return _common_xlsx_buf(header, rows)


def _zip_io(empty=True):
    master_header = ["ITEM_NO", "PRODUCT_CATEGORY", "PRODUCT_STYLE"]
    sched_header = ["LINE_CODE", "SHIFT_NAME", "PLAN_ITEM", "SKU", "PLAN_DATE", "PLAN_VALUE"]
    bal_header = ["PLAN_DATE", "SHIFT_NAME", "ITEM_CODE", "BALANCE_QTY"]

    if empty:
        sample_master = []
        sample_sched = []
        sample_bal = []
    else:
        sample_master = [
            ["FG001", "成品", "Style-A"],
            ["FG002", "成品", "Style-B"],
            ["GB001", "GB", "Style-A"],
            ["GB002", "GB", "Style-B"],
        ]
        sample_sched = [
            ["Line01", "白班", "INPUT", "FG001", "2024-06-01", 100],
            ["Line01", "白班", "OUTPUT", "FG001", "2024-06-01", 90],
            ["Line01", "白班", "CHECKIN", "FG001", "2024-06-01", 95],
            ["Line01", "白班", "CHECKOUT", "FG001", "2024-06-01", 85],
            ["Line02", "夜班", "INPUT", "FG002", "2024-06-01", 120],
            ["Line02", "夜班", "OUTPUT", "FG002", "2024-06-01", 110],
            ["Line02", "夜班", "CHECKIN", "FG002", "2024-06-01", 115],
            ["Line02", "夜班", "CHECKOUT", "FG002", "2024-06-01", 105],
            ["Line01", "白班", "INPUT", "GB001", "2024-06-01", 200],
            ["Line01", "白班", "OUTPUT", "GB001", "2024-06-01", 190],
            ["Line01", "白班", "CHECKIN", "GB001", "2024-06-01", 195],
            ["Line01", "白班", "CHECKOUT", "GB001", "2024-06-01", 185],
        ]
        sample_bal = [
            ["2024-06-01", "白班", "FG001", 500],
            ["2024-06-01", "白班", "FG002", 600],
            ["2024-06-01", "白班", "GB001", 1000],
        ]

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


@io_bp.route("/api/io/export/static", methods=["GET"])
def api_io_export_static():
    """Export current IO report dashboard as static HTML with embedded data and flexible filtering (like campus-planning-system/frontend/dist) — called when clicking Download Static HTML button"""
    try:
        import json
        import datetime
        from app.modules.io_report.engine import get_cache, build_reports_for_group, get_meta
        try:
            cache = get_cache(DEFAULT_DATA_DIR)
        except Exception as e:
            return _json_error(f"No data to export: {e}", 404)

        # Build embedded data for all groups and col_dims for full BI offline
        groups = ['FG','GB','FR','LT','RT']
        col_dims = ['shift','day','week','month']
        embedded = {"groups": {}, "status": {"loaded": True, "fg": len(cache.fg_items), "gb": len(cache.gb_items), "cats": cache.cats}}

        for g in groups:
            embedded["groups"][g] = {}
            for cd in col_dims:
                try:
                    meta = get_meta(cache, g, cd)
                    reports_line, _ = build_reports_for_group(cache, 'LINE_CODE', cd, g, '', '', '')
                    reports_pn, _ = build_reports_for_group(cache, 'ITEM_NO', cd, g, '', '', '')
                    reports_style, _ = build_reports_for_group(cache, 'STYLE', cd, g, '', '', '')
                    embedded["groups"][g][cd] = {
                        "meta": {"line_codes": meta.get("line_codes", [])[:100], "items": meta.get("items", [])[:100], "styles": meta.get("styles", [])[:50]},
                        "reportsLine": {k: {"columns": v.get("columns", [])[:20], "rows": v.get("rows", [])[:200]} for k,v in reports_line.items() if isinstance(v, dict) and "columns" in v},
                        "reportsPN": {k: {"columns": v.get("columns", [])[:20], "rows": v.get("rows", [])[:200]} for k,v in reports_pn.items() if isinstance(v, dict) and "columns" in v},
                        "reportsStyle": {k: {"columns": v.get("columns", [])[:20], "rows": v.get("rows", [])[:200]} for k,v in reports_style.items() if isinstance(v, dict) and "columns" in v},
                    }
                except Exception:
                    continue

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        static_json = json.dumps(embedded, ensure_ascii=False, default=str).replace("<", "\\u003c")

        html_content = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>I/O Report - Static BI - {now_str}</title>
<style>
body{{font-family:Arial,sans-serif;margin:16px;background:#f8fafc}}
h1{{font-size:18px;color:#1e293b}}
.sub{{font-size:11px;color:#64748b;margin-bottom:8px}}
.status{{margin:10px 0;padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px}}
.tabs{{display:flex;gap:6px;margin:10px 0;flex-wrap:wrap}}
.tab{{padding:6px 12px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;cursor:pointer;font-size:12px}}
.tab.active{{background:#3b82f6;color:#fff;border-color:#3b82f6}}
.filters{{background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px;margin:10px 0;display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}}
.filter-group{{display:flex;flex-direction:column;gap:4px;min-width:140px}}
.filter-group label{{font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase}}
.filter-group input{{padding:5px 8px;border:1px solid #cbd5e1;border-radius:5px;font-size:12px}}
.btn{{padding:5px 12px;border:1px solid #3b82f6;background:#3b82f6;color:#fff;border-radius:5px;font-size:12px;cursor:pointer}}
.btn-outline{{background:#fff;color:#64748b;border-color:#cbd5e1}}
.table-wrapper{{overflow:auto;border:1px solid #e2e8f0;border-radius:6px;background:#fff;margin-top:12px;max-height:70vh}}
table{{border-collapse:collapse;font-size:12px;white-space:nowrap;width:max-content;min-width:100%}}
th{{background:#1e293b;color:#fff;padding:6px 8px;position:sticky;top:0;z-index:2}}
td{{padding:4px 6px;border-bottom:1px solid #e2e8f0;border-right:1px solid #f1f5f9;text-align:right}}
td.frozen{{position:sticky;left:0;background:#fff;z-index:1;text-align:left;font-weight:500}}
</style></head><body>
<h1>📈 I/O Report — Static BI Report (Full Format & Filtering Preserved)</h1>
<div class="sub">Generated: {now_str} | Export via /api/io/export/static (calls export_static logic) | All groups (FG/GB/FR/LT/RT) and flexible dims embedded</div>
<div class="status" id="static-status"></div>
<div class="tabs" id="groupTabs"><button class="tab active" data-group="FG">FG</button><button class="tab" data-group="GB">GB</button><button class="tab" data-group="FR">FR</button><button class="tab" data-group="LT">LT</button><button class="tab" data-group="RT">RT</button></div>
<div class="tabs" id="colDimTabs"><button class="tab active" data-coldim="day">Day</button><button class="tab" data-coldim="shift">Shift</button><button class="tab" data-coldim="week">Week</button><button class="tab" data-coldim="month">Month</button></div>
<div class="tabs" id="rowDimTabs"><button class="tab active" data-rowdim="LINE_CODE">Line</button><button class="tab" data-rowdim="ITEM_NO">PN</button><button class="tab" data-rowdim="STYLE">Style</button></div>
<div class="filters">
  <div class="filter-group"><label>Search Line</label><input type="text" id="f-line" placeholder="Line filter"></div>
  <div class="filter-group"><label>Search PN</label><input type="text" id="f-pn" placeholder="PN filter"></div>
  <div class="filter-group"><label>Search Style</label><input type="text" id="f-style" placeholder="Style filter"></div>
  <div class="filter-group"><label>Search Any</label><input type="text" id="f-search" placeholder="Any text"></div>
  <div class="filter-group"><label>&nbsp;</label><div><button class="btn" id="f-apply">Apply</button> <button class="btn btn-outline" id="f-clear">Clear</button> <span id="f-count" style="font-size:11px;color:#64748b"></span></div></div>
</div>
<div id="static-all-content"></div>
<div style="margin-top:12px;font-size:10px;color:#94a3b8">Static BI report from I/O dashboard via export_static. All tabs (FG/GB/FR/LT/RT) and flexible dims (Line/PN/Style, Column Shift/Day/Week/Month) preserved with embedded numbers. Exported via /api/io/export/static.</div>
<script>
const STATIC_DATA = {static_json};
let curGroup = 'FG';
let curColDim = 'day';
let curRowDim = 'LINE_CODE';
function esc(s){{ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }}
function renderReports(){{
  const groupData = STATIC_DATA.groups[curGroup] && STATIC_DATA.groups[curGroup][curColDim];
  if(!groupData){{ document.getElementById('static-all-content').innerHTML='<div style="text-align:center;padding:20px;color:#94a3b8">No data for '+curGroup+' / '+curColDim+'</div>'; return; }}
  let reportsData;
  if(curRowDim==='ITEM_NO') reportsData = groupData.reportsPN;
  else if(curRowDim==='STYLE') reportsData = groupData.reportsStyle;
  else reportsData = groupData.reportsLine;
  if(!reportsData || Object.keys(reportsData).length===0){{
    document.getElementById('static-all-content').innerHTML='<div style="text-align:center;padding:20px;color:#94a3b8">No data for '+curGroup+' / '+curColDim+' / '+curRowDim+'</div>';
    return;
  }}
  let html='';
  const reportOrder = ['daily_input','daily_output','daily_checkin','daily_checkout','cum_input','cum_output','cum_checkin','cum_checkout','balance'];
  const reportNames = {{daily_input:'Daily Input',daily_output:'Daily Output',daily_checkin:'Daily Checkin',daily_checkout:'Daily Checkout',cum_input:'Cum Input',cum_output:'Cum Output',cum_checkin:'Cum Checkin',cum_checkout:'Cum Checkout',balance:'BOH'}};
  reportOrder.forEach(rt=>{{
    const data = reportsData[rt];
    if(!data || !data.rows || data.rows.length===0) return;
    const cols = data.columns || [];
    const rows = data.rows || [];
    html += '<div class="table-wrapper" style="margin-bottom:16px"><div style="font-weight:600;font-size:12px;margin:6px">'+esc(reportNames[rt]||rt)+' — '+rows.length+' rows × '+cols.length+' cols</div><table><thead><tr>';
    html += '<th class="frozen" style="left:0;min-width:120px">'+esc(curRowDim)+'</th><th class="frozen divider-col" style="left:120px;min-width:5px"></th>';
    cols.forEach(c=>{{ html += '<th>'+esc(c)+'</th>'; }});
    html += '</tr></thead><tbody>';
    rows.slice(0,500).forEach(r=>{{
      const dimVal = r[curRowDim] || r['LINE_CODE'] || r['ITEM_NO'] || r['STYLE'] || '';
      html += '<tr><td class="frozen" style="left:0;min-width:120px">'+esc(String(dimVal))+'</td><td class="frozen divider-col" style="left:120px"></td>';
      cols.forEach(c=>{{ const v=r[c]; html += '<td>'+(v!=null?Number(v).toLocaleString():'')+'</td>'; }});
      html += '</tr>';
    }});
    if(rows.length>500) html += '<tr><td colspan="999" style="text-align:center;color:#94a3b8">... '+rows.length+' total rows, showing first 500 for static ...</td></tr>';
    html += '</tbody></table></div>';
  }});
  document.getElementById('static-all-content').innerHTML = html || '<div style="text-align:center;padding:20px;color:#94a3b8">No data</div>';
  applyFilter();
}}
function applyFilter(){{
  const lineF = document.getElementById('f-line').value.toLowerCase();
  const pnF = document.getElementById('f-pn').value.toLowerCase();
  const styleF = document.getElementById('f-style').value.toLowerCase();
  const search = document.getElementById('f-search').value.toLowerCase();
  const content = document.getElementById('static-all-content');
  if(!content) return;
  let visible=0, total=0;
  content.querySelectorAll('tr').forEach(tr=>{{
    if(tr.querySelector('th')) return;
    total++;
    const text = tr.textContent.toLowerCase();
    let show = true;
    if(lineF && !text.includes(lineF)) show=false;
    if(pnF && !text.includes(pnF)) show=false;
    if(styleF && !text.includes(styleF)) show=false;
    if(search && !text.includes(search)) show=false;
    tr.style.display = show ? '' : 'none';
    if(show) visible++;
  }});
  document.getElementById('f-count').textContent = visible+' / '+total+' rows';
}}
document.querySelectorAll('#groupTabs .tab').forEach(b=>{{ b.addEventListener('click', ()=>{{ document.querySelectorAll('#groupTabs .tab').forEach(x=>x.classList.remove('active')); b.classList.add('active'); curGroup=b.dataset.group; renderReports(); }}); }});
document.querySelectorAll('#colDimTabs .tab').forEach(b=>{{ b.addEventListener('click', ()=>{{ document.querySelectorAll('#colDimTabs .tab').forEach(x=>x.classList.remove('active')); b.classList.add('active'); curColDim=b.dataset.coldim; renderReports(); }}); }});
document.querySelectorAll('#rowDimTabs .tab').forEach(b=>{{ b.addEventListener('click', ()=>{{ document.querySelectorAll('#rowDimTabs .tab').forEach(x=>x.classList.remove('active')); b.classList.add('active'); curRowDim=b.dataset.rowdim; renderReports(); }}); }});
document.getElementById('f-apply')?.addEventListener('click', applyFilter);
document.getElementById('f-clear')?.addEventListener('click', ()=>{{ document.getElementById('f-line').value=''; document.getElementById('f-pn').value=''; document.getElementById('f-style').value=''; document.getElementById('f-search').value=''; applyFilter(); }});
document.getElementById('f-search')?.addEventListener('input', applyFilter);
document.getElementById('f-line')?.addEventListener('input', applyFilter);
document.getElementById('f-pn')?.addEventListener('input', applyFilter);
document.getElementById('f-style')?.addEventListener('input', applyFilter);
const statusEl = document.getElementById('static-status');
if(statusEl){{ const st = STATIC_DATA.status; statusEl.innerHTML = '✅ Ready: '+(st.fg||0)+' FG / '+(st.gb||0)+' GB | Cats: '+(st.cats||[]).join(', '); }}
renderReports();
</script>
</body></html>"""

        from flask import Response
        return Response(html_content, mimetype='text/html', headers={
            "Content-Disposition": f"attachment; filename=io_report_static_BI_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(f"Export static failed: {e}")


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
