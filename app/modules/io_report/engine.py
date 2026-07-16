"""
IO Report Engine - Python port of Go implementation in gtk-aps-result-analysis/gtk-aps-report/main.go
支持 5 张报表: Daily Input / Daily Output / Cum Input / Cum Output / Balance
行维度: LINE_CODE / ITEM_NO / STYLE + detail (ITEM+LINE+STYLE)
列维度: shift / day / week / month
"""
import os
from datetime import datetime, date, timedelta
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import re

# ---------- data structures ----------

@dataclass
class ScheduleRow:
    LineCode: str
    ShiftName: str
    PlanItem: str   # INPUT / OUTPUT
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

# ---------- helpers ----------

def _to_datetime(v) -> Optional[datetime]:
    """Parse value to datetime, handling Excel datetime objects and multiple string formats."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date) and not isinstance(v, datetime):
        return datetime(v.year, v.month, v.day)
    s = str(v).strip()
    if not s:
        return None
    # Try common formats from Go: 2006/1/2, 2006-01-02, 2006/01/02, 1/2/2006
    fmts = [
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except:
            continue
    # Fallback: try split
    # Handle like 2024/1/5 or 1/5/2024
    try:
        # Replace - with /
        parts = re.split(r'[/\-]', s)
        if len(parts) == 3:
            if len(parts[0]) == 4:  # Y/M/D
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2].split()[0])
                return datetime(y, m, d)
            else:  # M/D/Y
                m, d, y = int(parts[0]), int(parts[1]), int(parts[2].split()[0])
                # handle 2-digit year
                if y < 100:
                    y += 2000
                return datetime(y, m, d)
    except:
        pass
    return None

def first_day_of_iso_week(year: int, week: int) -> datetime:
    """Monday of ISO week."""
    try:
        # Python 3.8+
        return datetime.fromisocalendar(year, week, 1)
    except:
        # fallback similar to Go's intention but more correct
        jan4 = datetime(year, 1, 4)
        # weekday Monday=0
        monday = jan4 - timedelta(days=jan4.weekday())
        return monday + timedelta(weeks=week - 1)

def sorted_keys(m: dict) -> List[str]:
    return sorted([k for k in m.keys() if k])

def sorted_keys_set(s: set) -> List[str]:
    return sorted([k for k in s if k])

def col_labels(cols: List[dict]) -> List[str]:
    return [c["Label"] for c in cols]

def _resolve_data_dir(data_dir: Optional[str] = None) -> str:
    """Resolve to project_root/data if not provided."""
    if data_dir and os.path.isdir(data_dir):
        return data_dir
    # Try project root data
    this_file = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        data_dir,
        os.path.join(this_file, "..", "..", "..", "data"),
        os.path.join(this_file, "..", "..", "..", "..", "data"),
        os.path.join(os.getcwd(), "data"),
        os.path.abspath("data"),
        "/Users/zhiyingchen/openhands_workspace/Projects/gtk-result-table/data",
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            # check if contains at least one xlsx
            if any(f.endswith(".xlsx") for f in os.listdir(c)):
                return os.path.abspath(c)
    # fallback to first existing
    for c in candidates:
        if c and os.path.isdir(os.path.abspath(c)):
            return os.path.abspath(c)
    return os.path.abspath(candidates[1]) if candidates[1] else "data"

def _find_file(data_dir: str, exact_name: str, keywords: List[str]) -> Optional[str]:
    exact_path = os.path.join(data_dir, exact_name)
    if os.path.exists(exact_path):
        return exact_path
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
    # exact match
    for i, h in enumerate(headers):
        if h == target:
            return i
    # trimmed
    t = target.strip()
    for i, h in enumerate(headers):
        if h and str(h).strip() == t:
            return i
    # case-insensitive
    for i, h in enumerate(headers):
        if h and str(h).strip().lower() == t.lower():
            return i
    return -1

# ---------- core logic ported from Go ----------

def get_col_defs(sched: List[ScheduleRow], bal: List[BalanceRow], col_dim: str) -> List[dict]:
    seen_date = {}
    seen_shift = {}
    raw = []

    def add_shift(d: datetime, s: str):
        dk = d.strftime("%Y-%m-%d")
        sk = dk + "|" + (s or "")
        if sk not in seen_shift:
            seen_shift[sk] = True
            raw.append({
                "Date": d,
                "Label": d.strftime("%m/%d") + "_" + (s or ""),
                "SortDate": d,
                "SortKey": s or ""
            })

    def add_day(d: datetime):
        dk = d.strftime("%Y-%m-%d")
        if dk not in seen_date:
            seen_date[dk] = True
            raw.append({
                "Date": d,
                "Label": d.strftime("%m/%d"),
                "SortDate": d,
                "SortKey": ""
            })

    def add_week(d: datetime):
        iso = d.isocalendar()
        y, w = iso[0], iso[1]
        wk = f"{y}-W{w:02d}"
        if wk not in seen_date:
            seen_date[wk] = True
            monday = first_day_of_iso_week(y, w)
            raw.append({
                "Date": monday,
                "Label": monday.strftime("%m/%d"),
                "SortDate": monday,
                "SortKey": ""
            })

    def add_month(d: datetime):
        ym = d.strftime("%Y-%m")
        if ym not in seen_date:
            seen_date[ym] = True
            first = datetime(d.year, d.month, 1)
            raw.append({
                "Date": first,
                "Label": d.strftime("%m月"),
                "SortDate": first,
                "SortKey": ""
            })

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

    # Sort: SortDate asc, then 白班 first
    def sort_key_fn(c):
        sd = c["SortDate"]
        sk = c["SortKey"]
        # priority for shift
        if sk == "白班":
            shift_prio = 0
        elif sk == "夜班":
            shift_prio = 1
        else:
            shift_prio = 2
        return (sd, shift_prio, sk)

    raw.sort(key=sort_key_fn)

    # Deduplicate by Label
    seen = {}
    out = []
    for c in raw:
        lbl = c["Label"]
        if lbl not in seen:
            seen[lbl] = True
            out.append(c)
    return out

def agg_key_for_row_s(r: ScheduleRow, col_dim: str) -> str:
    d = r.PlanDate
    if not d:
        return ""
    if col_dim == "day":
        return d.strftime("%m/%d")
    elif col_dim == "week":
        y, w = d.isocalendar()[0], d.isocalendar()[1]
        monday = first_day_of_iso_week(y, w)
        return monday.strftime("%m/%d")
    elif col_dim == "month":
        return d.strftime("%m月")
    else:
        return d.strftime("%m/%d") + "_" + (r.ShiftName or "")

def bal_col_key(r: BalanceRow, col_dim: str) -> str:
    d = r.PlanDate
    if not d:
        return ""
    if col_dim == "day":
        return d.strftime("%m/%d")
    elif col_dim == "week":
        y, w = d.isocalendar()[0], d.isocalendar()[1]
        return first_day_of_iso_week(y, w).strftime("%m/%d")
    elif col_dim == "month":
        return d.strftime("%m月")
    else:
        return d.strftime("%m/%d") + "_" + (r.ShiftName or "")

def build_io_sched(sched: List[ScheduleRow], dim_col: str, cols: List[dict], plan_item: str, cumulative: bool, col_dim: str):
    filtered = [r for r in sched if r.PlanItem == plan_item]
    if not filtered:
        return [], []

    actual_dim = dim_col
    if dim_col == "ITEM_NO":
        actual_dim = "SKU"
    elif dim_col == "STYLE":
        actual_dim = "STYLE"

    agg = {}
    pivot = {}
    dim_set = set()

    for r in filtered:
        if actual_dim == "LINE_CODE":
            dim_val = r.LineCode or ""
        elif actual_dim == "STYLE":
            dim_val = r.Style or ""
        else:
            dim_val = r.SKU or ""
        col_l = agg_key_for_row_s(r, col_dim)
        key = (dim_val, col_l)
        agg[key] = agg.get(key, 0) + (r.PlanValue or 0)

    for (dim_val, col_l), v in agg.items():
        if dim_val not in pivot:
            pivot[dim_val] = {}
        pivot[dim_val][col_l] = pivot[dim_val].get(col_l, 0) + v
        dim_set.add(dim_val)

    dims = sorted(dim_set)
    col_headers = col_labels(cols)

    rows = []
    for dim in dims:
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
    filtered = [r for r in sched if r.PlanItem == plan_item]
    if not filtered:
        return [], []

    # agg by (item, line, style, col)
    agg = {}
    pivot = {}
    row_set = {}

    for r in filtered:
        rk = (r.SKU or "", r.LineCode or "", r.Style or "")
        col_l = agg_key_for_row_s(r, col_dim)
        key = (rk, col_l)
        agg[key] = agg.get(key, 0) + (r.PlanValue or 0)

    for (rk, col_l), v in agg.items():
        if rk not in pivot:
            pivot[rk] = {}
        pivot[rk][col_l] = pivot[rk].get(col_l, 0) + v
        row_set[rk] = True

    row_keys = list(row_set.keys())
    row_keys.sort(key=lambda x: (x[1], x[0], x[2]))  # line, item, style

    col_headers = col_labels(cols)
    rows = []
    for rk in row_keys:
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
    if not bal:
        return [], []
    if dim_col == "LINE_CODE":
        return [], []

    def dim_val_fn(r: BalanceRow):
        if dim_col == "STYLE":
            return r.Style or ""
        return r.ItemCode or ""

    agg = {}
    dim_set = set()
    for r in bal:
        dv = dim_val_fn(r)
        col = bal_col_key(r, col_dim)
        key = (dv, col)
        agg[key] = agg.get(key, 0) + (r.BalanceQty or 0)
        dim_set.add(dv)

    pivot = {}
    for (dv, col), v in agg.items():
        if dv not in pivot:
            pivot[dv] = {}
        pivot[dv][col] = pivot[dv].get(col, 0) + v

    dims = sorted(dim_set)
    col_headers = col_labels(cols)
    rows = []
    for dim in dims:
        entry = {dim_col: dim}
        vals = pivot.get(dim, {})
        for h in col_headers:
            entry[h] = int(vals.get(h, 0))
        rows.append(entry)
    return col_headers, rows

def bal_to_sched(bal: List[BalanceRow]) -> List[ScheduleRow]:
    out = []
    for b in bal:
        out.append(ScheduleRow(
            SKU=b.ItemCode,
            Style=b.Style or "",
            PlanDate=b.PlanDate,
            ShiftName=b.ShiftName or "",
            PlanValue=b.BalanceQty or 0,
            PlanItem="INPUT",
            LineCode=""
        ))
    return out

def build_one_report(sched: List[ScheduleRow], bal: List[BalanceRow], rtype: str, dim: str, cols: List[dict], col_dim: str):
    """rtype: daily_input/out/checkin/checkout, cum_*, balance/boh"""
    # normalize
    rt = rtype.lower()
    if rt in ("boh", "balance"):
        rt = "balance"

    # map for detail vs flat
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
        if dim == "detail":
            return build_io_sched_detail(bal_to_sched(bal), cols, "INPUT", False, col_dim)
        else:
            return build_balance(bal, dim, cols, col_dim)

    if rt not in mapping:
        # fallback for older names like input/output only
        # try to infer
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

    if dim == "detail":
        return build_io_sched_detail(sched, cols, plan, cum, col_dim)
    else:
        return build_io_sched(sched, dim, cols, plan, cum, col_dim)

# ---------- Excel loading ----------

def _load_openpyxl_data(data_dir: str) -> DataCache:
    import openpyxl

    data_dir = _resolve_data_dir(data_dir)

    # 1. Master
    mm_path = _find_file(data_dir, "料号主表.xlsx", ["料号主表", "料号", "master", "物料"])
    if not mm_path or not os.path.exists(mm_path):
        raise FileNotFoundError(f"料号主表.xlsx not found in {data_dir}, tried {mm_path}")

    wb = openpyxl.load_workbook(mm_path, data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows_iter = ws.iter_rows(min_row=1, max_row=1, values_only=True)
    headers = list(next(rows_iter))
    item_no_idx = _get_col_index(headers, "ITEM_NO")
    prod_cat_idx = _get_col_index(headers, "PRODUCT_CATEGORY")
    style_idx = _get_col_index(headers, "PRODUCT_STYLE")
    if item_no_idx < 0 or prod_cat_idx < 0:
        # try alternative reading with header string search
        raise ValueError(f"料号主表 missing ITEM_NO or PRODUCT_CATEGORY, headers={headers}")

    item_to_cat = {}
    item_to_style = {}
    fg_items = []
    gb_items = []
    style_fg_set = set()
    style_gb_set = set()

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        if item_no_idx >= len(row) or prod_cat_idx >= len(row):
            continue
        item = row[item_no_idx]
        cat = row[prod_cat_idx]
        if item is None or cat is None:
            continue
        item = str(item).strip()
        cat = str(cat).strip()
        if not item or not cat:
            continue
        style = ""
        if style_idx >= 0 and style_idx < len(row) and row[style_idx] is not None:
            style = str(row[style_idx]).strip()
        item_to_cat[item] = cat
        item_to_style[item] = style
        if cat == "成品":
            fg_items.append(item)
            if style:
                style_fg_set.add(style)
        elif cat == "GB":
            gb_items.append(item)
            if style:
                style_gb_set.add(style)
    wb.close()

    fg_set = set(fg_items)
    gb_set = set(gb_items)
    style_fg = sorted(style_fg_set)
    style_gb = sorted(style_gb_set)

    # 2. Schedule
    sched_path = _find_file(data_dir, "排产结果表.xlsx", ["排产结果表", "排产", "schedule", "排产结果"])
    if not sched_path or not os.path.exists(sched_path):
        raise FileNotFoundError(f"排产结果表.xlsx not found in {data_dir}")

    wb2 = openpyxl.load_workbook(sched_path, data_only=True, read_only=True)
    ws2 = wb2[wb2.sheetnames[0]]
    headers2 = list(next(ws2.iter_rows(min_row=1, max_row=1, values_only=True)))
    line_idx = _get_col_index(headers2, "LINE_CODE")
    shift_idx = _get_col_index(headers2, "SHIFT_NAME")
    plan_item_idx = _get_col_index(headers2, "PLAN_ITEM")
    sku_idx = _get_col_index(headers2, "SKU")
    plan_date_idx = _get_col_index(headers2, "PLAN_DATE")
    plan_val_idx = _get_col_index(headers2, "PLAN_VALUE")

    sched_fg = []
    sched_gb = []
    line_fg_set = set()
    line_gb_set = set()

    for row in ws2.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        # bounds check
        if len(row) <= max(line_idx, shift_idx, plan_item_idx, sku_idx, plan_date_idx, plan_val_idx):
            continue
        sku_raw = row[sku_idx]
        if not sku_raw:
            continue
        sku = str(sku_raw).strip()
        is_fg = sku in fg_set
        is_gb = sku in gb_set
        if not is_fg and not is_gb:
            continue
        # parse value
        val_raw = row[plan_val_idx]
        try:
            val = float(val_raw) if val_raw is not None and str(val_raw).strip() != "" else 0.0
        except:
            try:
                val = float(str(val_raw).strip())
            except:
                val = 0.0
        plan_date_raw = row[plan_date_idx]
        pd = _to_datetime(plan_date_raw)
        if not pd:
            continue
        sr = ScheduleRow(
            LineCode=str(row[line_idx] or "").strip(),
            ShiftName=str(row[shift_idx] or "").strip(),
            PlanItem=str(row[plan_item_idx] or "").strip(),
            SKU=sku,
            PlanDate=pd,
            PlanValue=val,
            Style=item_to_style.get(sku, "")
        )
        if is_fg:
            sched_fg.append(sr)
            if sr.LineCode:
                line_fg_set.add(sr.LineCode)
        else:
            sched_gb.append(sr)
            if sr.LineCode:
                line_gb_set.add(sr.LineCode)
    wb2.close()

    # 3. Balance
    bal_path = _find_file(data_dir, "结存表.xlsx", ["结存表", "结存", "balance"])
    if not bal_path or not os.path.exists(bal_path):
        raise FileNotFoundError(f"结存表.xlsx not found in {data_dir}")

    wb3 = openpyxl.load_workbook(bal_path, data_only=True, read_only=True)
    ws3 = wb3[wb3.sheetnames[0]]
    headers3 = list(next(ws3.iter_rows(min_row=1, max_row=1, values_only=True)))
    bal_date_idx = _get_col_index(headers3, "PLAN_DATE")
    bal_shift_idx = _get_col_index(headers3, "SHIFT_NAME")
    bal_item_idx = _get_col_index(headers3, "ITEM_CODE")
    bal_qty_idx = _get_col_index(headers3, "BALANCE_QTY")

    bal_fg = []
    bal_gb = []

    for row in ws3.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        if len(row) <= max(bal_date_idx, bal_shift_idx, bal_item_idx, bal_qty_idx):
            continue
        item_raw = row[bal_item_idx]
        if not item_raw:
            continue
        item_code = str(item_raw).strip()
        is_fg = item_code in fg_set
        is_gb = item_code in gb_set
        if not is_fg and not is_gb:
            continue
        qty_raw = row[bal_qty_idx]
        try:
            qty = float(qty_raw) if qty_raw is not None and str(qty_raw).strip() != "" else 0.0
        except:
            try:
                qty = float(str(qty_raw).strip())
            except:
                qty = 0.0
        pd = _to_datetime(row[bal_date_idx])
        if not pd:
            continue
        br = BalanceRow(
            PlanDate=pd,
            ShiftName=str(row[bal_shift_idx] or "").strip(),
            ItemCode=item_code,
            BalanceQty=qty,
            Style=item_to_style.get(item_code, "")
        )
        if is_fg:
            bal_fg.append(br)
        else:
            bal_gb.append(br)
    wb3.close()

    fg_items_sorted = sorted(set(fg_items))
    gb_items_sorted = sorted(set(gb_items))
    line_fg = sorted(line_fg_set)
    line_gb = sorted(line_gb_set)

    return DataCache(
        item_to_cat=item_to_cat,
        item_to_style=item_to_style,
        fg_items=fg_items_sorted,
        gb_items=gb_items_sorted,
        sched_fg=sched_fg,
        sched_gb=sched_gb,
        bal_fg=bal_fg,
        bal_gb=bal_gb,
        line_fg=line_fg,
        line_gb=line_gb,
        style_fg=style_fg,
        style_gb=style_gb,
    )

# Public alias for compatibility
def load_data(data_dir: str = None) -> DataCache:
    if data_dir is None:
        data_dir = _resolve_data_dir()
    else:
        data_dir = _resolve_data_dir(data_dir)
    return _load_openpyxl_data(data_dir)

# Global cache singleton
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

# ----- Backward compat helpers -----

def build_col_defs(cache: DataCache, col_mode: str, cat: str):
    # cat: FG or GB or 成品/GB
    # normalize
    if cat in ("FG", "成品"):
        sched = cache.sched_fg
        bal = cache.bal_fg
    else:
        sched = cache.sched_gb
        bal = cache.bal_gb
    return get_col_defs(sched, bal, col_mode)

def build_io_sched_compat(cache, dim, col_mode, report_type, cat, dim_filter=None):
    # report_type INPUT/OUTPUT/CUM_INPUT etc?
    # Normalize to INPUT/OUTPUT and cumulative flag
    cumulative = False
    base_type = report_type
    if report_type in ("CUM_INPUT", "CUM_OUTPUT", "cum_input", "cum_output"):
        cumulative = True
        base_type = "INPUT" if "INPUT" in report_type else "OUTPUT"
    # also handle already uppercase
    is_input = "INPUT" in base_type and "OUTPUT" not in base_type or base_type == "INPUT"
    plan_item = "INPUT" if is_input else "OUTPUT" if "OUTPUT" in base_type else base_type
    # map
    sched = cache.sched_fg if cat in ("FG", "成品") else cache.sched_gb
    cols = get_col_defs(sched, cache.bal_fg if cat in ("FG","成品") else cache.bal_gb, col_mode)
    ch, rows = build_io_sched(sched, dim, cols, plan_item, cumulative, col_mode)
    # convert to old shape?
    # return same as new
    return {"cols": ch, "rows": rows, "columns": ch, "col_defs": cols}

def build_balance_compat(cache, dim, col_mode, cat, dim_filter=None):
    bal = cache.bal_fg if cat in ("FG","成品") else cache.bal_gb
    sched = cache.sched_fg if cat in ("FG","成品") else cache.sched_gb
    cols = get_col_defs(sched, bal, col_mode)
    ch, rows = build_balance(bal, dim, cols, col_mode)
    return {"cols": ch, "rows": rows, "columns": ch}

def build_one_report_compat(cache, dim, col_mode, report_type, cat, dim_filter=None):
    # report_type: INPUT, OUTPUT, CUM_INPUT, CUM_OUTPUT, BALANCE
    # returns dict
    sched = cache.sched_fg if cat in ("FG","成品") else cache.sched_gb
    bal = cache.bal_fg if cat in ("FG","成品") else cache.bal_gb
    cols = get_col_defs(sched, bal, col_mode)
    rtype_map = {
        "INPUT": "daily_input",
        "OUTPUT": "daily_output",
        "CUM_INPUT": "cum_input",
        "CUM_OUTPUT": "cum_output",
        "BALANCE": "balance"
    }
    # convert if incoming is already mapped
    inv_map = {v:k for k,v in rtype_map.items()}
    if report_type in inv_map:
        internal_rt = inv_map[report_type]
        # Wait actually we need go's rtype
        go_rtype = report_type
    else:
        # assume report_type is GO style like daily_input
        go_rtype = report_type
        # but build_one_report expects go style
    ch, rows = build_one_report(sched, bal, go_rtype, dim, cols, col_mode)
    return {"columns": ch, "rows": rows}

# For direct use
def build_reports_for_group(cache: DataCache, dim: str, col_dim: str, group: str,
                            line_code_filter: str = "", item_no_filter: str = "", style_filter: str = ""):
    """
    Build 9 reports: daily/cum for INPUT, OUTPUT, CHECKIN, CHECKOUT + BOH
    group: 成品 / GB / FG / GB
    dim: LINE_CODE / ITEM_NO / STYLE / detail / ""
    """
    is_fg = group in ("成品", "FG", "FG (Finished)", "FG (SKU)")
    if is_fg:
        sched = list(cache.sched_fg)
        bal = list(cache.bal_fg)
    else:
        sched = list(cache.sched_gb)
        bal = list(cache.bal_gb)

    # Apply filters
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
    # 8 I/O reports + BOH = 9
    all_rtypes = [
        "daily_input", "daily_output", "daily_checkin", "daily_checkout",
        "cum_input", "cum_output", "cum_checkin", "cum_checkout",
        "balance"
    ]
    for rtype in all_rtypes:
        col_h, rows = build_one_report(sched, bal, rtype, dim, col_defs, col_dim)
        result[rtype] = {"columns": col_h, "rows": rows}
    result["pair_count"] = len(col_defs)
    return result, col_defs

def get_meta(cache: DataCache, group: str, col_dim: str):
    is_fg = group in ("成品", "FG")
    if is_fg:
        sched = cache.sched_fg
        bal = cache.bal_fg
        line_codes = cache.line_fg
        items = cache.fg_items
        styles = cache.style_fg
    else:
        sched = cache.sched_gb
        bal = cache.bal_gb
        line_codes = cache.line_gb
        items = cache.gb_items
        styles = cache.style_gb
    cols = get_col_defs(sched, bal, col_dim)
    return {
        "date_shift_pairs": [c["Label"] for c in cols],
        "line_codes": line_codes,
        "items": items,
        "styles": styles,
        # compat with old api
        "lines_fg": cache.line_fg,
        "lines_gb": cache.line_gb,
        "items_fg": cache.fg_items,
        "items_gb": cache.gb_items,
        "styles_fg": cache.style_fg,
        "styles_gb": cache.style_gb,
    }

# Keep old functions for backward
def load_and_build(data_dir, dim, col_mode, cat, dim_filter=None):
    cache = load_data(data_dir)
    meta = {
        "lines": get_dim_values(cache, "LINE_CODE", cat),
        "items": get_dim_values(cache, "ITEM_NO", cat),
        "styles": get_dim_values(cache, "STYLE", cat),
        "fg_items": cache.fg_items,
        "gb_items": cache.gb_items,
    }
    reports = {}
    is_fg = cat in ("FG", "成品", "FG (SKU)")
    sched = cache.sched_fg if is_fg else cache.sched_gb
    bal = cache.bal_fg if is_fg else cache.bal_gb
    col_defs = get_col_defs(sched, bal, col_mode)
    for rt in ["daily_input", "daily_output", "daily_checkin", "daily_checkout", "cum_input", "cum_output", "cum_checkin", "cum_checkout", "balance"]:
        ch, rows = build_one_report(sched, bal, rt, dim, col_defs, col_mode)
        reports[rt] = {"columns": ch, "rows": rows, "cols": ch}
    return {"meta": meta, "reports": reports}

def get_dim_values(cache: DataCache, dim: str, cat: str):
    if cat in ("FG", "成品"):
        if dim == "LINE_CODE":
            return cache.line_fg
        elif dim == "ITEM_NO":
            return cache.fg_items
        elif dim == "STYLE":
            return cache.style_fg
    else:
        if dim == "LINE_CODE":
            return cache.line_gb
        elif dim == "ITEM_NO":
            return cache.gb_items
        elif dim == "STYLE":
            return cache.style_gb
    return []
