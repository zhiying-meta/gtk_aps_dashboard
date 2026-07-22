"""
Plan Input parser - Virtual aggregated input view
Refactored for SKU level comparison:
- Fixed PN_CODE (SKU) + Time level
- Supports granularity: day, week, month/monthly
- For FCST weekly data, monthly = sum of weeks in month, daily = weekly value (since FCST is weekly)
- Columns: SKU, TIME, PREV, LATEST, DIFF, TAG
- Default only_diff=True
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
    """JOIN detail+main to get PN_CODE and build time buckets"""
    try:
        if detail_df.empty or main_df.empty:
            return pd.DataFrame()
        detail_df = detail_df.copy()
        main_df = main_df.copy()
        # Ensure ID columns are string for merge
        main_df["ID_STR"] = main_df["ID"].astype(str)
        detail_df["MAIN_ID_STR"] = detail_df["MAIN_ID"].astype(str)
        merged = pd.merge(detail_df, main_df[["ID_STR", "PN_CODE"]], left_on="MAIN_ID_STR", right_on="ID_STR", how="left")
        # Convert ACTUALFIRSTDAYOFWEEK to datetime
        merged["_WEEK_DT"] = pd.to_datetime(merged["ACTUALFIRSTDAYOFWEEK"], errors='coerce')
        merged = merged[~merged["_WEEK_DT"].isna()]
        if merged.empty:
            return merged
        merged["_WEEK"] = merged["_WEEK_DT"].dt.strftime("%Y-%m-%d")
        merged["_DATE"] = merged["_WEEK"]  # For FCST, date is week date
        merged["_MONTH"] = merged["_WEEK_DT"].dt.strftime("%Y-%m")
        merged["_DATE_DT"] = merged["_WEEK_DT"]
        return merged
    except Exception as e:
        print(f"FCST normalize error: {e}")
        return pd.DataFrame()

def parse_plan_input(fcst_main_path, fcst_detail_path, supply_path=None):
    pass

def get_time_col(gran):
    gran = (gran or "week").lower()
    if gran in ["monthly", "month"]:
        return "_MONTH"
    elif gran == "week":
        return "_WEEK"
    elif gran == "day":
        return "_DATE"
    else:
        return "_WEEK"

def diff_plan_input(fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b, supply_a=None, supply_b=None, group_by=None, granularity="week", filters=None, only_diff=True, threshold_abs=0):
    """
    Fixed SKU level diff for Plan Input
    - group_by ignored, forced to PN_CODE + time
    - granularity: week, month, day (all map to appropriate time bucket)
    """
    try:
        merged_a = normalize_fcst_detail(fcst_detail_a, fcst_main_a)
        merged_b = normalize_fcst_detail(fcst_detail_b, fcst_main_b)

        if merged_a.empty and merged_b.empty:
            return {"total_a": 0, "total_b": 0, "records": [], "pagination": {"page": 1, "page_size": 100, "total": 0}}

        # Apply filters
        def apply_filters(df, filters):
            if not filters or df.empty:
                return df
            for k, v in filters.items():
                if v is None or v == "" or df.empty:
                    continue
                kup = k.upper()
                if kup in ["PN_CODE", "SKU", "ITEM_CODE"] and "PN_CODE" in df.columns:
                    df = df[df["PN_CODE"] == v]
                if kup in ["WEEK", "_WEEK"] and "_WEEK" in df.columns:
                    df = df[df["_WEEK"] == v]
                if kup in ["MONTH", "_MONTH"] and "_MONTH" in df.columns:
                    df = df[df["_MONTH"] == v]
            return df

        merged_a = apply_filters(merged_a, filters)
        merged_b = apply_filters(merged_b, filters)

        gran = (granularity or "week").lower()
        time_col = get_time_col(gran)

        # Fixed keys: PN_CODE + time_col
        valid_keys = ["PN_CODE", time_col]
        valid_keys = [k for k in valid_keys if k in merged_a.columns or k in merged_b.columns]
        if not valid_keys:
            valid_keys = ["PN_CODE"]

        # Aggregate sum ACTUALWEEKVALUE per PN_CODE + time
        agg_a = merged_a.groupby(valid_keys, as_index=False)["ACTUALWEEKVALUE"].sum() if not merged_a.empty else pd.DataFrame(columns=valid_keys + ["ACTUALWEEKVALUE"])
        agg_b = merged_b.groupby(valid_keys, as_index=False)["ACTUALWEEKVALUE"].sum() if not merged_b.empty else pd.DataFrame(columns=valid_keys + ["ACTUALWEEKVALUE"])

        # Merge
        merged = pd.merge(agg_a, agg_b, on=valid_keys, how="outer", suffixes=("_A", "_B"))
        merged["ACTUALWEEKVALUE_A"] = merged["ACTUALWEEKVALUE_A"].fillna(0)
        merged["ACTUALWEEKVALUE_B"] = merged["ACTUALWEEKVALUE_B"].fillna(0)
        merged["diff"] = merged["ACTUALWEEKVALUE_B"] - merged["ACTUALWEEKVALUE_A"]
        merged["abs_diff"] = merged["diff"].abs()
        # Diff% - for Plan Input, percentage vs Previous
        merged["diff_pct"] = merged.apply(lambda r: (r["diff"] / r["ACTUALWEEKVALUE_A"] * 100) if r["ACTUALWEEKVALUE_A"] != 0 else (100 if r["diff"] !=0 else 0), axis=1)

        # Tag logic
        set_a = set([tuple(x) for x in agg_a[valid_keys].to_numpy()]) if not agg_a.empty else set()
        set_b = set([tuple(x) for x in agg_b[valid_keys].to_numpy()]) if not agg_b.empty else set()

        def compute_tag(row):
            key_tuple = tuple(row[k] for k in valid_keys)
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

        merged = merged.sort_values("abs_diff", ascending=False)

        total = len(merged)
        # For simplicity return first 1000, pagination handled in diff_engine but we provide full here
        records = []
        for _, row in merged.head(1000).iterrows():
            pn = row.get("PN_CODE") or "Unknown"
            time_val = row.get(time_col) or ""
            records.append({
                "PN_CODE": str(pn),
                "SKU": str(pn),
                "ITEM_CODE": str(pn),
                "TIME": str(time_val),
                "TIME_LABEL": str(time_val),
                time_col: str(time_val),
                "_WEEK": str(row.get("_WEEK")) if row.get("_WEEK") else None,
                "_MONTH": str(row.get("_MONTH")) if row.get("_MONTH") else None,
                "_DATE": str(row.get("_DATE")) if row.get("_DATE") else None,
                "PREV": float(row.get("ACTUALWEEKVALUE_A", 0)),
                "LATEST": float(row.get("ACTUALWEEKVALUE_B", 0)),
                "PREVIOUS": float(row.get("ACTUALWEEKVALUE_A", 0)),
                "LATEST_VALUE": float(row.get("ACTUALWEEKVALUE_B", 0)),
                "ACTUALWEEKVALUE_A": float(row.get("ACTUALWEEKVALUE_A", 0)),
                "ACTUALWEEKVALUE_B": float(row.get("ACTUALWEEKVALUE_B", 0)),
                "diff": float(row.get("diff", 0)),
                "DIFF": float(row.get("diff", 0)),
                "abs_diff": float(row.get("abs_diff", 0)),
                "diff_pct": float(row.get("diff_pct", 0)),
                "change_tag": row.get("change_tag", "MODIFY"),
                "change_type": row.get("change_tag", "MODIFY"),
                "TAG": row.get("change_tag", "MODIFY"),
                "_group_values": {k: str(row.get(k)) for k in valid_keys},
            })

        return {
            "total_a": len(merged_a),
            "total_b": len(merged_b),
            "aggregated_a": len(agg_a),
            "aggregated_b": len(agg_b),
            "total_after_filter": total,
            "records": records,
            "pagination": {"page": 1, "page_size": 100, "total": total},
            "group_by": valid_keys,
            "granularity": granularity,
            "valid_keys": valid_keys,
            "filters": filters or {}
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"total_a": 0, "total_b": 0, "error": str(e), "records": [], "pagination": {"page": 1, "page_size": 100, "total": 0}}


def get_chart_data_plan_input(fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b, pn_code=None, granularity="week"):
    try:
        merged_a = normalize_fcst_detail(fcst_detail_a, fcst_main_a)
        merged_b = normalize_fcst_detail(fcst_detail_b, fcst_main_b)

        if pn_code:
            merged_a = merged_a[merged_a["PN_CODE"] == pn_code]
            merged_b = merged_b[merged_b["PN_CODE"] == pn_code]

        time_col = get_time_col(granularity)

        agg_a = merged_a.groupby(time_col, as_index=False)["ACTUALWEEKVALUE"].sum().sort_values(time_col) if not merged_a.empty else pd.DataFrame()
        agg_b = merged_b.groupby(time_col, as_index=False)["ACTUALWEEKVALUE"].sum().sort_values(time_col) if not merged_b.empty else pd.DataFrame()

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


def normalize_fcst_for_matrix(detail_df, main_df):
    """For matrix, normalize FCST detail+main to have _DATE_DT, _WEEK, _MONTH, PN_CODE"""
    try:
        if detail_df.empty or main_df.empty:
            return pd.DataFrame()
        detail_df = detail_df.copy()
        main_df = main_df.copy()
        main_df["ID_STR"] = main_df["ID"].astype(str)
        detail_df["MAIN_ID_STR"] = detail_df["MAIN_ID"].astype(str)
        merged = pd.merge(detail_df, main_df[["ID_STR", "PN_CODE"]], left_on="MAIN_ID_STR", right_on="ID_STR", how="left")
        merged["_WEEK_DT"] = pd.to_datetime(merged["ACTUALFIRSTDAYOFWEEK"], errors='coerce')
        merged = merged[~merged["_WEEK_DT"].isna()]
        if merged.empty:
            return merged
        merged["_DATE_DT"] = merged["_WEEK_DT"]
        merged["_WEEK"] = merged["_WEEK_DT"].dt.strftime("%Y-%m-%d")
        merged["_DATE"] = merged["_WEEK"]
        merged["_MONTH"] = merged["_WEEK_DT"].dt.strftime("%Y-%m")
        return merged
    except Exception as e:
        print(f"FCST matrix normalize error: {e}")
        return pd.DataFrame()


def get_plan_input_horizontal_matrix(fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b, granularity="week", sku_category="ALL", only_diff=True, change_type="ALL"):
    """
    Horizontal matrix for Plan Input (FCST) - NEW LOGIC per user request 2026-07-22:
    - day/week: for FCST weekly data, day is same as week but we show detailed numbers for day granularity
    - week/month: yellow-only indicator: any change inside bucket -> yellow, no numbers
    """
    try:
        from .matrix_helpers import apply_sku_filter_df, generate_time_buckets
        import pandas as pd
        from datetime import timedelta

        df_a_norm = normalize_fcst_for_matrix(fcst_detail_a, fcst_main_a)
        df_b_norm = normalize_fcst_for_matrix(fcst_detail_b, fcst_main_b)

        df_a_filt = apply_sku_filter_df(df_a_norm, "PN_CODE", sku_category)
        df_b_filt = apply_sku_filter_df(df_b_norm, "PN_CODE", sku_category)

        if df_a_filt.empty and df_b_filt.empty:
            return {"time_buckets": [], "sku_list": [], "matrix": {}, "summary": {"total_skus":0, "total_times":0}}

        gran = (granularity or "week").lower()

        def agg_sum(df, keys):
            if df.empty:
                return pd.DataFrame(columns=keys + ["ACTUALWEEKVALUE"])
            try:
                return df.groupby(keys, as_index=False)["ACTUALWEEKVALUE"].sum()
            except:
                return pd.DataFrame(columns=keys + ["ACTUALWEEKVALUE"])

        # For day granularity we still show detailed numbers (weekly values but per week bucket)
        # For week/month we switch to yellow-only
        if gran == "day":
            # Detailed numbers per week (since FCST is weekly)
            time_col = "_WEEK"
            try:
                uniq_weeks_a = df_a_filt["_WEEK"].dropna().unique().tolist() if "_WEEK" in df_a_filt.columns else []
                uniq_weeks_b = df_b_filt["_WEEK"].dropna().unique().tolist() if "_WEEK" in df_b_filt.columns else []
                time_buckets = sorted(list(set(uniq_weeks_a + uniq_weeks_b)))
            except:
                time_buckets = generate_time_buckets(df_a_filt, df_b_filt, "week")
            if not time_buckets:
                return {"time_buckets": [], "sku_list": [], "matrix": {}, "summary": {"total_skus":0, "total_times":0}}
            group_keys = ["PN_CODE", time_col]
            agg_a = agg_sum(df_a_filt, group_keys)
            agg_b = agg_sum(df_b_filt, group_keys)
            def get_label(r):
                return r.get(time_col)
            lookup_a={}
            lookup_b={}
            if not agg_a.empty:
                for _, r in agg_a.iterrows():
                    sku=r.get("PN_CODE")
                    t=get_label(r)
                    if sku and t:
                        lookup_a[(sku,t)]=float(r.get("ACTUALWEEKVALUE",0))
            if not agg_b.empty:
                for _, r in agg_b.iterrows():
                    sku=r.get("PN_CODE")
                    t=get_label(r)
                    if sku and t:
                        lookup_b[(sku,t)]=float(r.get("ACTUALWEEKVALUE",0))
            all_skus=sorted(list(set(agg_a["PN_CODE"].dropna()) | set(agg_b["PN_CODE"].dropna()) if not agg_a.empty or not agg_b.empty else []))
            bucket_labels=time_buckets
            def matches_ct(tag,fct):
                if not fct or fct.upper()=="ALL":
                    return True
                return tag.upper()==fct.upper()
            matrix={}
            for sku in all_skus:
                matrix[sku]={}
                has_match=False
                for tb in bucket_labels:
                    prev=lookup_a.get((sku,tb),None)
                    latest=lookup_b.get((sku,tb),None)
                    if prev is None and latest is None:
                        matrix[sku][tb]=None
                    else:
                        p_val=prev if prev is not None else 0
                        l_val=latest if latest is not None else 0
                        diff=l_val-p_val
                        if prev is None and latest is not None:
                            tag="ADDED"
                        elif prev is not None and latest is None:
                            tag="DELETED"
                        else:
                            tag="MODIFY" if diff!=0 else "UNCHANGED"
                        if not matches_ct(tag, change_type):
                            matrix[sku][tb]=None
                            continue
                        if tag=="UNCHANGED" and only_diff:
                            matrix[sku][tb]=None
                            continue
                        if diff!=0 or tag in ["ADDED","DELETED"]:
                            has_match=True
                        matrix[sku][tb]={"prev":p_val,"latest":l_val,"diff":diff,"tag":tag,"prev_raw":prev,"latest_raw":latest}
                if only_diff and not has_match:
                    if not any(v is not None for v in matrix[sku].values()):
                        if sku in matrix:
                            del matrix[sku]
            final_skus=sorted(list(matrix.keys()))
            return {
                "time_buckets": time_buckets,
                "bucket_labels": bucket_labels,
                "sku_list": final_skus,
                "matrix": matrix,
                "granularity": gran,
                "sku_category": sku_category,
                "display_mode": "detailed",
                "summary": {
                    "total_skus": len(final_skus),
                    "total_times": len(bucket_labels),
                    "total_original_skus": len(all_skus),
                    "time_range": f"{bucket_labels[0]} to {bucket_labels[-1]}" if bucket_labels else ""
                }
            }

        # For week and month: yellow-only logic
        # First compute weekly diff
        weekly_col = "_WEEK"
        # For FCST, use unique _WEEK values as buckets (not Saturdays) to avoid mismatch
        try:
            uniq_weeks_a = df_a_filt["_WEEK"].dropna().unique().tolist() if "_WEEK" in df_a_filt.columns else []
            uniq_weeks_b = df_b_filt["_WEEK"].dropna().unique().tolist() if "_WEEK" in df_b_filt.columns else []
            weekly_buckets = sorted(list(set(uniq_weeks_a + uniq_weeks_b)))
        except:
            weekly_buckets = generate_time_buckets(df_a_filt, df_b_filt, "week")
        group_keys_weekly = ["PN_CODE", weekly_col]
        agg_a_weekly = agg_sum(df_a_filt, group_keys_weekly)
        agg_b_weekly = agg_sum(df_b_filt, group_keys_weekly)
        lookup_a_weekly={}
        lookup_b_weekly={}
        if not agg_a_weekly.empty:
            for _, r in agg_a_weekly.iterrows():
                sku=r.get("PN_CODE")
                t=r.get(weekly_col)
                if sku and t:
                    lookup_a_weekly[(sku,t)]=float(r.get("ACTUALWEEKVALUE",0))
        if not agg_b_weekly.empty:
            for _, r in agg_b_weekly.iterrows():
                sku=r.get("PN_CODE")
                t=r.get(weekly_col)
                if sku and t:
                    lookup_b_weekly[(sku,t)]=float(r.get("ACTUALWEEKVALUE",0))
        skus_a = set(agg_a_weekly["PN_CODE"].dropna()) if not agg_a_weekly.empty and "PN_CODE" in agg_a_weekly.columns else set()
        skus_b = set(agg_b_weekly["PN_CODE"].dropna()) if not agg_b_weekly.empty and "PN_CODE" in agg_b_weekly.columns else set()
        all_skus = sorted(list(skus_a | skus_b))

        # Build weekly has_change set per SKU
        weekly_has_change={}
        for sku in all_skus:
            weekly_has_change[sku]=set()
            for wb in weekly_buckets:
                prev=lookup_a_weekly.get((sku,wb),None)
                latest=lookup_b_weekly.get((sku,wb),None)
                if prev is None and latest is None:
                    continue
                p_val=prev if prev is not None else 0
                l_val=latest if latest is not None else 0
                diff=l_val-p_val
                if prev is None and latest is not None:
                    tag="ADDED"
                elif prev is not None and latest is None:
                    tag="DELETED"
                else:
                    tag="MODIFY" if diff!=0 else "UNCHANGED"
                if tag!="UNCHANGED":
                    weekly_has_change[sku].add(wb)

        if gran in ["month","monthly"]:
            # Monthly buckets from unique _MONTH
            try:
                uniq_months_a = df_a_filt["_MONTH"].dropna().unique().tolist() if "_MONTH" in df_a_filt.columns else []
                uniq_months_b = df_b_filt["_MONTH"].dropna().unique().tolist() if "_MONTH" in df_b_filt.columns else []
                monthly_buckets = sorted(list(set(uniq_months_a + uniq_months_b)))
            except:
                monthly_buckets = generate_time_buckets(df_a_filt, df_b_filt, "month")
            def week_to_month(week_str):
                try:
                    return week_str[:7]
                except:
                    return None
            # Map week -> month
            matrix={}
            for sku in all_skus:
                changed_weeks = weekly_has_change.get(sku,set())
                if not changed_weeks and only_diff:
                    continue
                matrix[sku]={}
                has_any=False
                for mb in monthly_buckets:
                    # Any week in this month that has change?
                    changed_in_month=[w for w in changed_weeks if week_to_month(w)==mb]
                    if changed_in_month:
                        has_any=True
                        matrix[sku][mb]={
                            "has_change": True,
                            "tag": "HAS_CHANGE",
                            "changed_weeks": sorted(changed_in_month),
                            "changed_count": len(changed_in_month),
                            "display_mode": "has_change"
                        }
                    else:
                        matrix[sku][mb]=None
                if only_diff and not has_any:
                    if sku in matrix:
                        del matrix[sku]
            final_skus=sorted(list(matrix.keys()))
            return {
                "time_buckets": monthly_buckets,
                "bucket_labels": monthly_buckets,
                "sku_list": final_skus,
                "matrix": matrix,
                "granularity": gran,
                "sku_category": sku_category,
                "display_mode": "has_change",
                "summary": {
                    "total_skus": len(final_skus),
                    "total_times": len(monthly_buckets),
                    "total_original_skus": len(all_skus),
                    "time_range": f"{monthly_buckets[0]} to {monthly_buckets[-1]}" if monthly_buckets else "",
                    "note": "Monthly yellow-only: any weekly change inside month -> yellow"
                }
            }
        else:  # week granularity -> yellow indicator per week
            matrix={}
            for sku in all_skus:
                changed_weeks = weekly_has_change.get(sku,set())
                if not changed_weeks and only_diff:
                    continue
                matrix[sku]={}
                has_any=False
                for wb in weekly_buckets:
                    if wb in changed_weeks:
                        has_any=True
                        matrix[sku][wb]={
                            "has_change": True,
                            "tag": "HAS_CHANGE",
                            "changed_weeks": [wb],
                            "changed_count": 1,
                            "display_mode": "has_change"
                        }
                    else:
                        matrix[sku][wb]=None
                if only_diff and not has_any:
                    del matrix[sku]
            final_skus=sorted(list(matrix.keys()))
            return {
                "time_buckets": weekly_buckets,
                "bucket_labels": weekly_buckets,
                "sku_list": final_skus,
                "matrix": matrix,
                "granularity": gran,
                "sku_category": sku_category,
                "display_mode": "has_change",
                "summary": {
                    "total_skus": len(final_skus),
                    "total_times": len(weekly_buckets),
                    "total_original_skus": len(all_skus),
                    "time_range": f"{weekly_buckets[0]} to {weekly_buckets[-1]}" if weekly_buckets else "",
                    "note": "Weekly yellow-only: any change in that week -> yellow"
                }
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "time_buckets": [], "sku_list": [], "matrix": {}}

