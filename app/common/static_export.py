"""
Static export helpers - unified logic for offline static export
"""
import os
import io
import shutil
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


def build_static_response_from_export(tmp_dist_path: Path):
    """Create zip response from dist dir - reused in app/__init__.py"""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(tmp_dist_path):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(tmp_dist_path)
                zf.write(full_path, arcname=str(rel_path))
    zip_buf.seek(0)
    return zip_buf
