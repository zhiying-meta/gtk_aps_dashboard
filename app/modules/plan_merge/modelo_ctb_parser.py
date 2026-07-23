"""
Modelo CTB Parser - Handles MPM's irregular CTB format (optimized)
- Modelo GB CTB Publish 0722.xlsx with MP FrameModule sections
- Modelo SKU CTB Publish 0722.xlsx with SKU explicit

GB file: module headers like "MP Frame Module TTL", materials before next module.
Each material row has style, color, usage but no explicit GB PN - need to map via item master.

SKU file has explicit SKU PN.

Output: {PN: {date_str: cumulative_value}}
"""
import os
from collections import defaultdict
from datetime import datetime

import pandas as pd

STYLE_MAP = {
    "rectangle m": "rec m",
    "rectangle l": "rec l",
    "rectangle": "rec",
    "rec m": "rec m",
    "rec l": "rec l",
    "rec": "rec",
    "bold": "bold",
    "cateye": "cateye",
    "panthos m": "panthos m",
    "panthos s": "panthos s",
    "panthos": "panthos",
    "slim oval": "slim",
    "slim": "slim",
    "common": "common",
}

def normalize_style(s):
    if not s:
        return "", ""
    low = str(s).strip().lower()
    low = low.replace("rectangle", "rec").replace("  ", " ").strip()
    nospace = low.replace(" ", "")
    return low, nospace

def styles_match(ctb_style, item_style):
    if not ctb_style or not item_style:
        return False
    ctb_low, ctb_nospace = normalize_style(ctb_style)
    item_low, item_nospace = normalize_style(item_style)
    if ctb_low == item_low or ctb_nospace == item_nospace:
        return True
    ctb_canon = STYLE_MAP.get(ctb_low, ctb_low)
    item_canon = STYLE_MAP.get(item_low, item_low)
    if ctb_canon == item_canon or ctb_canon.replace(" ", "") == item_canon.replace(" ", ""):
        return True
    # fuzzy: slim, bold, cateye, panthos
    for kw in ("slim", "bold", "cateye", "panthos m", "panthos s", "panthos"):
        if kw in ctb_low and kw in item_low:
            return True
    if "rec" in ctb_low and "rec" in item_low:
        # check M/L
        if (" m" in ctb_low or ctb_low.endswith("m")) and (" m" in item_low or item_low.endswith("m")):
            return True
        if (" l" in ctb_low or ctb_low.endswith("l")) and (" l" in item_low or item_low.endswith("l")):
            return True
        if ctb_low == "rec" or item_low == "rec":
            return True
    return False

def colors_match(ctb_color, item_color):
    if not ctb_color or not item_color:
        return False
    c1 = str(ctb_color).strip().lower()
    c2 = str(item_color).strip().lower()
    if c1 == c2:
        return True
    if "low cost" in c1 and "low cost" in c2:
        base1 = c1.replace("(low cost)", "").replace("deep", "").strip()
        base2 = c2.replace("(low cost)", "").replace("deep", "").strip()
        if base1 == base2 or "black" in c1 and "black" in c2:
            return True
        if base1 in c2 or base2 in c1:
            return True
    if c1 in c2 or c2 in c1:
        return True
    if "black ice" in c1 and "black ice" in c2:
        return True
    return False

def _norm_date(s):
    if pd.isna(s):
        return ""
    try:
        dt = pd.to_datetime(str(s), errors='coerce')
        if pd.isna(dt):
            return str(s).strip()
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(s).strip()

def _clean(v):
    if pd.isna(v):
        return ""
    return str(v).strip()

def _load_sheet_data(file_path):
    """Load workbook and return dict of sheet_name -> list of rows (values_only) for fast parsing"""
    import openpyxl
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    sheets_data = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        # Read first 20 rows for header detection
        # and all rows as list for module parsing? We'll read all at once via iter_rows but cache
        # For efficiency, read all rows as list of tuples
        try:
            # Limit to max 1000 rows for header search, but for data we need up to maybe 1000 rows
            # Read entire sheet as list (may be heavy but okay for 800x400 = 320k cells)
            # Use iter_rows with values_only
            rows = list(ws.iter_rows(values_only=True))
            sheets_data[sheet_name] = rows
        except Exception as e:
            print(f"[Modelo] failed to read sheet {sheet_name}: {e}")
            continue
    wb.close()
    return sheets_data

def _find_dates_and_header(rows):
    """
    rows: list of tuples (from sheet)
    Returns (header_idx, date_row_idx, date_col_start, dates_list)
    header_idx is index in rows list (0-based) where Title/Process header is
    date_row_idx is index where dates are
    """
    header_idx = None
    date_row_idx = None
    date_col_start = None
    dates = []

    # Search first 20 rows for header
    for i in range(min(20, len(rows))):
        r = rows[i]
        if not r:
            continue
        # Convert to list of str lower
        # Check col0 == Title and col4 == Process or col2 == Style
        c0 = str(r[0]).strip().lower() if r[0] else ""
        c2 = str(r[2]).strip().lower() if len(r) > 2 and r[2] else ""
        c4 = str(r[4]).strip().lower() if len(r) > 4 and r[4] else ""
        if c0 == "title" and ("process" in c4 or "style" in c2 or "frame color" in c2):
            header_idx = i
            # Look for date row: check row above and same row for datetime in col 9 onwards
            for dr_idx in [i-1, i]:
                if dr_idx < 0 or dr_idx >= len(rows):
                    continue
                dr = rows[dr_idx]
                # Count datetime-like in col 9 onwards
                dt_count = 0
                temp_dates = []
                temp_start = None
                for c_idx in range(9, min(len(dr), 50)):
                    v = dr[c_idx]
                    if v:
                        try:
                            dt = pd.to_datetime(v, errors='coerce')
                            if not pd.isna(dt):
                                if temp_start is None:
                                    temp_start = c_idx
                                temp_dates.append(dt.strftime("%Y-%m-%d"))
                                dt_count += 1
                        except:
                            pass
                if dt_count >= 3:
                    date_row_idx = dr_idx
                    date_col_start = temp_start
                    dates = temp_dates
                    # Continue to collect all dates from this row to end
                    # Actually we already have first 40 cols, need to continue beyond 50
                    # For now we have partial, we will extend later
                    break
            if dates:
                break

    # Fallback: dates in row 1 (index 1) from col 9
    if not dates:
        for i in range(min(5, len(rows))):
            r = rows[i]
            if not r or len(r) < 10:
                continue
            temp_dates = []
            temp_start = None
            for c_idx in range(9, len(r)):
                v = r[c_idx]
                if v:
                    try:
                        dt = pd.to_datetime(v, errors='coerce')
                        if not pd.isna(dt):
                            if temp_start is None:
                                temp_start = c_idx
                            temp_dates.append(dt.strftime("%Y-%m-%d"))
                    except:
                        pass
            if len(temp_dates) >= 5:
                date_row_idx = i
                date_col_start = temp_start
                dates = temp_dates
                header_idx = i+1
                break

    return header_idx, date_row_idx, date_col_start, dates

def _get_full_dates_from_rows(rows, date_row_idx, date_col_start):
    """Re-extract full dates from date row, including all columns"""
    if date_row_idx is None or date_row_idx >= len(rows):
        return []
    r = rows[date_row_idx]
    dates = []
    for c_idx in range(date_col_start, len(r)):
        v = r[c_idx]
        if v is None:
            continue
        try:
            dt = pd.to_datetime(v, errors='coerce')
            if not pd.isna(dt):
                dates.append(dt.strftime("%Y-%m-%d"))
        except:
            continue
    return dates

def _find_module_boundaries(rows, target_keyword="MP Frame Module"):
    """
    Find module headers: rows where col4 contains "Module" and col5 contains "TTL"
    Returns list of (row_idx, module_name) and target start/end
    """
    headers = []
    for i, r in enumerate(rows):
        if not r or len(r) < 6:
            continue
        c4 = str(r[4]).strip() if r[4] else ""
        c5 = str(r[5]).strip() if len(r) > 5 and r[5] else ""
        if "Module" in c4 and "TTL" in c5:
            headers.append((i, c4))
        elif "Frame Module" in c4 and "TTL" in c5:
            headers.append((i, c4))
        elif "Lens" in c4 and "TTL" in c5:
            headers.append((i, c4))
        elif c4 and "Module" in c4:
            # Also check if col5 is TTL
            if c5 and "TTL" in c5:
                headers.append((i, c4))

    # More precise: look for rows where col4 contains target_keyword
    target_start = None
    target_end = len(rows)
    # Find all headers that contain Module
    all_mod_headers = []
    for i, r in enumerate(rows):
        if not r or len(r) < 6:
            continue
        c4 = str(r[4]).strip() if r[4] else ""
        c5 = str(r[5]).strip() if len(r) > 5 and r[5] else ""
        # Condition: col4 contains "Module" and (col5 contains TTL or col4 contains TTL)
        if ("Module" in c4 and ("TTL" in c5 or "TTL" in c4)) or (target_keyword.lower() in c4.lower() and "TTL" in c5):
            all_mod_headers.append((i, c4))

    # Also include generic: if row has "MP Frame Module" in col4
    for i, r in enumerate(rows):
        if not r or len(r) < 5:
            continue
        c4 = str(r[4]).strip() if r[4] else ""
        if target_keyword.lower() in c4.lower() and "TTL" in str(r[5]).lower() if len(r) > 5 and r[5] else False:
            # Already captured
            pass

    for idx, (row_idx, mod_name) in enumerate(all_mod_headers):
        if target_keyword.lower() in mod_name.lower():
            target_start = row_idx + 1
            if idx + 1 < len(all_mod_headers):
                target_end = all_mod_headers[idx+1][0]
            else:
                target_end = len(rows)
            break

    return target_start, target_end, all_mod_headers

def parse_modelo_gb_ctb(file_path, item_gb_list):
    """
    Parse Modelo GB CTB
    item_gb_list: list of dicts with ITEM_NO, SYLTE, COLOR, PURPOSE
    """
    sheets_data = _load_sheet_data(file_path)
    # Find target sheet
    target_sheet_name = None
    for name in sheets_data.keys():
        if "GB CTB" in name and "V2V" not in name:
            target_sheet_name = name
            break
    if not target_sheet_name:
        # Take first sheet that has Frame Module
        for name, rows in sheets_data.items():
            for r in rows[:50]:
                if r and len(r) > 4 and r[4] and "Frame Module" in str(r[4]):
                    target_sheet_name = name
                    break
            if target_sheet_name:
                break
    if not target_sheet_name:
        target_sheet_name = list(sheets_data.keys())[0] if sheets_data else None

    if not target_sheet_name:
        raise ValueError(f"No sheet found in {file_path}")

    rows = sheets_data[target_sheet_name]

    header_idx, date_row_idx, date_col_start, dates = _find_dates_and_header(rows)
    if not dates or date_col_start is None:
        # Try to get full dates
        if date_row_idx is not None and date_col_start is not None:
            dates = _get_full_dates_from_rows(rows, date_row_idx, date_col_start)
        if not dates:
            raise ValueError(f"Could not find dates in sheet {target_sheet_name}")

    # Ensure full dates from date row (extend beyond initial 50 cols)
    full_dates = _get_full_dates_from_rows(rows, date_row_idx, date_col_start)
    if len(full_dates) > len(dates):
        dates = full_dates

    target_start, target_end, all_mods = _find_module_boundaries(rows, target_keyword="MP Frame Module")
    if target_start is None:
        # Fallback: if no MP Frame Module found, try any Frame Module
        target_start, target_end, _ = _find_module_boundaries(rows, target_keyword="Frame Module")
        if target_start is None:
            # Fallback to data after header
            target_start = (header_idx or 2) + 1
            target_end = len(rows)

    gb_ctb = defaultdict(dict)

    if not item_gb_list:
        raise ValueError("item_gb_list empty")

    for r_idx in range(target_start, min(target_end, len(rows))):
        r = rows[r_idx]
        if not r or len(r) < 7:
            continue
        c0 = str(r[0]).strip() if r[0] else ""
        c4 = str(r[4]).strip() if len(r) > 4 and r[4] else ""
        c5 = str(r[5]).strip() if len(r) > 5 and r[5] else ""
        c6 = str(r[6]).strip() if len(r) > 6 and r[6] else ""
        # Filter: must be CTB and MP
        if c0 != "CTB":
            continue
        if c4 != "MP":
            continue
        style = _clean(c5)
        color = _clean(c6)
        if not style or not color:
            continue

        # Find matching GB
        matched = None
        for item in item_gb_list:
            if styles_match(style, item.get("SYLTE")) and colors_match(color, item.get("COLOR")):
                matched = item.get("ITEM_NO")
                break

        if not matched:
            continue

        # Extract values
        # Date values start at date_col_start
        for d_idx, date_str in enumerate(dates):
            col = date_col_start + d_idx
            if col >= len(r):
                break
            v = r[col]
            if v is None:
                continue
            try:
                fv = float(v)
                if pd.isna(fv):
                    continue
            except:
                continue
            # Sum if duplicate
            existing = gb_ctb[matched].get(date_str, 0)
            gb_ctb[matched][date_str] = existing + fv if existing else fv

    return {k: dict(v) for k, v in gb_ctb.items()}

def parse_modelo_sku_ctb(file_path):
    """
    Parse Modelo SKU CTB - has explicit SKU
    Returns {SKU: {date: value}}
    """
    sheets_data = _load_sheet_data(file_path)
    target_sheet_name = None
    for name in sheets_data.keys():
        if "SKU CTB" in name and "V2V" not in name:
            target_sheet_name = name
            break
    if not target_sheet_name:
        target_sheet_name = list(sheets_data.keys())[0] if sheets_data else None

    if not target_sheet_name:
        raise ValueError(f"No sheet found in {file_path}")

    rows = sheets_data[target_sheet_name]
    header_idx, date_row_idx, date_col_start, dates = _find_dates_and_header(rows)

    if not dates:
        # Fallback dates from row 1
        dates = _get_full_dates_from_rows(rows, 1, 9) if len(rows) > 1 else []
        date_col_start = 9
        header_idx = 2

    if not dates:
        raise ValueError(f"Could not find dates in SKU CTB {target_sheet_name}")

    full_dates = _get_full_dates_from_rows(rows, date_row_idx, date_col_start) if date_row_idx is not None else []
    if len(full_dates) > len(dates):
        dates = full_dates

    # Find SKU col: in header row, col where value == "SKU"
    sku_col = None
    if header_idx is not None and header_idx < len(rows):
        hr = rows[header_idx]
        for c_idx, val in enumerate(hr):
            if val and str(val).strip().upper() == "SKU":
                sku_col = c_idx
                break
    if sku_col is None:
        sku_col = 6  # Default observed

    sku_ctb = defaultdict(dict)

    start_row = (header_idx or 2) + 1
    for r_idx in range(start_row, len(rows)):
        r = rows[r_idx]
        if not r or len(r) <= sku_col:
            continue
        c0 = str(r[0]).strip() if r[0] else ""
        if c0 != "CTB":
            continue
        sku = r[sku_col]
        if not sku:
            continue
        sku = str(sku).strip()
        if not sku.startswith("SK-"):
            continue

        for d_idx, date_str in enumerate(dates):
            col = date_col_start + d_idx
            if col >= len(r):
                break
            v = r[col]
            if v is None:
                continue
            try:
                fv = float(v)
                if pd.isna(fv):
                    continue
            except:
                continue
            existing = sku_ctb[sku].get(date_str, 0)
            sku_ctb[sku][date_str] = existing + fv if existing else fv

    return {k: dict(v) for k, v in sku_ctb.items()}

def parse_item_snapshot_for_gb_mapping(file_path):
    import openpyxl
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = rows[0]
    col_map = {}
    for idx, h in enumerate(header):
        if h:
            col_map[str(h).strip().upper()] = idx

    item_no_col = col_map.get("ITEM_NO", 0)
    prod_cat_col = col_map.get("PRODUCT_CATEGORY", 3)
    purpose_col = col_map.get("PURPOSE", 8)
    style_col = col_map.get("SYLTE", col_map.get("STYLE", col_map.get("PRODUCT_STYLE", 9)))
    color_col = col_map.get("COLOR", 10)

    gb_list = []
    for r in rows[1:]:
        if not r or len(r) <= item_no_col:
            continue
        item_no = r[item_no_col]
        if not item_no:
            continue
        item_no = str(item_no).strip()
        if not item_no.startswith("GB-"):
            continue
        prod_cat = r[prod_cat_col] if prod_cat_col < len(r) else None
        purpose = r[purpose_col] if purpose_col < len(r) else None
        style = r[style_col] if style_col < len(r) else None
        color = r[color_col] if color_col < len(r) else None
        gb_list.append({
            "ITEM_NO": item_no,
            "PRODUCT_CATEGORY": prod_cat,
            "PURPOSE": purpose,
            "SYLTE": style,
            "COLOR": color,
        })

    wb.close()
    return gb_list
