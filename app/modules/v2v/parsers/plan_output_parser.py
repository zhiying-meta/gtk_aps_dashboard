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
    df["_MONTH"] = df["_DATE_DT"].dt.strftime("%Y-%m")
    df["_YEAR_MONTH_DT"] = pd.to_datetime(df["_DATE_DT"].dt.to_period('M').astype(str), errors='coerce')
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
    clean_gb = []
    for g in group_by:
        g = g.strip()
        if g and g not in clean_gb:
            clean_gb.append(g)
    
    if granularity == "week":
        time_cols = ["_WEEK"]
    elif granularity == "day":
        time_cols = ["_DATE"]
    elif granularity == "monthly" or granularity == "month":
        time_cols = ["_MONTH"]
    else:  # shift
        time_cols = ["_DATE", "SHIFT_NAME", "PLAN_ITEM"]
        time_cols = [c for c in time_cols if c not in clean_gb]

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
                     page: int = 1, page_size: int = 100,
                     cum: bool = False):
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

        # Cumulative handling: if cum=True, compute cumsum per clean_gb group sorted by time
        if cum:
            # Determine time col for sorting
            time_col = None
            for tc in ["_DATE", "_WEEK", "_MONTH"]:
                if tc in valid_keys:
                    time_col = tc
                    break
            if time_col and clean_gb:
                # For each version, sort by time and cumsum per clean_gb
                # clean_gb may be empty (overall), then cumsum overall sorted by time
                def cumsum_per_group(df_agg):
                    if df_agg.empty:
                        return df_agg
                    # Sort by time
                    # Need to handle _DATE_DT for proper sorting? Use time_col string sort might work for YYYY-MM-DD
                    # For month, YYYY-MM string sort works
                    # For week, YYYY-MM-DD string sort works
                    # Sort by clean_gb + time_col
                    sort_keys = clean_gb + [time_col]
                    # Ensure clean_gb columns exist
                    sort_keys = [k for k in sort_keys if k in df_agg.columns]
                    if not sort_keys:
                        sort_keys = [time_col] if time_col in df_agg.columns else []
                    if sort_keys:
                        df_agg = df_agg.sort_values(sort_keys)
                    # Group by clean_gb and cumsum
                    if clean_gb:
                        # Only cumsum if clean_gb columns exist
                        valid_gb = [g for g in clean_gb if g in df_agg.columns]
                        if valid_gb:
                            df_agg["PLAN_VALUE"] = df_agg.groupby(valid_gb)["PLAN_VALUE"].cumsum()
                        else:
                            df_agg["PLAN_VALUE"] = df_agg["PLAN_VALUE"].cumsum()
                    else:
                        df_agg["PLAN_VALUE"] = df_agg["PLAN_VALUE"].cumsum()
                    return df_agg
                agg_a = cumsum_per_group(agg_a)
                agg_b = cumsum_per_group(agg_b)
            elif time_col:
                # No group_by, overall cumsum
                agg_a = agg_a.sort_values(time_col) if time_col in agg_a.columns else agg_a
                agg_b = agg_b.sort_values(time_col) if time_col in agg_b.columns else agg_b
                if not agg_a.empty:
                    agg_a["PLAN_VALUE"] = agg_a["PLAN_VALUE"].cumsum()
                if not agg_b.empty:
                    agg_b["PLAN_VALUE"] = agg_b["PLAN_VALUE"].cumsum()

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


def get_daily_matrix(df_a, df_b, sku_prefix="SK", line_filter=None, shift_filter=None, granularity="day", cum=True, filters=None):
    """
    Detailed daily matrix for Plan Output
    - Rows: SKU (filtered by prefix, e.g., SK for FG, GB/LT/FR/RT for intermediate)
    - Columns: Daily dates, grouped by week Sun-Sat, with weekly/monthly aggregation option
    - Values: A, B, Diff, optionally cumulative (cum=True prioritized for V2V)
    - Supports drill-down: line, shift, etc. via filters

    Returns:
    {
        dates: [YYYY-MM-DD],
        weeks: [{week_label, start_date, end_date, dates: [...]}, ...],
        months: [{month_label, dates: [...]}, ...],
        sku_list: [SKU],
        data: {
            SKU: {
                date: {a, b, diff, cum_a, cum_b, cum_diff},
                ...
            }
        },
        summary: ...
    }
    """
    try:
        # Normalize
        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)

        # Apply base filters
        df_a_filt = apply_filters(df_a_norm, filters) if filters else df_a_norm
        df_b_filt = apply_filters(df_b_norm, filters) if filters else df_b_norm

        # Filter by SKU prefix (FG vs intermediate)
        if sku_prefix and sku_prefix != "ALL":
            # sku_prefix can be "SK", "GB", "LT", "FR", "RT" or comma separated
            prefixes = [p.strip() for p in sku_prefix.split(",") if p.strip()]
            if prefixes:
                # Keep rows where SKU starts with any prefix
                def matches_prefix(sku):
                    if pd.isna(sku):
                        return False
                    s = str(sku)
                    for pref in prefixes:
                        if s.startswith(pref+"-") or s.startswith(pref):
                            return True
                    return False
                df_a_filt = df_a_filt[df_a_filt["SKU"].apply(matches_prefix)]
                df_b_filt = df_b_filt[df_b_filt["SKU"].apply(matches_prefix)]

        # Filter by line
        if line_filter and line_filter != "ALL":
            lines = [l.strip() for l in line_filter.split(",") if l.strip()]
            if lines:
                df_a_filt = df_a_filt[df_a_filt["LINE_CODE"].isin(lines)]
                df_b_filt = df_b_filt[df_b_filt["LINE_CODE"].isin(lines)]

        # Filter by shift
        if shift_filter and shift_filter != "ALL":
            df_a_filt = df_a_filt[df_a_filt["SHIFT_NAME"] == shift_filter]
            df_b_filt = df_b_filt[df_b_filt["SHIFT_NAME"] == shift_filter]

        if df_a_filt.empty and df_b_filt.empty:
            return {"dates": [], "weeks": [], "sku_list": [], "data": {}, "summary": {"total_skus": 0, "total_dates": 0}}

        # Determine date range and daily aggregation per SKU
        # Group by SKU + DATE
        agg_a_daily = df_a_filt.groupby(["SKU", "_DATE"], as_index=False)["PLAN_VALUE"].sum() if not df_a_filt.empty else pd.DataFrame(columns=["SKU", "_DATE", "PLAN_VALUE"])
        agg_b_daily = df_b_filt.groupby(["SKU", "_DATE"], as_index=False)["PLAN_VALUE"].sum() if not df_b_filt.empty else pd.DataFrame(columns=["SKU", "_DATE", "PLAN_VALUE"])

        # Get all unique dates sorted
        all_dates_a = set(agg_a_daily["_DATE"].dropna()) if not agg_a_daily.empty else set()
        all_dates_b = set(agg_b_daily["_DATE"].dropna()) if not agg_b_daily.empty else set()
        all_dates = sorted(list(all_dates_a | all_dates_b))

        # Get all unique SKUs
        all_skus_a = set(agg_a_daily["SKU"].dropna()) if not agg_a_daily.empty else set()
        all_skus_b = set(agg_b_daily["SKU"].dropna()) if not agg_b_daily.empty else set()
        all_skus = sorted(list(all_skus_a | all_skus_b))

        # Build week grouping: Sun-Sat
        # For each date, find Sunday of that week
        from datetime import datetime, timedelta
        def get_sunday(d_str):
            try:
                dt = datetime.strptime(d_str, "%Y-%m-%d")
                # weekday Mon=0...Sun=6, Sunday is 6, so days since Sunday = (weekday+1)%7
                days_since_sunday = (dt.weekday() + 1) % 7
                sunday = dt - timedelta(days=days_since_sunday)
                return sunday.strftime("%Y-%m-%d")
            except:
                return None

        def get_month(d_str):
            try:
                dt = datetime.strptime(d_str, "%Y-%m-%d")
                return dt.strftime("%Y-%m")
            except:
                return None

        # Build weeks
        weeks_dict = {}
        for d in all_dates:
            sun = get_sunday(d)
            if sun not in weeks_dict:
                weeks_dict[sun] = []
            weeks_dict[sun].append(d)

        weeks = []
        for sun in sorted(weeks_dict.keys()):
            dates_in_week = sorted(weeks_dict[sun])
            # Saturday is Sunday+6
            try:
                sun_dt = datetime.strptime(sun, "%Y-%m-%d")
                sat_dt = sun_dt + timedelta(days=6)
                weeks.append({
                    "week_start_sunday": sun,
                    "week_end_saturday": sat_dt.strftime("%Y-%m-%d"),
                    "week_label": f"Wk {sun} to {sat_dt.strftime('%Y-%m-%d')}",
                    "dates": dates_in_week
                })
            except:
                weeks.append({
                    "week_start_sunday": sun,
                    "week_end_saturday": "",
                    "week_label": sun,
                    "dates": dates_in_week
                })

        # Build months
        months_dict = {}
        for d in all_dates:
            m = get_month(d)
            if m not in months_dict:
                months_dict[m] = []
            months_dict[m].append(d)

        months = []
        for m in sorted(months_dict.keys()):
            months.append({
                "month": m,
                "month_label": m,
                "dates": sorted(months_dict[m])
            })

        # Build data dict: SKU -> date -> values
        # Create lookup dicts for fast access
        lookup_a = {}
        for _, row in agg_a_daily.iterrows():
            key = (row["SKU"], row["_DATE"])
            lookup_a[key] = row["PLAN_VALUE"]

        lookup_b = {}
        for _, row in agg_b_daily.iterrows():
            key = (row["SKU"], row["_DATE"])
            lookup_b[key] = row["PLAN_VALUE"]

        data = {}
        for sku in all_skus:
            data[sku] = {}
            cum_a = 0
            cum_b = 0
            for d in all_dates:
                a_val = lookup_a.get((sku, d), 0)
                b_val = lookup_b.get((sku, d), 0)
                cum_a += a_val
                cum_b += b_val
                data[sku][d] = {
                    "a": float(a_val),
                    "b": float(b_val),
                    "diff": float(b_val - a_val),
                    "cum_a": float(cum_a),
                    "cum_b": float(cum_b),
                    "cum_diff": float(cum_b - cum_a)
                }

        # For weekly/monthly views, we can aggregate the daily data on the fly in frontend,
        # but also provide pre-aggregated weekly data for convenience
        # Weekly aggregation
        # Group daily data into weekly sums per SKU
        weekly_data = {}
        for sku in all_skus:
            weekly_data[sku] = {}
            for wk in weeks:
                wk_label = wk["week_start_sunday"]
                sum_a = sum(data[sku][d]["a"] for d in wk["dates"] if d in data[sku])
                sum_b = sum(data[sku][d]["b"] for d in wk["dates"] if d in data[sku])
                weekly_data[sku][wk_label] = {
                    "a": sum_a,
                    "b": sum_b,
                    "diff": sum_b - sum_a
                }
                # Cum up to this week: sum of all dates <= week_end
                # For simplicity, cum for weekly is cum up to week_end
                # Find cum at last date of week
                if wk["dates"]:
                    last_d = wk["dates"][-1]
                    weekly_data[sku][wk_label]["cum_a"] = data[sku].get(last_d, {}).get("cum_a", 0)
                    weekly_data[sku][wk_label]["cum_b"] = data[sku].get(last_d, {}).get("cum_b", 0)
                    weekly_data[sku][wk_label]["cum_diff"] = data[sku].get(last_d, {}).get("cum_diff", 0)

        # Monthly aggregation
        monthly_data = {}
        for sku in all_skus:
            monthly_data[sku] = {}
            for mo in months:
                mo_label = mo["month"]
                sum_a = sum(data[sku][d]["a"] for d in mo["dates"] if d in data[sku])
                sum_b = sum(data[sku][d]["b"] for d in mo["dates"] if d in data[sku])
                monthly_data[sku][mo_label] = {
                    "a": sum_a,
                    "b": sum_b,
                    "diff": sum_b - sum_a
                }
                if mo["dates"]:
                    last_d = mo["dates"][-1]
                    monthly_data[sku][mo_label]["cum_a"] = data[sku].get(last_d, {}).get("cum_a", 0)
                    monthly_data[sku][mo_label]["cum_b"] = data[sku].get(last_d, {}).get("cum_b", 0)
                    monthly_data[sku][mo_label]["cum_diff"] = data[sku].get(last_d, {}).get("cum_diff", 0)

        return {
            "dates": all_dates,
            "weeks": weeks,
            "months": months,
            "sku_list": all_skus,
            "data": data,
            "weekly_data": weekly_data,
            "monthly_data": monthly_data,
            "summary": {
                "total_skus": len(all_skus),
                "total_dates": len(all_dates),
                "total_weeks": len(weeks),
                "total_months": len(months),
                "date_range": f"{all_dates[0]} to {all_dates[-1]}" if all_dates else "",
                "sku_prefix": sku_prefix,
                "line_filter": line_filter,
                "cum_default": True
            },
            "filters": {
                "sku_prefix": sku_prefix,
                "line_filter": line_filter,
                "shift_filter": shift_filter
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "dates": [], "sku_list": [], "data": {}}
