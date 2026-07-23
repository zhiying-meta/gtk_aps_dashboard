"""
V2V Routes
"""
import os
import uuid
import shutil
import zipfile
import tempfile
from flask import request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from . import v2v_bp
from .config import TABLE_DEFS, SUPPORTED_GRANULARITIES, DEFAULT_GRANULARITY
from .utils import scan_folder_for_tables, parse_folder_data, clean_version_name, identify_table_type
from .diff_engine import compare_two_versions, get_detailed_diff
import math

# In-memory job store (MVP) - maps job_id to {folder_a, folder_b, result}
JOB_STORE = {}
# Caches for performance optimization
JOB_DF_CACHE = {}  # job_id -> {table_key: df}
MATRIX_CACHE = {}  # (job_id, table, gran, sku_cat, line_cat, only_diff, change_type) -> result
UPLOAD_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'uploads', 'v2v')
os.makedirs(UPLOAD_ROOT, exist_ok=True)

def get_cached_df(job_id, folder, table_key):
    """Get cached dataframe or load and cache"""
    if job_id not in JOB_DF_CACHE:
        JOB_DF_CACHE[job_id] = {}
    cache = JOB_DF_CACHE[job_id]
    # Use table_key as cache key, but also need folder distinction (a vs b) - we'll use folder+table
    cache_key = f"{folder}__{table_key}"
    if cache_key in cache:
        return cache[cache_key]
    try:
        from .diff_engine import load_single_table
        # For fcst we need special handling
        if table_key == "fcst":
            # load_single_table returns dict? Actually for fcst it returns df? Let's check
            df = load_single_table(folder, table_key)
            cache[cache_key] = df
            return df
        else:
            df = load_single_table(folder, table_key)
            cache[cache_key] = df
            return df
    except Exception as e:
        print(f"Cache load failed for {table_key} in {folder}: {e}")
        return None

def get_cached_matrix(job_id, table, gran, sku_cat, line_cat, only_diff, change_type):
    key = (job_id, table, gran, sku_cat, line_cat, only_diff, change_type)
    return MATRIX_CACHE.get(key)

def set_cached_matrix(job_id, table, gran, sku_cat, line_cat, only_diff, change_type, result):
    key = (job_id, table, gran, sku_cat, line_cat, only_diff, change_type)
    # Limit cache size to 100 entries
    if len(MATRIX_CACHE) > 100:
        # Remove oldest
        oldest = next(iter(MATRIX_CACHE))
        del MATRIX_CACHE[oldest]
    MATRIX_CACHE[key] = result

def sanitize_for_json(obj):
    """Recursively replace NaN, Infinity, -Infinity, NaT with None for valid JSON, and convert datetime to string.
    Robust version to avoid NaTType timetuple errors.
    """
    # Fast path for None
    if obj is None:
        return None

    # Dict
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    # List/tuple
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]

    # Float NaN/Infinity
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    # Try pandas/numpy handling
    try:
        import pandas as pd
        import datetime as dt
        import numpy as np

        # NaT and NaN check - must be before datetime isinstance because NaT is not datetime but pd.isna True
        try:
            if pd.isna(obj):
                return None
        except:
            pass

        # Explicit NaT type
        try:
            if isinstance(obj, pd._libs.tslibs.nattype.NaTType):
                return None
        except:
            pass

        # String 'NaT' 
        try:
            if str(obj) == 'NaT':
                return None
        except:
            pass

        # Numpy float/int
        if isinstance(obj, (np.floating, np.integer)):
            try:
                if np.isnan(obj) or np.isinf(obj):
                    return None
            except:
                pass
            try:
                return float(obj) if isinstance(obj, np.floating) else int(obj)
            except:
                return None

        # Pandas Timestamp, datetime
        if isinstance(obj, (pd.Timestamp, dt.datetime, dt.date)):
            try:
                if pd.isna(obj):
                    return None
            except:
                pass
            try:
                # Use isoformat but guard against NaT timetuple bug
                return obj.isoformat()
            except Exception:
                try:
                    return str(obj)
                except:
                    return None

        # Numpy datetime64
        if isinstance(obj, np.datetime64):
            try:
                if pd.isna(obj):
                    return None
            except:
                pass
            try:
                return str(obj)
            except:
                return None

        # Objects with item() (numpy scalars)
        if hasattr(obj, 'item'):
            try:
                val = obj.item()
                # Recursively sanitize val
                return sanitize_for_json(val)
            except:
                pass

    except Exception:
        pass

    # Basic types
    if isinstance(obj, (str, int, bool)):
        return obj

    # Fallback: try to convert to string if it's not serializable, but avoid crashing
    try:
        # If obj is already JSON serializable, return as is
        # For any other object, convert to string
        return obj
    except:
        return str(obj)

def _save_uploaded_files(files, job_id, version_label):
    """
    Save uploaded files to job folder
    files: list of FileStorage
    Returns folder path
    """
    version_folder = os.path.join(UPLOAD_ROOT, job_id, version_label)
    os.makedirs(version_folder, exist_ok=True)
    saved = []
    for f in files:
        if f.filename == '':
            continue
        # For webkitdirectory, filename includes relative path like "Ivy-.../BOM快照.xlsx"
        # We want to save only base xlsx, or preserve structure? For simplicity, save basename
        filename = os.path.basename(f.filename)
        if not filename.lower().endswith('.xlsx'):
            continue
        if filename.startswith('~$'):
            continue
        dest = os.path.join(version_folder, filename)
        f.save(dest)
        saved.append(dest)
    return version_folder


@v2v_bp.route('/v2v/api/versions', methods=['GET'])
def list_versions():
    """
    Scan server-side for available version folders
    Auto-scans multiple locations and any folder containing at least 2 recognized xlsx files
    Supports folders like Ivy-*, 0721, gated, etc.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    candidates = []
    seen_paths = set()

    def is_version_folder(fpath):
        """Check if folder is a valid version folder by containing at least 2 recognized tables"""
        try:
            if not os.path.isdir(fpath):
                return False
            scan = scan_folder_for_tables(fpath)
            # Consider valid if at least 2 recognized tables (to avoid random folders)
            # Or if folder name contains keywords like Ivy, gated, 0721, version, etc.
            recognized = scan["stats"]["recognized"]
            total = scan["stats"]["total_files"]
            # If has at least 2 xlsx and at least 2 recognized, or name contains date-like pattern
            if total >= 2 and recognized >= 2:
                return True
            # Also check if folder name looks like a version (contains digits and is not too generic)
            name = os.path.basename(fpath).lower()
            # Allow any folder that has at least 1 xlsx and name contains version-like keywords or date
            if total >= 1 and any(k in name for k in ["ivy", "gated", "0721", "072", "v2", "v3", "version", "snapshot", "aps"]):
                return True
            # If folder name is date-like (e.g., 0721, 20260721, etc.)
            if total >= 1 and any(char.isdigit() for char in name) and len(name) <= 30:
                # Check if it has at least 1 recognized table
                if recognized >= 1:
                    return True
            return False
        except:
            return False

    def scan_directory(base_path, max_depth=1):
        """Scan a directory for version folders, with optional depth"""
        try:
            if not os.path.exists(base_path):
                return
            for item in os.listdir(base_path):
                fpath = os.path.join(base_path, item)
                if fpath in seen_paths:
                    continue
                if os.path.isdir(fpath):
                    # Skip hidden, venv, node_modules, etc.
                    if item.startswith('.') or item in ['__pycache__', 'node_modules', '.venv', 'venv', 'uploads', 'app', 'static', 'docs']:
                        continue
                    if is_version_folder(fpath):
                        scan = scan_folder_for_tables(fpath)
                        candidates.append({
                            "name": item,
                            "path": fpath,
                            "file_count": scan["stats"]["total_files"],
                            "recognized": scan["stats"]["recognized"],
                            "missing": scan["stats"]["missing"]
                        })
                        seen_paths.add(fpath)
        except Exception as e:
            print(f"Scan error for {base_path}: {e}")

    # Scan locations - prioritize input_files as user mentioned all folders are there
    # Order: input_files first, then v2v_data, data, then project_root
    # This ensures input_files folders appear first if same sort key
    for sub in ["input_files", "v2v_data", "data"]:
        sub_path = os.path.join(project_root, sub)
        scan_directory(sub_path)

    # Also scan project root (for backward compatibility)
    scan_directory(project_root)

    # Sort by date (middle time) descending, then version v1/v2 etc.
    # Folder name format examples:
    # Ivy-20260716-gated-v2 -> date 20260716, version 2
    # Ivy-20260721-gated-v1 -> date 20260721, version 1
    # 0721_test -> date 0721 (as 0721), version 0
    # 20260721_snapshot -> date 20260721
    import re

    def parse_date_version(name):
        """
        Parse folder name to extract date and version
        Returns (date_int, version_int)
        Date: try to find 8-digit YYYYMMDD, fallback to 4-digit MMDD, or 6-digit
        Version: v1, v2, _v1, -v1, etc.
        """
        date_val = 0
        version_val = 0

        # Find 8-digit date YYYYMMDD
        m = re.search(r'(20\d{6})', name)  # e.g., 20260716, 20260721
        if m:
            try:
                date_val = int(m.group(1))
            except:
                pass
        else:
            # Try 6-digit YYMMDD or MMDDYY?
            # Try 4-digit MMDD like 0721
            m = re.search(r'(\d{4})', name)
            if m:
                # If it's like 0721, treat as 721, but need to distinguish from version numbers
                # We'll use the first 4-digit that looks like date (e.g., 0721, 0716, 0723)
                # For sorting, 0721 > 0716
                try:
                    # If name is like "0721_test", 0721 is date
                    # If name is "Ivy-20260716-gated-v2", we already handled 8-digit, so this won't trigger
                    # So for remaining, try to find 4-digit that is not version
                    # Version is usually single digit after v, so 4-digit is likely date
                    date_val = int(m.group(1))
                    # If date_val < 100, it's version, not date, set to 0
                    if date_val < 100:
                        date_val = 0
                except:
                    pass

        # Find version: v1, v2, -v1, _v1, etc.
        m = re.search(r'[vV](\d+)', name)
        if m:
            try:
                version_val = int(m.group(1))
            except:
                pass
        else:
            # Try to find trailing _1, -1, etc. after date?
            # e.g., gated-v1, gated-v2
            m = re.search(r'[-_](\d+)$', name)
            if m:
                try:
                    # If it's at end and small, treat as version
                    v = int(m.group(1))
                    if v < 100:
                        version_val = v
                except:
                    pass

        return (date_val, version_val)

    def sort_key(item):
        name = item["name"]
        date_val, version_val = parse_date_version(name)
        # Also consider file modification time as fallback?
        # For now, use date and version
        # Return tuple for sorting: (date, version, recognized)
        # We want newest date first, then version descending if same day
        return (date_val, version_val, item["recognized"])

    # Sort by date descending, then version descending, then recognized descending
    # Note: Python sort ascending, so reverse=True
    candidates.sort(key=lambda x: (parse_date_version(x["name"])[0], parse_date_version(x["name"])[1], x["recognized"]), reverse=True)

    return jsonify(sanitize_for_json({"versions": candidates, "scanned_at": __import__('datetime').datetime.now().isoformat()}))


@v2v_bp.route('/v2v/api/scan', methods=['POST'])
def scan_upload():
    """
    Scan uploaded folder without full compare - for preview
    FormData: files (multiple xlsx)
    """
    try:
        job_id = str(uuid.uuid4())
        files = request.files.getlist('files')
        if not files:
            files = request.files.getlist('files_a') + request.files.getlist('files_b')
        
        # For single version scan, try to detect version folders via relative paths
        # Group by folder prefix if available (webkitdirectory sends relative paths)
        folders = {}
        for f in files:
            # f.filename may contain folder path
            parts = f.filename.split('/')
            if len(parts) > 1:
                folder_name = parts[0]
            else:
                folder_name = "Version"
            if folder_name not in folders:
                folders[folder_name] = []
            folders[folder_name].append(f)

        results = {}
        for folder_name, flist in folders.items():
            tmp_folder = _save_uploaded_files(flist, job_id, folder_name)
            scan = scan_folder_for_tables(tmp_folder)
            parsed = parse_folder_data(tmp_folder)
            results[folder_name] = {
                "folder": folder_name,
                "scan": scan,
                "tables": parsed["tables_data"]
            }

        # Cleanup
        shutil.rmtree(os.path.join(UPLOAD_ROOT, job_id), ignore_errors=True)

        return jsonify(sanitize_for_json({"job_id": job_id, "folders": results}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@v2v_bp.route('/v2v/api/compare', methods=['POST'])
def compare():
    """
    Main compare endpoint
    Supports:
    - FormData with files_a[] and files_b[] (webkitdirectory)
    - Or single 'files' with folder grouping
    - Or JSON with a_path, b_path for server-side folders
    """
    try:
        # Check for server path mode
        if request.is_json:
            data = request.get_json()
            a_path = data.get('a_path')
            b_path = data.get('b_path')
            granularity = data.get('granularity', DEFAULT_GRANULARITY)
        else:
            a_path = request.form.get('a_path')
            b_path = request.form.get('b_path')
            granularity = request.form.get('granularity', DEFAULT_GRANULARITY)

        job_id = str(uuid.uuid4())[:8]
        folder_a = None
        folder_b = None

        if a_path and b_path:
            # Server-side path mode
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            # Allow relative or absolute
            if not os.path.isabs(a_path):
                # Try project_root join
                candidate = os.path.join(project_root, a_path)
                if os.path.exists(candidate):
                    a_path = candidate
                else:
                    # Try v2v_data
                    candidate = os.path.join(project_root, 'v2v_data', a_path)
                    if os.path.exists(candidate):
                        a_path = candidate
            if not os.path.isabs(b_path):
                candidate = os.path.join(project_root, b_path)
                if os.path.exists(candidate):
                    b_path = candidate
                else:
                    candidate = os.path.join(project_root, 'v2v_data', b_path)
                    if os.path.exists(candidate):
                        b_path = candidate

            if not os.path.exists(a_path):
                return jsonify({"error": f"Version A path not found: {a_path}"}), 400
            if not os.path.exists(b_path):
                return jsonify({"error": f"Version B path not found: {b_path}"}), 400

            folder_a = a_path
            folder_b = b_path
        else:
            # File upload mode
            files_a = request.files.getlist('files_a') or request.files.getlist('version_a') or request.files.getlist('files')
            files_b = request.files.getlist('files_b') or request.files.getlist('version_b')

            # If only 'files' provided, try to split by folder name prefix
            if not files_b and files_a:
                # Group by first folder component
                groups = {}
                for f in files_a:
                    parts = f.filename.split('/')
                    folder_key = parts[0] if len(parts) > 1 else "unknown"
                    if folder_key not in groups:
                        groups[folder_key] = []
                    groups[folder_key].append(f)
                if len(groups) >= 2:
                    keys = list(groups.keys())
                    files_a = groups[keys[0]]
                    files_b = groups[keys[1]]
                elif len(groups) == 1:
                    # Only one folder uploaded, need second
                    return jsonify({"error": "Need two versions: please upload Version A and Version B separately"}), 400

            if not files_a or not files_b:
                return jsonify({"error": "Need both Version A and Version B files. Upload folders containing xlsx files."}), 400

            folder_a = _save_uploaded_files(files_a, job_id, "version_a")
            folder_b = _save_uploaded_files(files_b, job_id, "version_b")

        # Validate granularity
        if granularity not in SUPPORTED_GRANULARITIES:
            granularity = DEFAULT_GRANULARITY

        # Perform comparison
        result = compare_two_versions(folder_a, folder_b, granularity)

        result["job_id"] = job_id
        result["folders"] = {
            "a": folder_a,
            "b": folder_b
        }

        # Store job for later detailed queries
        JOB_STORE[job_id] = {
            "folder_a": folder_a,
            "folder_b": folder_b,
            "granularity": granularity,
            "result": result,
            "version_a_name": os.path.basename(folder_a),
            "version_b_name": os.path.basename(folder_b)
        }

        # Preload and cache dataframes for faster detail queries (optimization)
        try:
            from .diff_engine import load_single_table
            # Clear old cache for this job
            if job_id in JOB_DF_CACHE:
                del JOB_DF_CACHE[job_id]
            JOB_DF_CACHE[job_id] = {}
            # Preload key tables
            for tbl in ["balance", "plan_output", "fcst", "fcst_detail"]:
                try:
                    df_a = load_single_table(folder_a, tbl)
                    df_b = load_single_table(folder_b, tbl)
                    JOB_DF_CACHE[job_id][f"{folder_a}__{tbl}"] = df_a
                    JOB_DF_CACHE[job_id][f"{folder_b}__{tbl}"] = df_b
                except Exception as ce:
                    print(f"Preload cache failed for {tbl}: {ce}")
            # Clear matrix cache for old jobs if too many
            if len(MATRIX_CACHE) > 200:
                # Keep only recent 100
                keys = list(MATRIX_CACHE.keys())[-100:]
                new_cache = {k: MATRIX_CACHE[k] for k in keys}
                MATRIX_CACHE.clear()
                MATRIX_CACHE.update(new_cache)
        except Exception as ce:
            print(f"Cache preload error: {ce}")

        return jsonify(sanitize_for_json(result))

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@v2v_bp.route('/v2v/api/diff/<table_name>', methods=['GET'])
def diff_detail(table_name):
    """
    Get detailed diff for a table
    Query params: job_id, granularity, change_type, week, line, sku, page, page_size
    """
    try:
        job_id = request.args.get('job_id')
        if not job_id or job_id not in JOB_STORE:
            return jsonify({"error": "Invalid or expired job_id"}), 400

        job = JOB_STORE[job_id]
        granularity = request.args.get('granularity', job.get('granularity', 'week'))
        change_type = request.args.get('change_type', 'ALL')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 100))

        # Extended params for Phase3 output tables
        filters = {
            "change_type": change_type,
            "week": request.args.get('week'),
            "line": request.args.get('line'),
            "sku": request.args.get('sku'),
            "group_by": request.args.get('group_by'),
            "only_diff": request.args.get('only_diff', 'true'),
            "threshold_abs": request.args.get('threshold_abs', '0'),
            "threshold_pct": request.args.get('threshold_pct', '0'),
            "sort": request.args.get('sort', 'abs_diff_desc'),
            "compare_field": request.args.get('compare_field', 'BALANCE_QTY' if table_name=='balance' else 'PLAN_VALUE'),
            "item_code": request.args.get('item_code'),
            "pn_code": request.args.get('pn_code'),
            "line_code": request.args.get('line_code'),
            "cum": request.args.get('cum', 'true'),
            "monthly": request.args.get('monthly', 'false')
        }
        # Also allow direct filter params like LINE_CODE, SKU, ITEM_CODE, etc.
        for extra_key in ["LINE_CODE", "SKU", "ITEM_CODE", "WEEK", "DATE", "PLAN_ITEM", "SHIFT_NAME"]:
            if request.args.get(extra_key):
                filters[extra_key] = request.args.get(extra_key)
            if request.args.get(extra_key.lower()):
                filters[extra_key] = request.args.get(extra_key.lower())

        # If group_by is provided as encoded, keep it
        # For plan_output/balance, we pass group_by via filters as well as separate
        detail = get_detailed_diff(job["folder_a"], job["folder_b"], table_name, granularity, filters, page, page_size)
        detail["job_id"] = job_id
        detail["version_a_name"] = job.get("version_a_name")
        detail["version_b_name"] = job.get("version_b_name")

        return jsonify(sanitize_for_json(detail))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@v2v_bp.route('/v2v/api/job/<job_id>', methods=['GET'])
def get_job(job_id):
    if job_id not in JOB_STORE:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(sanitize_for_json(JOB_STORE[job_id]["result"]))


@v2v_bp.route('/v2v/api/chart/<table_name>', methods=['GET'])
def get_chart(table_name):
    """
    Get chart data for a table
    Query: job_id, pn_code, line_code, plan_type, shift_name, sku
    """
    try:
        job_id = request.args.get('job_id')
        if not job_id or job_id not in JOB_STORE:
            return jsonify({"error": "Invalid job_id"}), 400
        job = JOB_STORE[job_id]
        from .diff_engine import get_chart_data
        kwargs = {
            "pn_code": request.args.get('pn_code'),
            "line_code": request.args.get('line_code'),
            "plan_type": request.args.get('plan_type'),
            "shift_name": request.args.get('shift_name'),
            "sku": request.args.get('sku')
        }
        # Remove None
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        data = get_chart_data(job["folder_a"], job["folder_b"], table_name, **kwargs)
        data["job_id"] = job_id
        data["table"] = table_name
        return jsonify(sanitize_for_json(data))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@v2v_bp.route('/v2v/api/download/current_view', methods=['POST'])
def download_current_view():
    """
    Download current view as Excel
    Body JSON: {job_id, table, group_by, granularity, filters, only_diff, threshold_abs, threshold_pct, compare_field}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing JSON body"}), 400
        job_id = data.get('job_id')
        table_name = data.get('table', 'bom')
        if not job_id or job_id not in JOB_STORE:
            return jsonify({"error": "Invalid job_id"}), 400

        job = JOB_STORE[job_id]
        from .diff_engine import get_detailed_diff
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Border, Side
        from io import BytesIO
        from flask import send_file

        # Parse params
        granularity = data.get('granularity', 'week')
        group_by = data.get('group_by')
        if isinstance(group_by, str):
            group_by = [g.strip() for g in group_by.split(',') if g.strip()] if group_by else None

        filters = data.get('filters', {})
        # Merge with other filter fields from data
        for k in ['group_by', 'only_diff', 'threshold_abs', 'threshold_pct', 'sort', 'compare_field', 'week', 'line', 'sku', 'LINE_CODE', 'SKU', 'ITEM_CODE', 'WEEK']:
            if k in data and k not in filters:
                filters[k] = data[k]

        # For output tables, ensure group_by passed
        if group_by:
            filters['group_by'] = ','.join(group_by) if isinstance(group_by, list) else group_by

        # Get all records (no pagination, max 10000)
        # For large tables, limit to 10000
        detail = get_detailed_diff(job["folder_a"], job["folder_b"], table_name, granularity, filters, page=1, page_size=10000)

        records = detail.get('records', [])
        if not records:
            # Try to get at least summary
            return jsonify({"error": "No records to download", "detail": detail.get('message', 'No diff')}), 400

        # Create workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"{table_name}_diff"

        # Headers based on table
        # Flatten records: get all keys from first record
        # For dict with nested key, we flatten
        def flatten_record(rec):
            flat = {}
            # Handle key dict
            if 'key' in rec and isinstance(rec['key'], dict):
                for k,v in rec['key'].items():
                    flat[f"key_{k}"] = v
            # Other fields
            for k,v in rec.items():
                if k == 'key' or k.startswith('_'):
                    continue
                if isinstance(v, dict):
                    continue
                flat[k] = v
            return flat

        flat_records = [flatten_record(r) for r in records]
        if not flat_records:
            return jsonify({"error": "No flat records"}), 400

        headers = list(flat_records[0].keys())
        ws.append(headers)

        # Style header
        header_fill = PatternFill(start_color="1e293b", end_color="1e293b", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=11)
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font

        # Data rows
        for rec in flat_records:
            row = [rec.get(h) for h in headers]
            ws.append(row)

        # Auto column width
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)
            ws.column_dimensions[column].width = adjusted_width

        # Save to memory
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"V2V_{table_name}_{job_id[:6]}.xlsx"
        return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500



@v2v_bp.route('/v2v/api/export/html', methods=['POST', 'GET'])
def export_html():
    """
    Export full V2V comparison as standalone HTML for sharing - Full functionality version
    """
    try:
        if request.is_json:
            data = request.get_json()
            job_id = data.get('job_id')
        else:
            job_id = request.args.get('job_id') or request.form.get('job_id')

        if not job_id or job_id not in JOB_STORE:
            return jsonify({"error": "Invalid job_id"}), 400

        job = JOB_STORE[job_id]
        result = job["result"]
        folder_a = job["folder_a"]
        folder_b = job["folder_b"]

        from .diff_engine import get_detailed_diff, load_single_table
        from .parsers.balance_parser import get_boh_horizontal_matrix
        from .parsers.plan_output_parser import get_plan_output_horizontal_matrix
        from .parsers.plan_input_parser import get_plan_input_horizontal_matrix
        from .parsers.fcst_parser import get_fcst_horizontal_matrix
        from .export_html_generator import generate_full_featured_html
        import os
        from datetime import datetime

        previous_name = job.get("version_a_name", "Previous Version")
        latest_name = job.get("version_b_name", "Latest Version")
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Collect matrices
        matrices = {}
        def safe_matrix(fn, *args, **kwargs):
            try:
                import time
                start_t = time.time()
                m = fn(*args, **kwargs)
                elapsed = time.time() - start_t
                print(f"[Export] Matrix {fn.__name__} {kwargs.get('granularity')} took {elapsed:.2f}s, skus={len(m.get('sku_list',[]))} buckets={len(m.get('bucket_labels',[]))}")
                # Aggressive limits for export to keep HTML small and fast
                if m.get("sku_list") and len(m["sku_list"]) > 200:
                    orig_skus = m["sku_list"]
                    m["sku_list"] = orig_skus[:200]
                    filtered_matrix = {sku: m["matrix"].get(sku, {}) for sku in m["sku_list"]}
                    m["matrix"] = filtered_matrix
                    m["summary"]["truncated_skus"] = True
                    m["summary"]["original_sku_count"] = len(orig_skus)
                if m.get("bucket_labels") and len(m["bucket_labels"]) > 100:
                    orig_len = len(m["bucket_labels"])
                    keep = m["bucket_labels"][:100]
                    m["bucket_labels"] = keep
                    if isinstance(m.get("time_buckets"), list):
                        m["time_buckets"] = m["time_buckets"][:100]
                    for sku in list(m["matrix"].keys()):
                        # Keep only non-None and in keep
                        new_row = {k: v for k, v in m["matrix"][sku].items() if k in keep and v is not None}
                        m["matrix"][sku] = new_row
                    m["summary"]["truncated_buckets"] = True
                    m["summary"]["original_bucket_count"] = orig_len
                else:
                    # Make sparse: remove None entries to reduce JSON size
                    for sku in list(m["matrix"].keys()):
                        sparse_row = {k: v for k, v in m["matrix"][sku].items() if v is not None}
                        m["matrix"][sku] = sparse_row
                return m
            except Exception as e:
                import traceback; traceback.print_exc()
                return {"error": str(e), "time_buckets": [], "sku_list": [], "matrix": {}, "summary": {}}

        try:
            df_balance_a = load_single_table(folder_a, "balance")
            df_balance_b = load_single_table(folder_b, "balance")
            df_plan_output_a = load_single_table(folder_a, "plan_output")
            df_plan_output_b = load_single_table(folder_b, "plan_output")
            df_fcst_main_a = load_single_table(folder_a, "fcst")
            df_fcst_detail_a = load_single_table(folder_a, "fcst_detail")
            df_fcst_main_b = load_single_table(folder_b, "fcst")
            df_fcst_detail_b = load_single_table(folder_b, "fcst_detail")
        except Exception as e:
            df_balance_a = df_balance_b = df_plan_output_a = df_plan_output_b = None
            df_fcst_main_a = df_fcst_detail_a = df_fcst_main_b = df_fcst_detail_b = None

        # Optimized: only export week and day (month same logic as week yellow), use cache if available, and limit size aggressively for speed
        export_grans_balance = ["week", "day"]  # month can be derived from week yellow, but include month for completeness
        # Try to use cached matrices first to be fast
        def get_matrix_cached_or_compute(table, gran, fn, *args, **kwargs):
            cached = get_cached_matrix(job_id, table, gran, "ALL", "ALL", True, "ALL")
            if cached and not cached.get("error"):
                return cached
            return safe_matrix(fn, *args, **kwargs)

        for gran in ["week", "day", "month"]:
            if df_balance_a is not None and df_balance_b is not None:
                if "balance" not in matrices:
                    matrices["balance"] = {}
                matrices["balance"][gran] = get_matrix_cached_or_compute("balance", gran, get_boh_horizontal_matrix, df_balance_a, df_balance_b, granularity=gran, sku_category="ALL", only_diff=True, change_type="ALL")
            if df_plan_output_a is not None and df_plan_output_b is not None:
                if "plan_output" not in matrices:
                    matrices["plan_output"] = {}
                matrices["plan_output"][gran] = get_matrix_cached_or_compute("plan_output", gran, get_plan_output_horizontal_matrix, df_plan_output_a, df_plan_output_b, granularity=gran, sku_category="ALL", line_category="ALL", only_diff=True, change_type="ALL")

        for gran in ["week", "day"]:
            if df_fcst_main_a is not None and df_fcst_detail_a is not None and df_fcst_main_b is not None and df_fcst_detail_b is not None:
                if "plan_input" not in matrices:
                    matrices["plan_input"] = {}
                matrices["plan_input"][gran] = get_matrix_cached_or_compute("plan_input", gran, get_plan_input_horizontal_matrix, df_fcst_main_a, df_fcst_detail_a, df_fcst_main_b, df_fcst_detail_b, granularity=gran, sku_category="ALL", only_diff=True, change_type="ALL")
                if "fcst" not in matrices:
                    matrices["fcst"] = {}
                matrices["fcst"][gran] = get_matrix_cached_or_compute("fcst", gran, get_fcst_horizontal_matrix, df_fcst_main_a, df_fcst_detail_a, df_fcst_main_b, df_fcst_detail_b, granularity=gran, sku_category="ALL", only_diff=True, change_type="ALL")

        vertical_diffs = {}
        for table_name in result.get("summary", {}).keys():
            if table_name in ["balance", "plan_output", "plan_input", "fcst"]:
                continue
            try:
                detail = get_detailed_diff(folder_a, folder_b, table_name, granularity="week", filters={"only_diff": "true"}, page=1, page_size=300)
                vertical_diffs[table_name] = detail
            except Exception as e:
                vertical_diffs[table_name] = {"error": str(e), "records": []}

        embedded_data = {
            "meta": {
                "previous_name": previous_name,
                "latest_name": latest_name,
                "generated_at": generated_at,
                "job_id": job_id,
                "version_a_name": previous_name,
                "version_b_name": latest_name,
                "overall": result.get("overall", {}),
                "export_version": "v2-full-featured"
            },
            "summary": result.get("summary", {}),
            "matrices": matrices,
            "vertical_diffs": vertical_diffs
        }

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        css_global = ""
        css_v2v = ""
        try:
            with open(os.path.join(project_root, "static", "global", "style.css"), "r") as f:
                css_global = f.read()
        except:
            css_global = ""
        try:
            with open(os.path.join(project_root, "static", "modules", "v2v", "style.css"), "r") as f:
                css_v2v = f.read()
        except:
            css_v2v = ""

        from .config import TABLE_DEFS

        html_content = generate_full_featured_html(
            embedded_data=embedded_data,
            table_defs=TABLE_DEFS,
            css_global=css_global,
            css_v2v=css_v2v,
            previous_name=previous_name,
            latest_name=latest_name,
            generated_at=generated_at,
            job_id=job_id,
            summary_count=len(result.get("summary", {})),
            overall=result.get("overall", {})
        )

        from io import BytesIO
        from flask import send_file

        output = BytesIO()
        output.write(html_content.encode('utf-8'))
        output.seek(0)

        filename = f"V2V_Full_Featured_{previous_name}_vs_{latest_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
        filename = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
        filename = filename.replace(" ", "_")
        if not filename.endswith(".html"):
            filename += ".html"

        return send_file(output, as_attachment=True, download_name=filename, mimetype='text/html')

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@v2v_bp.route('/v2v/api/bom/children', methods=['GET'])
def get_bom_children_api():
    """
    Get BOM children for a given parent PN
    Query: job_id, pn_code, recursive (true/false), max_depth
    """
    try:
        job_id = request.args.get('job_id')
        pn_code = request.args.get('pn_code') or request.args.get('parent')
        recursive = request.args.get('recursive', 'false').lower() in ['true', '1', 'yes']
        max_depth = int(request.args.get('max_depth', 2))

        if not job_id or job_id not in JOB_STORE:
            return jsonify({"error": "Invalid job_id"}), 400
        if not pn_code:
            return jsonify({"error": "Missing pn_code"}), 400

        job = JOB_STORE[job_id]
        from .diff_engine import load_single_table
        from .parsers.bom_parser import get_bom_children, get_bom_tree

        df_a = load_single_table(job["folder_a"], "bom")
        df_b = load_single_table(job["folder_b"], "bom")

        # Use version A BOM for structure, but also check B for diff
        children_a = get_bom_children(df_a, pn_code, recursive=recursive, max_depth=max_depth) if df_a is not None else []
        children_b = get_bom_children(df_b, pn_code, recursive=recursive, max_depth=max_depth) if df_b is not None else []

        # Merge to show diff
        # For simplicity, return A children and B children separate, and also diff of children list
        # Find added/deleted children
        set_a = set([c["child"] for c in children_a])
        set_b = set([c["child"] for c in children_b])
        added = list(set_b - set_a)
        deleted = list(set_a - set_b)
        common = list(set_a & set_b)

        return jsonify(sanitize_for_json({
            "job_id": job_id,
            "parent": pn_code,
            "recursive": recursive,
            "children_a": children_a,
            "children_b": children_b,
            "added": added,
            "deleted": deleted,
            "common": common,
            "total_a": len(children_a),
            "total_b": len(children_b)
        }))

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@v2v_bp.route('/v2v/api/plan_output/breakdown', methods=['GET'])
def get_plan_output_breakdown():
    """
    Breakdown by line/shift for a given SKU and date
    Query: job_id, sku, date (YYYY-MM-DD), granularity
    """
    try:
        job_id = request.args.get('job_id')
        sku = request.args.get('sku')
        date = request.args.get('date')
        granularity = request.args.get('granularity', 'day')

        if not job_id or job_id not in JOB_STORE:
            return jsonify({"error": "Invalid job_id"}), 400
        if not sku:
            return jsonify({"error": "Missing sku"}), 400

        job = JOB_STORE[job_id]
        from .diff_engine import load_single_table
        from .parsers.plan_output_parser import get_breakdown_by_line_shift

        df_a = load_single_table(job["folder_a"], "plan_output")
        df_b = load_single_table(job["folder_b"], "plan_output")

        if df_a is None or df_b is None:
            return jsonify({"error": "Missing plan_output"}), 400

        result = get_breakdown_by_line_shift(df_a, df_b, sku=sku, date=date, granularity=granularity)
        result["job_id"] = job_id
        return jsonify(sanitize_for_json(result))

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@v2v_bp.route('/v2v/api/plan_output/matrix', methods=['GET'])
def get_plan_output_matrix():
    """
    Detailed daily matrix for Plan Output (legacy, kept for compatibility)
    """
    try:
        job_id = request.args.get('job_id')
        if not job_id or job_id not in JOB_STORE:
            return jsonify({"error": "Invalid job_id"}), 400
        job = JOB_STORE[job_id]
        from .parsers.plan_output_parser import get_daily_matrix
        from .diff_engine import load_single_table

        sku_prefix = request.args.get('sku_prefix', 'SK')
        line_filter = request.args.get('line_filter', None)
        shift_filter = request.args.get('shift_filter', None)
        exact_sku = request.args.get('exact_sku', None)
        granularity = request.args.get('granularity', 'day')
        cum = request.args.get('cum', 'true').lower() in ['true', '1', 'yes']

        df_a = load_single_table(job["folder_a"], "plan_output")
        df_b = load_single_table(job["folder_b"], "plan_output")
        if df_a is None or df_b is None:
            return jsonify({"error": "Missing plan_output"}), 400

        matrix = get_daily_matrix(df_a, df_b, sku_prefix=sku_prefix, line_filter=line_filter, shift_filter=shift_filter, granularity=granularity, cum=cum, exact_sku=exact_sku)

        matrix["job_id"] = job_id
        matrix["table"] = "plan_output"
        matrix["params"] = {
            "sku_prefix": sku_prefix,
            "line_filter": line_filter,
            "shift_filter": shift_filter,
            "granularity": granularity,
            "cum": cum,
            "exact_sku": exact_sku
        }
        return jsonify(sanitize_for_json(matrix))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@v2v_bp.route('/v2v/api/matrix/<table_name>', methods=['GET'])
def get_horizontal_matrix(table_name):
    """
    Optimized horizontal matrix with caching
    """
    try:
        job_id = request.args.get('job_id')
        if not job_id or job_id not in JOB_STORE:
            return jsonify({"error": "Invalid job_id"}), 400
        job = JOB_STORE[job_id]

        granularity = request.args.get('granularity', 'week')
        sku_category = request.args.get('sku_category', request.args.get('sku_prefix', 'ALL'))
        line_category = request.args.get('line_category', request.args.get('line_filter', 'ALL'))
        only_diff = request.args.get('only_diff', 'true').lower() in ['true', '1', 'yes']
        change_type = request.args.get('change_type', request.args.get('changeType', 'ALL'))

        table_name = table_name.lower()
        if table_name == 'boh':
            table_name = 'balance'

        # Check cache first
        cached = get_cached_matrix(job_id, table_name, granularity, sku_category, line_category, only_diff, change_type)
        if cached:
            cached["job_id"] = job_id
            cached["table"] = table_name
            cached["params"] = {
                "granularity": granularity,
                "sku_category": sku_category,
                "line_category": line_category,
                "only_diff": only_diff,
                "change_type": change_type,
                "cached": True
            }
            return jsonify(sanitize_for_json(cached))

        if table_name in ['balance', 'boh']:
            from .parsers.balance_parser import get_boh_horizontal_matrix
            df_a = get_cached_df(job_id, job["folder_a"], "balance")
            df_b = get_cached_df(job_id, job["folder_b"], "balance")
            if df_a is None or df_b is None:
                return jsonify({"error": "Missing BOH/balance data"}), 400
            result = get_boh_horizontal_matrix(df_a, df_b, granularity=granularity, sku_category=sku_category, only_diff=only_diff, change_type=change_type)

        elif table_name == 'plan_output':
            from .parsers.plan_output_parser import get_plan_output_horizontal_matrix
            df_a = get_cached_df(job_id, job["folder_a"], "plan_output")
            df_b = get_cached_df(job_id, job["folder_b"], "plan_output")
            if df_a is None or df_b is None:
                return jsonify({"error": "Missing plan_output"}), 400
            result = get_plan_output_horizontal_matrix(df_a, df_b, granularity=granularity, sku_category=sku_category, line_category=line_category, only_diff=only_diff, change_type=change_type)

        elif table_name == 'plan_input':
            from .parsers.plan_input_parser import get_plan_input_horizontal_matrix
            fcst_main_a = get_cached_df(job_id, job["folder_a"], "fcst")
            fcst_detail_a = get_cached_df(job_id, job["folder_a"], "fcst_detail")
            fcst_main_b = get_cached_df(job_id, job["folder_b"], "fcst")
            fcst_detail_b = get_cached_df(job_id, job["folder_b"], "fcst_detail")
            if any(x is None for x in [fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b]):
                return jsonify({"error": "Missing FCST data for plan_input"}), 400
            result = get_plan_input_horizontal_matrix(fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b, granularity=granularity, sku_category=sku_category, only_diff=only_diff, change_type=change_type)

        elif table_name == 'fcst':
            from .parsers.fcst_parser import get_fcst_horizontal_matrix
            fcst_main_a = get_cached_df(job_id, job["folder_a"], "fcst")
            fcst_detail_a = get_cached_df(job_id, job["folder_a"], "fcst_detail")
            fcst_main_b = get_cached_df(job_id, job["folder_b"], "fcst")
            fcst_detail_b = get_cached_df(job_id, job["folder_b"], "fcst_detail")
            if any(x is None for x in [fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b]):
                return jsonify({"error": "Missing FCST data"}), 400
            result = get_fcst_horizontal_matrix(fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b, granularity=granularity, sku_category=sku_category, only_diff=only_diff, change_type=change_type)

        else:
            return jsonify({"error": f"Matrix not supported for table {table_name}. Supported: balance/boh, plan_output, plan_input, fcst"}), 400

        result["job_id"] = job_id
        result["table"] = table_name
        result["params"] = {
            "granularity": granularity,
            "sku_category": sku_category,
            "line_category": line_category,
            "only_diff": only_diff,
            "change_type": change_type
        }

        # Cache result
        set_cached_matrix(job_id, table_name, granularity, sku_category, line_category, only_diff, change_type, result)
        return jsonify(sanitize_for_json(result))

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@v2v_bp.route('/v2v/templates/schema', methods=['GET'])
def get_schema():
    """Return table definitions as schema"""
    return jsonify(TABLE_DEFS)


@v2v_bp.route('/v2v/', methods=['GET'])
def v2v_index():
    """Redirect to main page with v2v module param"""
    # Serve the global index.html but frontend will handle module switching via query param
    from flask import current_app
    import os
    static_folder = current_app.static_folder
    return send_from_directory(os.path.join(static_folder, 'global'), 'index.html')


# For template download (future)
@v2v_bp.route('/v2v/templates/<name>', methods=['GET'])
def download_template(name):
    # Placeholder
    return jsonify({"message": "Template download not yet implemented", "requested": name})
