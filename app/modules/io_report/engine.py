"""
IO Report Engine - Python port of Go implementation
9 reports: daily/cum INPUT/OUTPUT/CHECKIN/CHECKOUT + BOH
Row dim: LINE_CODE / ITEM_NO / STYLE / detail
Col dim: shift / day / week / month
"""
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional


@dataclass
class ScheduleRow:
    LineCode: str
    ShiftName: str
    PlanItem: str
    SKU: str
    PlanDate: datetime
    PlanValue: float
    Style: str = ""


@dataclass
class BalanceRow:
    PlanDate: datetime
    ShiftName: str
    ItemCode: str
    BalanceQty: float
    Style: str = ""


@dataclass
class DataCache:
    item_to_cat: dict
    item_to_style: dict
    fg_items: List[str]
    gb_items: List[str]
    sched_fg: List[ScheduleRow]
    sched_gb: List[ScheduleRow]
    bal_fg: List[BalanceRow]
    bal_gb: List[BalanceRow]
    line_fg: List[str]
    line_gb: List[str]
    style_fg: List[str]
    style_gb: List[str]
    # extended categories
    items_by_cat: dict = None
    sched_by_cat: dict = None
    bal_by_cat: dict = None
    lines_by_cat: dict = None
    styles_by_cat: dict = None
    cats: List[str] = None


def _to_datetime(v) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date) and not isinstance(v, datetime):
        return datetime(v.year, v.month, v.day)
    s = str(v).strip()
    if not s:
        return None
    fmts = [
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    try:
        parts = re.split(r"[/\-]", s)
        if len(parts) == 3:
            if len(parts[0]) == 4:
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2].split()[0])
                return datetime(y, m, d)
            else:
                m, d, y = int(parts[0]), int(parts[1]), int(parts[2].split()[0])
                if y < 100:
                    y += 2000
                return datetime(y, m, d)
    except Exception:
        pass
    return None


def first_day_of_iso_week(year: int, week: int) -> datetime:
    try:
        return datetime.fromisocalendar(year, week, 1)
    except Exception:
        jan4 = datetime(year, 1, 4)
        return jan4 - timedelta(days=jan4.weekday()) + timedelta(weeks=week - 1)


def _resolve_data_dir(data_dir: Optional[str] = None) -> str:
    if data_dir and os.path.isdir(data_dir):
        return os.path.abspath(data_dir)
    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(this_dir, "..", "..", "..", "data"),
        os.path.join(os.getcwd(), "data"),
        os.path.abspath("data"),
    ]
    for c in candidates:
        if c and os.path.isdir(c) and any(f.endswith(".xlsx") for f in os.listdir(c)):
            return os.path.abspath(c)
    for c in candidates:
        if c and os.path.isdir(c):
            return os.path.abspath(c)
    return os.path.abspath(candidates[0])


def _find_file(data_dir: str, exact_name: str, keywords: List[str]) -> Optional[str]:
    exact = os.path.join(data_dir, exact_name)
    if os.path.exists(exact):
        return exact
    if not os.path.isdir(data_dir):
        return None
    for f in os.listdir(data_dir):
        if exact_name in f:
            return os.path.join(data_dir, f)
    for f in os.listdir(data_dir):
        lf = f.lower()
        for kw in keywords:
            if kw in lf or kw in f:
                return os.path.join(data_dir, f)
    return None


def _get_col_index(headers: List, target: str) -> int:
    if not headers:
        return -1
    for i, h in enumerate(headers):
        if h == target:
            return i
    for i, h in enumerate(headers):
        if h and str(h).strip() == target.strip():
            return i
    for i, h in enumerate(headers):
        if h and str(h).strip().lower() == target.lower():
            return i
    return -1


def _get_col_index_by_candidates(headers: List, candidates: List[str]) -> int:
    """Try multiple candidate names for same column, return first found index"""
    if not headers or not candidates:
        return -1
    # Normalize headers for matching
    norm_headers = [(str(h).strip() if h else "", str(h).strip().upper() if h else "") for h in headers]
    for cand in candidates:
        cand_strip = str(cand).strip()
        cand_up = cand_strip.upper()
        for i, (orig, up) in enumerate(norm_headers):
            if orig == cand_strip:
                return i
            if up == cand_up:
                return i
    # Fallback: contains match
    for cand in candidates:
        cand_up = str(cand).strip().upper()
        for i, (orig, up) in enumerate(norm_headers):
            if cand_up and (cand_up in up or up in cand_up):
                return i
    return -1


def _load_workbook_robust(path: str):
    """
    Robustly load workbook: try read_only=False first (handles files with no default style and 17M large files),
    fallback to read_only=True if needed. Returns workbook.
    """
    import openpyxl
    # First try read_only=False (handles 17M files in data/20260723 that fail with read_only=True)
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
        return wb
    except Exception as e1:
        try:
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            return wb
        except Exception as e2:
            raise FileNotFoundError(f"Failed to open {path}: {e1} / {e2}")


def _find_header_row(ws, expected_keywords, scan_rows=15):
    """
    Scan first scan_rows rows to find header row containing at least 2 expected keywords.
    Returns (header_row_idx (1-based), headers list) or (1, first row headers) if not found.
    Robust for files where header is not in row 1 (e.g., user file has title row or empty rows).
    """
    best = None
    best_score = -1
    best_headers = None
    for r_idx in range(1, scan_rows + 1):
        try:
            row = next(ws.iter_rows(min_row=r_idx, max_row=r_idx, values_only=True), None)
            if not row:
                continue
            # Clean row: strip and upper for matching, keep original for _get_col_index
            cleaned = [str(c).strip() if c is not None else "" for c in row]
            cleaned_upper = [c.upper() for c in cleaned]
            # Count how many expected keywords appear (exact or case-insensitive), skip empty
            score = 0
            for kw in expected_keywords:
                kw_up = kw.upper()
                for c_up in cleaned_upper:
                    if not c_up:
                        continue
                    if kw_up == c_up or kw_up in c_up or c_up in kw_up:
                        score += 1
                        break
            if score > best_score:
                best_score = score
                best = r_idx
                best_headers = list(row)
        except Exception:
            continue
    # If best_score >=2, use it, else fallback to row 1
    if best is not None and best_score >= 2:
        return best, best_headers
    # fallback row 1
    try:
        first = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        return 1, list(first) if first else []
    except Exception:
        return 1, []


def _find_best_sheet_and_header(wb, expected_keywords, scan_rows=15):
    """
    Search all sheets in workbook for best header match.
    Returns (sheet_name, ws, header_row_idx, headers, score)
    """
    best_overall = None
    best_score_overall = -1
    best_info = None
    for sheet_name in wb.sheetnames:
        try:
            ws = wb[sheet_name]
            # For each sheet, find best header
            header_idx, headers = _find_header_row(ws, expected_keywords, scan_rows=scan_rows)
            # Compute score for this header
            if not headers:
                continue
            cleaned = [str(c).strip().upper() if c else "" for c in headers]
            score = 0
            for kw in expected_keywords:
                kw_up = kw.upper()
                for c_up in cleaned:
                    if not c_up:
                        continue
                    if kw_up == c_up or kw_up in c_up:
                        score += 1
                        break
            # Also consider if sheet has data rows after header
            # Count non-empty rows after header (up to 5)
            data_rows = 0
            try:
                for _r in ws.iter_rows(min_row=header_idx + 1, max_row=header_idx + 10, values_only=True):
                    if _r and any(c is not None and str(c).strip() != "" for c in _r):
                        data_rows += 1
            except Exception:
                data_rows = 0
            # Prefer sheets with more data rows if score equal
            combined_score = score * 100 + data_rows
            if combined_score > best_score_overall:
                best_score_overall = combined_score
                best_overall = sheet_name
                best_info = (ws, header_idx, headers, score, data_rows)
        except Exception:
            continue
    if best_info:
        ws, header_idx, headers, score, data_rows = best_info
        return best_overall, ws, header_idx, headers, score
    # fallback to first sheet
    try:
        ws = wb[wb.sheetnames[0]]
        header_idx, headers = _find_header_row(ws, expected_keywords, scan_rows=scan_rows)
        return wb.sheetnames[0], ws, header_idx, headers, 0
    except Exception:
        return None, None, 1, [], 0


# ---------- column defs ----------
def get_col_defs(sched: List[ScheduleRow], bal: List[BalanceRow], col_dim: str) -> List[dict]:
    seen_date = {}
    seen_shift = {}
    raw = []

    def add_shift(d: datetime, s: str):
        sk = d.strftime("%Y-%m-%d") + "|" + (s or "")
        if sk not in seen_shift:
            seen_shift[sk] = True
            raw.append({"Date": d, "Label": d.strftime("%m/%d") + "_" + (s or ""), "SortDate": d, "SortKey": s or ""})

    def add_day(d: datetime):
        dk = d.strftime("%Y-%m-%d")
        if dk not in seen_date:
            seen_date[dk] = True
            raw.append({"Date": d, "Label": d.strftime("%m/%d"), "SortDate": d, "SortKey": ""})

    def add_week(d: datetime):
        iso = d.isocalendar()
        wk = f"{iso[0]}-W{iso[1]:02d}"
        if wk not in seen_date:
            seen_date[wk] = True
            monday = first_day_of_iso_week(iso[0], iso[1])
            raw.append({"Date": monday, "Label": monday.strftime("%m/%d"), "SortDate": monday, "SortKey": ""})

    def add_month(d: datetime):
        ym = d.strftime("%Y-%m")
        if ym not in seen_date:
            seen_date[ym] = True
            first = datetime(d.year, d.month, 1)
            raw.append({"Date": first, "Label": d.strftime("%m月"), "SortDate": first, "SortKey": ""})

    for r in sched:
        if not r.PlanDate:
            continue
        if col_dim == "day":
            add_day(r.PlanDate)
        elif col_dim == "week":
            add_week(r.PlanDate)
        elif col_dim == "month":
            add_month(r.PlanDate)
        else:
            add_shift(r.PlanDate, r.ShiftName)

    for r in bal:
        if not r.PlanDate:
            continue
        if col_dim == "day":
            add_day(r.PlanDate)
        elif col_dim == "week":
            add_week(r.PlanDate)
        elif col_dim == "month":
            add_month(r.PlanDate)
        else:
            add_shift(r.PlanDate, r.ShiftName)

    def sort_fn(c):
        prio = 0 if c["SortKey"] == "白班" else 1 if c["SortKey"] == "夜班" else 2
        return (c["SortDate"], prio, c["SortKey"])

    raw.sort(key=sort_fn)
    seen = {}
    out = []
    for c in raw:
        if c["Label"] not in seen:
            seen[c["Label"]] = True
            out.append(c)
    return out


def col_labels(cols: List[dict]) -> List[str]:
    return [c["Label"] for c in cols]


def agg_key_for_row_s(r: ScheduleRow, col_dim: str) -> str:
    if not r.PlanDate:
        return ""
    d = r.PlanDate
    if col_dim == "day":
        return d.strftime("%m/%d")
    if col_dim == "week":
        y, w = d.isocalendar()[0], d.isocalendar()[1]
        return first_day_of_iso_week(y, w).strftime("%m/%d")
    if col_dim == "month":
        return d.strftime("%m月")
    return d.strftime("%m/%d") + "_" + (r.ShiftName or "")


def bal_col_key(r: BalanceRow, col_dim: str) -> str:
    if not r.PlanDate:
        return ""
    d = r.PlanDate
    if col_dim == "day":
        return d.strftime("%m/%d")
    if col_dim == "week":
        y, w = d.isocalendar()[0], d.isocalendar()[1]
        return first_day_of_iso_week(y, w).strftime("%m/%d")
    if col_dim == "month":
        return d.strftime("%m月")
    return d.strftime("%m/%d") + "_" + (r.ShiftName or "")


# ---------- aggregation ----------
def build_io_sched(sched: List[ScheduleRow], dim_col: str, cols: List[dict], plan_item: str, cumulative: bool, col_dim: str):
    # Case-insensitive PlanItem matching (fix 0 rows when INPUT is lowercase or with spaces)
    plan_upper = (plan_item or "").strip().upper()
    filtered = [r for r in sched if (r.PlanItem or "").strip().upper() == plan_upper]
    if not filtered:
        return [], []

    actual_dim = {"ITEM_NO": "SKU", "STYLE": "STYLE"}.get(dim_col, dim_col)
    agg = {}
    pivot = {}
    dim_set = set()

    for r in filtered:
        dim_val = {"LINE_CODE": r.LineCode or "", "STYLE": r.Style or ""}.get(actual_dim, r.SKU or "")
        col_l = agg_key_for_row_s(r, col_dim)
        agg[(dim_val, col_l)] = agg.get((dim_val, col_l), 0) + (r.PlanValue or 0)

    for (dim_val, col_l), v in agg.items():
        pivot.setdefault(dim_val, {})[col_l] = pivot.get(dim_val, {}).get(col_l, 0) + v
        dim_set.add(dim_val)

    col_headers = col_labels(cols)
    rows = []
    for dim in sorted(dim_set):
        entry = {dim_col: dim}
        vals = pivot.get(dim, {})
        if cumulative:
            running = 0
            for h in col_headers:
                running += vals.get(h, 0)
                entry[h] = int(running)
        else:
            for h in col_headers:
                entry[h] = int(vals.get(h, 0))
        rows.append(entry)
    return col_headers, rows


def build_io_sched_detail(sched: List[ScheduleRow], cols: List[dict], plan_item: str, cumulative: bool, col_dim: str):
    plan_upper = (plan_item or "").strip().upper()
    filtered = [r for r in sched if (r.PlanItem or "").strip().upper() == plan_upper]
    if not filtered:
        return [], []

    agg = {}
    pivot = {}
    row_set = {}

    for r in filtered:
        rk = (r.SKU or "", r.LineCode or "", r.Style or "")
        col_l = agg_key_for_row_s(r, col_dim)
        agg[(rk, col_l)] = agg.get((rk, col_l), 0) + (r.PlanValue or 0)

    for (rk, col_l), v in agg.items():
        pivot.setdefault(rk, {})[col_l] = pivot.get(rk, {}).get(col_l, 0) + v
        row_set[rk] = True

    col_headers = col_labels(cols)
    rows = []
    for rk in sorted(row_set.keys(), key=lambda x: (x[1], x[0], x[2])):
        item, line, style = rk
        entry = {"ITEM_NO": item, "LINE_CODE": line, "STYLE": style}
        vals = pivot.get(rk, {})
        if cumulative:
            running = 0
            for h in col_headers:
                running += vals.get(h, 0)
                entry[h] = int(running)
        else:
            for h in col_headers:
                entry[h] = int(vals.get(h, 0))
        rows.append(entry)
    return col_headers, rows


def build_balance(bal: List[BalanceRow], dim_col: str, cols: List[dict], col_dim: str):
    if not bal or dim_col == "LINE_CODE":
        return [], []

    def dim_val_fn(r: BalanceRow):
        return r.Style or "" if dim_col == "STYLE" else r.ItemCode or ""

    agg = {}
    dim_set = set()
    for r in bal:
        dv = dim_val_fn(r)
        agg[(dv, bal_col_key(r, col_dim))] = agg.get((dv, bal_col_key(r, col_dim)), 0) + (r.BalanceQty or 0)
        dim_set.add(dv)

    pivot = {}
    for (dv, col), v in agg.items():
        pivot.setdefault(dv, {})[col] = pivot.get(dv, {}).get(col, 0) + v

    col_headers = col_labels(cols)
    rows = []
    for dim in sorted(dim_set):
        entry = {dim_col: dim}
        vals = pivot.get(dim, {})
        for h in col_headers:
            entry[h] = int(vals.get(h, 0))
        rows.append(entry)
    return col_headers, rows


def bal_to_sched(bal: List[BalanceRow]) -> List[ScheduleRow]:
    return [
        ScheduleRow(SKU=b.ItemCode, Style=b.Style or "", PlanDate=b.PlanDate, ShiftName=b.ShiftName or "", PlanValue=b.BalanceQty or 0, PlanItem="INPUT", LineCode="")
        for b in bal
    ]


def build_one_report(sched: List[ScheduleRow], bal: List[BalanceRow], rtype: str, dim: str, cols: List[dict], col_dim: str):
    rt = rtype.lower()
    if rt in ("boh", "balance"):
        rt = "balance"

    mapping = {
        "daily_input": ("INPUT", False),
        "daily_output": ("OUTPUT", False),
        "daily_checkin": ("CHECKIN", False),
        "daily_checkout": ("CHECKOUT", False),
        "cum_input": ("INPUT", True),
        "cum_output": ("OUTPUT", True),
        "cum_checkin": ("CHECKIN", True),
        "cum_checkout": ("CHECKOUT", True),
    }

    if rt == "balance":
        return build_io_sched_detail(bal_to_sched(bal), cols, "INPUT", False, col_dim) if dim == "detail" else build_balance(bal, dim, cols, col_dim)

    if rt not in mapping:
        if "input" in rt:
            plan, cum = "INPUT", "cum" in rt
        elif "output" in rt:
            plan, cum = "OUTPUT", "cum" in rt
        elif "checkin" in rt:
            plan, cum = "CHECKIN", "cum" in rt
        elif "checkout" in rt:
            plan, cum = "CHECKOUT", "cum" in rt
        else:
            return [], []
    else:
        plan, cum = mapping[rt]

    return build_io_sched_detail(sched, cols, plan, cum, col_dim) if dim == "detail" else build_io_sched(sched, dim, cols, plan, cum, col_dim)


# ---------- Excel loading ----------
def _load_openpyxl_data(data_dir: str) -> DataCache:
    import openpyxl

    data_dir = _resolve_data_dir(data_dir)

    mm_path = _find_file(data_dir, "料号主表.xlsx", ["料号主表", "料号", "master"])
    if not mm_path or not os.path.exists(mm_path):
        raise FileNotFoundError(f"料号主表.xlsx not found in {data_dir}")

    wb = _load_workbook_robust(mm_path)
    # Search best sheet for master: supports file with multiple sheets, pick best match
    # Support alias SYLTE for STYLE (data/20260723/料号快照.xlsx uses SYLTE)
    best_sheet, ws, header_row_idx, headers, _score = _find_best_sheet_and_header(wb, ["ITEM_NO", "PRODUCT_CATEGORY", "PRODUCT_STYLE", "SYLTE"])
    print(f"[IO] Master: best sheet={best_sheet}, header_row={header_row_idx}, score={_score}, headers={headers}")
    item_no_idx = _get_col_index_by_candidates(headers, ["ITEM_NO", "ITEM_CODE", "SKU", "PN"])
    prod_cat_idx = _get_col_index_by_candidates(headers, ["PRODUCT_CATEGORY", "CATEGORY", "PRODUCT_CAT"])
    style_idx = _get_col_index_by_candidates(headers, ["PRODUCT_STYLE", "SYLTE", "STYLE", "PRODUCT_STYLE_NAME"])
    if item_no_idx < 0 or prod_cat_idx < 0:
        raise ValueError(f"料号主表 missing ITEM_NO or PRODUCT_CATEGORY, headers={headers} (detected at row {header_row_idx} in sheet {best_sheet}, score={_score})")

    item_to_cat, item_to_style = {}, {}
    fg_items, gb_items = [], []
    style_fg_set, style_gb_set = set(), set()

    # generic per-category containers
    from collections import defaultdict
    items_by_cat = defaultdict(list)
    styles_by_cat = defaultdict(set)
    all_items_set = set()

    for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
        if not row or item_no_idx >= len(row) or prod_cat_idx >= len(row):
            continue
        item_raw, cat_raw = row[item_no_idx], row[prod_cat_idx]
        if not item_raw:
            continue
        item = str(item_raw).strip()
        if not item:
            continue
        # cat may be blank -> RAW
        cat = str(cat_raw).strip() if cat_raw is not None and str(cat_raw).strip() != "" else "RAW"
        # keep original cat for item_to_cat (empty string for RAW if original blank, to preserve mapping)
        orig_cat = str(cat_raw).strip() if cat_raw is not None else ""
        item_to_cat[item] = orig_cat if orig_cat != "" else "RAW"
        style = str(row[style_idx]).strip() if style_idx >= 0 and style_idx < len(row) and row[style_idx] is not None else ""
        item_to_style[item] = style

        items_by_cat[cat].append(item)
        if style:
            styles_by_cat[cat].add(style)
        all_items_set.add(item)

        if cat == "成品":
            fg_items.append(item)
            if style:
                style_fg_set.add(style)
        elif cat == "GB":
            gb_items.append(item)
            if style:
                style_gb_set.add(style)
    wb.close()

    fg_set, gb_set = set(fg_items), set(gb_items)
    # Build case-insensitive maps for robust SKU matching (fix 0 schedule rows when master/schedule case differs)
    sku_upper_map = {}  # upper -> original canonical
    sku_lower_map = {}  # lower -> original
    for _it in all_items_set:
        _up = str(_it).strip().upper()
        _lo = str(_it).strip().lower()
        if _up not in sku_upper_map:
            sku_upper_map[_up] = _it
        if _lo not in sku_lower_map:
            sku_lower_map[_lo] = _it
    sku_upper_set = set(sku_upper_map.keys())
    sku_lower_set = set(sku_lower_map.keys())

    # for generic filtering, include all known items
    sched_by_cat = defaultdict(list)
    bal_by_cat = defaultdict(list)
    lines_by_cat = defaultdict(set)

    sched_path = _find_file(data_dir, "排产结果表.xlsx", ["排产结果表", "排产", "schedule"])
    if not sched_path or not os.path.exists(sched_path):
        raise FileNotFoundError(f"排产结果表.xlsx not found in {data_dir}")

    wb2 = _load_workbook_robust(sched_path)
    sched_best_sheet, ws2, sched_header_row_idx, headers2, sched_score = _find_best_sheet_and_header(wb2, ["LINE_CODE", "PLAN_ITEM", "SKU", "PLAN_DATE", "PLAN_VALUE", "SHIFT_NAME"])
    print(f"[IO] Schedule: best sheet={sched_best_sheet}, header_row={sched_header_row_idx}, score={sched_score}/6, headers={headers2}")
    # Support aliases: SKU can be ITEM_CODE, ITEM_NO, etc. PLAN_VALUE can be SHIFT_OUT_QTY etc for some variants, but we keep strict for schedule
    line_idx = _get_col_index_by_candidates(headers2, ["LINE_CODE", "LINE"])
    shift_idx = _get_col_index_by_candidates(headers2, ["SHIFT_NAME", "SHIFT_CODE"])
    plan_item_idx = _get_col_index_by_candidates(headers2, ["PLAN_ITEM", "PLAN_TYPE"])
    sku_idx = _get_col_index_by_candidates(headers2, ["SKU", "ITEM_NO", "ITEM_CODE", "PN", "SKU_CODE"])
    plan_date_idx = _get_col_index_by_candidates(headers2, ["PLAN_DATE", "MPS_DATE", "DATE"])
    plan_val_idx = _get_col_index_by_candidates(headers2, ["PLAN_VALUE", "VALUE", "QTY", "PLAN_QTY", "SHIFT_OUT_QTY"])

    # If headers missing, try fallback by position (common when user file has different header names)
    if line_idx < 0: line_idx = 0
    if shift_idx < 0: shift_idx = 1
    if plan_item_idx < 0: plan_item_idx = 2
    if sku_idx < 0: sku_idx = 3
    if plan_date_idx < 0: plan_date_idx = 4
    if plan_val_idx < 0: plan_val_idx = 5

    sched_fg, sched_gb = [], []
    line_fg_set, line_gb_set = set(), set()
    # stats for debugging 0 rows
    _sched_total = 0
    _sched_skip_no_sku = 0
    _sched_skip_sku_not_in_master = 0
    _sched_skip_no_date = 0
    _sched_kept = 0

    for row in ws2.iter_rows(min_row=sched_header_row_idx + 1, values_only=True):
        _sched_total += 1
        if not row or len(row) <= max(line_idx, shift_idx, plan_item_idx, sku_idx, plan_date_idx, plan_val_idx):
            _sched_skip_no_sku += 1
            continue
        sku_raw = row[sku_idx]
        if not sku_raw:
            _sched_skip_no_sku += 1
            continue
        sku_stripped = str(sku_raw).strip()
        if not sku_stripped:
            _sched_skip_no_sku += 1
            continue
        # Robust SKU lookup: exact -> upper -> lower
        sku_canonical = None
        if sku_stripped in all_items_set:
            sku_canonical = sku_stripped
        elif sku_stripped.upper() in sku_upper_map:
            sku_canonical = sku_upper_map[sku_stripped.upper()]
        elif sku_stripped.lower() in sku_lower_map:
            sku_canonical = sku_lower_map[sku_stripped.lower()]
        else:
            _sched_skip_sku_not_in_master += 1
            continue
        sku = sku_canonical
        try:
            val = float(row[plan_val_idx]) if row[plan_val_idx] not in (None, "") else 0.0
        except Exception:
            try:
                val = float(str(row[plan_val_idx]).strip())
            except Exception:
                val = 0.0
        pd = _to_datetime(row[plan_date_idx])
        if not pd:
            _sched_skip_no_date += 1
            continue
        # Normalize PlanItem to upper trimmed for case-insensitive matching (INPUT/OUTPUT etc)
        plan_item_raw = str(row[plan_item_idx] or "").strip()
        plan_item_norm = plan_item_raw.upper()
        sr = ScheduleRow(
            LineCode=str(row[line_idx] or "").strip(),
            ShiftName=str(row[shift_idx] or "").strip(),
            PlanItem=plan_item_norm,
            SKU=sku,
            PlanDate=pd,
            PlanValue=val,
            Style=item_to_style.get(sku, "") or item_to_style.get(sku_canonical, ""),
        )
        _sched_kept += 1
        # legacy FG/GB - use canonical mapping
        if sku in fg_set or sku_upper_map.get(sku.upper(), "") in fg_set or sku_lower_map.get(sku.lower(), "") in fg_set:
            sched_fg.append(sr)
            if sr.LineCode:
                line_fg_set.add(sr.LineCode)
        elif sku in gb_set or sku_upper_map.get(sku.upper(), "") in gb_set or sku_lower_map.get(sku.lower(), "") in gb_set:
            sched_gb.append(sr)
            if sr.LineCode:
                line_gb_set.add(sr.LineCode)
        else:
            # If SKU not in FG/GB set but in all_items, still check via cat mapping (generic)
            # For legacy counters, try cat
            _cat_tmp = item_to_cat.get(sku, "")
            if _cat_tmp == "成品":
                sched_fg.append(sr)
                if sr.LineCode:
                    line_fg_set.add(sr.LineCode)
            elif _cat_tmp == "GB":
                sched_gb.append(sr)
                if sr.LineCode:
                    line_gb_set.add(sr.LineCode)

        # generic
        cat = item_to_cat.get(sku, "RAW")
        if cat == "":
            cat = "RAW"
        # normalize FG alias
        if cat == "成品":
            cat_key = "成品"
        else:
            cat_key = cat
        sched_by_cat[cat_key].append(sr)
        if sr.LineCode:
            lines_by_cat[cat_key].add(sr.LineCode)
    wb2.close()
    print(f"[IO] Sched stats: total={_sched_total}, kept={_sched_kept}, skip_no_sku={_sched_skip_no_sku}, skip_not_in_master={_sched_skip_sku_not_in_master}, skip_no_date={_sched_skip_no_date}, master_count={len(all_items_set)}")

    bal_path = _find_file(data_dir, "结存表.xlsx", ["结存表", "结存", "balance"])
    if not bal_path or not os.path.exists(bal_path):
        raise FileNotFoundError(f"结存表.xlsx not found in {data_dir}")

    wb3 = _load_workbook_robust(bal_path)
    bal_best_sheet, ws3, bal_header_row_idx, headers3, bal_score = _find_best_sheet_and_header(wb3, ["PLAN_DATE", "ITEM_CODE", "BALANCE_QTY", "SHIFT_NAME"])
    print(f"[IO] Balance: best sheet={bal_best_sheet}, header_row={bal_header_row_idx}, score={bal_score}/4, headers={headers3}")
    bal_date_idx = _get_col_index_by_candidates(headers3, ["PLAN_DATE", "MPS_DATE", "DATE"])
    bal_shift_idx = _get_col_index_by_candidates(headers3, ["SHIFT_NAME", "SHIFT_CODE"])
    bal_item_idx = _get_col_index_by_candidates(headers3, ["ITEM_CODE", "ITEM_NO", "SKU", "PN"])
    bal_qty_idx = _get_col_index_by_candidates(headers3, ["BALANCE_QTY", "BALANCE", "QTY", "SHIFT_OUT_QTY"])

    bal_fg, bal_gb = [], []
    for row in ws3.iter_rows(min_row=bal_header_row_idx + 1, values_only=True):
        if not row or len(row) <= max(bal_date_idx, bal_shift_idx, bal_item_idx, bal_qty_idx):
            continue
        item_raw = row[bal_item_idx]
        if not item_raw:
            continue
        item_stripped = str(item_raw).strip()
        if not item_stripped:
            continue
        # robust lookup
        item_canonical = None
        if item_stripped in all_items_set:
            item_canonical = item_stripped
        elif item_stripped.upper() in sku_upper_map:
            item_canonical = sku_upper_map[item_stripped.upper()]
        elif item_stripped.lower() in sku_lower_map:
            item_canonical = sku_lower_map[item_stripped.lower()]
        else:
            continue
        item_code = item_canonical
        try:
            qty = float(row[bal_qty_idx]) if row[bal_qty_idx] not in (None, "") else 0.0
        except Exception:
            try:
                qty = float(str(row[bal_qty_idx]).strip())
            except Exception:
                qty = 0.0
        pd = _to_datetime(row[bal_date_idx])
        if not pd:
            continue
        br = BalanceRow(
            PlanDate=pd,
            ShiftName=str(row[bal_shift_idx] or "").strip(),
            ItemCode=item_code,
            BalanceQty=qty,
            Style=item_to_style.get(item_code, ""),
        )
        if item_code in fg_set or sku_upper_map.get(item_code.upper(), "") in fg_set:
            bal_fg.append(br)
        elif item_code in gb_set or sku_upper_map.get(item_code.upper(), "") in gb_set:
            bal_gb.append(br)

        # generic
        cat = item_to_cat.get(item_code, "RAW")
        if cat == "":
            cat = "RAW"
        if cat == "成品":
            cat_key = "成品"
        else:
            cat_key = cat
        bal_by_cat[cat_key].append(br)
    wb3.close()

    # finalize generic dicts
    # ensure all cats have entries
    for cat in list(items_by_cat.keys()):
        items_by_cat[cat] = sorted(set(items_by_cat[cat]))
        styles_by_cat[cat] = sorted(styles_by_cat.get(cat, set()))
        if cat not in lines_by_cat:
            lines_by_cat[cat] = set()
        if cat not in sched_by_cat:
            sched_by_cat[cat] = []
        if cat not in bal_by_cat:
            bal_by_cat[cat] = []

    # also ensure RAW
    if "RAW" not in items_by_cat:
        items_by_cat["RAW"] = []
        styles_by_cat["RAW"] = []
        lines_by_cat["RAW"] = set()
        sched_by_cat["RAW"] = []
        bal_by_cat["RAW"] = []

    # convert sets to sorted lists for lines
    lines_by_cat_sorted = {k: sorted(v) for k, v in lines_by_cat.items()}
    # for cat keys, unify 成品 alias
    if "成品" not in items_by_cat and fg_items:
        items_by_cat["成品"] = sorted(set(fg_items))
    if "GB" not in items_by_cat and gb_items:
        items_by_cat["GB"] = sorted(set(gb_items))

    return DataCache(
        item_to_cat=item_to_cat,
        item_to_style=item_to_style,
        fg_items=sorted(set(fg_items)),
        gb_items=sorted(set(gb_items)),
        sched_fg=sched_fg,
        sched_gb=sched_gb,
        bal_fg=bal_fg,
        bal_gb=bal_gb,
        line_fg=sorted(line_fg_set),
        line_gb=sorted(line_gb_set),
        style_fg=sorted(style_fg_set),
        style_gb=sorted(style_gb_set),
        items_by_cat=dict(items_by_cat),
        sched_by_cat=dict(sched_by_cat),
        bal_by_cat=dict(bal_by_cat),
        lines_by_cat=lines_by_cat_sorted,
        styles_by_cat={k: sorted(v) for k, v in styles_by_cat.items()},
        cats=sorted(items_by_cat.keys()),
    )


# ---------- public API ----------
def load_data(data_dir: str = None) -> DataCache:
    return _load_openpyxl_data(_resolve_data_dir(data_dir))


_global_cache: Optional[DataCache] = None
_global_data_dir: Optional[str] = None


def get_cache(data_dir: str = None) -> DataCache:
    global _global_cache, _global_data_dir
    resolved = _resolve_data_dir(data_dir)
    if _global_cache is None or _global_data_dir != resolved:
        _global_cache = load_data(resolved)
        _global_data_dir = resolved
    return _global_cache


def reload_cache(data_dir: str = None) -> DataCache:
    global _global_cache, _global_data_dir
    resolved = _resolve_data_dir(data_dir)
    _global_cache = load_data(resolved)
    _global_data_dir = resolved
    return _global_cache


def _normalize_group(group: str) -> str:
    if not group:
        return "成品"
    g = str(group).strip()
    upper = g.upper()
    if g in ("成品", "FG", "FG (SKU)", "SKU"):
        return "成品"
    if upper == "GB":
        return "GB"
    if upper == "FR":
        return "FR"
    if upper == "LT":
        return "LT"
    if upper == "RT":
        return "RT"
    if upper in ("RAW", "BLANK", "原材料", ""):
        return "RAW"
    # fallback: if exactly matches a cat in cache, keep
    return g


def _get_sched_bal_for_group(cache: DataCache, group: str):
    norm = _normalize_group(group)
    # generic dict path
    if cache.sched_by_cat and norm in cache.sched_by_cat:
        sched = list(cache.sched_by_cat.get(norm, []))
        bal = list(cache.bal_by_cat.get(norm, []))
        return sched, bal, norm
    # also try original FG/GB
    if norm == "成品":
        return list(cache.sched_fg), list(cache.bal_fg), norm
    if norm == "GB":
        return list(cache.sched_gb), list(cache.bal_gb), norm
    # fallback: try case-insensitive search in cats
    if cache.cats:
        for cat in cache.cats:
            if cat.upper() == norm.upper():
                return list(cache.sched_by_cat.get(cat, [])), list(cache.bal_by_cat.get(cat, [])), cat
    # default to FG
    return list(cache.sched_fg), list(cache.bal_fg), "成品"


def build_reports_for_group(cache: DataCache, dim: str, col_dim: str, group: str, line_code_filter: str = "", item_no_filter: str = "", style_filter: str = ""):
    sched, bal, _norm = _get_sched_bal_for_group(cache, group)

    if line_code_filter:
        sched = [s for s in sched if s.LineCode == line_code_filter]
    if item_no_filter:
        sched = [s for s in sched if s.SKU == item_no_filter]
        bal = [b for b in bal if b.ItemCode == item_no_filter]
    if style_filter:
        sched = [s for s in sched if s.Style == style_filter]
        bal = [b for b in bal if b.Style == style_filter]

    col_defs = get_col_defs(sched, bal, col_dim)
    if not col_defs:
        return {}, []

    result = {}
    # For RAW, only BOH is meaningful, but still build all; frontend can filter
    report_types = ("daily_input", "daily_output", "daily_checkin", "daily_checkout", "cum_input", "cum_output", "cum_checkin", "cum_checkout", "balance")
    if _norm == "RAW":
        # only balance needed, but we still compute balance; others will be empty if no sched
        pass
    for rtype in report_types:
        col_h, rows = build_one_report(sched, bal, rtype, dim, col_defs, col_dim)
        result[rtype] = {"columns": col_h, "rows": rows}
    result["pair_count"] = len(col_defs)
    return result, col_defs


def get_meta(cache: DataCache, group: str, col_dim: str):
    sched, bal, norm = _get_sched_bal_for_group(cache, group)
    cols = get_col_defs(sched, bal, col_dim)

    # build generic meta for all cats
    all_meta = {}
    if cache.cats:
        for cat in cache.cats:
            s = cache.sched_by_cat.get(cat, [])
            b = cache.bal_by_cat.get(cat, [])
            # quick col defs not needed for meta lists, just return stored lists
            all_meta[cat] = {
                "items": cache.items_by_cat.get(cat, []),
                "lines": cache.lines_by_cat.get(cat, []),
                "styles": cache.styles_by_cat.get(cat, []),
            }

    return {
        "date_shift_pairs": [c["Label"] for c in cols],
        "line_codes": cache.lines_by_cat.get(norm, []) if cache.lines_by_cat else (cache.line_fg if norm == "成品" else cache.line_gb),
        "items": cache.items_by_cat.get(norm, []) if cache.items_by_cat else (cache.fg_items if norm == "成品" else cache.gb_items),
        "styles": cache.styles_by_cat.get(norm, []) if cache.styles_by_cat else (cache.style_fg if norm == "成品" else cache.style_gb),
        "lines_fg": cache.line_fg,
        "lines_gb": cache.line_gb,
        "items_fg": cache.fg_items,
        "items_gb": cache.gb_items,
        "styles_fg": cache.style_fg,
        "styles_gb": cache.style_gb,
        # extended
        "cats": cache.cats or [],
        "items_by_cat": cache.items_by_cat or {},
        "lines_by_cat": cache.lines_by_cat or {},
        "styles_by_cat": cache.styles_by_cat or {},
        "current_group": norm,
        "all_meta": all_meta,
    }
