import os

PORT = 8502
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # Increased for V2V large folder uploads (Ivy folders 50M+ each, total 100M+)

# Uploads folder is always project_root/uploads (simple, no packaging logic)
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
