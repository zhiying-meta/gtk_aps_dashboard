"""Entry point for the application"""
import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", app.config.get("PORT", 8501)))
    print(f"🌐 http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
