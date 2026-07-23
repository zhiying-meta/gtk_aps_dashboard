"""
Unified upload handling - to reduce duplication across modules
Provides helpers for collecting files from request.files and classifying them.
"""
import os
import shutil
import tempfile
from pathlib import Path

from app.common.zip_handler import is_zip_file, extract_zip_to_tmp
from app.common.xlsx_validator import is_valid_xlsx_by_content


def collect_uploaded_files(request_files):
    """Collect all files from request.files regardless of key - IO-style."""
    all_files = []
    for key in request_files:
        all_files.extend([(key, f) for f in request_files.getlist(key)])
    return all_files


def save_and_classify_files(all_files, tmp_extract_dir, work_dir, classify_func, allowed_keywords=None):
    """
    Common flow:
    - Handle zip files -> extract
    - Save regular files to tmp with _raw_ prefix
    - Classify into target names via classify_func(filename, field) -> target_name or None
    Returns (final_files_list, uploaded_info_list)
    """
    pending_regular = []
    for field_key, f in all_files:
        if not f.filename:
            continue
        fname = f.filename
        if is_zip_file(fname):
            zip_tmp = os.path.join(work_dir, f"_upload_{field_key}_{os.path.basename(fname)}")
            f.save(zip_tmp)
            extracted = extract_zip_to_tmp(zip_tmp, tmp_extract_dir, allowed_keywords=allowed_keywords)
            for ep in extracted:
                # Try classify
                target_name = classify_func(os.path.basename(ep), os.path.basename(ep)) if classify_func else None
                if target_name:
                    dest = os.path.join(tmp_extract_dir, target_name)
                    if os.path.abspath(ep) != os.path.abspath(dest) and not os.path.exists(dest):
                        shutil.copyfile(ep, dest)
                    # remove dup if different
                    try:
                        if os.path.exists(ep) and os.path.abspath(ep) != os.path.abspath(dest):
                            os.remove(ep)
                    except Exception:
                        pass
                else:
                    pending_regular.append((field_key, ep, True))
            try:
                os.remove(zip_tmp)
            except Exception:
                pass
        else:
            safe_name = os.path.basename(fname)
            if not safe_name:
                continue
            temp_path = os.path.join(tmp_extract_dir, f"_raw_{field_key}_{safe_name}")
            c = 1
            b, e = os.path.splitext(temp_path)
            while os.path.exists(temp_path):
                temp_path = f"{b}_{c}{e}"
                c += 1
            f.save(temp_path)
            pending_regular.append((field_key, temp_path, True))

    # Second pass classify remaining
    for field_key, f_or_path, is_path in pending_regular:
        src_path = f_or_path
        if not os.path.exists(src_path):
            continue
        fname = os.path.basename(src_path)
        target_filename = classify_func(fname, field_key) if classify_func else None

        # Handle _raw_ prefix stripping for classify retry
        if not target_filename and fname.startswith("_raw_"):
            orig = "_".join(fname.split("_")[2:]) if "_" in fname else fname
            target_filename = classify_func(orig, field_key) if classify_func else None

        if target_filename:
            dest = os.path.join(tmp_extract_dir, target_filename)
            if not os.path.exists(dest):
                shutil.copyfile(src_path, dest)

    # Collect final files (excluding _raw_ and _upload_ temp)
    final_files = []
    for root, _, files in os.walk(tmp_extract_dir):
        for fn in files:
            if fn.startswith("_raw_") or fn.startswith("_upload_"):
                continue
            fp = os.path.join(root, fn)
            if os.path.isfile(fp):
                final_files.append(fp)

    return final_files
