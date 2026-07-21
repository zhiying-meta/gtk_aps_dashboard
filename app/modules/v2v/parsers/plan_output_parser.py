"""
Plan Output parser - 排产结果快照表_输出
Refactored for SKU level comparison as per user request:
- Fixed SKU level (SKU + Time), not dimension builder
- Default only_diff=True
- Supports granularity: day, week, month/monthly, shift
- Columns: TIME (vertical), SKU (vertical), PREV, LATEST, DIFF, TAG
- Also keeps legacy matrix API for detailed view
Optimized for performance: vectorized date handling, minimal columns, NaT safe.
"""

import pandas as pd
from datetime import timedelta
from typing import List, Dict

def parse_plan_output(file_path: str):
    df = pd.read_excel(file_path)
    return df

def to_saturday_series(series):
    try:
        dow = series.dt.weekday
        delta = (5 - dow) % 7
        return series + pd.to_timedelta(delta, unit='D')
    except:
        return series

def normalize_dates(df):
    if df.empty:
        df["_DATE_DT"] = pd.Series(dtype='datetime64[ns]')
        df["_DATE"] = pd.Series(dtype='object')
        df["_WEEK"] = pd.Series(dtype='object')
        df["_MONTH"] = pd.Series(dtype='object')
        return df
    df = df.copy()
    df["_DATE_DT"] = pd.to_datetime(df["PLAN_DATE"], errors='coerce')
    df = df[~df["_DATE_DT"].isna()]
    if df.empty:
        df["_DATE"] = pd.Series(dtype='object')
        df["_WEEK"] = pd.Series(dtype='object')
        df["_MONTH"] = pd.Series(dtype='object')
        return df
    df["_DATE"] = df["_DATE_DT"].dt.strftime("%Y-%m-%d")
    week_dt = to_saturday_series(df["_DATE_DT"])
    df["_WEEK"] = week_dt.dt.strftime("%Y-%m-%d")
    df["_MONTH"] = df["_DATE_DT"].dt.strftime("%Y-%m")
    return df

def apply_filters(df, filters: Dict):
    if not filters or df.empty:
        return df
    df = df.copy()
    for key, val in filters.items():
        if val is None or val == "" or df.empty:
            continue
        key_upper = key.upper()
        if key_upper in ["WEEK", "_WEEK"]:
            if "_WEEK" in df.columns:
                df = df[df["_WEEK"] == val]
        elif key_upper in ["DATE", "PLAN_DATE", "_DATE"]:
            if "_DATE" in df.columns:
                df = df[df["_DATE"] == val]
        elif key_upper in ["MONTH", "_MONTH"]:
            if "_MONTH" in df.columns:
                df = df[df["_MONTH"] == val]
        elif key_upper in ["LINE_CODE", "LINE"]:
            if "LINE_CODE" in df.columns:
                df = df[df["LINE_CODE"] == val]
        elif key_upper == "SKU":
            if "SKU" in df.columns:
                df = df[df["SKU"] == val]
        elif key_upper == "SHIFT_NAME":
            if "SHIFT_NAME" in df.columns:
                df = df[df["SHIFT_NAME"] == val]
        else:
            if key in df.columns:
                df = df[df[key].astype(str) == str(val)]
    return df

def get_time_col(granularity):
    gran = (granularity or "week").lower()
    if gran in ["monthly", "month"]:
        return "_MONTH"
    elif gran == "week":
        return "_WEEK"
    elif gran == "day":
        return "_DATE"
    elif gran == "shift":
        return "_DATE"
    else:
        return "_WEEK"

def get_group_keys_fixed_sku(granularity):
    """Force SKU level + time"""
    gran = (granularity or "week").lower()
    time_col = get_time_col(gran)
    if gran == "shift":
        return ["SKU", "_DATE", "SHIFT_NAME"], time_col
    else:
        return ["SKU", time_col], time_col

def aggregate_plan_output(df, group_by: List[str], granularity: str, filters: Dict = None):
    """
    Legacy aggregation - kept for compatibility but now optimized
    """
    df = normalize_dates(df)
    df = apply_filters(df, filters)
    if df.empty:
        return pd.DataFrame(), []

    # If group_by is None or empty, use fixed SKU
    if not group_by:
        group_by = ["SKU"]
    # For new logic, force SKU level if group_by contains only SKU or LINE_CODE
    # But keep flexible for legacy calls
    gran = (granularity or "week").lower()
    time_col = get_time_col(gran)

    # Build final keys
    clean_gb = [g for g in group_by if g and g not in [time_col]]
    # Deduplicate
    clean_gb = list(dict.fromkeys(clean_gb))

    if gran == "shift":
        time_cols = ["_DATE", "SHIFT_NAME"]
    else:
        time_cols = [time_col]

    # Ensure time cols not duplicated in clean_gb
    time_cols = [c for c in time_cols if c not in clean_gb]
    final_keys = clean_gb + time_cols
    valid_keys = [k for k in final_keys if k in df.columns]
    if not valid_keys:
        valid_keys = time_cols

    agg = df.groupby(valid_keys, as_index=False)["PLAN_VALUE"].sum()
    return agg, valid_keys

def diff_plan_output(df_a, df_b, group_by: List[str] = None, granularity: str = "week",
                     filters: Dict = None, only_diff: bool = True,
                     threshold_abs: float = 0, threshold_pct: float = 0,
                     sort_by: str = "abs_diff_desc",
                     page: int = 1, page_size: int = 100,
                     cum: bool = False):
    """
    Main diff for plan_output - Fixed SKU level per user request
    - group_by is forced to SKU + time (ignore builder)
    - granularity controls time bucket: day/week/month/shift
    - only_diff default True
    - Returns records with PREV, LATEST, DIFF, TAG etc
    """
    try:
        # For new UI, force SKU level regardless of incoming group_by
        # If incoming group_by is None, use SKU
        # If it contains ITEM_CODE or PN_CODE, map to SKU
        forced_group_by = None
        if group_by:
            # If group_by contains LINE_CODE, we still want SKU level per request, but keep LINE if explicitly requested?
            # Per user: Plan Output also SKU level same as BOH
            # So force SKU
            if any(g.upper() in ["SKU", "PN_CODE", "ITEM_CODE"] for g in group_by):
                forced_group_by = ["SKU"]
            else:
                # If old builder had LINE_CODE, keep SKU as primary
                forced_group_by = ["SKU"]
        else:
            forced_group_by = ["SKU"]

        # Normalize
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
                "group_by": forced_group_by,
                "granularity": granularity
            }

        gran = (granularity or "week").lower()
        time_col = get_time_col(gran)

        if gran == "shift":
            group_keys = ["SKU", "_DATE", "SHIFT_NAME"]
        else:
            group_keys = ["SKU", time_col]

        group_keys = [k for k in group_keys if k in df_a_filt.columns or k in df_b_filt.columns]
        if not group_keys:
            group_keys = ["SKU"]

        # Aggregate sum per group
        agg_a = df_a_filt.groupby(group_keys, as_index=False)["PLAN_VALUE"].sum() if not df_a_filt.empty else pd.DataFrame(columns=group_keys + ["PLAN_VALUE"])
        agg_b = df_b_filt.groupby(group_keys, as_index=False)["PLAN_VALUE"].sum() if not df_b_filt.empty else pd.DataFrame(columns=group_keys + ["PLAN_VALUE"])

        # Cumulative handling - if cum=True, compute cumsum per SKU sorted by time
        if cum:
            # Determine time col for sorting
            time_sort = time_col
            if gran == "shift":
                time_sort = "_DATE"
            # Sort by SKU + time
            for agg_df in [agg_a, agg_b]:
                if not agg_df.empty and time_sort in agg_df.columns:
                    # Need proper time sorting - use string sort for YYYY-MM-DD which works
                    sort_keys = ["SKU", time_sort] if "SKU" in agg_df.columns else [time_sort]
                    sort_keys = [k for k in sort_keys if k in agg_df.columns]
                    if sort_keys:
                        agg_df.sort_values(sort_keys, inplace=True)
                    if "SKU" in agg_df.columns:
                        agg_df["PLAN_VALUE"] = agg_df.groupby("SKU")["PLAN_VALUE"].cumsum()
                    else:
                        agg_df["PLAN_VALUE"] = agg_df["PLAN_VALUE"].cumsum()

        # Merge
        merged = pd.merge(agg_a, agg_b, on=group_keys, how="outer", suffixes=("_A", "_B"))
        merged["PLAN_VALUE_A"] = merged["PLAN_VALUE_A"].fillna(0)
        merged["PLAN_VALUE_B"] = merged["PLAN_VALUE_B"].fillna(0)
        merged["diff"] = merged["PLAN_VALUE_B"] - merged["PLAN_VALUE_A"]
        merged["abs_diff"] = merged["diff"].abs()

        # Tag logic
        set_a = set([tuple(x) for x in agg_a[group_keys].to_numpy()]) if not agg_a.empty else set()
        set_b = set([tuple(x) for x in agg_b[group_keys].to_numpy()]) if not agg_b.empty else set()

        def compute_tag(row):
            key_tuple = tuple(row[k] for k in group_keys)
            in_a = key_tuple in set_a
            in_b = key_tuple in set_b
            if not in_a and in_b:
                return "ADDED"
            elif in_a and not in_b:
                return "DELETED"
            else:
                if row["diff"] == 0:
                    return "UNCHANGED"
                else:
                    return "MODIFY"

        merged["change_tag"] = merged.apply(compute_tag, axis=1)
        merged["change_type"] = merged["change_tag"]

        if only_diff:
            merged = merged[merged["change_tag"] != "UNCHANGED"]

        if threshold_abs > 0:
            merged = merged[merged["abs_diff"] >= threshold_abs]
        if threshold_pct > 0:
            merged["diff_pct"] = merged.apply(lambda r: (r["diff"] / r["PLAN_VALUE_A"] * 100) if r["PLAN_VALUE_A"] != 0 else (100 if r["diff"] !=0 else 0), axis=1)
            merged = merged[merged["diff_pct"].abs() >= threshold_pct]
        else:
            merged["diff_pct"] = merged.apply(lambda r: (r["diff"] / r["PLAN_VALUE_A"] * 100) if r["PLAN_VALUE_A"] != 0 else (100 if r["diff"] !=0 else 0), axis=1)

        # Sort
        if sort_by == "abs_diff_desc":
            merged = merged.sort_values("abs_diff", ascending=False)
        elif sort_by == "diff_desc":
            merged = merged.sort_values("diff", ascending=False)
        elif sort_by == "diff_asc":
            merged = merged.sort_values("diff", ascending=True)

        total = len(merged)
        start = (page-1)*page_size
        end = start+page_size
        paged = merged.iloc[start:end] if total>0 else merged

        # Build records
        enriched = []
        for _, rec in paged.iterrows():
            # Safe conversion
            sku_val = rec.get("SKU") or "Unknown"
            time_val = rec.get(time_col) or rec.get("_DATE") or rec.get("_WEEK") or rec.get("_MONTH") or ""
            enriched.append({
                "SKU": str(sku_val),
                "ITEM_CODE": str(sku_val),
                "TIME": str(time_val),
                "TIME_LABEL": str(time_val),
                "_DATE": str(rec.get("_DATE")) if rec.get("_DATE") else None,
                "_WEEK": str(rec.get("_WEEK")) if rec.get("_WEEK") else None,
                "_MONTH": str(rec.get("_MONTH")) if rec.get("_MONTH") else None,
                time_col: str(time_val),
                "PREV": float(rec.get("PLAN_VALUE_A", 0)),
                "LATEST": float(rec.get("PLAN_VALUE_B", 0)),
                "PREVIOUS": float(rec.get("PLAN_VALUE_A", 0)),
                "LATEST_VALUE": float(rec.get("PLAN_VALUE_B", 0)),
                "PLAN_VALUE_A": float(rec.get("PLAN_VALUE_A", 0)),
                "PLAN_VALUE_B": float(rec.get("PLAN_VALUE_B", 0)),
                "diff": float(rec.get("diff", 0)),
                "DIFF": float(rec.get("diff", 0)),
                "abs_diff": float(rec.get("abs_diff", 0)),
                "diff_pct": float(rec.get("diff_pct", 0)),
                "change_tag": rec.get("change_tag", "MODIFY"),
                "change_type": rec.get("change_tag", "MODIFY"),
                "TAG": rec.get("change_tag", "MODIFY"),
                "_group_values": {k: str(rec.get(k)) for k in group_keys},
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
            "group_by": group_keys,
            "granularity": granularity,
            "valid_keys": group_keys,
            "time_cols": [time_col],
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


def get_breakdown_by_line_shift(df_a, df_b, sku, date, granularity="day"):
    try:
        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)

        df_a_filt = df_a_norm[df_a_norm["SKU"] == sku] if sku else df_a_norm
        df_b_filt = df_b_norm[df_b_norm["SKU"] == sku] if sku else df_b_norm

        if date:
            df_a_filt = df_a_filt[df_a_filt["_DATE"] == date]
            df_b_filt = df_b_filt[df_b_filt["_DATE"] == date]

        if df_a_filt.empty and df_b_filt.empty:
            return {"sku": sku, "date": date, "breakdown": [], "total_a": 0, "total_b": 0}

        group_cols = ["LINE_CODE", "SHIFT_NAME", "PLAN_ITEM"]
        valid_a = [c for c in group_cols if c in df_a_filt.columns]
        valid_b = [c for c in group_cols if c in df_b_filt.columns]
        valid = list(set(valid_a) & set(valid_b))
        if not valid:
            valid = ["LINE_CODE", "SHIFT_NAME"]

        agg_a = df_a_filt.groupby(valid, as_index=False)["PLAN_VALUE"].sum() if not df_a_filt.empty else pd.DataFrame(columns=valid + ["PLAN_VALUE"])
        agg_b = df_b_filt.groupby(valid, as_index=False)["PLAN_VALUE"].sum() if not df_b_filt.empty else pd.DataFrame(columns=valid + ["PLAN_VALUE"])

        merged = pd.merge(agg_a, agg_b, on=valid, how="outer", suffixes=("_A", "_B"))
        merged["PLAN_VALUE_A"] = merged["PLAN_VALUE_A"].fillna(0)
        merged["PLAN_VALUE_B"] = merged["PLAN_VALUE_B"].fillna(0)
        merged["diff"] = merged["PLAN_VALUE_B"] - merged["PLAN_VALUE_A"]
        merged["abs_diff"] = merged["diff"].abs()
        merged = merged.sort_values("abs_diff", ascending=False)

        return {
            "sku": sku,
            "date": date,
            "granularity": granularity,
            "total_a": float(agg_a["PLAN_VALUE"].sum()) if not agg_a.empty else 0,
            "total_b": float(agg_b["PLAN_VALUE"].sum()) if not agg_b.empty else 0,
            "breakdown": merged.to_dict(orient="records"),
            "count": len(merged)
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "sku": sku, "date": date, "breakdown": []}


def get_chart_data_plan_output(df_a, df_b, group_by=None, filters=None, granularity="day", line_code=None, sku=None):
    try:
        eff_filters = filters.copy() if filters else {}
        if line_code:
            eff_filters["LINE_CODE"] = line_code
        if sku:
            eff_filters["SKU"] = sku

        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)

        df_a_filt = apply_filters(df_a_norm, eff_filters)
        df_b_filt = apply_filters(df_b_norm, eff_filters)

        gran = (granularity or "day").lower()
        time_col = get_time_col(gran)

        df_a_filt = df_a_filt.groupby(time_col, as_index=False)["PLAN_VALUE"].sum() if not df_a_filt.empty else df_a_filt
        df_b_filt = df_b_filt.groupby(time_col, as_index=False)["PLAN_VALUE"].sum() if not df_b_filt.empty else df_b_filt

        df_a_filt = df_a_filt.sort_values(time_col) if time_col in df_a_filt.columns else df_a_filt
        df_b_filt = df_b_filt.sort_values(time_col) if time_col in df_b_filt.columns else df_b_filt

        merged = pd.merge(df_a_filt, df_b_filt, on=time_col, how="outer", suffixes=("_A", "_B"))
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


def get_daily_matrix(df_a, df_b, sku_prefix="SK", line_filter=None, shift_filter=None, granularity="day", cum=True, filters=None, exact_sku=None):
    try:
        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)

        df_a_filt = apply_filters(df_a_norm, filters) if filters else df_a_norm
        df_b_filt = apply_filters(df_b_norm, filters) if filters else df_b_norm

        if exact_sku and exact_sku.strip():
            exact = exact_sku.strip()
            df_a_filt = df_a_filt[df_a_filt["SKU"] == exact]
            df_b_filt = df_b_filt[df_b_filt["SKU"] == exact]
        else:
            if sku_prefix and sku_prefix != "ALL":
                prefixes = [p.strip() for p in sku_prefix.split(",") if p.strip()]
                if prefixes:
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

        if line_filter and line_filter != "ALL":
            lines = [l.strip() for l in line_filter.split(",") if l.strip()]
            if lines:
                df_a_filt = df_a_filt[df_a_filt["LINE_CODE"].isin(lines)]
                df_b_filt = df_b_filt[df_b_filt["LINE_CODE"].isin(lines)]

        if shift_filter and shift_filter != "ALL":
            df_a_filt = df_a_filt[df_a_filt["SHIFT_NAME"] == shift_filter]
            df_b_filt = df_b_filt[df_b_filt["SHIFT_NAME"] == shift_filter]

        if df_a_filt.empty and df_b_filt.empty:
            return {"dates": [], "weeks": [], "sku_list": [], "data": {}, "summary": {"total_skus": 0, "total_dates": 0}}

        agg_a_daily = df_a_filt.groupby(["SKU", "_DATE"], as_index=False)["PLAN_VALUE"].sum() if not df_a_filt.empty else pd.DataFrame(columns=["SKU", "_DATE", "PLAN_VALUE"])
        agg_b_daily = df_b_filt.groupby(["SKU", "_DATE"], as_index=False)["PLAN_VALUE"].sum() if not df_b_filt.empty else pd.DataFrame(columns=["SKU", "_DATE", "PLAN_VALUE"])

        all_dates_a = set(agg_a_daily["_DATE"].dropna()) if not agg_a_daily.empty else set()
        all_dates_b = set(agg_b_daily["_DATE"].dropna()) if not agg_b_daily.empty else set()
        all_dates = sorted(list(all_dates_a | all_dates_b))

        all_skus_a = set(agg_a_daily["SKU"].dropna()) if not agg_a_daily.empty else set()
        all_skus_b = set(agg_b_daily["SKU"].dropna()) if not agg_b_daily.empty else set()
        all_skus = sorted(list(all_skus_a | all_skus_b))

        from datetime import datetime, timedelta

        def get_sunday(d_str):
            try:
                dt = datetime.strptime(d_str, "%Y-%m-%d")
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

        weeks_dict = {}
        for d in all_dates:
            sun = get_sunday(d)
            if sun not in weeks_dict:
                weeks_dict[sun] = []
            weeks_dict[sun].append(d)

        weeks = []
        for sun in sorted(weeks_dict.keys()):
            dates_in_week = sorted(weeks_dict[sun])
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
                if wk["dates"]:
                    last_d = wk["dates"][-1]
                    weekly_data[sku][wk_label]["cum_a"] = data[sku].get(last_d, {}).get("cum_a", 0)
                    weekly_data[sku][wk_label]["cum_b"] = data[sku].get(last_d, {}).get("cum_b", 0)
                    weekly_data[sku][wk_label]["cum_diff"] = data[sku].get(last_d, {}).get("cum_diff", 0)

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
