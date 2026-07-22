"""
BOH (Balance) parser - Optimized with vectorized merge
"""
import pandas as pd
from datetime import timedelta

def parse_balance(file_path: str):
    df = pd.read_excel(file_path)
    return df

def to_saturday_dt(series):
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
        df["_SHIFT_ORDER"] = pd.Series(dtype='int')
        return df
    df = df.copy()
    df["_DATE_DT"] = pd.to_datetime(df["PLAN_DATE"], errors='coerce')
    df = df[~df["_DATE_DT"].isna()]
    if df.empty:
        df["_DATE"] = pd.Series(dtype='object')
        df["_WEEK"] = pd.Series(dtype='object')
        df["_MONTH"] = pd.Series(dtype='object')
        df["_SHIFT_ORDER"] = pd.Series(dtype='int')
        return df
    df["_DATE"] = df["_DATE_DT"].dt.strftime("%Y-%m-%d")
    week_dt = to_saturday_dt(df["_DATE_DT"])
    df["_WEEK"] = week_dt.dt.strftime("%Y-%m-%d")
    df["_MONTH"] = df["_DATE_DT"].dt.strftime("%Y-%m")
    if "SHIFT_CODE" in df.columns:
        df["_SHIFT_ORDER"] = pd.to_numeric(df["SHIFT_CODE"], errors='coerce').fillna(1)
    else:
        mapping = {"白班": 1, "夜班": 2}
        if "SHIFT_NAME" in df.columns:
            df["_SHIFT_ORDER"] = df["SHIFT_NAME"].map(mapping).fillna(1)
        else:
            df["_SHIFT_ORDER"] = 1
    if "ITEM_CODE" not in df.columns:
        for col in ["SKU", "PN_CODE", "ITEM_NO"]:
            if col in df.columns:
                df["ITEM_CODE"] = df[col]
                break
    return df

def apply_filters(df, filters):
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
        elif key_upper in ["ITEM_CODE", "ITEM", "SKU", "PN_CODE"]:
            if "ITEM_CODE" in df.columns:
                df = df[df["ITEM_CODE"].astype(str) == str(val)]
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

def diff_balance(df_a, df_b, group_by=None, granularity="week", filters=None, only_diff=True,
                 threshold_abs=0, threshold_pct=0, sort_by="abs_diff_desc", page=1, page_size=100,
                 compare_field="BALANCE_QTY"):
    try:
        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)
        df_a_filt = apply_filters(df_a_norm, filters)
        df_b_filt = apply_filters(df_b_norm, filters)
        if df_a_filt.empty and df_b_filt.empty:
            return {"total_a": 0, "total_b": 0, "records": [], "pagination": {"page": 1, "page_size": page_size, "total": 0}, "group_by": ["ITEM_CODE"], "granularity": granularity}
        gran = (granularity or "week").lower()
        time_col = get_time_col(gran)
        if gran == "shift":
            group_keys = ["ITEM_CODE", "_DATE", "SHIFT_NAME"]
            if "SHIFT_NAME" not in df_a_filt.columns:
                df_a_filt["SHIFT_NAME"] = "白班"
            if "SHIFT_NAME" not in df_b_filt.columns:
                df_b_filt["SHIFT_NAME"] = "白班"
        else:
            group_keys = ["ITEM_CODE", time_col]
        group_keys = [k for k in group_keys if k in df_a_filt.columns or k in df_b_filt.columns]
        if not group_keys:
            group_keys = ["ITEM_CODE"]
        if compare_field not in df_a_filt.columns:
            compare_field = "BALANCE_QTY"
        if compare_field not in df_b_filt.columns:
            compare_field = "BALANCE_QTY"
        def sort_and_last(df, keys, field):
            if df.empty:
                return pd.DataFrame(columns=keys + [field])
            sort_cols = []
            if "_DATE_DT" in df.columns:
                sort_cols.append("_DATE_DT")
            if "_SHIFT_ORDER" in df.columns:
                sort_cols.append("_SHIFT_ORDER")
            if sort_cols:
                df = df.sort_values(sort_cols)
            try:
                agg = df.groupby(keys, as_index=False)[field].last()
                return agg
            except Exception:
                try:
                    agg = df.groupby(keys, as_index=False).last()
                    keep = keys + [field]
                    agg = agg[[c for c in keep if c in agg.columns]]
                    return agg
                except:
                    return pd.DataFrame(columns=keys + [field])
        agg_a = sort_and_last(df_a_filt, group_keys, compare_field)
        agg_b = sort_and_last(df_b_filt, group_keys, compare_field)
        merged = pd.merge(agg_a, agg_b, on=group_keys, how="outer", suffixes=("_A", "_B"))
        col_a = f"{compare_field}_A"
        col_b = f"{compare_field}_B"
        if col_a not in merged.columns:
            merged[col_a] = 0
        if col_b not in merged.columns:
            merged[col_b] = 0
        merged[col_a] = merged[col_a].fillna(0)
        merged[col_b] = merged[col_b].fillna(0)
        merged["diff"] = merged[col_b] - merged[col_a]
        merged["abs_diff"] = merged["diff"].abs()
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
            merged["diff_pct"] = merged.apply(lambda r: (r["diff"] / r[col_a] * 100) if r[col_a] != 0 else (100 if r["diff"] !=0 else 0), axis=1)
            merged = merged[merged["diff_pct"].abs() >= threshold_pct]
        else:
            merged["diff_pct"] = merged.apply(lambda r: (r["diff"] / r[col_a] * 100) if r[col_a] != 0 else (100 if r["diff"] !=0 else 0), axis=1)
        if sort_by == "abs_diff_desc":
            merged = merged.sort_values("abs_diff", ascending=False)
        elif sort_by == "diff_desc":
            merged = merged.sort_values("diff", ascending=False)
        elif sort_by == "diff_asc":
            merged = merged.sort_values("diff", ascending=True)
        elif sort_by == "item_asc":
            sort_key = group_keys[0] if group_keys else col_a
            if sort_key in merged.columns:
                merged = merged.sort_values(sort_key)
        total = len(merged)
        start = (page-1)*page_size
        end = start+page_size
        paged = merged.iloc[start:end] if total>0 else merged
        records = []
        for _, row in paged.iterrows():
            rec = {}
            for k in group_keys:
                v = row.get(k)
                if pd.isna(v):
                    rec[k] = None
                else:
                    try:
                        if hasattr(v, 'strftime'):
                            rec[k] = v.strftime("%Y-%m-%d") if hasattr(v, 'year') else str(v)
                        else:
                            rec[k] = str(v) if not isinstance(v, (int, float)) else v
                    except:
                        rec[k] = str(v)
            rec["ITEM_CODE"] = rec.get("ITEM_CODE") or row.get("ITEM_CODE") or "Unknown"
            time_val = rec.get(time_col) or row.get(time_col) or rec.get("_DATE") or rec.get("_WEEK") or rec.get("_MONTH")
            rec["TIME"] = time_val
            rec["DATE"] = rec.get("_DATE") or row.get("_DATE") if "_DATE" in group_keys else rec.get(time_col)
            rec["WEEK"] = rec.get("_WEEK") if "_WEEK" in row else None
            rec["MONTH"] = rec.get("_MONTH") if "_MONTH" in row else None
            if gran == "month" or gran == "monthly":
                rec["TIME_LABEL"] = rec.get("_MONTH")
            elif gran == "week":
                rec["TIME_LABEL"] = rec.get("_WEEK")
            else:
                rec["TIME_LABEL"] = rec.get("_DATE")
            rec["PREV"] = float(row.get(col_a, 0))
            rec["LATEST"] = float(row.get(col_b, 0))
            rec["PREVIOUS"] = rec["PREV"]
            rec["LATEST_VALUE"] = rec["LATEST"]
            rec[f"{compare_field}_A"] = rec["PREV"]
            rec[f"{compare_field}_B"] = rec["LATEST"]
            rec["diff"] = float(row.get("diff", 0))
            rec["DIFF"] = rec["diff"]
            rec["abs_diff"] = float(row.get("abs_diff", 0))
            rec["diff_pct"] = float(row.get("diff_pct", 0))
            rec["change_tag"] = row.get("change_tag", "MODIFY")
            rec["change_type"] = rec["change_tag"]
            rec["TAG"] = rec["change_tag"]
            rec["_group_values"] = {k: rec.get(k) for k in group_keys}
            rec["_DATE"] = rec.get("_DATE")
            rec["_WEEK"] = rec.get("_WEEK")
            rec["_MONTH"] = rec.get("_MONTH")
            rec["ITEM_CODE"] = rec.get("ITEM_CODE")
            records.append(rec)
        return {
            "total_a": len(df_a),
            "total_b": len(df_b),
            "filtered_a": len(df_a_filt),
            "filtered_b": len(df_b_filt),
            "aggregated_a": len(agg_a),
            "aggregated_b": len(agg_b),
            "total_after_filter": total,
            "records": records,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "group_by": group_keys,
            "granularity": granularity,
            "valid_keys": group_keys,
            "compare_field": compare_field,
            "filters": filters or {},
            "display_name": "BOH",
            "table": "balance"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"total_a": len(df_a) if 'df_a' in locals() else 0, "total_b": len(df_b) if 'df_b' in locals() else 0, "error": str(e), "records": [], "pagination": {"page": 1, "page_size": page_size, "total": 0}}

def get_chart_data_balance(df_a, df_b, item_code=None, granularity="day", compare_field="BALANCE_QTY"):
    try:
        eff_filters = {}
        if item_code:
            eff_filters["ITEM_CODE"] = item_code
        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)
        df_a_filt = apply_filters(df_a_norm, eff_filters)
        df_b_filt = apply_filters(df_b_norm, eff_filters)
        gran = (granularity or "day").lower()
        time_col = get_time_col(gran)
        if df_a_filt.empty and df_b_filt.empty:
            return {"dates": [], "values_a": [], "values_b": []}
        def agg_for_chart(df):
            if df.empty:
                return pd.DataFrame()
            sort_cols = []
            if "_DATE_DT" in df.columns:
                sort_cols.append("_DATE_DT")
            if "_SHIFT_ORDER" in df.columns:
                sort_cols.append("_SHIFT_ORDER")
            if sort_cols:
                df = df.sort_values(sort_cols)
            try:
                agg = df.groupby(time_col, as_index=False)[compare_field].last()
                return agg
            except:
                return df
        agg_a = agg_for_chart(df_a_filt)
        agg_b = agg_for_chart(df_b_filt)
        if agg_a.empty and agg_b.empty:
            return {"dates": [], "values_a": [], "values_b": []}
        merged = pd.merge(agg_a, agg_b, on=time_col, how="outer", suffixes=("_A", "_B"))
        merged = merged.sort_values(time_col)
        merged = merged.fillna(0)
        col_a = f"{compare_field}_A"
        col_b = f"{compare_field}_B"
        if col_a not in merged.columns:
            col_a = "BALANCE_QTY_A" if "BALANCE_QTY_A" in merged.columns else col_a
        if col_b not in merged.columns:
            col_b = "BALANCE_QTY_B" if "BALANCE_QTY_B" in merged.columns else col_b
        dates = merged[time_col].astype(str).tolist()
        vals_a = merged[col_a].tolist() if col_a in merged.columns else []
        vals_b = merged[col_b].tolist() if col_b in merged.columns else []
        return {"dates": dates, "values_a": vals_a, "values_b": vals_b, "granularity": granularity, "compare_field": compare_field, "filters": eff_filters}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "dates": [], "values_a": [], "values_b": []}

def get_boh_horizontal_matrix(df_a, df_b, granularity="week", sku_category="ALL", only_diff=True, compare_field="BALANCE_QTY", change_type="ALL"):
    try:
        from .matrix_helpers import apply_sku_filter_df, generate_time_buckets
        from datetime import timedelta
        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)
        df_a_filt = apply_sku_filter_df(df_a_norm, "ITEM_CODE", sku_category)
        df_b_filt = apply_sku_filter_df(df_b_norm, "ITEM_CODE", sku_category)
        if df_a_filt.empty and df_b_filt.empty:
            return {"time_buckets": [], "sku_list": [], "matrix": {}, "summary": {"total_skus":0, "total_times":0}}
        gran = (granularity or "week").lower()
        def agg_last(df, keys, field):
            if df.empty:
                return pd.DataFrame(columns=keys + [field])
            sort_cols = []
            if "_DATE_DT" in df.columns:
                sort_cols.append("_DATE_DT")
            if "_SHIFT_ORDER" in df.columns:
                sort_cols.append("_SHIFT_ORDER")
            if sort_cols:
                df = df.sort_values(sort_cols)
            try:
                return df.groupby(keys, as_index=False)[field].last()
            except:
                return pd.DataFrame(columns=keys + [field])

        if gran in ["day"]:
            time_buckets = generate_time_buckets(df_a_filt, df_b_filt, "day")
            if not time_buckets:
                return {"time_buckets": [], "sku_list": [], "matrix": {}, "summary": {"total_skus":0, "total_times":0}}
            group_keys=["ITEM_CODE","_DATE"]
            agg_a=agg_last(df_a_filt, group_keys, compare_field)
            agg_b=agg_last(df_b_filt, group_keys, compare_field)
            merged = pd.merge(agg_a, agg_b, on=group_keys, how="outer", suffixes=("_A","_B"), indicator=True)
            merged[compare_field+"_A"] = merged[compare_field+"_A"].fillna(0)
            merged[compare_field+"_B"] = merged[compare_field+"_B"].fillna(0)
            merged["diff"] = merged[compare_field+"_B"] - merged[compare_field+"_A"]
            def get_tag(r):
                if r["_merge"]=="left_only":
                    return "DELETED"
                elif r["_merge"]=="right_only":
                    return "ADDED"
                else:
                    return "MODIFY" if r["diff"]!=0 else "UNCHANGED"
            merged["tag"] = merged.apply(get_tag, axis=1)
            if only_diff:
                merged = merged[merged["tag"]!="UNCHANGED"]
            merged["_BUCKET"] = merged["_DATE"]
            bucket_labels=time_buckets
            matrix={}
            for sku, group in merged.groupby("ITEM_CODE"):
                row={}
                for _, r in group.iterrows():
                    tb=r["_BUCKET"]
                    row[tb]={"prev":float(r[compare_field+"_A"]), "latest":float(r[compare_field+"_B"]), "diff":float(r["diff"]), "tag":r["tag"]}
                full_row={b: row.get(b) for b in bucket_labels}
                if only_diff and not any(v is not None for v in full_row.values()):
                    continue
                matrix[sku]=full_row
            final_skus=sorted(list(matrix.keys()))
            return {"time_buckets": time_buckets, "bucket_labels": bucket_labels, "sku_list": final_skus, "matrix": matrix, "granularity": gran, "sku_category": sku_category, "display_mode": "detailed", "summary": {"total_skus": len(final_skus), "total_times": len(bucket_labels), "total_original_skus": len(set(agg_a["ITEM_CODE"].dropna()) | set(agg_b["ITEM_CODE"].dropna())) if not agg_a.empty or not agg_b.empty else 0, "time_range": f"{bucket_labels[0]} to {bucket_labels[-1]}" if bucket_labels else "", "compare_field": compare_field}}

        # week/month yellow-only
        daily_keys=["ITEM_CODE","_DATE"]
        agg_a_daily=agg_last(df_a_filt, daily_keys, compare_field)
        agg_b_daily=agg_last(df_b_filt, daily_keys, compare_field)
        if agg_a_daily.empty and agg_b_daily.empty:
            return {"time_buckets": [], "sku_list": [], "matrix": {}, "summary": {"total_skus":0, "total_times":0}}
        merged_daily = pd.merge(agg_a_daily, agg_b_daily, on=daily_keys, how="outer", suffixes=("_A","_B"), indicator=True)
        merged_daily[compare_field+"_A"] = merged_daily[compare_field+"_A"].fillna(0)
        merged_daily[compare_field+"_B"] = merged_daily[compare_field+"_B"].fillna(0)
        merged_daily["diff"] = merged_daily[compare_field+"_B"] - merged_daily[compare_field+"_A"]
        def daily_tag(r):
            if r["_merge"]=="left_only":
                return "DELETED"
            elif r["_merge"]=="right_only":
                return "ADDED"
            else:
                return "MODIFY" if r["diff"]!=0 else "UNCHANGED"
        merged_daily["tag"] = merged_daily.apply(daily_tag, axis=1)
        merged_daily_diff = merged_daily[merged_daily["tag"]!="UNCHANGED"]
        if merged_daily_diff.empty and only_diff:
            return {"time_buckets": [], "sku_list": [], "matrix": {}, "summary": {"total_skus":0, "total_times":0, "note":"No diff"}}
        daily_has_change = {}
        for sku, group in merged_daily_diff.groupby("ITEM_CODE"):
            daily_has_change[sku] = set(group["_DATE"].astype(str).tolist())
        all_skus = sorted(list(daily_has_change.keys())) if only_diff else sorted(list(set(agg_a_daily["ITEM_CODE"].dropna()) | set(agg_b_daily["ITEM_CODE"].dropna())))

        if gran in ["month","monthly"]:
            target_buckets = generate_time_buckets(df_a_filt, df_b_filt, "month")
            matrix={}
            for sku in all_skus:
                changed_set = daily_has_change.get(sku, set())
                if not changed_set and only_diff:
                    continue
                row={}
                has_any=False
                for mb in target_buckets:
                    changed_in_month = [d for d in changed_set if d.startswith(mb)]
                    if changed_in_month:
                        has_any=True
                        row[mb]={"has_change":True,"tag":"HAS_CHANGE","changed_days":sorted(changed_in_month),"changed_count":len(changed_in_month),"display_mode":"has_change"}
                    else:
                        row[mb]=None
                if only_diff and not has_any:
                    continue
                matrix[sku]=row
            final_skus=sorted(list(matrix.keys()))
            return {"time_buckets": target_buckets, "bucket_labels": target_buckets, "sku_list": final_skus, "matrix": matrix, "granularity": gran, "sku_category": sku_category, "display_mode": "has_change", "summary": {"total_skus": len(final_skus), "total_times": len(target_buckets), "total_original_skus": len(all_skus), "time_range": f"{target_buckets[0]} to {target_buckets[-1]}" if target_buckets else "", "compare_field": compare_field, "note": "Yellow-only"}}
        else:
            target_buckets = generate_time_buckets(df_a_filt, df_b_filt, "week")
            def dates_in_week(saturday_str):
                try:
                    sat_dt = pd.to_datetime(saturday_str)
                    sun_dt = sat_dt - timedelta(days=6)
                    dates=[]
                    cur=sun_dt
                    for _ in range(7):
                        dates.append(cur.strftime("%Y-%m-%d"))
                        cur+=timedelta(days=1)
                    return set(dates)
                except:
                    return set()
            week_to_dates={wb: dates_in_week(wb) for wb in target_buckets}
            matrix={}
            for sku in all_skus:
                changed_set = daily_has_change.get(sku, set())
                if not changed_set and only_diff:
                    continue
                row={}
                has_any=False
                for wb in target_buckets:
                    dset=week_to_dates.get(wb,set())
                    changed_in_week = [d for d in changed_set if d in dset]
                    if changed_in_week:
                        has_any=True
                        row[wb]={"has_change":True,"tag":"HAS_CHANGE","changed_days":sorted(changed_in_week),"changed_count":len(changed_in_week),"display_mode":"has_change"}
                    else:
                        row[wb]=None
                if only_diff and not has_any:
                    continue
                matrix[sku]=row
            final_skus=sorted(list(matrix.keys()))
            return {"time_buckets": target_buckets, "bucket_labels": target_buckets, "sku_list": final_skus, "matrix": matrix, "granularity": gran, "sku_category": sku_category, "display_mode": "has_change", "summary": {"total_skus": len(final_skus), "total_times": len(target_buckets), "total_original_skus": len(all_skus), "time_range": f"{target_buckets[0]} to {target_buckets[-1]}" if target_buckets else "", "compare_field": compare_field, "note": "Yellow-only"}}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "time_buckets": [], "sku_list": [], "matrix": {}}
