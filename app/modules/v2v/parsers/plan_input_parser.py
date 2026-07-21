"""
Plan Input parser - Virtual aggregated input view
Similar to Plan Output but for input side: FCST demand + Supply availability
For detailed view: FG SKU daily table, weekly/monthly, cum
"""
import pandas as pd
from datetime import timedelta

def to_saturday(dt):
    if pd.isna(dt):
        return None
    dow = dt.weekday()
    delta = (5 - dow) % 7
    return dt + timedelta(days=delta)

def normalize_fcst_detail(detail_df, main_df):
    """JOIN detail+main to get PN_CODE and build daily/weekly/monthly aggregation base"""
    try:
        detail_df = detail_df.copy()
        main_df = main_df.copy()
        main_df["ID_STR"] = main_df["ID"].astype(str)
        detail_df["MAIN_ID_STR"] = detail_df["MAIN_ID"].astype(str)
        merged = pd.merge(detail_df, main_df[["ID_STR", "PN_CODE"]], left_on="MAIN_ID_STR", right_on="ID_STR", how="left")
        # Convert ACTUALFIRSTDAYOFWEEK to datetime (Saturday)
        merged["_WEEK_DT"] = pd.to_datetime(merged["ACTUALFIRSTDAYOFWEEK"], errors='coerce')
        merged["_WEEK"] = merged["_WEEK_DT"].dt.strftime("%Y-%m-%d")
        merged["_DATE_DT"] = merged["_WEEK_DT"]  # For FCST, week date is the Saturday
        merged["_DATE"] = merged["_WEEK"]
        return merged
    except Exception as e:
        print(f"FCST normalize error: {e}")
        return pd.DataFrame()

def parse_plan_input(fcst_main_path, fcst_detail_path, supply_path=None):
    # For direct file parsing, not used in diff (we use dataframes)
    pass

def diff_plan_input(fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b, supply_a=None, supply_b=None, group_by=None, granularity="week", filters=None, only_diff=True, threshold_abs=0):
    """
    Diff for Plan Input virtual table
    Currently focuses on FCST demand aggregated, similar to Plan Output
    group_by: e.g., ["PN_CODE"] or ["SKU"] - we use PN_CODE for FCST
    granularity: week/day/monthly
    """
    try:
        # Build base
        merged_a = normalize_fcst_detail(fcst_detail_a, fcst_main_a)
        merged_b = normalize_fcst_detail(fcst_detail_b, fcst_main_b)

        if merged_a.empty and merged_b.empty:
            return {"total_a": 0, "total_b": 0, "records": [], "pagination": {"total": 0}}

        # Apply filters
        def apply_filters(df, filters):
            if not filters:
                return df
            for k,v in filters.items():
                if v is None or v == "":
                    continue
                if k.upper() in ["PN_CODE", "SKU", "ITEM_CODE"] and "PN_CODE" in df.columns:
                    df = df[df["PN_CODE"] == v]
                if k.upper() in ["WEEK", "_WEEK"] and "_WEEK" in df.columns:
                    df = df[df["_WEEK"] == v]
            return df

        merged_a = apply_filters(merged_a, filters)
        merged_b = apply_filters(merged_b, filters)

        # Determine grouping
        if not group_by:
            group_by = ["PN_CODE"]

        # Map SKU to PN_CODE for consistency
        group_by_mapped = []
        for g in group_by:
            if g.upper() in ["SKU", "ITEM_CODE", "PN_CODE"]:
                group_by_mapped.append("PN_CODE")
            else:
                group_by_mapped.append(g)
        group_by_mapped = list(dict.fromkeys(group_by_mapped))  # dedup

        # Time col based on granularity
        if granularity == "week":
            time_col = "_WEEK"
        elif granularity == "monthly":
            # Monthly: YYYY-MM
            merged_a["_MONTH"] = pd.to_datetime(merged_a["_WEEK"]).dt.strftime("%Y-%m")
            merged_b["_MONTH"] = pd.to_datetime(merged_b["_WEEK"]).dt.strftime("%Y-%m")
            time_col = "_MONTH"
        else:  # day
            time_col = "_DATE"

        # For FCST, granularity day is same as week (since FCST is weekly), but we keep
        valid_keys = [k for k in group_by_mapped if k in merged_a.columns] + [time_col]
        valid_keys = list(dict.fromkeys(valid_keys))

        # Aggregate sum ACTUALWEEKVALUE
        agg_a = merged_a.groupby(valid_keys, as_index=False)["ACTUALWEEKVALUE"].sum() if not merged_a.empty else pd.DataFrame(columns=valid_keys + ["ACTUALWEEKVALUE"])
        agg_b = merged_b.groupby(valid_keys, as_index=False)["ACTUALWEEKVALUE"].sum() if not merged_b.empty else pd.DataFrame(columns=valid_keys + ["ACTUALWEEKVALUE"])

        # Merge
        merged = pd.merge(agg_a, agg_b, on=valid_keys, how="outer", suffixes=("_A", "_B"))
        merged["ACTUALWEEKVALUE_A"] = merged["ACTUALWEEKVALUE_A"].fillna(0)
        merged["ACTUALWEEKVALUE_B"] = merged["ACTUALWEEKVALUE_B"].fillna(0)
        merged["diff"] = merged["ACTUALWEEKVALUE_B"] - merged["ACTUALWEEKVALUE_A"]
        merged["abs_diff"] = merged["diff"].abs()

        if only_diff:
            merged = merged[merged["diff"] != 0]
        if threshold_abs > 0:
            merged = merged[merged["abs_diff"] >= threshold_abs]

        # Sort by abs_diff
        merged = merged.sort_values("abs_diff", ascending=False)

        total = len(merged)
        records = merged.to_dict(orient="records")
        # Enrich with drill info
        enriched = []
        for rec in records:
            enriched.append({
                **rec,
                "_group_values": {k: rec.get(k) for k in valid_keys},
                "_drill": {"can_drill_day": granularity=="week", "can_drill_shift": False, "next_granularity": "day" if granularity=="week" else None}
            })

        return {
            "total_a": len(merged_a),
            "total_b": len(merged_b),
            "aggregated_a": len(agg_a),
            "aggregated_b": len(agg_b),
            "total_after_filter": total,
            "records": enriched[:1000],  # limit to 1000 for display
            "pagination": {"page": 1, "page_size": 100, "total": total},
            "group_by": group_by,
            "granularity": granularity,
            "valid_keys": valid_keys,
            "filters": filters or {}
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"total_a": 0, "total_b": 0, "error": str(e), "records": [], "pagination": {"total": 0}}


def get_chart_data_plan_input(fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b, pn_code=None, granularity="week"):
    """Chart data for Plan Input: FCST demand over time"""
    try:
        merged_a = normalize_fcst_detail(fcst_detail_a, fcst_main_a)
        merged_b = normalize_fcst_detail(fcst_detail_b, fcst_main_b)

        if pn_code:
            merged_a = merged_a[merged_a["PN_CODE"] == pn_code]
            merged_b = merged_b[merged_b["PN_CODE"] == pn_code]

        if granularity == "monthly":
            merged_a["_MONTH"] = pd.to_datetime(merged_a["_WEEK"]).dt.strftime("%Y-%m")
            merged_b["_MONTH"] = pd.to_datetime(merged_b["_WEEK"]).dt.strftime("%Y-%m")
            time_col = "_MONTH"
        else:
            time_col = "_WEEK"

        agg_a = merged_a.groupby(time_col, as_index=False)["ACTUALWEEKVALUE"].sum().sort_values(time_col) if not merged_a.empty else pd.DataFrame()
        agg_b = merged_b.groupby(time_col, as_index=False)["ACTUALWEEKVALUE"].sum().sort_values(time_col) if not merged_b.empty else pd.DataFrame()

        # Merge for chart
        if not agg_a.empty or not agg_b.empty:
            merged = pd.merge(agg_a, agg_b, on=time_col, how="outer", suffixes=("_A", "_B")).sort_values(time_col)
            merged = merged.fillna(0)
            dates = merged[time_col].astype(str).tolist()
            vals_a = merged["ACTUALWEEKVALUE_A"].tolist() if "ACTUALWEEKVALUE_A" in merged.columns else []
            vals_b = merged["ACTUALWEEKVALUE_B"].tolist() if "ACTUALWEEKVALUE_B" in merged.columns else []
        else:
            dates = []
            vals_a = []
            vals_b = []

        return {"dates": dates, "values_a": vals_a, "values_b": vals_b, "granularity": granularity, "pn_code": pn_code}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "dates": [], "values_a": [], "values_b": []}
