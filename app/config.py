import os

PORT = 8502
MAX_CONTENT_LENGTH = 100 * 1024 * 1024
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
