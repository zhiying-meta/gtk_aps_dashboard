"""FCST parser - Main + Detail JOIN"""
import pandas as pd

def parse_fcst(main_path: str, detail_path: str):
    try:
        main_df = pd.read_excel(main_path)
        detail_df = pd.read_excel(detail_path)
        return main_df, detail_df
    except Exception as e:
        raise e


def build_fcst_joined(main_df, detail_df):
    """
    JOIN main and detail via ID = MAIN_ID, then build SKU x Week matrix
    Returns DataFrame with SKU, Week, Value
    """
    try:
        # Ensure ID columns are same type
        main_df = main_df.copy()
        detail_df = detail_df.copy()
        # Convert ID to string for join safety
        main_df["ID_STR"] = main_df["ID"].astype(str)
        detail_df["MAIN_ID_STR"] = detail_df["MAIN_ID"].astype(str)

        # Merge
        merged = pd.merge(detail_df, main_df[["ID_STR", "PN_CODE"]], left_on="MAIN_ID_STR", right_on="ID_STR", how="left")
        # Now merged has PN_CODE, ACTUALFIRSTDAYOFWEEK, ACTUALWEEKVALUE
        # Group by PN_CODE, ACTUALFIRSTDAYOFWEEK sum ACTUALWEEKVALUE
        if "ACTUALFIRSTDAYOFWEEK" not in merged.columns or "PN_CODE" not in merged.columns:
            return pd.DataFrame()

        # Normalize week date
        # Keep relevant cols
        grouped = merged.groupby(["PN_CODE", "ACTUALFIRSTDAYOFWEEK"], as_index=False)["ACTUALWEEKVALUE"].sum()
        return grouped
    except Exception as e:
        print(f"FCST JOIN error: {e}")
        return pd.DataFrame()


def diff_fcst(main_a, detail_a, main_b, detail_b):
    try:
        joined_a = build_fcst_joined(main_a, detail_a)
        joined_b = build_fcst_joined(main_b, detail_b)

        if joined_a.empty and joined_b.empty:
            return {
                "total_a": 0,
                "total_b": 0,
                "added": 0,
                "deleted": 0,
                "modified": 0,
                "records": [],
                "summary": {}
            }

        # Outer merge on PN_CODE + Week
        merged = pd.merge(joined_a, joined_b, on=["PN_CODE", "ACTUALFIRSTDAYOFWEEK"], how="outer", suffixes=("_A", "_B"), indicator=True)
        added = merged[merged["_merge"] == "right_only"]
        deleted = merged[merged["_merge"] == "left_only"]
        both = merged[merged["_merge"] == "both"]

        modified = []
        for _, row in both.iterrows():
            va = row.get("ACTUALWEEKVALUE_A")
            vb = row.get("ACTUALWEEKVALUE_B")
            if pd.isna(va) and pd.isna(vb):
                continue
            if va != vb:
                try:
                    if pd.isna(va) or pd.isna(vb):
                        pass
                    else:
                        if float(va) == float(vb):
                            continue
                except:
                    if str(va) == str(vb):
                        continue
                modified.append({
                    "key": {"PN_CODE": row["PN_CODE"], "WEEK": str(row["ACTUALFIRSTDAYOFWEEK"])},
                    "field": "ACTUALWEEKVALUE",
                    "value_a": float(va) if not pd.isna(va) else 0,
                    "value_b": float(vb) if not pd.isna(vb) else 0,
                    "delta": float(vb)-float(va) if not pd.isna(va) and not pd.isna(vb) else None,
                    "change_type": "MODIFY"
                })

        return {
            "total_a": len(joined_a),
            "total_b": len(joined_b),
            "added": len(added),
            "deleted": len(deleted),
            "modified": len(modified),
            "records": {
                "added": added.head(100).to_dict(orient="records"),
                "deleted": deleted.head(100).to_dict(orient="records"),
                "modified": modified[:100]
            },
            "summary": {
                "total_weeks_a": joined_a["ACTUALFIRSTDAYOFWEEK"].nunique() if not joined_a.empty else 0,
                "total_weeks_b": joined_b["ACTUALFIRSTDAYOFWEEK"].nunique() if not joined_b.empty else 0,
                "total_skus_a": joined_a["PN_CODE"].nunique() if not joined_a.empty else 0,
                "total_skus_b": joined_b["PN_CODE"].nunique() if not joined_b.empty else 0
            }
        }
    except Exception as e:
        return {
            "total_a": 0,
            "total_b": 0,
            "added": 0,
            "deleted": 0,
            "modified": 0,
            "error": str(e),
            "records": []
        }
