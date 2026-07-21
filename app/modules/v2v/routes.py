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

# In-memory job store (MVP) - maps job_id to {folder_a, folder_b, result}
JOB_STORE = {}
UPLOAD_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'uploads', 'v2v')
os.makedirs(UPLOAD_ROOT, exist_ok=True)

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
    Looks in project_root/Ivy-* and project_root/v2v_data/
    """
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    candidates = []

    # Look for Ivy-* folders in project root
    for item in os.listdir(project_root):
        fpath = os.path.join(project_root, item)
        if os.path.isdir(fpath) and (item.startswith('Ivy-') or 'gated' in item.lower()):
            scan = scan_folder_for_tables(fpath)
            candidates.append({
                "name": item,
                "path": fpath,
                "file_count": scan["stats"]["total_files"],
                "recognized": scan["stats"]["recognized"],
                "missing": scan["stats"]["missing"]
            })

    # Also look in v2v_data folder if exists
    v2v_data_path = os.path.join(project_root, 'v2v_data')
    if os.path.exists(v2v_data_path):
        for item in os.listdir(v2v_data_path):
            fpath = os.path.join(v2v_data_path, item)
            if os.path.isdir(fpath):
                scan = scan_folder_for_tables(fpath)
                candidates.append({
                    "name": item,
                    "path": fpath,
                    "file_count": scan["stats"]["total_files"],
                    "recognized": scan["stats"]["recognized"],
                    "missing": scan["stats"]["missing"]
                })

    return jsonify({"versions": candidates})


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

        return jsonify({"job_id": job_id, "folders": results})
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

        return jsonify(result)

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

        return jsonify(detail)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@v2v_bp.route('/v2v/api/job/<job_id>', methods=['GET'])
def get_job(job_id):
    if job_id not in JOB_STORE:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(JOB_STORE[job_id]["result"])


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
        return jsonify(data)
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

        return jsonify({
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
        })

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
        return jsonify(result)

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
        granularity = request.args.get('granularity', 'day')
        cum = request.args.get('cum', 'true').lower() in ['true', '1', 'yes']

        df_a = load_single_table(job["folder_a"], "plan_output")
        df_b = load_single_table(job["folder_b"], "plan_output")
        if df_a is None or df_b is None:
            return jsonify({"error": "Missing plan_output"}), 400

        # For matrix, we ignore granularity for now and always return daily with weekly grouping,
        # but we respect sku_prefix, line_filter, shift_filter
        matrix = get_daily_matrix(df_a, df_b, sku_prefix=sku_prefix, line_filter=line_filter, shift_filter=shift_filter, granularity=granularity, cum=cum)

        matrix["job_id"] = job_id
        matrix["table"] = "plan_output"
        matrix["params"] = {
            "sku_prefix": sku_prefix,
            "line_filter": line_filter,
            "shift_filter": shift_filter,
            "granularity": granularity,
            "cum": cum
        }
        return jsonify(matrix)
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
