import os
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScheduleRow:
    LineCode: str
    ShiftName: str
    PlanItem: str  # INPUT / OUTPUT
    SKU: str
    PlanDate: str  # yyyy-mm-dd
    PlanValue: float


@dataclass
class BalanceRow:
    PlanDate: str
    ShiftName: str
    ItemCode: str
    BalanceQty: float


@dataclass
class DataCache:
    item_to_cat: dict       # ITEM_NO -> PRODUCT_CATEGORY
    item_to_style: dict     # ITEM_NO -> PRODUCT_STYLE
    fg_items: list          # 成品 items
    gb_items: list          # GB items
    sched_fg: list          # ScheduleRow for 成品
    sched_gb: list          # ScheduleRow for GB
    bal_fg: list            # BalanceRow for 成品
    bal_gb: list            # BalanceRow for GB
    line_fg: set            # unique LINE_CODE for 成品
    line_gb: set            # unique LINE_CODE for GB
    style_fg: set           # unique STYLE for 成品
    style_gb: set           # unique STYLE for GB


def parse_date(s):
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d")
    except:
        try:
            return datetime.strptime(str(s).strip(), "%Y/%m/%d")
        except:
            return None


def date_to_iso_week(d):
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def agg_key_for_date(d, shift, col_mode):
    if col_mode == "shift":
        return f"{d.strftime('%m/%d')}_{shift}"
    elif col_mode == "day":
        return d.strftime("%m/%d")
    elif col_mode == "week":
        return date_to_iso_week(d)
    elif col_mode == "month":
        return d.strftime("%Y-%m")
    return f"{d.strftime('%m/%d')}_{shift}"


def first_day_of_iso_week(year, week):
    jan4 = datetime(year, 1, 4)
    jan4_weekday = jan4.weekday()
    # Monday = 0
    days_to_monday = (jan4_weekday - 0) % 7
    jan4_monday = jan4 - timedelta(days=days_to_monday)
    return jan4_monday + timedelta(weeks=week - 1)


def load_data(data_dir):
    import openpyxl

    # 1. Read material master
    mm_path = os.path.join(data_dir, "料号主表.xlsx")
    if not os.path.exists(mm_path):
        # try other names
        for f in os.listdir(data_dir):
            if "料号" in f or "master" in f.lower() or "物料" in f:
                mm_path = os.path.join(data_dir, f)
                break

    wb = openpyxl.load_workbook(mm_path, data_only=True)
    ws = wb[wb.sheetnames[0]]

    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    col_map = {h: i for i, h in enumerate(headers)}

    item_to_cat = {}
    item_to_style = {}
    fg_items = []
    gb_items = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        item_no = row[col_map.get("ITEM_NO", 0)]
        cat = row[col_map.get("PRODUCT_CATEGORY", 1)]
        style = row[col_map.get("PRODUCT_STYLE", 2)]
        if not item_no:
            continue
        item_no = str(item_no).strip()
        cat = str(cat).strip() if cat else ""
        style = str(style).strip() if style else ""
        item_to_cat[item_no] = cat
        item_to_style[item_no] = style
        if cat == "成品":
            fg_items.append(item_no)
        elif cat == "GB":
            gb_items.append(item_no)

    # 2. Read schedule results
    sched_path = os.path.join(data_dir, "排产结果表.xlsx")
    if not os.path.exists(sched_path):
        for f in os.listdir(data_dir):
            if "排产" in f or "sched" in f.lower():
                sched_path = os.path.join(data_dir, f)
                break

    wb2 = openpyxl.load_workbook(sched_path, data_only=True)
    ws2 = wb2[wb2.sheetnames[0]]
    headers2 = [c.value for c in next(ws2.iter_rows(min_row=1, max_row=1))]
    col_map2 = {h: i for i, h in enumerate(headers2)}

    sched_fg = []
    sched_gb = []
    line_fg = set()
    line_gb = set()
    style_fg = set()
    style_gb = set()

    for row in ws2.iter_rows(min_row=2, values_only=True):
        if not row[col_map2.get("SKU", 4)]:
            continue
        sku = str(row[col_map2.get("SKU", 4)]).strip()
        cat = item_to_cat.get(sku, "")
        if cat not in ("成品", "GB"):
            continue
        sr = ScheduleRow(
            LineCode=str(row[col_map2.get("LINE_CODE", 2)] or "").strip(),
            ShiftName=str(row[col_map2.get("SHIFT_NAME", 3)] or "").strip(),
            PlanItem=str(row[col_map2.get("PLAN_ITEM", 5)] or "").strip(),
            SKU=sku,
            PlanDate=str(row[col_map2.get("PLAN_DATE", 6)] or "").strip(),
            PlanValue=float(row[col_map2.get("PLAN_VALUE", 7)] or 0),
        )
        if cat == "成品":
            sched_fg.append(sr)
            line_fg.add(sr.LineCode)
            style_fg.add(item_to_style.get(sku, ""))
        else:
            sched_gb.append(sr)
            line_gb.add(sr.LineCode)
            style_gb.add(item_to_style.get(sku, ""))

    # 3. Read balance
    bal_path = os.path.join(data_dir, "结存表.xlsx")
    if not os.path.exists(bal_path):
        for f in os.listdir(data_dir):
            if "结存" in f or "balance" in f.lower():
                bal_path = os.path.join(data_dir, f)
                break

    wb3 = openpyxl.load_workbook(bal_path, data_only=True)
    ws3 = wb3[wb3.sheetnames[0]]
    headers3 = [c.value for c in next(ws3.iter_rows(min_row=1, max_row=1))]
    col_map3 = {h: i for i, h in enumerate(headers3)}

    bal_fg = []
    bal_gb = []

    for row in ws3.iter_rows(min_row=2, values_only=True):
        item_code = row[col_map3.get("ITEM_CODE", 3)]
        if not item_code:
            continue
        item_code = str(item_code).strip()
        cat = item_to_cat.get(item_code, "")
        if cat not in ("成品", "GB"):
            continue
        br = BalanceRow(
            PlanDate=str(row[col_map3.get("PLAN_DATE", 1)] or "").strip(),
            ShiftName=str(row[col_map3.get("SHIFT_NAME", 2)] or "").strip(),
            ItemCode=item_code,
            BalanceQty=float(row[col_map3.get("BALANCE_QTY", 6)] or 0),
        )
        if cat == "成品":
            bal_fg.append(br)
        else:
            bal_gb.append(br)

    return DataCache(
        item_to_cat=item_to_cat,
        item_to_style=item_to_style,
        fg_items=fg_items,
        gb_items=gb_items,
        sched_fg=sched_fg,
        sched_gb=sched_gb,
        bal_fg=bal_fg,
        bal_gb=bal_gb,
        line_fg=sorted(line_fg - {""}),
        line_gb=sorted(line_gb - {""}),
        style_fg=sorted(style_fg - {""}),
        style_gb=sorted(style_gb - {""}),
    )


def build_col_defs(cache, col_mode, cat):
    """Build column definitions from schedule + balance data."""
    sched = cache.sched_fg if cat == "FG" else cache.sched_gb
    bal = cache.bal_fg if cat == "FG" else cache.bal_gb

    keys = set()
    for sr in sched:
        d = parse_date(sr.PlanDate)
        if d:
            keys.add(agg_key_for_date(d, sr.ShiftName, col_mode))
    for br in bal:
        d = parse_date(br.PlanDate)
        if d:
            keys.add(agg_key_for_date(d, br.ShiftName, col_mode))

    def sort_key(k):
        if col_mode == "shift":
            parts = k.split("_")
            try:
                return (datetime.strptime(parts[0], "%m/%d"), parts[1])
            except:
                return (datetime(1900, 1, 1), k)
        elif col_mode == "day":
            try:
                return datetime.strptime(k, "%m/%d")
            except:
                return datetime(1900, 1, 1)
        elif col_mode == "week":
            try:
                parts = k.split("-W")
                y, w = int(parts[0]), int(parts[1])
                return first_day_of_iso_week(y, w)
            except:
                return datetime(1900, 1, 1)
        else:  # month
            try:
                return datetime.strptime(k, "%Y-%m")
            except:
                return datetime(1900, 1, 1)

    return sorted(keys, key=sort_key)


def build_io_sched(cache, dim, col_mode, report_type, cat, dim_filter=None):
    """
    Build I/O schedule report.
    dim: LINE_CODE, ITEM_NO, or STYLE
    report_type: INPUT or OUTPUT
    """
    sched = cache.sched_fg if cat == "FG" else cache.sched_gb
    cols = build_col_defs(cache, col_mode, cat)

    # Group by dimension
    groups = defaultdict(lambda: defaultdict(float))
    for sr in sched:
        if sr.PlanItem != report_type:
            continue
        if dim_filter and sr.SKU not in dim_filter and sr.LineCode not in dim_filter:
            continue
        d = parse_date(sr.PlanDate)
        if not d:
            continue
        col_key = agg_key_for_date(d, sr.ShiftName, col_mode)
        if dim == "LINE_CODE":
            row_key = sr.LineCode or "(blank)"
        elif dim == "ITEM_NO":
            row_key = sr.SKU
        elif dim == "STYLE":
            row_key = cache.item_to_style.get(sr.SKU, "(blank)")
        else:
            row_key = sr.SKU
        groups[row_key][col_key] += sr.PlanValue

    # Compute cumulative sums
    result = {}
    for row_key, col_vals in groups.items():
        sorted_vals = {}
        cum = 0.0
        for c in cols:
            val = col_vals.get(c, 0)
            cum += val
            sorted_vals[c] = cum if report_type.startswith("CUM") else val
        result[row_key] = sorted_vals

    return {"rows": result, "cols": cols}


def build_balance(cache, dim, col_mode, cat, dim_filter=None):
    """Build balance report."""
    bal = cache.bal_fg if cat == "FG" else cache.bal_gb
    cols = build_col_defs(cache, col_mode, cat)

    groups = defaultdict(lambda: defaultdict(float))
    for br in bal:
        if dim_filter and br.ItemCode not in dim_filter:
            continue
        d = parse_date(br.PlanDate)
        if not d:
            continue
        col_key = agg_key_for_date(d, br.ShiftName, col_mode)

        if dim == "LINE_CODE":
            row_key = "(no line)"
        elif dim == "ITEM_NO":
            row_key = br.ItemCode
        elif dim == "STYLE":
            row_key = cache.item_to_style.get(br.ItemCode, "(blank)")
        else:
            row_key = br.ItemCode
        groups[row_key][col_key] += br.BalanceQty

    result = {}
    for row_key, col_vals in groups.items():
        result[row_key] = {c: col_vals.get(c, 0) for c in cols}
    return {"rows": result, "cols": cols}


def build_one_report(cache, dim, col_mode, report_type, cat, dim_filter=None):
    """Dispatch to appropriate report builder."""
    if report_type == "BALANCE":
        return build_balance(cache, dim, col_mode, cat, dim_filter)
    return build_io_sched(cache, dim, col_mode, report_type, cat, dim_filter)


def build_reports(cache, dim, col_mode, cat, dim_filter=None):
    """Build all 5 reports for a given category."""
    reports = {}
    for rt in ["INPUT", "OUTPUT", "CUM_INPUT", "CUM_OUTPUT", "BALANCE"]:
        data = build_one_report(cache, dim, col_mode, rt, cat, dim_filter)
        reports[rt] = data
    return reports


def get_dim_values(cache, dim, cat):
    if cat == "FG":
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


def load_and_build(data_dir, dim, col_mode, cat, dim_filter=None):
    cache = load_data(data_dir)
    meta = {
        "lines": get_dim_values(cache, "LINE_CODE", cat),
        "items": get_dim_values(cache, "ITEM_NO", cat),
        "styles": get_dim_values(cache, "STYLE", cat),
        "fg_items": cache.fg_items,
        "gb_items": cache.gb_items,
    }
    reports = build_reports(cache, dim, col_mode, cat, dim_filter)
    return {"meta": meta, "reports": reports}
