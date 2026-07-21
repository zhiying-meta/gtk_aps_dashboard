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

        import pathlib
        base_path = pathlib.Path(DEFAULT_DATA_DIR)
        files_found = []
        for ver in ['gated','ungated']:
            util_dir = base_path / "utilization" / ver
            if util_dir.exists() and (util_dir / "工作日历快照.xlsx").exists() and (util_dir / "排产结果表.xlsx").exists():
                files_found.append(ver)
        if not files_found:
            for sub in base_path.iterdir():
                if sub.is_dir() and ('Gated' in sub.name or 'gated' in sub.name.lower()):
                    if (sub / "工作日历快照.xlsx").exists() and (sub / "排产结果表.xlsx").exists():
                        files_found.append('gated')
                        break
            if not files_found:
                for sub in base_path.iterdir():
                    if sub.is_dir():
                        if (sub / "工作日历快照.xlsx").exists() and (sub / "排产结果表.xlsx").exists():
                            files_found.append('gated')
                            break

        # Truly ready only when cache exists
        if cached_versions:
            return jsonify({
                "loaded": True,
                "versions": list(cached_versions.keys()),
                "details": cached_versions,
                "files_found": files_found,
            })
        else:
            # Not yet computed, but files may exist
            return jsonify({
                "loaded": False,
                "versions": [],
                "details": {},
                "files_found": files_found,
                "needs_compute": len(files_found) > 0,
            })

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

@util_bp.route("/api/utilization/pivot", methods=["GET"])
def api_pivot():
    """
    Pivot table for utilization matrix like Packout report.
    Supports version_type per row: Gated / Ungated
    mode=shift -> columns = date + shift
    mode=day -> columns = date
    Returns rows with line_code + version_type, plus columns for dates.
    Includes color coding, thick line separation by line_code.
    """
    try:
        caches = get_all_caches(DEFAULT_DATA_DIR)
        if not caches:
            return _json_error("No data. Upload first.", 404)

        mode = request.args.get("mode", "day")
        version_param = request.args.get("version", "all")  # gated, ungated, all, compare
        version_filter = request.args.get("version_type", "")  # optional filter Gated/Ungated
        line_filter = request.args.get("line_code", "") or request.args.get("line", "")
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")

        from app.modules.utilization_report.engine import build_report

        # Determine which versions to include
        versions_to_include = []
        if version_param == "all" or version_param == "compare" or "," in version_param:
            # Include all available caches
            if version_param == "all" or version_param == "compare":
                versions_to_include = list(caches.keys())
            else:
                versions_to_include = [v.strip() for v in version_param.split(",") if v.strip() in caches]
        else:
            # Single version
            if version_param in caches:
                versions_to_include = [version_param]
            else:
                # fallback to first available
                versions_to_include = [list(caches.keys())[0]]

        # If version_type filter provided, further filter
        if version_filter:
            vt_low = version_filter.lower()
            # Map Gated/Ungated to cache keys
            filtered = []
            for ver in versions_to_include:
                if vt_low in ver.lower() or vt_low in ver:
                    filtered.append(ver)
            if filtered:
                versions_to_include = filtered

        # Collect records per version
        all_recs = []  # list of dict with extra version_type
        for ver in versions_to_include:
            cache = caches.get(ver)
            if not cache:
                continue
            recs = build_report(cache, mode=mode, line_filter=line_filter, date_from=date_from, date_to=date_to)
            for r in recs:
                nr = dict(r)
                nr['version_type'] = ver.capitalize()  # Gated / Ungated
                nr['version_key'] = ver
                all_recs.append(nr)

        if not all_recs:
            return jsonify({"mode": mode, "columns": [], "rows": [], "detail": {}, "lines": [], "total_lines": 0, "total_cols": 0})

        # Build columns
        if mode == "shift":
            cols_set = set()
            for r in all_recs:
                col = f"{r['plan_date']}|{r['shift_name']}"
                cols_set.add(col)
            cols = sorted(list(cols_set))
        else:
            cols = sorted(list(set(r['plan_date'] for r in all_recs)))

        # Limit columns to 200 for performance (keep date range filtering in frontend if needed)
        max_cols = 200
        if len(cols) > max_cols:
            cols = cols[:max_cols]

        # Build matrix keyed by (line_code, version_type) -> col -> util
        # Also keep detail
        from collections import defaultdict
        matrix = {}  # key = (line, version_type) -> dict col->util
        detail = {}  # key = (line, version_type) -> col -> detail
        lines_set = set()
        for r in all_recs:
            key = (r['line_code'], r['version_type'])
            lines_set.add(r['line_code'])
            if key not in matrix:
                matrix[key] = {}
                detail[key] = {}
            col = f"{r['plan_date']}|{r['shift_name']}" if mode == "shift" else r['plan_date']
            if col not in cols:
                continue
            util_pct = r.get('utilization_pct', 0)
            capped = min(100.0, util_pct) if util_pct is not None else 0
            matrix[key][col] = capped
            detail[key][col] = {
                'util_raw': util_pct,
                'util_capped': capped,
                'load': r['load'],
                'capacity': r['capacity'],
                'uph': r['uph'],
                'efficiency': r['efficiency'],
                'working_hours': r['working_hours'],
                'is_overload': r.get('is_overload', False),
            }

        # Sort keys by line_code, then version_type (Gated before Ungated for consistency)
        def sort_key(k):
            line, vtype = k
            # Gated first
            order = 0 if vtype.lower() == 'gated' else 1
            return (line, order, vtype)
        sorted_keys = sorted(matrix.keys(), key=sort_key)

        # Build rows for frontend with version_type field and thick border flag
        rows = []
        last_line = None
        for (line, vtype) in sorted_keys:
            row = {
                'line_code': line,
                'version_type': vtype,
                'is_new_line': line != last_line,
            }
            last_line = line
            for col in cols:
                row[col] = matrix[(line, vtype)].get(col, None)
            rows.append(row)

        # Convert detail to string keys for JSON (line|version_type)
        detail_json = {}
        for (line, vtype), col_map in detail.items():
            key_str = f"{line}||{vtype}"
            detail_json[key_str] = col_map

        return jsonify({
            "mode": mode,
            "versions": versions_to_include,
            "columns": cols,
            "rows": rows,
            "detail": detail_json,
            "lines": sorted(list(lines_set)),
            "total_lines": len(sorted_keys),
            "total_cols": len(cols),
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(str(e))

@util_bp.route("/api/utilization/upload", methods=["POST"])
def api_upload():
    """
    Upload handler supporting:
    - Separate upload: calendar alone or schedule alone (per version)
    - One-click: calendar + schedule together (or zip)
    - Multi-version: gated + ungated together (4 files or zip with both)
    Like I/O Report: supports .xlsx, .zip, multiple files
    """
    if not request.files:
        return _json_error("Expected calendar and schedule files (xlsx or zip)", 400)

    tmp_dir = tempfile.mkdtemp(prefix="util_upload_")
    try:
        import zipfile

        # Collect all uploaded files, handle zip extraction
        extracted_files = []  # list of paths in tmp_dir

        for key in request.files:
            for f in request.files.getlist(key):
                if not f.filename:
                    continue
                fname = f.filename
                low = fname.lower()
                tmp_path = os.path.join(tmp_dir, fname)
                f.save(tmp_path)

                if low.endswith('.zip'):
                    # Extract zip
                    try:
                        with zipfile.ZipFile(tmp_path, 'r') as zf:
                            for info in zf.infolist():
                                if info.is_dir():
                                    continue
                                if not info.filename.lower().endswith('.xlsx'):
                                    continue
                                # Save with basename to avoid path traversal
                                base = os.path.basename(info.filename)
                                # Add prefix to avoid collision
                                out_path = os.path.join(tmp_dir, f"zip_{base}")
                                with zf.open(info) as src, open(out_path, 'wb') as dst:
                                    shutil.copyfileobj(src, dst)
                                extracted_files.append(out_path)
                        # Remove zip itself after extraction
                        os.remove(tmp_path)
                    except Exception as ze:
                        print(f"[util] zip extract failed {fname}: {ze}")
                        # Keep zip as is? Skip
                        continue
                else:
                    extracted_files.append(tmp_path)

        if not extracted_files:
            return _json_error("No xlsx files found (including inside zip)", 400)

        # Classify files into gated/ungated calendar/schedule
        # Map: version -> {calendar: path, schedule: path}
        def classify_file(path):
            name = os.path.basename(path).lower()
            # Check content hint if needed
            is_calendar = False
            is_schedule = False
            if "工作日历" in name or "calendar" in name or "日历" in name:
                is_calendar = True
            elif "排产结果" in name or "schedule" in name or "排产" in name:
                is_schedule = True
            else:
                # Try to guess by reading small sample for UPH/工时
                try:
                    import pandas as pd
                    df = pd.read_excel(path, nrows=5, engine='openpyxl')
                    txt = df.to_string()
                    if "UPH" in txt and "工时" in txt:
                        is_calendar = True
                    else:
                        is_schedule = True
                except:
                    # Fallback: larger file likely calendar
                    try:
                        size = os.path.getsize(path)
                        # Calendar is usually larger (18M vs 9M) but not reliable, assume first large is calendar
                        pass
                    except:
                        pass
                    is_schedule = True

            # Determine version by filename
            ver = "gated"  # default
            if "ungated" in name or "ungate" in name:
                ver = "ungated"
            elif "gated" in name:
                ver = "gated"
            else:
                # If no hint, will be assigned later
                ver = None

            return ver, is_calendar, is_schedule

        # Group
        version_groups = {
            "gated": {"calendar": None, "schedule": None},
            "ungated": {"calendar": None, "schedule": None},
        }

        # First pass: assign files with explicit version hint
        unassigned = []
        for p in extracted_files:
            ver, is_cal, is_sched = classify_file(p)
            if ver and is_cal and not version_groups[ver]["calendar"]:
                version_groups[ver]["calendar"] = p
            elif ver and is_sched and not version_groups[ver]["schedule"]:
                version_groups[ver]["schedule"] = p
            else:
                unassigned.append((p, is_cal, is_sched, ver))

        # Second pass: assign unassigned files to fill gaps
        # Priority: fill gated first, then ungated
        for p, is_cal, is_sched, ver_hint in unassigned:
            # If ver_hint is None, try to assign to first version missing that type
            target_vers = ["gated", "ungated"] if ver_hint is None else [ver_hint]
            assigned = False
            for tv in target_vers:
                if is_cal and not version_groups[tv]["calendar"]:
                    version_groups[tv]["calendar"] = p
                    assigned = True
                    break
                if is_sched and not version_groups[tv]["schedule"]:
                    version_groups[tv]["schedule"] = p
                    assigned = True
                    break
            if not assigned:
                # If still not assigned, try any missing slot
                for tv in ["gated", "ungated"]:
                    if is_cal and not version_groups[tv]["calendar"]:
                        version_groups[tv]["calendar"] = p
                        assigned = True
                        break
                    if is_sched and not version_groups[tv]["schedule"]:
                        version_groups[tv]["schedule"] = p
                        assigned = True
                        break

        # Now we have version_groups with possibly partial (only calendar or only schedule)
        # Save whatever we have to persist_dir, and for those versions where both exist, compute cache
        results = {}
        any_saved = False

        for ver in ["gated", "ungated"]:
            cal_path = version_groups[ver]["calendar"]
            sched_path = version_groups[ver]["schedule"]
            persist_dir = os.path.join(DEFAULT_DATA_DIR, "utilization", ver)
            os.makedirs(persist_dir, exist_ok=True)

            # If we have a file for this version, copy it to persist dir (even if partial)
            # Keep existing file if new one not provided
            if cal_path:
                dest = os.path.join(persist_dir, "工作日历快照.xlsx")
                shutil.copyfile(cal_path, dest)
                any_saved = True
            if sched_path:
                dest = os.path.join(persist_dir, "排产结果表.xlsx")
                shutil.copyfile(sched_path, dest)
                any_saved = True

            # Check if after saving, both files exist in persist_dir
            cal_persist = os.path.join(persist_dir, "工作日历快照.xlsx")
            sched_persist = os.path.join(persist_dir, "排产结果表.xlsx")
            if os.path.exists(cal_persist) and os.path.exists(sched_persist):
                # Try to compute / validate
                try:
                    cache = _compute_records(ver, cal_persist, sched_persist)
                    results[ver] = {
                        "lines": len(cache.lines),
                        "dates": len(cache.dates),
                        "records_shift": len(cache.records_shift),
                        "ready": True,
                    }
                except Exception as ve:
                    import traceback
                    traceback.print_exc()
                    results[ver] = {"ready": False, "error": str(ve)}
            else:
                # Partial
                has_cal = os.path.exists(cal_persist)
                has_sched = os.path.exists(sched_persist)
                if has_cal or has_sched:
                    results[ver] = {
                        "ready": False,
                        "partial": True,
                        "has_calendar": has_cal,
                        "has_schedule": has_sched,
                        "message": f"Partial upload for {ver}: calendar={has_cal}, schedule={has_sched}. Upload missing file to complete.",
                    }

        if not any_saved and not results:
            return _json_error("No valid calendar/schedule files classified. Please upload 工作日历快照.xlsx and 排产结果表.xlsx, or zip containing them.", 400)

        # Reload caches
        reload_all(DEFAULT_DATA_DIR)

        # Build response
        return jsonify({
            "ok": True,
            "results": results,
            "saved_versions": list(results.keys()),
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
