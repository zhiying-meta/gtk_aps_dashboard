"""
Unified zip handling - previously duplicated in 4 modules
"""
import os
import shutil
import zipfile


def is_zip_file(filename: str) -> bool:
    return filename.lower().endswith(".zip")


def extract_zip_to_tmp(zip_path: str, tmp_dir: str, allowed_keywords=None, min_size=1024, skip_exts=None):
    """
    Extract xlsx files from zip to tmp_dir.
    - allowed_keywords: list of keywords to allow even if not .xlsx (e.g. ["料号","BOM","gated"])
    - min_size: minimum file size to consider
    - skip_exts: extensions to skip (e.g. .txt, .pdf)
    Returns list of extracted file paths that are valid xlsx (or match keywords)
    """
    if skip_exts is None:
        skip_exts = ('.txt', '.csv', '.pdf', '.png', '.jpg', '.docx')

    extracted = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                raw_name = info.filename
                base = os.path.basename(raw_name)
                if not base or base.startswith('.') or base.startswith('~$'):
                    continue
                low = base.lower()

                # Decision logic - permissive but safe
                should_extract = False
                if low.endswith('.xlsx'):
                    should_extract = True
                elif allowed_keywords and any(kw.lower() in low or kw.lower() in raw_name.lower() for kw in allowed_keywords):
                    should_extract = True
                elif info.file_size > min_size and not low.endswith(skip_exts):
                    # fallback: extract files >1KB that are not obviously non-excel
                    if '.' not in low or low.endswith(('.xls', '.xlsx')):
                        should_extract = True
                    elif '.' not in low:
                        should_extract = True

                if not should_extract and info.file_size > min_size and not low.endswith(skip_exts):
                    # Extra fallback for unknown but sizeable files
                    if info.file_size > 1024:
                        should_extract = True

                if not should_extract:
                    continue

                base = base.strip()
                if not base:
                    continue
                target_path = os.path.join(tmp_dir, base)
                c = 1
                bname, ext = os.path.splitext(target_path)
                while os.path.exists(target_path):
                    target_path = f"{bname}_{c}{ext}"
                    c += 1
                try:
                    with zf.open(info) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    # Validate content
                    from app.common.xlsx_validator import is_valid_xlsx_by_content
                    if is_valid_xlsx_by_content(target_path):
                        extracted.append(target_path)
                    else:
                        # Keep if name matches keywords
                        if allowed_keywords and any(kw.lower() in base.lower() for kw in allowed_keywords):
                            extracted.append(target_path)
                        else:
                            try:
                                os.remove(target_path)
                            except Exception:
                                pass
                except Exception as ex:
                    print(f"[zip_handler] extract file {base} failed: {ex}")
                    continue
    except Exception as e:
        print(f"[zip_handler] zip extract failed {e}")
        import traceback
        traceback.print_exc()
    return extracted


def extract_all_xlsx(zip_path: str, tmp_dir: str):
    """Simple extraction - only xlsx files"""
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if not info.filename.lower().endswith(".xlsx"):
                    continue
                base = os.path.basename(info.filename)
                target_path = os.path.join(tmp_dir, base)
                with zf.open(info) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted.append(target_path)
    except Exception as e:
        print(f"[zip_handler] zip extract failed {e}")
    return extracted
