import os
import json
import shutil
import tempfile
from pathlib import Path

from flask import jsonify, request, send_file

from app.modules.inventory_dashboard import inventory_bp
from app.modules.inventory_dashboard.engine import (
    parse_bom_file,
    build_dashboard_from_balance_rows,
    find_bom_files_in_data_dir,
    load_balance_from_io_cache,
    parse_balance_excel,
    PROJECT_ROOT,
)

# Global in-memory cache
_global_dashboard_data = None
_global_dashboard_meta = None  # info about source

def _json_error(msg, code=400):
    return jsonify({"error": msg}), code


def _resolve_project_root():
    return PROJECT_ROOT


def _try_find_bom_auto():
    """Try to find BOM file automatically, prioritizing current IO folder.
    If a folder is selected via IO module, only look in that folder (return None if not found -> flat list).
    Otherwise, scan all data/ for BOM.
    """
    # First, try current IO folder if selected - check actual folder path stored in engine
    try:
        import app.modules.io_report.engine as io_eng
        import app.modules.io_report.routes as io_routes
        # Determine if we are in folder selection mode - must be defined first
        current_folder = getattr(io_routes, '_current_io_folder', None)
        is_folder_mode = current_folder is not None
        actual_dir = getattr(io_eng, '_global_data_dir_actual', None)

        # Check extra attr for actual folder path (set by load_from_folder)
        if actual_dir and os.path.isdir(actual_dir):
            from app.modules.io_report.engine import _find_file as _io_find_actual
            bom_path = _io_find_actual(actual_dir, "BOM快照.xlsx", ["BOM快照", "BOM", "bom"])
            if bom_path and os.path.exists(bom_path):
                return bom_path
            # If in folder mode and BOM not found in selected folder, return None (flat) instead of scanning all data/
            if is_folder_mode:
                return None

        if current_folder:
            # Resolve folder path
            from pathlib import Path
            proj_root = Path(PROJECT_ROOT)
            data_root = proj_root / "data"
            if current_folder == ".":
                cand_dir = data_root
            else:
                clean = current_folder[5:] if current_folder.startswith("data/") else current_folder
                cand_dir = data_root / clean
            if cand_dir.is_dir():
                # Look for BOM file in this specific folder
                from app.modules.io_report.engine import _find_file as _io_find
                bom_path = _io_find(str(cand_dir), "BOM快照.xlsx", ["BOM快照", "BOM", "bom"])
                if bom_path and os.path.exists(bom_path):
                    return bom_path
            # If folder mode and not found, don't fallback to global scan - return None for flat inventory
            if is_folder_mode:
                return None

        # Also check io engine's global data dir (set after load_from_folder) - only if not in folder mode or as fallback
        if not is_folder_mode:
            g_dir = getattr(io_eng, '_global_data_dir', None)
            if g_dir and os.path.isdir(g_dir):
                from app.modules.io_report.engine import _find_file as _io_find2
                bom_path = _io_find2(g_dir, "BOM快照.xlsx", ["BOM快照", "BOM", "bom"])
                if bom_path and os.path.exists(bom_path):
                    return bom_path
    except Exception as e:
        print(f"[inventory] check current IO folder for BOM failed: {e}")
        import traceback
        traceback.print_exc()

    files = find_bom_files_in_data_dir(PROJECT_ROOT)
    if files:
        return files[0]
    # Also check gated.ungated.ctb folder
    demo_dir = os.path.join(PROJECT_ROOT, "data", "gated.ungated.ctb")
    if os.path.isdir(demo_dir):
        for fn in os.listdir(demo_dir):
            if "bom" in fn.lower() and fn.lower().endswith(".xlsx"):
                fp = os.path.join(demo_dir, fn)
                if os.path.exists(fp):
                    return fp
    # Also check current working data dir
    return None


def _build_from_auto_sources():
    """
    Try to build dashboard from auto-found sources:
    - Balance from io cache
    - BOM from auto-found file
    Returns dashboard_data dict or None
    """
    bal_rows = load_balance_from_io_cache()
    if not bal_rows:
        return None, "No balance data in io cache, upload balance file or load IO report first"

    bom_path = _try_find_bom_auto()
    bom_children = {}
    bom_parents = {}
    has_children = []
    bom_src = None
    if bom_path and os.path.exists(bom_path):
        try:
            bom_children, bom_parents, has_children = parse_bom_file(bom_path)
            bom_src = bom_path
        except Exception as e:
            print(f"[inventory_dashboard] auto BOM parse failed {bom_path}: {e}")
            bom_children, bom_parents, has_children = {}, {}, []

    data = build_dashboard_from_balance_rows(bal_rows, bom_children, bom_parents, has_children)
    meta = {
        "balance_source": "io_cache",
        "balance_count": len(bal_rows),
        "bom_source": bom_src,
        "bom_found": bool(bom_src),
        "material_count": len(data.get("inventory", {})),
        "time_bucket_count": len(data.get("timeBuckets", [])),
    }
    return data, meta


@inventory_bp.route("/api/inventory-dashboard/status", methods=["GET"])
def api_status():
    global _global_dashboard_data, _global_dashboard_meta

    # If we have cached dashboard data, return its meta
    if _global_dashboard_data:
        meta = _global_dashboard_meta or {}
        return jsonify({
            "loaded": True,
            "has_dashboard_data": True,
            "has_bom": bool(meta.get("bom_source") or ( _global_dashboard_data.get("bomChildren") and len(_global_dashboard_data.get("bomChildren"))>0)),
            "has_balance": True,
            "material_count": len(_global_dashboard_data.get("inventory", {})),
            "time_bucket_count": len(_global_dashboard_data.get("timeBuckets", [])),
            "bom_source": meta.get("bom_source"),
            "balance_source": meta.get("balance_source", "memory"),
            "balance_count": meta.get("balance_count", 0),
        })

    # Check io cache
    bal_rows = load_balance_from_io_cache()
    has_balance = bool(bal_rows)
    bom_path = _try_find_bom_auto()
    has_bom = bool(bom_path and os.path.exists(bom_path))

    material_count = 0
    time_bucket_count = 0
    if has_balance:
        try:
            # quick estimate
            material_count = len(set([getattr(r, "ItemCode", "") for r in bal_rows]))
        except Exception:
            material_count = len(bal_rows) // 10

    return jsonify({
        "loaded": has_balance,
        "has_dashboard_data": False,
        "has_bom": has_bom,
        "has_balance": has_balance,
        "material_count": material_count,
        "time_bucket_count": time_bucket_count,
        "bom_source": bom_path,
        "balance_source": "io_cache" if has_balance else None,
        "balance_count": len(bal_rows) if bal_rows else 0,
        "auto_bom_candidates": find_bom_files_in_data_dir(PROJECT_ROOT)[:5],
    })


@inventory_bp.route("/api/inventory-dashboard/data", methods=["GET"])
def api_data():
    global _global_dashboard_data, _global_dashboard_meta

    # If cached, return it
    if _global_dashboard_data:
        return jsonify(_global_dashboard_data)

    # Try build from auto sources
    data, meta_or_msg = _build_from_auto_sources()
    if data is None:
        # meta_or_msg is error string
        return _json_error(meta_or_msg, 404)

    # Cache it
    _global_dashboard_data = data
    _global_dashboard_meta = meta_or_msg if isinstance(meta_or_msg, dict) else {}

    return jsonify(data)


@inventory_bp.route("/api/inventory-dashboard/build", methods=["POST"])
def api_build():
    """
    Force rebuild from auto sources (io cache + auto BOM)
    """
    global _global_dashboard_data, _global_dashboard_meta
    data, meta = _build_from_auto_sources()
    if data is None:
        return _json_error(meta, 404)

    _global_dashboard_data = data
    _global_dashboard_meta = meta if isinstance(meta, dict) else {}

    return jsonify({
        "ok": True,
        "message": "Dashboard built from auto sources",
        "meta": _global_dashboard_meta,
        "dashboard": data,
    })


@inventory_bp.route("/api/inventory-dashboard/upload", methods=["POST"])
def api_upload():
    """
    Upload:
    - bom: BOM Excel (optional if auto found)
    - balance: Balance Excel (optional if io cache exists)
    - dashboard_json: dashboard_data.json directly (alternative)
    Supports:
    - multipart with files: bom, balance, json
    - Also supports generic 'files' for auto-classification
    - Also supports zip containing files
    """
    global _global_dashboard_data, _global_dashboard_meta

    tmp_dir = tempfile.mkdtemp(prefix="inv_dash_")
    try:
        # Check if JSON file uploaded directly
        json_file = None
        bom_file = None
        bal_file = None

        # Helper to classify
        def classify_file(filename, field_key):
            low = (filename or "").lower()
            field_low = (field_key or "").lower()
            if low.endswith(".json"):
                if "dashboard" in low or "inventory" in low or "dash" in low or field_low in ("dashboard", "json", "dashboard_json"):
                    return "json"
                # Also treat any json as dashboard json
                return "json"
            if "bom" in low or "bom" in field_low or "bom" in filename.lower():
                return "bom"
            if "balance" in low or "结存" in filename or "boh" in low or "onhand" in low or "ending" in low or "balance" in field_low or "boh" in field_low or "结存" in field_low or field_low in ("balance", "boh", "结存"):
                return "balance"
            # Generic fallback: if filename contains result or 结存 related
            if "result" in low or "onhand" in low:
                return "balance"
            return None

        from app.common.zip_handler import is_zip_file, extract_all_xlsx

        all_files = []
        for key in request.files:
            all_files.extend([(key, f) for f in request.files.getlist(key)])

        if not all_files:
            return _json_error("No files uploaded. Expected BOM Excel and/or Balance Excel or dashboard_data.json", 400)

        # Save files to tmp_dir and classify
        saved = []
        for field_key, f in all_files:
            if not f.filename:
                continue
            fname = f.filename
            if is_zip_file(fname):
                zip_tmp = os.path.join(tmp_dir, f"_zip_{field_key}_{os.path.basename(fname)}")
                f.save(zip_tmp)
                extracted = extract_all_xlsx(zip_tmp, tmp_dir)
                # Also include json files from zip
                # extract_all_xlsx may only extract xlsx, so manually list
                try:
                    import zipfile
                    with zipfile.ZipFile(zip_tmp, 'r') as zf:
                        for zi in zf.infolist():
                            if zi.filename.lower().endswith(".json"):
                                zf.extract(zi, tmp_dir)
                                saved.append(os.path.join(tmp_dir, zi.filename))
                except Exception:
                    pass
                for ep in extracted:
                    saved.append(ep)
                try:
                    os.remove(zip_tmp)
                except Exception:
                    pass
            else:
                safe_name = os.path.basename(fname)
                dest = os.path.join(tmp_dir, f"_{field_key}_{safe_name}")
                c = 1
                b, e = os.path.splitext(dest)
                while os.path.exists(dest):
                    dest = f"{b}_{c}{e}"
                    c += 1
                f.save(dest)
                saved.append(dest)

        # Classify saved files
        for fp in saved:
            base = os.path.basename(fp)
            # Strip prefix _{field}_
            orig = base
            if base.startswith("_"):
                parts = base.split("_", 2)
                if len(parts) >= 3:
                    orig = parts[2]
            cls = classify_file(orig, base)
            if cls == "json":
                json_file = fp
            elif cls == "bom":
                bom_file = fp
            elif cls == "balance":
                bal_file = fp
            else:
                # Try content inspection
                low = orig.lower()
                if low.endswith(".json"):
                    json_file = fp
                elif "bom" in low:
                    bom_file = fp
                elif "balance" in low or "结存" in orig or "boh" in low:
                    bal_file = fp

        # If json file present, load it directly
        if json_file and os.path.exists(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as jf:
                    data = json.load(jf)
                # Validate
                if not isinstance(data, dict) or "inventory" not in data or "timeBuckets" not in data:
                    return _json_error(f"JSON file {os.path.basename(json_file)} does not look like dashboard_data.json - missing inventory/timeBuckets", 400)
                # Ensure bomChildren / bomParents / hasChildren exist
                if "bomChildren" not in data:
                    data["bomChildren"] = {}
                if "bomParents" not in data:
                    data["bomParents"] = {}
                if "hasChildren" not in data:
                    data["hasChildren"] = list(data.get("bomChildren", {}).keys())

                _global_dashboard_data = data
                _global_dashboard_meta = {
                    "balance_source": f"json:{os.path.basename(json_file)}",
                    "bom_source": "embedded in json",
                    "material_count": len(data.get("inventory", {})),
                    "time_bucket_count": len(data.get("timeBuckets", [])),
                }
                return jsonify({
                    "ok": True,
                    "message": f"Loaded dashboard_data.json directly: {len(data.get('inventory', {}))} materials, {len(data.get('timeBuckets', []))} time buckets",
                    "meta": _global_dashboard_meta,
                    "dashboard": data,
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                return _json_error(f"Failed to parse JSON file {os.path.basename(json_file)}: {e}", 400)

        # Otherwise need balance data
        bal_rows = None
        bal_source = None
        if bal_file and os.path.exists(bal_file):
            try:
                bal_rows = parse_balance_excel(bal_file)
                bal_source = os.path.basename(bal_file)
            except Exception as e:
                import traceback
                traceback.print_exc()
                return _json_error(f"Failed to parse Balance file {os.path.basename(bal_file)}: {e}", 400)
        else:
            # Try io cache
            bal_rows = load_balance_from_io_cache()
            if bal_rows:
                bal_source = "io_cache"
            else:
                return _json_error("Missing Balance data. Upload 结存表.xlsx or first load IO and BOH (which provides balance), or upload dashboard_data.json directly", 400)

        # BOM
        bom_children = {}
        bom_parents = {}
        has_children = []
        bom_src = None
        if bom_file and os.path.exists(bom_file):
            try:
                bom_children, bom_parents, has_children = parse_bom_file(bom_file)
                bom_src = os.path.basename(bom_file)
            except Exception as e:
                import traceback
                traceback.print_exc()
                return _json_error(f"Failed to parse BOM file {os.path.basename(bom_file)}: {e}", 400)
        else:
            # Try auto BOM
            auto_bom = _try_find_bom_auto()
            if auto_bom and os.path.exists(auto_bom):
                try:
                    bom_children, bom_parents, has_children = parse_bom_file(auto_bom)
                    bom_src = auto_bom
                except Exception as e:
                    print(f"[inventory_dashboard] auto BOM parse failed: {e}")
                    bom_children, bom_parents, has_children = {}, {}, []
                    bom_src = None
            else:
                # No BOM - still allow flat display
                bom_children, bom_parents, has_children = {}, {}, []
                bom_src = None

        # Build dashboard
        try:
            data = build_dashboard_from_balance_rows(bal_rows, bom_children, bom_parents, has_children)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _json_error(f"Failed to build dashboard: {e}", 500)

        _global_dashboard_data = data
        _global_dashboard_meta = {
            "balance_source": bal_source,
            "balance_count": len(bal_rows) if bal_rows else 0,
            "bom_source": bom_src,
            "bom_found": bool(bom_src),
            "material_count": len(data.get("inventory", {})),
            "time_bucket_count": len(data.get("timeBuckets", [])),
        }

        return jsonify({
            "ok": True,
            "message": f"Dashboard built: {len(data.get('inventory', {}))} materials, {len(data.get('timeBuckets', []))} time buckets, BOM {'found' if bom_src else 'not found (flat list)'}",
            "meta": _global_dashboard_meta,
            "dashboard": data,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(f"Upload failed: {e}", 500)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@inventory_bp.route("/api/inventory-dashboard/clear", methods=["POST", "DELETE"])
def api_clear():
    global _global_dashboard_data, _global_dashboard_meta
    _global_dashboard_data = None
    _global_dashboard_meta = None
    return jsonify({"ok": True, "message": "Cleared inventory dashboard cache — now Not Ready"})


@inventory_bp.route("/api/inventory-dashboard/templates/schema", methods=["GET"])
def api_schema():
    return jsonify({
        "dashboard_data_json": {
            "file": "dashboard_data.json",
            "fields": {
                "timeBuckets": "List of 'YYYY-MM-DD 白班/夜班'",
                "inventory": "Dict[PartNumber -> Dict[TimeBucket -> Ending_OnHand]]",
                "bomChildren": "Dict[Parent -> List[Child]]",
                "bomParents": "Dict[Child -> List[Parent]]",
                "hasChildren": "List of parents with children"
            },
            "note": "This is the output of gtk-aps-inventory-analysis build_dashboard_json. Upload this JSON directly to render dashboard without Excel parsing."
        },
        "bom": {
            "file": "BOM快照.xlsx",
            "fields": [
                ["PARENT_PN_CODE", "String", "Parent PN (e.g., SK-xxx)"],
                ["ITEM_NO", "String", "Child PN (e.g., GB-yyy)"]
            ],
            "note": "Used to build tree structure. If missing, dashboard shows flat list."
        },
        "balance": {
            "file": "结存表.xlsx",
            "fields": [
                ["PLAN_DATE", "Date", "Balance date"],
                ["SHIFT_NAME", "String", "白班/夜班"],
                ["ITEM_CODE", "String", "Material number"],
                ["BALANCE_QTY", "Number", "Ending OnHand / BOH"]
            ],
            "note": "Already calculated Ending OnHand — no recalculation, just display. If missing, uses IO and BOH cache."
        }
    })


@inventory_bp.route("/api/inventory-dashboard/export", methods=["GET"])
def api_export():
    """Export current dashboard_data as JSON file"""
    global _global_dashboard_data
    if not _global_dashboard_data:
        return _json_error("No dashboard data — build or upload first", 404)
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
    try:
        json.dump(_global_dashboard_data, tmp, ensure_ascii=False, indent=2)
        tmp.close()
        return send_file(tmp.name, mimetype='application/json', as_attachment=True, download_name='dashboard_data.json')
    except Exception as e:
        return _json_error(f"Export failed: {e}", 500)
