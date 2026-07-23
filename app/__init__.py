import os
from flask import Flask, send_from_directory


def _register_blueprints(app):
    """Register all module blueprints - kept separate for clarity"""
    from app.modules.plan_merge import plan_merge_bp
    app.register_blueprint(plan_merge_bp)

    try:
        from app.modules.v2v import v2v_bp
        app.register_blueprint(v2v_bp)
        print("✅ V2V module registered")
    except Exception as e:
        print(f"⚠️ V2V module failed to load: {e}")

    try:
        from app.modules.io_report import io_bp
        app.register_blueprint(io_bp)
    except Exception as e:
        print(f"[app] io_report not loaded: {e}")

    try:
        from app.modules.utilization_report import util_bp
        app.register_blueprint(util_bp)
    except Exception as e:
        print(f"[app] utilization_report not loaded: {e}")


def create_app():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(project_root, 'static')

    app = Flask(__name__, static_folder=static_dir, static_url_path="/static")
    app.config.from_object("app.config")

    try:
        os.makedirs(app.config.get("UPLOAD_FOLDER", "uploads"), exist_ok=True)
    except Exception:
        pass

    _register_blueprints(app)

    @app.errorhandler(413)
    def handle_413(e):
        # Return JSON for API routes, HTML for others
        from flask import request, jsonify
        if request.path.startswith('/api/'):
            return jsonify({"error": f"File too large (413), max {app.config.get('MAX_CONTENT_LENGTH', 0)//1024//1024}MB"}), 413
        return e

    @app.errorhandler(500)
    def handle_500(e):
        from flask import request, jsonify
        if request.path.startswith('/api/'):
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Internal server error (500): {e}"}), 500
        return e

    @app.errorhandler(404)
    def handle_404(e):
        from flask import request, jsonify
        if request.path.startswith('/api/'):
            return jsonify({"error": f"API not found (404): {request.path}"}), 404
        return e

    @app.after_request
    def no_cache(resp):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp

    @app.route('/api/export/static/dist', methods=['GET'])
    def export_static_dist():
        """Export full static offline site - delegates to export_static module"""
        import tempfile
        import shutil
        from pathlib import Path
        try:
            from export_static import (
                copy_static, generate_data_js, try_bundle_xlsx_lib,
                inject_data_js, process_file, DEFAULT_CONFIG, find_default_inputs
            )
            from app.common.static_export import build_static_response_from_export
            import datetime

            tmp_dist = Path(tempfile.mkdtemp(prefix="static_dist_"))
            index_path = copy_static(tmp_dist)

            cfg = {
                "exf_cut": "Saturday",
                "etd_cut": DEFAULT_CONFIG["etd_cut"],
                "output_cut": DEFAULT_CONFIG["output_cut"],
                "gb_cut": DEFAULT_CONFIG["gb_cut"],
                "etd_packout_offset": DEFAULT_CONFIG["etd_packout_offset"],
            }
            versions = [v for fp in find_default_inputs() if (v := process_file(fp, cfg))]

            meta = {
                "generated_at": datetime.datetime.now().isoformat(),
                "count": len(versions),
                "note": "Full offline export via Download Static HTML button",
                "full_offline": True,
                "client_engine": True,
            }
            generate_data_js(versions, tmp_dist / "data.js", meta, include_schema=True)
            try_bundle_xlsx_lib(tmp_dist, index_path)
            inject_data_js(index_path)

            zip_buf = build_static_response_from_export(tmp_dist)
            shutil.rmtree(tmp_dist, ignore_errors=True)

            from flask import send_file
            return send_file(
                zip_buf, mimetype='application/zip', as_attachment=True,
                download_name=f"offline_static_dist_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            from flask import jsonify
            return jsonify({"error": f"Export static failed: {e}"}), 500

    @app.route('/')
    def index():
        return send_from_directory(os.path.join(app.static_folder, 'global'), 'index.html')

    return app
