import os
from flask import Flask, send_from_directory

def create_app():
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
    app = Flask(__name__, static_folder=static_dir, static_url_path='/static')
    app.config.from_object('app.config')

    from app.modules.plan_merge import plan_merge_bp
    app.register_blueprint(plan_merge_bp)
    from app.modules.io_report.routes import io_bp
    app.register_blueprint(io_bp)

    @app.after_request
    def no_cache(resp):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp

    @app.route('/')
    def index():
        return send_from_directory(os.path.join(app.static_folder, 'global'), 'index.html')

    return app
