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

    # Optional io_report module if present (feat/io-report branch)
    try:
        from app.modules.io_report.routes import io_bp
        app.register_blueprint(io_bp)
    except Exception:
        pass

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

    @app.route('/')
    def index():
        return send_from_directory(os.path.join(app.static_folder, 'global'), 'index.html')

    return app
