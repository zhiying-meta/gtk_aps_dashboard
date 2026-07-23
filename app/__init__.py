import os
from flask import Flask, send_from_directory


def create_app():
    # Project root is one level above app/
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(project_root, 'static')

    app = Flask(__name__, static_folder=static_dir, static_url_path="/static")
    app.config.from_object("app.config")

    # Ensure upload folder exists
    try:
        os.makedirs(app.config.get("UPLOAD_FOLDER", "uploads"), exist_ok=True)
    except Exception:
        pass

    from app.modules.plan_merge import plan_merge_bp
    app.register_blueprint(plan_merge_bp)

    # V2V Comparison module (integrated from feat/io-report / feat/v2v)
    try:
        from app.modules.v2v import v2v_bp
        app.register_blueprint(v2v_bp)
        print("✅ V2V module registered")
    except Exception as e:
        print(f"⚠️ V2V module failed to load: {e}")

    # Optional io_report module if present (feat/io-report branch)
    try:
        from app.modules.io_report.routes import io_bp
        app.register_blueprint(io_bp)
    except Exception as e:
        print(f"[app] io_report not loaded: {e}")

    # Utilization report module
    try:
        from app.modules.utilization_report.routes import util_bp
        app.register_blueprint(util_bp)
    except Exception as e:
        print(f"[app] utilization_report not loaded: {e}")

    @app.after_request
    def no_cache(resp):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp

    @app.route('/api/export/static', methods=['GET'])
    @app.route('/api/export/static/dist', methods=['GET'])
    def export_static_dist():
        """Export full static offline site like campus-planning-system/frontend/dist — preserves all format and filtering for all dashboards"""
        import tempfile
        import shutil
        import io
        import zipfile
        from pathlib import Path
        try:
            # Import export_static functions
            import sys
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            import export_static as es

            tmp_dist = Path(tempfile.mkdtemp(prefix="static_dist_"))
            # Use existing export_static logic to generate dist with all modules data
            # We call its main logic directly without argparse
            from export_static import copy_static, generate_data_js, try_bundle_xlsx_lib, inject_data_js, process_file, DEFAULT_CONFIG, TEMPLATE_DIR, find_default_inputs, is_plan_merge_file
            import glob

            input_files = find_default_inputs()
            # Also include any xlsx in data/ that are plan_merge files
            # For full export, we use existing demo and any uploaded? For now use default

            index_path = copy_static(tmp_dist)

            cfg = {
                "exf_cut": "Saturday",
                "etd_cut": DEFAULT_CONFIG["etd_cut"],
                "output_cut": DEFAULT_CONFIG["output_cut"],
                "gb_cut": DEFAULT_CONFIG["gb_cut"],
                "etd_packout_offset": DEFAULT_CONFIG["etd_packout_offset"],
            }
            versions = []
            for fp in input_files:
                v = process_file(fp, cfg)
                if v:
                    versions.append(v)

            meta = {"generated_at": __import__('datetime').datetime.now().isoformat(), "count": len(versions), "note": "Full offline export via Download Static HTML button", "full_offline": True, "client_engine": True}
            data_js_path = tmp_dist / "data.js"
            generate_data_js(versions, data_js_path, meta, include_schema=True)
            try_bundle_xlsx_lib(tmp_dist, index_path)
            inject_data_js(index_path)

            # Create zip of dist
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(tmp_dist):
                    for file in files:
                        full_path = Path(root) / file
                        rel_path = full_path.relative_to(tmp_dist)
                        zf.write(full_path, arcname=str(rel_path))
            zip_buf.seek(0)

            # Cleanup tmp
            shutil.rmtree(tmp_dist, ignore_errors=True)

            from flask import send_file
            return send_file(zip_buf, mimetype='application/zip', as_attachment=True, download_name=f"offline_static_dist_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")

        except Exception as e:
            import traceback
            traceback.print_exc()
            from flask import jsonify
            return jsonify({"error": f"Export static failed: {e}"}), 500

    @app.route('/')
    def index():
        return send_from_directory(os.path.join(app.static_folder, 'global'), 'index.html')

    return app
