import os
import shutil
import tempfile
import pathlib

from flask import Blueprint, jsonify, request

from app.modules.utilization_report.engine import (
    get_all_caches,
    get_cache_for_version,
    get_status,
    build_report,
    build_compare_report,
    reload_all,
    _compute_records,
)

util_bp = Blueprint("utilization_report", __name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# For upload, we expect 2 files: calendar and schedule
# TARGET mapping similar to io_report but for utilization

def _json_error(msg, code=500):
    return jsonify({"error": msg}), code

@util_bp.route("/api/utilization/status", methods=["GET"])
def api_status():
    try:
        # Fast path: check cache first, if cached return quickly
        from app.modules.utilization_report.engine import _CACHES
        cached_versions = {}
        for k in _CACHES.keys():
            if k.startswith(DEFAULT_DATA_DIR + "::"):
                ver = k.split("::")[-1]
                c = _CACHES[k]
                cached_versions[ver] = {
                    'lines': len(c.lines),
                    'dates': len(c.dates),
                    'shifts': len(c.shifts),
                    'records_shift': len(c.records_shift),
                    'records_day': len(c.records_day),
                }
        if cached_versions:
            return jsonify({"loaded": True, "versions": list(cached_versions.keys()), "details": cached_versions})

        # Check file existence without loading full Excel (fast)
        import pathlib
        base_path = pathlib.Path(DEFAULT_DATA_DIR)
        versions_found = []
        # Check utilization/gated, utilization/ungated
        for ver in ['gated','ungated']:
            util_dir = base_path / "utilization" / ver
            if util_dir.exists() and (util_dir / "工作日历快照.xlsx").exists() and (util_dir / "排产结果表.xlsx").exists():
                versions_found.append(ver)
        # Check IVY folders
        if not versions_found:
            for sub in base_path.iterdir():
                if sub.is_dir() and ('Gated' in sub.name or 'gated' in sub.name.lower()):
                    if (sub / "工作日历快照.xlsx").exists() and (sub / "排产结果表.xlsx").exists():
                        versions_found.append('gated')
                        break
            # Also check any folder containing the pair (first match)
            if not versions_found:
                # Quick scan one level
                for sub in base_path.iterdir():
                    if sub.is_dir():
                        if (sub / "工作日历快照.xlsx").exists() and (sub / "排产结果表.xlsx").exists():
                            versions_found.append('gated')
                            break

        loaded = len(versions_found) > 0
        return jsonify({"loaded": loaded, "versions": versions_found, "details": {}})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(str(e))

@util_bp.route("/api/utilization/meta", methods=["GET"])
def api_meta():
    try:
        caches = get_all_caches(DEFAULT_DATA_DIR)
        if not caches:
            return _json_error("No utilization data loaded. Upload calendar + schedule or place files in data/ folder.", 404)
        # Use gated as primary for meta, fallback to any
        primary = caches.get('gated') or list(caches.values())[0]
        return jsonify({
            "lines": primary.lines,
            "dates": primary.dates,
            "shifts": primary.shifts,
            "versions": list(caches.keys()),
            "date_min": min(primary.dates) if primary.dates else "",
            "date_max": max(primary.dates) if primary.dates else "",
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(str(e))

@util_bp.route("/api/utilization/reports", methods=["GET"])
def api_reports():
    try:
        caches = get_all_caches(DEFAULT_DATA_DIR)
        if not caches:
            return _json_error("No data. Upload first.", 404)

        mode = request.args.get("mode", "shift")  # shift or day
        version = request.args.get("version", "gated")  # gated / ungated / compare
        line_filter = request.args.get("line_code", "") or request.args.get("line", "")
        shift_filter = request.args.get("shift_name", "") or request.args.get("shift", "")
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")

        filters = {
            "line_filter": line_filter,
            "shift_filter": shift_filter,
            "date_from": date_from,
            "date_to": date_to,
        }

        if version == "compare":
            if 'gated' in caches and 'ungated' in caches:
                gated = caches['gated']
                ungated = caches['ungated']
                data = build_compare_report(gated, ungated, mode=mode, **filters)
                return jsonify({
                    "mode": mode,
                    "version": "compare",
                    "count": len(data),
                    "records": data[:2000],  # limit
                    "total": len(data),
                })
            else:
                return _json_error("Need both gated and ungated data for compare. Currently have: " + ",".join(caches.keys()), 400)
        else:
            # Single version
            cache = caches.get(version)
            if not cache:
                # fallback to first available
                cache = list(caches.values())[0]
                version = cache.version
            data = build_report(cache, mode=mode, **filters)
            return jsonify({
                "mode": mode,
                "version": cache.version,
                "count": len(data),
                "records": data[:2000],
                "total": len(data),
                "lines": cache.lines[:100],
                "shifts": cache.shifts,
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(str(e))

@util_bp.route("/api/utilization/upload", methods=["POST"])
def api_upload():
    """
    Upload calendar and schedule files. Supports gated and ungated.
    Form fields:
      - version: gated / ungated (default gated)
      - calendar: file (工作日历快照.xlsx)
      - schedule: file (排产结果表.xlsx)
    Or zip containing both.
    """
    if not request.files:
        return _json_error("Expected calendar and schedule files", 400)

    version = request.form.get("version", "gated").lower()
    if version not in ("gated", "ungated"):
        version = "gated"

    tmp_dir = tempfile.mkdtemp(prefix="util_upload_")
    try:
        # Save files
        calendar_path = None
        schedule_path = None

        for key in request.files:
            files = request.files.getlist(key)
            for f in files:
                if not f.filename:
                    continue
                low = f.filename.lower()
                # Classify by name or field key
                field_low = key.lower()
                save_path = os.path.join(tmp_dir, f.filename)
                f.save(save_path)

                if "工作日历" in f.filename or "calendar" in low or "日历" in f.filename or "calendar" in field_low or "工作日历" in key:
                    calendar_path = save_path
                elif "排产结果" in f.filename or "schedule" in low or "排产" in f.filename or "schedule" in field_low or "排产" in key:
                    schedule_path = save_path
                else:
                    # Try to guess by content? For now check first rows? Simple heuristic: file contains UPH etc -> calendar
                    # We'll attempt to read small sample
                    try:
                        import pandas as pd
                        df_sample = pd.read_excel(save_path, nrows=5, engine='openpyxl')
                        cols = [str(c) for c in df_sample.columns]
                        if "PLAN_TYPE" in cols and "UPH" in df_sample.to_string():
                            # Could be calendar
                            if not calendar_path:
                                calendar_path = save_path
                            else:
                                if not schedule_path:
                                    schedule_path = save_path
                        else:
                            if not schedule_path:
                                schedule_path = save_path
                    except:
                        # fallback
                        if not calendar_path:
                            calendar_path = save_path
                        elif not schedule_path:
                            schedule_path = save_path

        if not calendar_path or not schedule_path:
            # Try to find in tmp_dir if we have at least 2 xlsx
            xlsxs = list(pathlib.Path(tmp_dir).glob("*.xlsx"))
            if len(xlsxs) >= 2:
                # Heuristic: larger file maybe calendar? Actually calendar is large (18M) vs schedule 9M, not reliable
                # Try to detect by reading
                for p in xlsxs:
                    try:
                        import pandas as pd
                        df = pd.read_excel(str(p), nrows=10, engine='openpyxl')
                        col_str = " ".join(map(str, df.columns))
                        data_str = df.to_string()
                        if "UPH" in data_str and "工时" in data_str:
                            calendar_path = str(p)
                        elif "PLAN_ITEM" in col_str:
                            # Both have PLAN_ITEM, but schedule has KITTING etc
                            # Check for SKU column
                            if "SKU" in col_str or "PLAN_VALUE" in col_str:
                                if calendar_path and str(p) != calendar_path:
                                    schedule_path = str(p)
                                elif not calendar_path:
                                    # Might be schedule
                                    pass
                    except:
                        continue
                # Fallback assign
                if not calendar_path and len(xlsxs) >= 1:
                    calendar_path = str(xlsxs[0])
                if not schedule_path and len(xlsxs) >= 2:
                    # pick different from calendar
                    for p in xlsxs:
                        if str(p) != calendar_path:
                            schedule_path = str(p)
                            break

        if not calendar_path or not schedule_path:
            return _json_error(f"Missing calendar or schedule. Got calendar={calendar_path}, schedule={schedule_path}. Please upload 工作日历快照.xlsx and 排产结果表.xlsx", 400)

        # Validate by computing
        try:
            cache = _compute_records(version, calendar_path, schedule_path)
        except Exception as ve:
            import traceback
            traceback.print_exc()
            return _json_error(f"Validation failed: {ve}", 400)

        # Save to persistent location: data/utilization/<version>/
        persist_dir = os.path.join(DEFAULT_DATA_DIR, "utilization", version)
        os.makedirs(persist_dir, exist_ok=True)
        # Copy files to fixed names
        shutil.copyfile(calendar_path, os.path.join(persist_dir, "工作日历快照.xlsx"))
        shutil.copyfile(schedule_path, os.path.join(persist_dir, "排产结果表.xlsx"))

        # Also clear cache and reload
        reload_all(DEFAULT_DATA_DIR)

        return jsonify({
            "ok": True,
            "version": version,
            "lines": len(cache.lines),
            "dates": len(cache.dates),
            "records_shift": len(cache.records_shift),
            "records_day": len(cache.records_day),
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(f"Upload failed: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

@util_bp.route("/api/utilization/demo/load", methods=["POST"])
def api_demo_load():
    """
    Load demo from data/IVY20260721Gated folder as gated version
    """
    try:
        base = pathlib.Path(DEFAULT_DATA_DIR) / "IVY20260721Gated"
        cal = base / "工作日历快照.xlsx"
        sched = base / "排产结果表.xlsx"
        if not cal.exists() or not sched.exists():
            return _json_error(f"Demo files not found in {base}", 404)
        persist_dir = pathlib.Path(DEFAULT_DATA_DIR) / "utilization" / "gated"
        persist_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(cal), str(persist_dir / "工作日历快照.xlsx"))
        shutil.copyfile(str(sched), str(persist_dir / "排产结果表.xlsx"))
        reload_all(DEFAULT_DATA_DIR)
        caches = get_all_caches(DEFAULT_DATA_DIR)
        cache = caches.get('gated')
        if not cache:
            return _json_error("Failed to load after copy", 500)
        return jsonify({
            "ok": True,
            "version": "gated",
            "lines": len(cache.lines),
            "dates": len(cache.dates),
            "records_shift": len(cache.records_shift),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(str(e))

# Templates
@util_bp.route("/api/utilization/templates/schema", methods=["GET"])
def api_schema():
    return jsonify({
        "calendar": {
            "file": "工作日历快照.xlsx",
            "fields": [
                ["LINE_CODE", "String", "Line code", "AL1-PKG"],
                ["PLAN_DATE", "Date", "Date", "2026/6/2"],
                ["SHIFT_NAME", "String", "Shift", "白班 / 夜班"],
                ["PLAN_TYPE", "String", "UPH / 工时 / 效率 / 良率", "UPH"],
                ["PLAN_VALUE", "Number", "UPH=300, 工时=10, 效率=0.9", "320"],
                ["PLAN_ITEM", "String", "INPUT", "INPUT"],
            ],
            "note": "Capacity per shift = UPH * 效率 * 工时 where PLAN_ITEM=INPUT",
        },
        "schedule": {
            "file": "排产结果表.xlsx",
            "fields": [
                ["LINE_CODE", "String", "Line", "AL1-PKG"],
                ["SHIFT_NAME", "String", "Shift", "白班"],
                ["PLAN_ITEM", "String", "INPUT", "INPUT"],
                ["PLAN_DATE", "Date", "Date", "2026/6/2"],
                ["PLAN_VALUE", "Number", "Qty", "1000"],
            ],
            "note": "Load per shift = sum PLAN_VALUE where PLAN_ITEM=INPUT",
        }
    })
