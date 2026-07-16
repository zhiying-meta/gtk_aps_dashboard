import os

PORT = 8502
MAX_CONTENT_LENGTH = 100 * 1024 * 1024

# Uploads folder is always project_root/uploads (simple, no packaging logic)
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
