"""
Inventory Dashboard Engine - Build dashboard_data.json from Balance + BOM
Ported from gtk-aps-inventory-analysis backend logic, but adapted to use
existing Balance data (already calculated) from io_report cache.

Data structure expected by frontend:
{
  "timeBuckets": ["2026-05-24 白班", "2026-05-24 夜班", ...],
  "inventory": { "SK-xxx": { "2026-05-24 白班": 123, ... }, ... },
  "bomChildren": { "SK-xxx": ["GB-yyy", ...], ... },
  "bomParents": { "GB-yyy": ["SK-xxx"], ... },
  "hasChildren": ["SK-xxx", ...]
}
"""
import os
import pathlib
from collections import defaultdict
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _load_workbook_robust(path: str):
    import openpyxl
    try:
        return openpyxl.load_workbook(path, data_only=True, read_only=False)
    except Exception:
        return openpyxl.load_workbook(path, data_only=True, read_only=True)


def _find_header_row(ws, expected_keywords, scan_rows=15):
    best = None
    best_score = -1
    best_headers = None
    for r_idx in range(1, scan_rows + 1):
        try:
            row = next(ws.iter_rows(min_row=r_idx, max_row=r_idx, values_only=True), None)
            if not row:
                continue
            cleaned = [str(c).strip() if c is not None else "" for c in row]
            cleaned_upper = [c.upper() for c in cleaned]
            score = 0
            for kw in expected_keywords:
                kw_up = kw.upper()
                for c_up in cleaned_upper:
                    if not c_up:
                        continue
                    if kw_up == c_up or kw_up in c_up:
                        score += 1
                        break
            if score > best_score:
                best_score = score
                best = r_idx
                best_headers = list(row)
        except Exception:
            continue
    if best is not None and best_score >= 1:
        return best, best_headers, best_score
    try:
        first = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        return 1, list(first) if first else [], 0
    except Exception:
        return 1, [], 0


def _get_col_index(headers: List, candidates: List[str]) -> int:
    if not headers:
        return -1
    norm = [(str(h).strip() if h else "", str(h).strip().upper() if h else "") for h in headers]
    for cand in candidates:
        cand_strip = str(cand).strip()
        cand_up = cand_strip.upper()
        for i, (orig, up) in enumerate(norm):
            if orig == cand_strip or up == cand_up:
                return i
    for cand in candidates:
        cand_up = str(cand).strip().upper()
        for i, (orig, up) in enumerate(norm):
            if cand_up and (cand_up in up or up in cand_up):
                return i
    return -1


def parse_bom_file(file_path: str) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], List[str]]:
    """
    Parse BOM file, return bomChildren, bomParents, hasChildren
    Expected columns: PARENT_PN_CODE and ITEM_NO (or similar)
    """
    wb = _load_workbook_robust(file_path)
    # Find best sheet
    best_sheet = None
    best_score = -1
    best_info = None
    expected = ["PARENT_PN_CODE", "PARENT", "ITEM_NO", "CHILD", "PARENT_PN", "CHILD_PN"]
    for sname in wb.sheetnames:
        try:
            ws = wb[sname]
            header_idx, headers, score = _find_header_row(ws, expected, scan_rows=15)
            if not headers:
                continue
            # Score based on having parent and child
            has_parent = _get_col_index(headers, ["PARENT_PN_CODE", "PARENT_PN", "PARENT_CODE", "PARENT", "PARENT_PN_CODE"]) >= 0
            has_child = _get_col_index(headers, ["ITEM_NO", "CHILD", "CHILD_PN", "ITEM_CODE", "COMPONENT", "CHILD_CODE"]) >= 0
            combined = (2 if has_parent else 0) + (2 if has_child else 0) + score
            # Count rows
            data_rows = 0
            try:
                for _r in ws.iter_rows(min_row=header_idx + 1, max_row=header_idx + 20, values_only=True):
                    if _r and any(c is not None and str(c).strip() != "" for c in _r):
                        data_rows += 1
            except Exception:
                data_rows = 0
            combined += min(data_rows, 10)
            if combined > best_score:
                best_score = combined
                best_sheet = sname
                best_info = (ws, header_idx, headers, score)
        except Exception:
            continue

    if not best_info:
        wb.close()
        raise ValueError(f"BOM file {os.path.basename(file_path)}: no sheet with PARENT/CHILD columns found")

    ws, header_idx, headers, score = best_info
    parent_idx = _get_col_index(headers, ["PARENT_PN_CODE", "PARENT_PN", "PARENT_CODE", "PARENT", "PARENT_ITEM", "PARENTPN"])
    child_idx = _get_col_index(headers, ["ITEM_NO", "CHILD", "CHILD_PN", "ITEM_CODE", "COMPONENT", "CHILD_CODE", "CHILD_ITEM", "ITEM"])

    # Fallback positions
    if parent_idx < 0:
        parent_idx = 0
    if child_idx < 0:
        child_idx = 1 if parent_idx == 0 else 0

    bom_children = defaultdict(list)
    bom_parents = defaultdict(list)

    for row in ws.iter_rows(min_row=header_idx + 1, values_only=True):
        if not row or len(row) <= max(parent_idx, child_idx):
            continue
        p_raw = row[parent_idx]
        c_raw = row[child_idx]
        if not p_raw or not c_raw:
            continue
        p = str(p_raw).strip()
        c = str(c_raw).strip()
        if not p or not c:
            continue
        if p.lower() in ("nan", "none") or c.lower() in ("nan", "none"):
            continue
        if c not in bom_children[p]:
            bom_children[p].append(c)
        if p not in bom_parents[c]:
            bom_parents[c].append(p)

    wb.close()

    has_children = [k for k, v in bom_children.items() if v]

    return dict(bom_children), dict(bom_parents), has_children


def build_dashboard_from_balance_rows(balance_rows, bom_children=None, bom_parents=None, has_children=None):
    """
    balance_rows: List of dict or object with attributes:
      - PlanDate (datetime or str), ShiftName (str), ItemCode (str), BalanceQty (float)
    Can also be list of BalanceRow dataclass from io_report engine.
    bom_children, bom_parents, has_children: from parse_bom_file or None
    Returns dashboard_data dict.
    """
    # Normalize bom structures
    if bom_children is None:
        bom_children = {}
    if bom_parents is None:
        bom_parents = {}
    if has_children is None:
        has_children = [k for k, v in bom_children.items() if v]

    SHIFT_ORDER = {"白班": 0, "Day": 0, "日班": 0, "白": 0, "D": 0,
                   "夜班": 1, "Night": 1, "夜": 1, "N": 1}

    time_buckets_set = set()
    inventory = defaultdict(dict)  # Part -> TimeBucket -> value

    # Also store for sorting: map timeBucket -> (date_str, shift_order)
    tb_meta = {}

    for row in balance_rows:
        # Support dict or dataclass
        if isinstance(row, dict):
            plan_date = row.get("PlanDate") or row.get("PLAN_DATE") or row.get("Date") or row.get("DATE")
            shift_name = row.get("ShiftName") or row.get("SHIFT_NAME") or row.get("Shift") or row.get("SHIFT") or "白班"
            item_code = row.get("ItemCode") or row.get("ITEM_CODE") or row.get("Part Number") or row.get("PN") or row.get("ITEM_NO")
            balance_qty = row.get("BalanceQty") if row.get("BalanceQty") is not None else row.get("BALANCE_QTY") if row.get("BALANCE_QTY") is not None else row.get("Ending_OnHand") if row.get("Ending_OnHand") is not None else row.get("Value") or 0
        else:
            # dataclass from io_report
            plan_date = getattr(row, "PlanDate", None)
            shift_name = getattr(row, "ShiftName", "") or "白班"
            item_code = getattr(row, "ItemCode", None) or getattr(row, "SKU", None)
            balance_qty = getattr(row, "BalanceQty", 0) or 0

        if not item_code:
            continue
        item_code = str(item_code).strip()
        if not item_code:
            continue

        # Normalize date to YYYY-MM-DD string
        date_str = ""
        if isinstance(plan_date, datetime):
            date_str = plan_date.strftime("%Y-%m-%d")
        elif isinstance(plan_date, date):
            date_str = plan_date.strftime("%Y-%m-%d")
        else:
            # Try parse string
            s = str(plan_date).strip() if plan_date else ""
            if not s:
                continue
            try:
                # Try common formats
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                    try:
                        dt = datetime.strptime(s.split()[0], fmt) if " " in s and "-" in s.split()[0] else datetime.strptime(s, fmt)
                        date_str = dt.strftime("%Y-%m-%d")
                        break
                    except Exception:
                        continue
                if not date_str:
                    # Fallback pd parsing
                    import pandas as pd
                    dt = pd.to_datetime(s, errors='coerce')
                    if pd.notna(dt):
                        date_str = dt.strftime("%Y-%m-%d")
                    else:
                        date_str = s[:10]
            except Exception:
                date_str = s[:10]

        if not date_str:
            continue

        shift_name = str(shift_name).strip() or "白班"
        # Normalize shift to 白班/夜班
        if shift_name.lower() in ("day", "d", "白班", "白", "日班", "1", "1.0"):
            shift_norm = "白班"
        elif shift_name.lower() in ("night", "n", "夜班", "夜", "2", "2.0"):
            shift_norm = "夜班"
        else:
            # Keep original if already 白班/夜班 else map unknown to 白班
            if shift_name in ("白班", "夜班"):
                shift_norm = shift_name
            else:
                # Try to infer from contains
                if "白" in shift_name or "day" in shift_name.lower() or "day" in shift_name.lower():
                    shift_norm = "白班"
                elif "夜" in shift_name or "night" in shift_name.lower():
                    shift_norm = "夜班"
                else:
                    shift_norm = shift_name or "白班"

        tb = f"{date_str} {shift_norm}"
        time_buckets_set.add(tb)
        tb_meta[tb] = (date_str, SHIFT_ORDER.get(shift_norm, 99))

        try:
            qty = float(balance_qty)
        except Exception:
            try:
                qty = float(str(balance_qty).replace(",", "").strip())
            except Exception:
                qty = 0

        inventory[item_code][tb] = qty

    # Sort timeBuckets by date then shift
    time_buckets = sorted(list(time_buckets_set), key=lambda x: (tb_meta.get(x, (x, 99))[0], tb_meta.get(x, (x, 99))[1], x))

    # Convert inventory defaultdict to dict of dicts, ensure all values are serializable
    inv_out = {}
    for k, v in inventory.items():
        inv_out[k] = dict(v)

    # If bom_children provided, ensure inventory keys for all bom nodes?
    # Not necessary, but we keep as is.

    out = {
        "timeBuckets": time_buckets,
        "inventory": inv_out,
        "bomChildren": bom_children,
        "bomParents": bom_parents,
        "hasChildren": has_children,
    }
    return out


def find_bom_files_in_data_dir(project_root=None):
    """
    Scan data dir for BOM files, return list of paths
    """
    if project_root is None:
        project_root = PROJECT_ROOT
    data_dir = os.path.join(project_root, "data")
    candidates = []
    if not os.path.isdir(data_dir):
        return candidates
    # Walk up to 2 levels deep
    for root, dirs, files in os.walk(data_dir):
        # Limit depth: relative path depth <=3
        rel = os.path.relpath(root, data_dir)
        depth = rel.count(os.sep) if rel != "." else 0
        if depth > 3:
            # prune deeper
            dirs[:] = []
            continue
        for f in files:
            low = f.lower()
            if "bom" in low and low.endswith(".xlsx"):
                full = os.path.join(root, f)
                # avoid too small files
                try:
                    if os.path.getsize(full) > 0:
                        candidates.append(full)
                except Exception:
                    pass
        # also check for subdirs like 20260723 etc, but limit
    # Sort by mtime descending, prefer larger file?
    candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return candidates


def load_balance_from_io_cache():
    """
    Try to load balance data from io_report cache (DataCache)
    Returns list of BalanceRows (combined all cats) or None if not available
    """
    try:
        from app.modules.io_report.engine import get_cache, _global_cache
        # Prefer in-memory global cache if exists (covers upload case where files not persisted to data/)
        cache = None
        if _global_cache is not None:
            try:
                cache = _global_cache
            except Exception:
                cache = None
        if cache is None:
            cache = get_cache()
        # Combine all bal_by_cat
        all_bal = []
        if getattr(cache, 'bal_by_cat', None):
            for cat, rows in cache.bal_by_cat.items():
                all_bal.extend(rows)
        else:
            all_bal.extend(getattr(cache, 'bal_fg', []) or [])
            all_bal.extend(getattr(cache, 'bal_gb', []) or [])
        if not all_bal:
            return None
        return all_bal
    except Exception as e:
        print(f"[inventory_dashboard] load from io cache failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def parse_balance_excel(file_path: str):
    """
    Parse Balance Excel file (like 结存表.xlsx) for dashboard
    Expected columns: PLAN_DATE, SHIFT_NAME, ITEM_CODE, BALANCE_QTY
    Returns list of dict rows
    """
    wb = _load_workbook_robust(file_path)
    # Find best sheet
    expected = ["PLAN_DATE", "ITEM_CODE", "BALANCE_QTY", "SHIFT_NAME", "BALANCE", "BOH"]
    best_sheet = None
    best_info = None
    best_score = -1
    for sname in wb.sheetnames:
        try:
            ws = wb[sname]
            header_idx, headers, score = _find_header_row(ws, expected, scan_rows=15)
            if not headers:
                continue
            # Must have at least ITEM_CODE and PLAN_DATE
            has_item = _get_col_index(headers, ["ITEM_CODE", "ITEM_NO", "SKU", "PN"]) >= 0
            has_date = _get_col_index(headers, ["PLAN_DATE", "DATE", "MPS_DATE"]) >= 0
            combined = score + (5 if has_item else 0) + (5 if has_date else 0)
            # Count rows
            rows_cnt = 0
            try:
                for _r in ws.iter_rows(min_row=header_idx + 1, max_row=header_idx + 20, values_only=True):
                    if _r and any(c is not None and str(c).strip() != "" for c in _r):
                        rows_cnt += 1
            except Exception:
                rows_cnt = 0
            combined += min(rows_cnt, 10)
            if combined > best_score:
                best_score = combined
                best_sheet = sname
                best_info = (ws, header_idx, headers)
        except Exception:
            continue

    if not best_info:
        wb.close()
        raise ValueError(f"Balance file {os.path.basename(file_path)}: no valid sheet found")

    ws, header_idx, headers = best_info
    date_idx = _get_col_index(headers, ["PLAN_DATE", "MPS_DATE", "DATE", "Date"])
    shift_idx = _get_col_index(headers, ["SHIFT_NAME", "SHIFT_CODE", "SHIFT", "Shift"])
    item_idx = _get_col_index(headers, ["ITEM_CODE", "ITEM_NO", "SKU", "PN", "ITEM", "Part Number", "PART_NUMBER", "PN_CODE", "PART"])
    qty_idx = _get_col_index(headers, ["BALANCE_QTY", "BALANCE", "QTY", "BOH", "ENDING_ONHAND", "ENDING", "Ending_OnHand", "BALANCE_QTY", "Ending"])

    if item_idx < 0 or date_idx < 0 or qty_idx < 0:
        wb.close()
        raise ValueError(f"Balance file {os.path.basename(file_path)} missing required columns: headers={headers}")

    rows = []
    for r in ws.iter_rows(min_row=header_idx + 1, values_only=True):
        if not r or len(r) <= max(date_idx, item_idx, qty_idx):
            continue
        item_raw = r[item_idx]
        if not item_raw:
            continue
        rows.append({
            "PLAN_DATE": r[date_idx],
            "SHIFT_NAME": r[shift_idx] if shift_idx >= 0 and shift_idx < len(r) else "白班",
            "ITEM_CODE": item_raw,
            "BALANCE_QTY": r[qty_idx],
        })

    wb.close()
    return rows
