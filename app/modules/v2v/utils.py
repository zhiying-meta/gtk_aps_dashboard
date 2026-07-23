"""
V2V Utils - File recognition, parsing helpers
"""
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import openpyxl

from .config import TABLE_DEFS

# Refactored: use common date utils to remove duplication
from app.common.date_utils import DATE_FORMATS as _DATE_FORMATS
from app.common.date_utils import normalize_date_str, to_saturday


def identify_table_type(filename: str) -> Optional[str]:
    """
    Identify table type by filename keywords fuzzy match
    Returns table key or None
    """
    fname_lower = filename.lower()
    # Remove extension
    fname_no_ext = os.path.splitext(fname_lower)[0]

    best_match = None
    best_score = 0

    for table_key, defn in TABLE_DEFS.items():
        for kw in defn["keywords"]:
            kw_lower = kw.lower()
            if kw_lower in fname_lower:
                # Score by keyword length (longer more specific)
                score = len(kw_lower)
                if score > best_score:
                    best_score = score
                    best_match = table_key

    # Special handling: BOM快照.xlsx exact
    if "bom" in fname_lower:
        return "bom"
    if "fcst主表" in fname_lower or ("fcst" in fname_lower and "主表" in fname_lower):
        return "fcst"
    if "fcst明细" in fname_lower or ("fcst" in fname_lower and "明细" in fname_lower):
        return "fcst_detail"
    # actual_io removed per user request 2026-07-21 - no longer compared
    # if "实际值" in fname_lower or "actual" in fname_lower:
    #     return "actual_io"
    if "supply" in fname_lower or "供应" in fname_lower:
        return "supply"
    if "切换矩阵" in fname_lower or "switch" in fname_lower:
        return "switch"
    if "料号快照" in fname_lower:
        return "item"
    if "线体日历" in fname_lower:
        return "calendar"
    if "线体快照" in fname_lower and "日历" not in fname_lower:
        return "line"
    if "计划设置" in fname_lower:
        return "plan_config"
    if "排产结果" in fname_lower:
        return "plan_output"
    if "结存" in fname_lower:
        return "balance"

    return best_match


def scan_folder_for_tables(folder_path: str) -> Dict:
    """
    Scan a folder containing xlsx files and identify each table type
    Returns: {table_key: file_path, ...} + stats
    """
    result = {
        "tables": {},
        "files": [],
        "unrecognized": [],
        "stats": {}
    }

    if not os.path.exists(folder_path):
        return result

    for fname in os.listdir(folder_path):
        fpath = os.path.join(folder_path, fname)
        if not os.path.isfile(fpath):
            continue
        if not fname.lower().endswith(".xlsx"):
            continue
        if fname.startswith("~$"):  # ignore temp excel files
            continue

        file_info = {
            "filename": fname,
            "path": fpath,
            "size": os.path.getsize(fpath),
            "identified_as": None
        }

        table_type = identify_table_type(fname)
        file_info["identified_as"] = table_type

        if table_type:
            result["tables"][table_type] = fpath
        else:
            result["unrecognized"].append(file_info)

        result["files"].append(file_info)

    # Stats
    result["stats"] = {
        "total_files": len(result["files"]),
        "recognized": len(result["tables"]),
        "unrecognized_count": len(result["unrecognized"]),
        "expected": len(TABLE_DEFS),
        "missing": [k for k in TABLE_DEFS.keys() if k not in result["tables"]]
    }

    return result


def read_excel_headers(file_path: str, max_cols: int = 50) -> List[str]:
    """Read first row headers from excel"""
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        headers = []
        for c in range(1, min(max_cols, ws.max_column + 1)):
            v = ws.cell(1, c).value
            if v is not None:
                headers.append(str(v).strip())
            else:
                headers.append("")
        wb.close()
        return [h for h in headers if h]
    except Exception as e:
        return []


def read_excel_as_dicts(file_path: str, usecols: List[str] = None, max_rows: int = None) -> List[Dict]:
    """
    Read excel into list of dicts, first row as header
    Optionally filter columns
    """
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        headers = []
        for c in range(1, ws.max_column + 1):
            v = ws.cell(1, c).value
            if v is None:
                headers.append(f"COL_{c}")
            else:
                headers.append(str(v).strip())

        rows = []
        row_count = 0
        for r in ws.iter_rows(min_row=2, values_only=True):
            row_count += 1
            if max_rows and row_count > max_rows:
                break
            d = {}
            for idx, val in enumerate(r):
                if idx >= len(headers):
                    break
                h = headers[idx]
                if usecols and h not in usecols:
                    continue
                d[h] = val
            rows.append(d)

        wb.close()
        return rows, headers
    except Exception as e:
        return [], []


def parse_folder_data(folder_path: str, sample_rows: int = 5) -> Dict:
    """
    Parse all tables in a folder, returning dataframes or dicts + metadata
    For MVP, we use lightweight reading (headers + row counts)
    Returns detailed info for frontend display
    """
    scan = scan_folder_for_tables(folder_path)
    parsed = {
        "folder": folder_path,
        "folder_name": os.path.basename(folder_path),
        "scan": scan,
        "tables_data": {}
    }

    # For each identified table, read basic info
    for table_key, fpath in scan["tables"].items():
        try:
            rows, headers = read_excel_as_dicts(fpath, max_rows=sample_rows)
            # Get full row count quickly
            wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
            ws = wb.active
            total_rows = ws.max_row - 1  # minus header
            wb.close()

            parsed["tables_data"][table_key] = {
                "file": os.path.basename(fpath),
                "path": fpath,
                "headers": headers,
                "sample_rows": rows[:sample_rows],
                "total_rows": total_rows,
                "status": "ok"
            }
        except Exception as e:
            parsed["tables_data"][table_key] = {
                "file": os.path.basename(fpath),
                "path": fpath,
                "error": str(e),
                "status": "error"
            }

    return parsed


def get_folder_date_range(parsed_data: Dict) -> Dict:
    """
    Try to extract date range from actual_io or plan_output data
    Returns min/max plan date
    """
    # Simplified: try to read date ranges from files if available
    # For now just return placeholder
    return {
        "min_date": None,
        "max_date": None
    }


def clean_version_name(folder_name: str) -> str:
    """Clean folder name for display"""
    name = folder_name
    # Remove common prefixes/suffixes but keep meaningful date
    # e.g., Ivy-20260716-gated-v2 -> 20260716-v2
    # Keep as is for now, but truncate if too long
    if len(name) > 30:
        return name[:30] + "..."
    return name
