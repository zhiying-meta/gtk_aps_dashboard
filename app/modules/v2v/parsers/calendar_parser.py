"""
Calendar parser - 线体日历快照表
Key: (LINE_CODE, PLAN_TYPE, PLAN_DATE, SHIFT_NAME, PLAN_ITEM)
Compare: PLAN_VALUE
Types: UPH, 工时, 良率, 效率, CHECKOUT
Supports chart: UPH curve per line
"""
import pandas as pd

def parse_calendar(file_path: str):
    df = pd.read_excel(file_path)
    return df

def diff_calendar(df_a, df_b, granularity="day"):
    """
    granularity: day (default) or week
    For calendar, day is natural, week aggregates? Keep day for MVP.
    """
    try:
        key_cols = ["LINE_CODE", "PLAN_TYPE", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM"]
        # Ensure columns exist
        for k in key_cols:
            if k not in df_a.columns:
                df_a[k] = None
            if k not in df_b.columns:
                df_b[k] = None

        # Normalize date
        df_a = df_a.copy()
        df_b = df_b.copy()
        df_a["_DATE_DT"] = pd.to_datetime(df_a["PLAN_DATE"], errors='coerce')
        df_b["_DATE_DT"] = pd.to_datetime(df_b["PLAN_DATE"], errors='coerce')

        if granularity == "week":
            def to_saturday(dt):
                if pd.isna(dt):
                    return None
                dow = dt.weekday()
                delta = (5 - dow) % 7
                from datetime import timedelta
                return dt + timedelta(days=delta)
            df_a["_WEEK"] = df_a["_DATE_DT"].apply(to_saturday)
            df_b["_WEEK"] = df_b["_DATE_DT"].apply(to_saturday)
            merge_keys = ["LINE_CODE", "PLAN_TYPE", "_WEEK", "SHIFT_NAME", "PLAN_ITEM"]
            df_a["_MERGE_WEEK"] = df_a["_WEEK"].astype(str)
            df_b["_MERGE_WEEK"] = df_b["_WEEK"].astype(str)
            agg_a = df_a.groupby(merge_keys, as_index=False)["PLAN_VALUE"].mean()
            agg_b = df_b.groupby(merge_keys, as_index=False)["PLAN_VALUE"].mean()
            agg_a["_WEEK_STR"] = agg_a["_WEEK"].astype(str)
            agg_b["_WEEK_STR"] = agg_b["_WEEK"].astype(str)
            merge_on = ["LINE_CODE", "PLAN_TYPE", "_WEEK_STR", "SHIFT_NAME", "PLAN_ITEM"]
            df_a_use = agg_a
            df_b_use = agg_b
        elif granularity in ["monthly", "month"]:
            df_a["_MONTH"] = df_a["_DATE_DT"].dt.strftime("%Y-%m")
            df_b["_MONTH"] = df_b["_DATE_DT"].dt.strftime("%Y-%m")
            merge_keys = ["LINE_CODE", "PLAN_TYPE", "_MONTH", "SHIFT_NAME", "PLAN_ITEM"]
            agg_a = df_a.groupby(merge_keys, as_index=False)["PLAN_VALUE"].mean()
            agg_b = df_b.groupby(merge_keys, as_index=False)["PLAN_VALUE"].mean()
            merge_on = ["LINE_CODE", "PLAN_TYPE", "_MONTH", "SHIFT_NAME", "PLAN_ITEM"]
            df_a_use = agg_a
            df_b_use = agg_b
        else:
            df_a["_DATE_STR"] = df_a["_DATE_DT"].dt.strftime("%Y-%m-%d")
            df_b["_DATE_STR"] = df_b["_DATE_DT"].dt.strftime("%Y-%m-%d")
            merge_on = ["LINE_CODE", "PLAN_TYPE", "_DATE_STR", "SHIFT_NAME", "PLAN_ITEM"]
            df_a_use = df_a
            df_b_use = df_b

        merged = pd.merge(df_a_use, df_b_use, on=merge_on, how="outer", suffixes=("_A", "_B"), indicator=True)

        added = merged[merged["_merge"] == "right_only"]
        deleted = merged[merged["_merge"] == "left_only"]
        both = merged[merged["_merge"] == "both"]

        modified = []
        for _, row in both.iterrows():
            va = row.get("PLAN_VALUE_A")
            vb = row.get("PLAN_VALUE_B")
            if pd.isna(va) and pd.isna(vb):
                continue
            try:
                if pd.isna(va) or pd.isna(vb):
                    diff = True
                else:
                    diff = abs(float(va) - float(vb)) > 1e-6
                    if not diff:
                        continue
            except:
                if str(va) == str(vb):
                    continue
                diff = True

            if diff:
                # Build key for display
                if granularity == "week":
                    key = {
                        "LINE_CODE": row["LINE_CODE"],
                        "PLAN_TYPE": row["PLAN_TYPE"],
                        "WEEK": row["_WEEK_STR"],
                        "SHIFT_NAME": row["SHIFT_NAME"],
                        "PLAN_ITEM": row["PLAN_ITEM"]
                    }
                else:
                    key = {
                        "LINE_CODE": row["LINE_CODE"],
                        "PLAN_TYPE": row["PLAN_TYPE"],
                        "PLAN_DATE": row.get("_DATE_STR", str(row.get("PLAN_DATE"))),
                        "SHIFT_NAME": row["SHIFT_NAME"],
                        "PLAN_ITEM": row["PLAN_ITEM"]
                    }

                try:
                    delta = float(vb) - float(va) if not pd.isna(va) and not pd.isna(vb) else None
                except:
                    delta = None

                modified.append({
                    "key": key,
                    "field": "PLAN_VALUE",
                    "value_a": float(va) if not pd.isna(va) and isinstance(va, (int,float)) else str(va) if not pd.isna(va) else None,
                    "value_b": float(vb) if not pd.isna(vb) and isinstance(vb, (int,float)) else str(vb) if not pd.isna(vb) else None,
                    "delta": delta,
                    "change_type": "MODIFY"
                })

        return {
            "total_a": len(df_a),
            "total_b": len(df_b),
            "added": len(added),
            "deleted": len(deleted),
            "modified": len(modified),
            "records": {
                "added": added.head(50).to_dict(orient="records"),
                "deleted": deleted.head(50).to_dict(orient="records"),
                "modified": modified[:100]
            },
            "summary": {
                "added": len(added),
                "deleted": len(deleted),
                "modified": len(modified),
                "granularity": granularity,
                "by_plan_type": both.groupby("PLAN_TYPE").size().to_dict() if not both.empty and "PLAN_TYPE" in both.columns else {}
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "total_a": len(df_a) if 'df_a' in locals() else 0,
            "total_b": len(df_b) if 'df_b' in locals() else 0,
            "added": 0,
            "deleted": 0,
            "modified": 0,
            "error": str(e),
            "records": []
        }


def get_chart_data_calendar(df_a, df_b, line_code=None, plan_type="UPH", shift_name="白班"):
    """
    Get UPH curve for a specific line and plan_type
    """
    try:
        # Filter
        if line_code:
            df_a = df_a[df_a["LINE_CODE"] == line_code]
            df_b = df_b[df_b["LINE_CODE"] == line_code]
        if plan_type:
            df_a = df_a[df_a["PLAN_TYPE"] == plan_type]
            df_b = df_b[df_b["PLAN_TYPE"] == plan_type]
        if shift_name:
            df_a = df_a[df_a["SHIFT_NAME"] == shift_name]
            df_b = df_b[df_b["SHIFT_NAME"] == shift_name]

        df_a = df_a.copy()
        df_b = df_b.copy()
        df_a["_DATE"] = pd.to_datetime(df_a["PLAN_DATE"], errors='coerce')
        df_b["_DATE"] = pd.to_datetime(df_b["PLAN_DATE"], errors='coerce')

        df_a = df_a.sort_values("_DATE")
        df_b = df_b.sort_values("_DATE")

        # Group by date mean
        agg_a = df_a.groupby("_DATE")["PLAN_VALUE"].mean().reset_index()
        agg_b = df_b.groupby("_DATE")["PLAN_VALUE"].mean().reset_index()

        merged = pd.merge(agg_a, agg_b, on="_DATE", how="outer", suffixes=("_A", "_B")).sort_values("_DATE")

        dates = [d.strftime("%Y-%m-%d") if hasattr(d, 'strftime') else str(d) for d in merged["_DATE"]]
        vals_a = merged["PLAN_VALUE_A"].fillna(0).tolist()
        vals_b = merged["PLAN_VALUE_B"].fillna(0).tolist()

        return {
            "dates": dates,
            "values_a": vals_a,
            "values_b": vals_b,
            "line_code": line_code,
            "plan_type": plan_type,
            "shift": shift_name
        }
    except Exception as e:
        return {"error": str(e), "dates": [], "values_a": [], "values_b": []}
