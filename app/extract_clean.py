"""
Extract clean data → data-ref/
- sku_master.csv (wide, with Pallet_Qty)
- plan_output_gated.csv (wide: SKU | daily dates...)
- plan_output_ungated.csv (wide)
- ctb_cum.csv (wide: SKU | daily dates...)
- forecast.csv (wide: SKU | weekly saturday dates...)
"""
import csv, os, openpyxl
from datetime import datetime, timedelta
from collections import defaultdict

SRC = os.path.join(os.path.dirname(__file__), "..", "data")
DST = os.path.join(os.path.dirname(__file__), "..", "data-ref")
os.makedirs(DST, exist_ok=True)

def wcsv(name, headers, rows):
    path = os.path.join(DST, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print(f"  {name}: {len(rows)} data rows")

# ============================================================
# 1. sku_master.csv — with Pallet_Qty
# ============================================================
print("[1] sku_master.csv")
wb = openpyxl.load_workbook(f"{SRC}/虚拟料号关系 20260623.xlsx", data_only=True)
ws = wb["Sheet1"]
rows = []
for r in range(2, ws.max_row + 1):
    sku = str(ws.cell(r, 1).value or "").strip()
    if not sku: continue
    pallet = 240 if sku == "SK-1002701-01" else 864
    rows.append([
        sku,
        str(ws.cell(r, 2).value or "").strip(),
        str(ws.cell(r, 3).value or "").strip().upper(),
        str(ws.cell(r, 5).value or "").strip(),
        str(ws.cell(r, 7).value or "").strip(),
        str(ws.cell(r, 9).value or "").strip(),
        str(ws.cell(r, 11).value or "").strip(),
        pallet,
    ])
wcsv("sku_master.csv",
     ["SKU", "Style", "Color", "GB_PN", "FR_PN", "LT_PN", "RT_PN", "Pallet_Qty"],
     rows)

# ============================================================
# 2. plan_output_gated.csv + plan_output_ungated.csv (wide)
# ============================================================
def extract_plan_wide(version):
    fname = f"Copy of Lager FATP By SKU Build Plan-20260713 {version}.xlsx"
    fp = f"{SRC}/{fname}"
    if not os.path.exists(fp): return [], []
    wb = openpyxl.load_workbook(fp, data_only=True)
    ws = wb["排产结果"]

    # Build date column map: col_index → date
    date_cols = {}
    for c in range(9, ws.max_column + 1):
        v = ws.cell(row=2, column=c).value
        if isinstance(v, (int, float)) and v > 40000:
            date_cols[c] = datetime(1899, 12, 30) + timedelta(days=v)

    # Collect daily sums per PN (SKU or GB)
    daily = defaultdict(lambda: defaultdict(float))
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row, values_only=True):
        dtype = str(row[3]).strip() if row[3] else ""
        sku = str(row[5]).strip() if row[5] else ""
        if dtype != "OUTPUT" or not sku or "TTL" in sku or sku in ("None",""):
            continue
        for col_idx, dt in date_cols.items():
            v = row[col_idx - 1] if col_idx - 1 < len(row) else None
            if v is not None and isinstance(v, (int, float)):
                daily[sku][dt] += v

    if not daily: return [], []

    all_dates = sorted(set(d for v in daily.values() for d in v))
    headers = ["PN"] + [d.strftime("%Y-%m-%d") for d in all_dates]
    rows = []
    for pn in sorted(daily.keys()):
        row = [pn] + [round(daily[pn].get(d, 0)) for d in all_dates]
        rows.append(row)
    return headers, rows

print("[2] plan_output tables (wide)...")
for ver in ["gated", "ungated"]:
    h, r = extract_plan_wide(ver)
    if h:
        wcsv(f"plan_output_{ver}.csv", h, r)

# ============================================================
# 3. ctb_cum.csv (wide)
# ============================================================
print("[3] ctb_cum.csv")
wb = openpyxl.load_workbook(f"{SRC}/Modelo SKU CTB Publish 0710 final.xlsx", data_only=True)
ws = wb["Modelo SKU CTB"]
daily = defaultdict(dict)
for r in range(4, ws.max_row + 1):
    sku = str(ws.cell(r, 7).value or "").strip()
    if not sku: continue
    for c in range(10, min(ws.max_column + 1, 420)):
        dt = ws.cell(3, c).value
        v = ws.cell(r, c).value
        if isinstance(dt, datetime) and v is not None and isinstance(v, (int, float)):
            daily[sku][dt] = v
all_dates = sorted(set(d for v in daily.values() for d in v))
headers = ["SKU"] + [d.strftime("%Y-%m-%d") for d in all_dates]
rows = []
for sku in sorted(daily.keys()):
    rows.append([sku] + [round(daily[sku].get(d, 0)) for d in all_dates])
wcsv("ctb_cum.csv", headers, rows)

# ============================================================
# 4. forecast.csv (wide)
# ============================================================
print("[4] forecast.csv")
wb = openpyxl.load_workbook(f"{SRC}/Copy of Lager FATP By SKU Build Plan-20260713 gated.xlsx", data_only=True)
ws = wb["FCST"]
daily = defaultdict(dict)
for r in range(4, ws.max_row + 1):
    sku = str(ws.cell(r, 5).value or "").strip()
    if not sku: continue
    for c in range(9, 61):
        dt = ws.cell(3, c).value
        v = ws.cell(r, c).value
        if isinstance(dt, datetime) and v is not None and isinstance(v, (int, float)):
            daily[sku][dt] = v
all_dates = sorted(set(d for v in daily.values() for d in v))
headers = ["SKU"] + [d.strftime("%Y-%m-%d") for d in all_dates]
rows = []
for sku in sorted(daily.keys()):
    rows.append([sku] + [round(daily[sku].get(d, 0)) for d in all_dates])
wcsv("forecast.csv", headers, rows)

# ============================================================
# 5. ctb_gb.csv (wide) — from GB CTB file
# ============================================================
print("[5] ctb_gb.csv")
wb = openpyxl.load_workbook(f"{SRC}/Modelo GB CTB Publish 0710 final.xlsx", data_only=True)
ws = wb["Modelo GB CTB "]
from collections import defaultdict as dd
daily_gb = defaultdict(lambda: defaultdict(float))
for r in range(4, ws.max_row + 1):
    title = str(ws.cell(r, 1).value or "")
    if title != "CTB": continue
    style = str(ws.cell(r, 6).value or "").strip()
    color = str(ws.cell(r, 7).value or "").strip().upper()
    if not style or not color or color == "COLOR": continue
    # Generate GB PN same way as sku_master
    # Mapping: Style+Color → need to lookup the GB PN from sku_master
    # For now, use Style+Color as identifier
    for c in range(10, min(ws.max_column + 1, 420)):
        dt = ws.cell(3, c).value
        v = ws.cell(r, c).value
        if isinstance(dt, datetime) and v is not None and isinstance(v, (int, float)):
            daily_gb[(style, color)][dt] += v

# Map (style,color) → GB PN using sku_master
sku_rows = []
with open(os.path.join(DST, "sku_master.csv"), encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        if row: sku_rows.append(row)

style_color_to_gb = {}
for row in sku_rows:
    style_color_to_gb[(row[1], row[2])] = row[3]  # GB_PN

all_dates_gb = sorted(set(d for v in daily_gb.values() for d in v))
headers_gb = ["PN"] + [d.strftime("%Y-%m-%d") for d in all_dates_gb]
rows_gb = []
for (style, color), vals in sorted(daily_gb.items()):
    gb_pn = style_color_to_gb.get((style, color), f"{style}_{color}")
    row = [gb_pn] + [round(vals.get(d, 0)) for d in all_dates_gb]
    rows_gb.append(row)
wcsv("ctb_gb.csv", headers_gb, rows_gb)

print(f"\nDone → {DST}")
