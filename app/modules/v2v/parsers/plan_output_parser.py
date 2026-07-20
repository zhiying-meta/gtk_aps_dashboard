"""
Plan Output parser - 排产结果快照表_输出
Supports flexible group_by + granularity (week/day/shift) + filters + threshold
Core for Phase3 refined design: query-driven aggregation, not full 20万 rows
"""
import pandas as pd
from datetime import timedelta
from typing import List, Dict

def parse_plan_output(file_path: str):
    df = pd.read_excel(file_path)
    return df

def to_saturday(dt):
    """Convert datetime to Saturday of that week (Sun-Sat week, Sat ending)"""
    if pd.isna(dt):
        return None
    # dt is Timestamp
    dow = dt.weekday()  # Mon=0...Sun=6
    delta = (5 - dow) % 7  # days to Saturday
    return dt + timedelta(days=delta)

def normalize_dates(df):
    df = df.copy()
    df["_DATE_DT"] = pd.to_datetime(df["PLAN_DATE"], errors='coerce')
    df["_DATE"] = df["_DATE_DT"].dt.strftime("%Y-%m-%d")
    df["_WEEK_DT"] = df["_DATE_DT"].apply(lambda x: to_saturday(x) if pd.notna(x) else None)
    df["_WEEK"] = df["_WEEK_DT"].apply(lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) and hasattr(x, 'strftime') else None)
    return df

def apply_filters(df, filters: Dict):
    """Apply filters dict: {LINE_CODE: 'AL6-Frame', WEEK: '2026-07-12', ...}"""
    if not filters:
        return df
    df = df.copy()
    for key, val in filters.items():
        if val is None or val == "":
            continue
        # Normalize key
        key_upper = key.upper()
        if key_upper == "WEEK" or key_upper == "_WEEK":
            if "_WEEK" in df.columns:
                df = df[df["_WEEK"] == val]
        elif key_upper in ["DATE", "PLAN_DATE", "_DATE"]:
            if "_DATE" in df.columns:
                df = df[df["_DATE"] == val]
        elif key_upper == "LINE_CODE" or key_upper == "LINE":
            if "LINE_CODE" in df.columns:
                df = df[df["LINE_CODE"] == val]
        elif key_upper == "SKU":
            if "SKU" in df.columns:
                df = df[df["SKU"] == val]
        elif key_upper == "SHIFT_NAME" or key_upper == "SHIFT":
            if "SHIFT_NAME" in df.columns:
                df = df[df["SHIFT_NAME"] == val]
        elif key_upper == "PLAN_ITEM":
            if "PLAN_ITEM" in df.columns:
                df = df[df["PLAN_ITEM"] == val]
        else:
            # Try direct column match
            if key in df.columns:
                df = df[df[key].astype(str) == str(val)]
    return df

def get_group_keys(group_by: List[str], granularity: str):
    """Build group keys including time dimension based on granularity"""
    # Clean group_by: remove empty, dedup, ensure valid columns
    clean_gb = []
    for g in group_by:
        g = g.strip()
        if g and g not in clean_gb:
            clean_gb.append(g)
    
    # Time columns based on granularity
    if granularity == "week":
        time_cols = ["_WEEK"]
    elif granularity == "day":
        time_cols = ["_DATE"]
    else:  # shift
        # For shift, we want date + shift + plan_item as time dimensions
        time_cols = ["_DATE", "SHIFT_NAME", "PLAN_ITEM"]
        # Avoid duplicate if already in group_by
        time_cols = [c for c in time_cols if c not in clean_gb]

    # Final keys = group_by + time_cols
    final_keys = clean_gb + time_cols
    return final_keys, clean_gb, time_cols

def aggregate_plan_output(df, group_by: List[str], granularity: str, filters: Dict = None):
    """
    Aggregate plan_output data
    Returns aggregated DataFrame with columns: group_by + time + PLAN_VALUE
    """
    df = normalize_dates(df)
    df = apply_filters(df, filters)

    if df.empty:
        return pd.DataFrame()

    group_keys, clean_gb, time_cols = get_group_keys(group_by, granularity)

    # Ensure group keys exist
    valid_keys = [k for k in group_keys if k in df.columns]
    if not valid_keys:
        # Fallback to time only
        valid_keys = time_cols

    agg = df.groupby(valid_keys, as_index=False)["PLAN_VALUE"].sum()
    return agg, valid_keys

def diff_plan_output(df_a, df_b, group_by: List[str], granularity: str = "week", 
                     filters: Dict = None, only_diff: bool = True,
                     threshold_abs: float = 0, threshold_pct: float = 0,
                     sort_by: str = "abs_diff_desc",
                     page: int = 1, page_size: int = 100):
    """
    Main diff for plan_output with grouping
    """
    try:
        # Normalize and filter
        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)

        df_a_filt = apply_filters(df_a_norm, filters)
        df_b_filt = apply_filters(df_b_norm, filters)

        if df_a_filt.empty and df_b_filt.empty:
            return {
                "total_a": 0,
                "total_b": 0,
                "aggregated_a": 0,
                "aggregated_b": 0,
                "records": [],
                "pagination": {"page": 1, "page_size": page_size, "total": 0},
                "group_by": group_by,
                "granularity": granularity
            }

        # Aggregate
        group_keys, clean_gb, time_cols = get_group_keys(group_by, granularity)

        valid_keys_a = [k for k in group_keys if k in df_a_filt.columns]
        valid_keys_b = [k for k in group_keys if k in df_b_filt.columns]
        valid_keys = list(set(valid_keys_a) & set(valid_keys_b))
        if not valid_keys:
            valid_keys = [k for k in group_keys if k in df_a_filt.columns or k in df_b_filt.columns]
            if not valid_keys:
                valid_keys = time_cols

        # Groupby sum
        agg_a = df_a_filt.groupby(valid_keys, as_index=False)["PLAN_VALUE"].sum() if not df_a_filt.empty else pd.DataFrame(columns=valid_keys + ["PLAN_VALUE"])
        agg_b = df_b_filt.groupby(valid_keys, as_index=False)["PLAN_VALUE"].sum() if not df_b_filt.empty else pd.DataFrame(columns=valid_keys + ["PLAN_VALUE"])

        # Merge
        merged = pd.merge(agg_a, agg_b, on=valid_keys, how="outer", suffixes=("_A", "_B"))
        merged["PLAN_VALUE_A"] = merged["PLAN_VALUE_A"].fillna(0)
        merged["PLAN_VALUE_B"] = merged["PLAN_VALUE_B"].fillna(0)
        merged["diff"] = merged["PLAN_VALUE_B"] - merged["PLAN_VALUE_A"]
        merged["diff_pct"] = merged.apply(lambda r: (r["diff"] / r["PLAN_VALUE_A"] * 100) if r["PLAN_VALUE_A"] != 0 else (100 if r["diff"] !=0 else 0), axis=1)
        merged["abs_diff"] = merged["diff"].abs()

        # Filter only_diff
        if only_diff:
            merged = merged[merged["diff"] != 0]

        # Threshold filters
        if threshold_abs > 0:
            merged = merged[merged["abs_diff"] >= threshold_abs]
        if threshold_pct > 0:
            merged = merged[merged["diff_pct"].abs() >= threshold_pct]

        # Sort
        if sort_by == "abs_diff_desc":
            merged = merged.sort_values("abs_diff", ascending=False)
        elif sort_by == "diff_desc":
            merged = merged.sort_values("diff", ascending=False)
        elif sort_by == "diff_asc":
            merged = merged.sort_values("diff", ascending=True)

        total = len(merged)
        # Pagination
        start = (page-1)*page_size
        end = start+page_size
        paged = merged.iloc[start:end] if total >0 else merged

        # Convert to records
        records = paged.to_dict(orient="records")

        # Enrich records with drill info
        enriched = []
        for rec in records:
            # Determine drill-down availability
            # If current granularity is week, can drill to day (need week filter) and to shift
            # If day, can drill to shift
            can_drill_day = granularity == "week"
            can_drill_shift = granularity in ["week", "day"]
            enriched.append({
                **rec,
                "_drill": {
                    "can_drill_day": can_drill_day,
                    "can_drill_shift": can_drill_shift,
                    "next_granularity": "day" if granularity=="week" else "shift" if granularity=="day" else None
                },
                # For frontend breadcrumb building
                "_group_values": {k: rec.get(k) for k in valid_keys}
            })

        return {
            "total_a": len(df_a),
            "total_b": len(df_b),
            "filtered_a": len(df_a_filt),
            "filtered_b": len(df_b_filt),
            "aggregated_a": len(agg_a),
            "aggregated_b": len(agg_b),
            "total_after_filter": total,
            "records": enriched,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "group_by": group_by,
            "granularity": granularity,
            "valid_keys": valid_keys,
            "time_cols": time_cols,
            "filters": filters or {}
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "total_a": len(df_a) if 'df_a' in locals() else 0,
            "total_b": len(df_b) if 'df_b' in locals() else 0,
            "error": str(e),
            "records": [],
            "pagination": {"page": 1, "page_size": page_size, "total": 0}
        }


def get_chart_data_plan_output(df_a, df_b, group_by=None, filters=None, granularity="day", line_code=None, sku=None):
    """
    Get time series for chart
    Filter to specific line/sku if provided, then aggregate by time
    """
    try:
        # Merge filters with line_code/sku
        eff_filters = filters.copy() if filters else {}
        if line_code:
            eff_filters["LINE_CODE"] = line_code
        if sku:
            eff_filters["SKU"] = sku

        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)

        df_a_filt = apply_filters(df_a_norm, eff_filters)
        df_b_filt = apply_filters(df_b_norm, eff_filters)

        # Determine time col
        if granularity == "week":
            time_col = "_WEEK"
            # For chart, we want daily or weekly? Use _WEEK
            df_a_filt = df_a_filt.groupby(time_col, as_index=False)["PLAN_VALUE"].sum() if not df_a_filt.empty else df_a_filt
            df_b_filt = df_b_filt.groupby(time_col, as_index=False)["PLAN_VALUE"].sum() if not df_b_filt.empty else df_b_filt
        elif granularity == "day":
            time_col = "_DATE"
            df_a_filt = df_a_filt.groupby(time_col, as_index=False)["PLAN_VALUE"].sum() if not df_a_filt.empty else df_a_filt
            df_b_filt = df_b_filt.groupby(time_col, as_index=False)["PLAN_VALUE"].sum() if not df_b_filt.empty else df_b_filt
        else:
            time_col = "_DATE"
            # For shift, aggregate by date + shift?
            df_a_filt = df_a_filt.groupby([time_col, "SHIFT_NAME"], as_index=False)["PLAN_VALUE"].sum() if not df_a_filt.empty else df_a_filt
            df_b_filt = df_b_filt.groupby([time_col, "SHIFT_NAME"], as_index=False)["PLAN_VALUE"].sum() if not df_b_filt.empty else df_b_filt
            # For simplicity, chart only date

        # Merge for chart
        if granularity == "shift":
            # For shift, we need to handle date+shift as x label
            # Simplify: just use date aggregation for chart
            time_col = "_DATE"
            df_a_chart = df_a_norm.copy()
            df_b_chart = df_b_norm.copy()
            if eff_filters:
                df_a_chart = apply_filters(df_a_chart, eff_filters)
                df_b_chart = apply_filters(df_b_chart, eff_filters)
            df_a_chart = df_a_chart.groupby(time_col, as_index=False)["PLAN_VALUE"].sum()
            df_b_chart = df_b_chart.groupby(time_col, as_index=False)["PLAN_VALUE"].sum()
        else:
            df_a_chart = df_a_filt
            df_b_chart = df_b_filt

        # Sort by time
        df_a_chart = df_a_chart.sort_values(time_col) if time_col in df_a_chart.columns else df_a_chart
        df_b_chart = df_b_chart.sort_values(time_col) if time_col in df_b_chart.columns else df_b_chart

        merged = pd.merge(df_a_chart, df_b_chart, on=time_col, how="outer", suffixes=("_A", "_B"))
        merged = merged.sort_values(time_col)
        merged = merged.fillna(0)

        dates = merged[time_col].astype(str).tolist()
        vals_a = merged["PLAN_VALUE_A"].tolist() if "PLAN_VALUE_A" in merged.columns else []
        vals_b = merged["PLAN_VALUE_B"].tolist() if "PLAN_VALUE_B" in merged.columns else []

        return {
            "dates": dates,
            "values_a": vals_a,
            "values_b": vals_b,
            "granularity": granularity,
            "filters": eff_filters
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "dates": [], "values_a": [], "values_b": []}
