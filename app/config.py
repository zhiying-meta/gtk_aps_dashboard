import os
import sys
import tempfile

PORT = 8502
MAX_CONTENT_LENGTH = 100 * 1024 * 1024


def _get_upload_folder():
    # When frozen (PyInstaller), use writable location
    if getattr(sys, 'frozen', False):
        # Try user data dir
        base = os.path.join(os.path.expanduser("~"), ".production_plan_review")
        try:
            os.makedirs(base, exist_ok=True)
            return os.path.join(base, "uploads")
        except Exception:
            # Fallback to temp
            return os.path.join(tempfile.gettempdir(), "production_plan_review_uploads")
    # Dev mode: project_root/uploads
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')


UPLOAD_FOLDER = _get_upload_folder()
