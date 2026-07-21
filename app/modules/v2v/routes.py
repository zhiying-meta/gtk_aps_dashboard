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
UPLOAD_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'uploads', 'v2v')
os.makedirs(UPLOAD_ROOT, exist_ok=True)

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

        # If folder_a was temp uploaded, keep it for job lifetime (cleanup after 1 hour could be implemented)
        # For server path mode, don't delete

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
    Export full V2V comparison as standalone HTML for sharing
    Query or JSON: job_id
    Returns HTML file that can be viewed offline, containing latest comparison data
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

        # Get detailed diffs for all tables (limited to 200 rows each for HTML size)
        from .diff_engine import get_detailed_diff
        all_diffs = {}
        for table_name in result.get("summary", {}).keys():
            try:
                # Get up to 200 rows per table
                detail = get_detailed_diff(job["folder_a"], job["folder_b"], table_name, granularity="week", filters={"only_diff": "true"}, page=1, page_size=200)
                all_diffs[table_name] = detail
            except Exception as e:
                all_diffs[table_name] = {"error": str(e), "records": []}

        # Build HTML
        from datetime import datetime
        previous_name = job.get("version_a_name", "Previous Version")
        latest_name = job.get("version_b_name", "Latest Version")
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V2V Comparison - {previous_name} vs {latest_name}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f8fafc; color: #0f172a; }}
.container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 24px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.header {{ border-bottom: 2px solid #0f172a; padding-bottom: 16px; margin-bottom: 24px; }}
.header h1 {{ margin: 0; font-size: 24px; }}
.header .meta {{ color: #64748b; font-size: 13px; margin-top: 8px; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.summary-card {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; }}
.summary-card h3 {{ margin: 0 0 8px 0; font-size: 14px; }}
.stat-row {{ display: flex; justify-content: space-between; font-size: 12px; margin: 2px 0; }}
.stat-label {{ color: #64748b; }}
.stat-value {{ font-weight: 600; }}
.add {{ color: #16a34a; }} .del {{ color: #dc2626; }} .mod {{ color: #d97706; }}
.table-section {{ margin-bottom: 32px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }}
.table-header {{ background: #0f172a; color: white; padding: 12px 16px; font-weight: 600; display: flex; justify-content: space-between; }}
.table-wrapper {{ max-height: 400px; overflow: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th {{ background: #1e293b; color: white; padding: 8px 10px; text-align: left; position: sticky; top: 0; }}
td {{ padding: 6px 10px; border-bottom: 1px solid #f1f5f9; }}
tr.diff-add td {{ background: #f0fdf4; }}
tr.diff-del td {{ background: #fef2f2; }}
tr.diff-mod td {{ background: #fffbeb; }}
.badge {{ font-size: 10px; padding: 2px 6px; border-radius: 10px; font-weight: 600; }}
.badge.add {{ background: #dcfce7; color: #166534; }}
.badge.del {{ background: #fecaca; color: #991b1b; }}
.badge.mod {{ background: #fef3c7; color: #92400e; }}
.footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; text-align: center; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>🔍 V2V Comparison Report</h1>
<div class="meta">
<div><b>Previous Version:</b> {previous_name}</div>
<div><b>Latest Version:</b> {latest_name}</div>
<div><b>Generated:</b> {generated_at} | <b>Job ID:</b> {job_id}</div>
<div><b>Overall:</b> Added {result.get('overall', {}).get('total_added', 0)} | Deleted {result.get('overall', {}).get('total_deleted', 0)} | Modified {result.get('overall', {}).get('total_modified', 0)} | Tables: {len(result.get('summary', {}))}</div>
</div>
</div>

<h2>Summary Dashboard</h2>
<div class="summary-grid">
"""

        for table_key, summary in result.get("summary", {}).items():
            total_a = summary.get("total_a", 0)
            total_b = summary.get("total_b", 0)
            added = summary.get("added", 0)
            deleted = summary.get("deleted", 0)
            modified = summary.get("modified", 0)
            html_content += f"""
<div class="summary-card">
<h3>{table_key}</h3>
<div class="stat-row"><span class="stat-label">Previous</span><span class="stat-value">{total_a} rows</span></div>
<div class="stat-row"><span class="stat-label">Latest</span><span class="stat-value">{total_b} rows</span></div>
<div class="stat-row"><span class="stat-label">Added</span><span class="stat-value add">+{added}</span></div>
<div class="stat-row"><span class="stat-label">Deleted</span><span class="stat-value del">-{deleted}</span></div>
<div class="stat-row"><span class="stat-label">Modified</span><span class="stat-value mod">{modified}</span></div>
</div>
"""

        html_content += """
</div>

<h2>Detailed Comparison (Time Horizontal - Month, Week, Daily, Shift)</h2>
<p style="font-size:12px;color:#64748b">Time is horizontal for all tables where applicable. Only rows with differences are shown (up to 200 per table).</p>
"""

        for table_key, diff_data in all_diffs.items():
            records = diff_data.get("records", [])[:100]  # limit 100 per table for HTML size
            if not records:
                continue
            html_content += f"""
<div class="table-section">
<div class="table-header">
<span>{table_key} - {len(records)} diffs (of {diff_data.get('pagination', {}).get('total', len(records))} total)</span>
<span style="font-size:11px;font-weight:400">Previous vs Latest</span>
</div>
<div class="table-wrapper">
<table>
<thead><tr>
"""
            # Headers from first record keys
            first = records[0]
            # Flatten keys
            headers = []
            if "key" in first and isinstance(first["key"], dict):
                for k in first["key"].keys():
                    headers.append(f"key_{k}")
            for k in first.keys():
                if k not in ["key", "_group_values", "_drill", "raw"]:
                    headers.append(k)
            # Limit headers
            headers = headers[:12]
            for h in headers:
                html_content += f"<th>{h}</th>"
            html_content += "</tr></thead><tbody>"

            for rec in records:
                ct = rec.get("change_type", "MODIFY")
                ct_lower = "add" if "ADD" in ct else "del" if "DEL" in ct or "INCONSISTENT" in ct else "mod"
                html_content += f'<tr class="diff-{ct_lower}">'
                flat = {}
                if "key" in rec and isinstance(rec["key"], dict):
                    for k,v in rec["key"].items():
                        flat[f"key_{k}"] = v
                for k,v in rec.items():
                    if k not in ["key", "_group_values", "_drill", "raw"] and k not in flat:
                        flat[k] = v
                for h in headers:
                    val = flat.get(h, "")
                    if isinstance(val, float):
                        val = f"{val:.2f}"
                    html_content += f"<td>{str(val)[:100]}</td>"
                html_content += "</tr>"

            html_content += """
</tbody>
</table>
</div>
</div>
"""

        html_content += f"""
<div class="footer">
Generated by V2V Comparison Tool | Job {job_id} | {generated_at} | Previous: {previous_name} vs Latest: {latest_name}<br>
This is a standalone HTML file containing embedded comparison data. No server needed.
</div>

</div>
</body>
</html>
"""

        from io import BytesIO
        from flask import send_file

        output = BytesIO()
        output.write(html_content.encode('utf-8'))
        output.seek(0)

        filename = f"V2V_Report_{previous_name}_vs_{latest_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
        # Sanitize filename
        filename = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
        filename = filename.replace(" ", "_") + ".html" if not filename.endswith(".html") else filename

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
    Detailed daily matrix for Plan Output
    Query: job_id, sku_prefix (SK,GB,LT,FR,RT or ALL), line_filter, shift_filter, granularity (day/week/monthly), cum (true/false)
    Returns dates grouped by week Sun-Sat, sku_list, and data dict with a/b/diff/cum
    """
    try:
        job_id = request.args.get('job_id')
        if not job_id or job_id not in JOB_STORE:
            return jsonify({"error": "Invalid job_id"}), 400
        job = JOB_STORE[job_id]
        from .parsers.plan_output_parser import get_daily_matrix
        from .diff_engine import load_single_table

        sku_prefix = request.args.get('sku_prefix', 'SK')  # default FG
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
