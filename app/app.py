import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import openpyxl
import os
from pathlib import Path

st.set_page_config(page_title="多版本计划拼接结果展示", layout="wide")

DATA_DIR = Path(__file__).parent.parent / "data"

# ============================================
# Cache: load data once
# ============================================
@st.cache_data
def load_sku_mapping():
    """Load 虚拟料号关系 → SKU ↔ Style/Color/GB mapping"""
    fp = DATA_DIR / "虚拟料号关系 20260623.xlsx"
    if not fp.exists():
        return None
    df = pd.read_excel(fp, sheet_name="Sheet1")
    df.columns = ["SKU", "Style", "Color", "GB_PN_旧", "GB_PN", "FR_PN_旧", "FR_PN",
                   "LT_PN_旧", "LT_PN", "RT_PN_旧", "RT_PN"]
    df = df[["SKU", "Style", "Color", "GB_PN", "FR_PN", "LT_PN", "RT_PN"]].copy()
    df["SKU"] = df["SKU"].astype(str).str.strip()
    return df

@st.cache_data
def load_fcst():
    """Load FCST (ExF) from gated file"""
    fp = DATA_DIR / "Copy of Lager FATP By SKU Build Plan-20260713 gated.xlsx"
    if not fp.exists():
        return None
    wb = openpyxl.load_workbook(fp, data_only=True)
    ws = wb["FCST"]
    rows = []
    for r in ws.iter_rows(min_row=4, max_row=ws.max_row, values_only=True):
        sku = str(r[4]).strip() if r[4] else None
        if not sku:
            continue
        prod_line = str(r[3]).strip() if r[3] else ""
        # Weekly values from col 8 onwards (I = index 8)
        weeks = {}
        for ci in range(8, min(60, len(r))):
            date_val = ws.cell(row=3, column=ci+1).value  # header row 3 has dates
            val = r[ci]
            if isinstance(date_val, datetime) and val is not None:
                week_label = f"{date_val.strftime('%b %d')} Sat"
                weeks[week_label] = val
        rows.append({"SKU": sku, "Product_Line": prod_line, **weeks})
    df = pd.DataFrame(rows)
    return df

@st.cache_data
def load_plan(version="ungated"):
    """Load 排产结果, filter OUTPUT+PKG, aggregate to weekly"""
    fname = f"Copy of Lager FATP By SKU Build Plan-20260713 {version}.xlsx"
    fp = DATA_DIR / fname
    if not fp.exists():
        st.warning(f"Missing: {fname}")
        return None

    wb = openpyxl.load_workbook(fp, data_only=True)
    ws = wb["排产结果"]

    # Read header dates (row 2, col I onwards = index 8)
    date_col_map = {}  # col_index → datetime
    for c in range(9, ws.max_column + 1):  # 1-indexed Excel cols
        v = ws.cell(row=2, column=c).value
        if isinstance(v, (int, float)) and v > 40000:
            dt = datetime(1899, 12, 30) + timedelta(days=v)
            date_col_map[c - 1] = dt  # 0-indexed

    # Read data rows: filter dtype=OUTPUT, line contains PKG
    records = []
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row, values_only=True):
        dtype = str(row[3]).strip() if row[3] else ""
        line = str(row[2]).strip() if row[2] else ""
        sku = str(row[5]).strip() if row[5] else ""
        shift = str(row[4]).strip() if row[4] else ""
        is_prod = str(row[6]).strip() if row[6] else ""

        if dtype != "OUTPUT" or "PKG" not in line or not sku or sku == "None" or "TTL" in sku:
            continue

        # Sum shifts (白班+夜班) by SKU
        records.append({
            "SKU": sku,
            "Line": line,
            "Shift": shift,
            "dtype": dtype,
            "daily": {date_col_map[i]: (row[i] if row[i] is not None and not isinstance(row[i], str) else 0)
                      for i in date_col_map if i < len(row)}
        })

    if not records:
        return None

    df = pd.DataFrame(records)

    # Pivot daily data: one row per SKU, columns = dates
    daily_rows = []
    for sku, grp in df.groupby("SKU"):
        all_dates = {}
        for _, r in grp.iterrows():
            for d, v in r["daily"].items():
                all_dates[d] = all_dates.get(d, 0) + (v if isinstance(v, (int, float)) else 0)
        daily_rows.append({"SKU": sku, **all_dates})

    df_daily = pd.DataFrame(daily_rows)

    # Weekly aggregation
    # Business week: Mon~Sun. Saturday Cut-Off → week ends on Sat
    # Wednesday Cut-Off: Thu~Wed
    if df_daily.empty:
        return None

    date_cols = [c for c in df_daily.columns if isinstance(c, datetime)]
    date_cols.sort()

    weeks_sat = {}
    weeks_wed = {}
    for d in date_cols:
        # Monday=0, Sunday=6
        dow = d.weekday()
        # Saturday Cut-Off: week is Mon(0)~Sun(6), label = Sat of that week
        if dow <= 5:  # Mon to Sat
            sat = d + timedelta(days=5 - dow)
        else:  # Sunday
            sat = d + timedelta(days=-1)
        sat_label = sat.strftime("%b %d Sat")

        # Wednesday Cut-Off: Thu(-3)~Wed(+2), label = Wed
        if dow <= 2:  # Mon(0)~Wed(2): week starts prev Thu
            wed = d + timedelta(days=2 - dow)
        else:  # Thu(3)~Sun(6): week ends this Wed
            wed = d + timedelta(days=2 - dow)
        wed_label = wed.strftime("%b %d Wed")

        if sat_label not in weeks_sat:
            weeks_sat[sat_label] = []
        weeks_sat[sat_label].append(d)
        if wed_label not in weeks_wed:
            weeks_wed[wed_label] = []
        weeks_wed[wed_label].append(d)

    # Aggregate
    result_dfs = {"Saturday": [], "Wednesday": []}
    for cut_label, weeks in [("Saturday", weeks_sat), ("Wednesday", weeks_wed)]:
        rows = []
        for _, rec in df_daily.iterrows():
            sku = rec["SKU"]
            week_vals = {}
            for wk_label, day_list in weeks.items():
                val = sum(rec[d] for d in day_list if d in rec and pd.notna(rec[d]))
                if val > 0:
                    week_vals[wk_label] = val
            if week_vals:
                rows.append({"SKU": sku, **week_vals})
        result_dfs[cut_label] = pd.DataFrame(rows) if rows else pd.DataFrame()

    return result_dfs

@st.cache_data
def load_ctb():
    """Load CTB data"""
    fp = DATA_DIR / "Modelo SKU CTB Publish 0710 final.xlsx"
    if not fp.exists():
        return None
    wb = openpyxl.load_workbook(fp, data_only=True)
    ws = wb["Modelo SKU CTB"]
    rows = []
    for r in ws.iter_rows(min_row=4, max_row=ws.max_row, values_only=True):
        sku = str(r[6]).strip() if r[6] else ""
        style = str(r[2]).strip() if r[2] else ""
        color = str(r[3]).strip() if r[3] else ""
        if not sku:
            continue
        daily = {}
        for ci in range(9, min(50, len(r))):
            v = r[ci]
            date_hdr = ws.cell(row=3, column=ci+1).value
            if isinstance(date_hdr, datetime) and v is not None and isinstance(v, (int, float)):
                daily[date_hdr] = v
        rows.append({"SKU": sku, "Style": style, "Color": color, "daily": daily})
    return pd.DataFrame(rows) if rows else None

# ============================================
# Build report
# ============================================
@st.cache_data
def build_report():
    """Combine all data → report format"""
    sku_map = load_sku_mapping()
    fcst = load_fcst()
    gated = load_plan("gated")
    ungated = load_plan("ungated")
    ctb_df = load_ctb()

    # Merge SKU attributes
    sku_attrs = {}
    if sku_map is not None:
        for _, r in sku_map.iterrows():
            sku_attrs[r["SKU"]] = {"Style": r.get("Style", ""), "Color": r.get("Color", ""),
                                    "GB_PN": r.get("GB_PN", "")}

    # Build rows for output table
    all_skus = set()
    if fcst is not None:
        all_skus.update(fcst["SKU"].unique())
    if gated:
        for cut, df in gated.items():
            if not df.empty:
                all_skus.update(df["SKU"].unique())
    if ungated:
        for cut, df in ungated.items():
            if not df.empty:
                all_skus.update(df["SKU"].unique())
    if ctb_df is not None:
        all_skus.update(ctb_df["SKU"].unique())

    all_skus = sorted(s for s in all_skus if s and s != "nan")

    # Collect all week columns
    all_weeks = set()
    if fcst is not None:
        for c in fcst.columns:
            if "Sat" in str(c) or "Wed" in str(c):
                all_weeks.add(c)
    for plan_dict in [gated, ungated]:
        if plan_dict:
            for cut, df in plan_dict.items():
                if not df.empty:
                    for c in df.columns:
                        if c != "SKU":
                            all_weeks.add(c)

    def week_sort_key(w):
        parts = w.split(" ")
        if len(parts) >= 3:
            try:
                return datetime.strptime(f"{parts[0]} {parts[1]} 2026", "%b %d %Y")
            except:
                return datetime(2099, 1, 1)
        return datetime(2099, 1, 1)
    all_weeks = sorted(all_weeks, key=week_sort_key)

    rows_data = []
    for sku in all_skus:
        attrs = sku_attrs.get(sku, {})
        style = attrs.get("Style", "")
        color = attrs.get("Color", "")
        gb_pn = attrs.get("GB_PN", "")

        # --- ExF row ---
        exf_vals = {}
        if fcst is not None:
            m = fcst[fcst["SKU"] == sku]
            if not m.empty:
                for w in all_weeks:
                    if w in m.columns:
                        exf_vals[w] = m.iloc[0][w]

        # --- Ungated ETD (Sat) with pallet rounding ---
        def get_plan_vals(plan_dict, cut_day, need_round=False, pallet=864):
            vals = {}
            if plan_dict is None or plan_dict.get(cut_day) is None:
                return vals
            df = plan_dict[cut_day]
            m = df[df["SKU"] == sku]
            if m.empty:
                return vals
            for w in all_weeks:
                if w in m.columns:
                    v = m.iloc[0][w]
                    if pd.notna(v) and v > 0:
                        if need_round:
                            v = (v // pallet) * pallet
                        vals[w] = v
            return vals

        ung_etd = get_plan_vals(ungated, "Saturday", need_round=True)
        ung_pack = get_plan_vals(ungated, "Wednesday")
        gat_etd = get_plan_vals(gated, "Saturday", need_round=True)
        gat_pack = get_plan_vals(gated, "Wednesday")

        # CTB
        ctb_vals = {}
        if ctb_df is not None:
            m = ctb_df[ctb_df["SKU"] == sku]
            if not m.empty:
                all_daily = {}
                for _, r in m.iterrows():
                    for d, v in r["daily"].items():
                        if v and v > 0:
                            dow = d.weekday()
                            # Map to week (Mon~Sun)
                            sat = d + timedelta(days=5 - dow) if dow <= 5 else d + timedelta(days=-1)
                            sat_label = sat.strftime("%b %d Sat")
                            all_daily[sat_label] = all_daily.get(sat_label, 0) + v
                ctb_vals = all_daily

        # Build rows
        def diff_dict(base, sub):
            return {k: (base.get(k, 0) or 0) - (sub.get(k, 0) or 0) for k in set(list(base.keys()) + list(sub.keys()))}

        rows_data.append({
            "PN": sku, "Usage": "Spring", "Style": style, "Color": color,
            "Version-Type": "ExF", "Version-Detail": "", "Cut Day": "Saturday",
            **exf_vals
        })
        rows_data.append({
            "PN": sku, "Usage": "Spring", "Style": style, "Color": color,
            "Version-Type": "Ungated", "Version-Detail": "ETD", "Cut Day": "Saturday",
            **ung_etd
        })
        rows_data.append({
            "PN": sku, "Usage": "Spring", "Style": style, "Color": color,
            "Version-Type": "Ungated", "Version-Detail": "ETD vs ExF", "Cut Day": "Saturday",
            **diff_dict(ung_etd, exf_vals)
        })
        rows_data.append({
            "PN": sku, "Usage": "Spring", "Style": style, "Color": color,
            "Version-Type": "Ungated", "Version-Detail": "Packout", "Cut Day": "Wednesday",
            **ung_pack
        })
        rows_data.append({
            "PN": sku, "Usage": "Spring", "Style": style, "Color": color,
            "Version-Type": "Ungated", "Version-Detail": "Packout vs ExF", "Cut Day": "Wednesday",
            **diff_dict(ung_pack, exf_vals)
        })
        rows_data.append({
            "PN": sku, "Usage": "Spring", "Style": style, "Color": color,
            "Version-Type": "Gated", "Version-Detail": "ETD", "Cut Day": "Saturday",
            **gat_etd
        })
        rows_data.append({
            "PN": sku, "Usage": "Spring", "Style": style, "Color": color,
            "Version-Type": "Gated", "Version-Detail": "ETD vs ExF", "Cut Day": "Saturday",
            **diff_dict(gat_etd, exf_vals)
        })
        rows_data.append({
            "PN": sku, "Usage": "Spring", "Style": style, "Color": color,
            "Version-Type": "Gated", "Version-Detail": "Packout", "Cut Day": "Wednesday",
            **gat_pack
        })
        rows_data.append({
            "PN": sku, "Usage": "Spring", "Style": style, "Color": color,
            "Version-Type": "Gated", "Version-Detail": "Packout vs ExF", "Cut Day": "Wednesday",
            **diff_dict(gat_pack, exf_vals)
        })
        rows_data.append({
            "PN": sku, "Usage": "Spring", "Style": style, "Color": color,
            "Version-Type": "CTB", "Version-Detail": "", "Cut Day": "",
            **ctb_vals
        })

    df_report = pd.DataFrame(rows_data)
    return df_report, list(all_weeks)


# ============================================
# Streamlit UI
# ============================================
st.title("📊 多版本计划拼接结果展示")
st.caption("基于排产结果 + Forecast + CTB 的灵活报表")

with st.spinner("正在加载数据并构建报表..."):
    df_report, week_cols = build_report()

if df_report.empty:
    st.error("未能加载数据，请检查 data/ 目录下的数据文件")
    st.stop()

# --- Filters ---
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    styles = ["All"] + sorted(df_report["Style"].dropna().unique())
    sel_style = st.selectbox("Style", styles)
with col2:
    colors = ["All"] + sorted(df_report["Color"].dropna().unique())
    sel_color = st.selectbox("Color", colors)
with col3:
    types = ["All"] + sorted(df_report["Version-Type"].dropna().unique())
    sel_type = st.selectbox("Version-Type", types)
with col4:
    details = ["All"] + sorted(d for d in df_report["Version-Detail"].dropna().unique() if d)
    sel_detail = st.selectbox("Version-Detail", details)
with col5:
    skus = ["All"] + sorted(df_report["PN"].dropna().unique())
    sel_sku = st.selectbox("PN/SKU", skus)

# Filter
df_view = df_report.copy()
if sel_style != "All":
    df_view = df_view[df_view["Style"] == sel_style]
if sel_color != "All":
    df_view = df_view[df_view["Color"] == sel_color]
if sel_type != "All":
    df_view = df_view[df_view["Version-Type"] == sel_type]
if sel_detail != "All":
    df_view = df_view[df_view["Version-Detail"] == sel_detail]
if sel_sku != "All":
    df_view = df_view[df_view["PN"] == sel_sku]

# --- Display ---
display_cols = ["PN", "Usage", "Style", "Color", "Version-Type", "Version-Detail", "Cut Day"]
display_cols += [w for w in week_cols if w in df_view.columns]

# Format numbers
df_display = df_view[display_cols].copy()
for c in df_display.columns:
    if df_display[c].dtype in [np.float64, np.int64, float, int]:
        df_display[c] = df_display[c].apply(lambda x: f"{x:,.0f}" if pd.notna(x) and x != 0 else "")

st.write(f"**{len(df_view)} 行**")
st.dataframe(df_display, width=None, height=600)

# --- Download ---
csv = df_view.to_csv(index=False).encode("utf-8-sig")
st.download_button("📥 下载 CSV", csv, "report.csv", "text/csv")

# --- Summary stats ---
st.divider()
st.subheader("📈 汇总")
if sel_type == "All" or sel_type == "ExF":
    exf_total = sum(df_report[df_report["Version-Type"] == "ExF"][w].sum() for w in week_cols if w in df_report.columns if df_report[w].dtype in [float, int])
    st.metric("ExF 总量", f"{exf_total:,.0f}")
