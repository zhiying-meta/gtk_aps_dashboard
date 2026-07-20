"""
Item Master parser - 料号快照表
Key: ITEM_NO
Compare: PRODUCT_STYLE, COLOR, TYPE, etc.
"""
import pandas as pd

def parse_item(file_path: str):
    df = pd.read_excel(file_path)
    return df

def diff_item(df_a, df_b):
    try:
        key = "ITEM_NO"
        compare_fields = ["PRODUCT_STYLE", "COLOR", "TYPE", "STYLE", "PRODUCT_TYPE", "MAKE_OR_BUY"]

        if key not in df_a.columns or key not in df_b.columns:
            return {"total_a": len(df_a), "total_b": len(df_b), "added":0,"deleted":0,"modified":0, "error": f"Missing {key}", "records":[]}

        merged = pd.merge(df_a, df_b, on=key, how="outer", suffixes=("_A","_B"), indicator=True)
        added = merged[merged["_merge"] == "right_only"]
        deleted = merged[merged["_merge"] == "left_only"]
        both = merged[merged["_merge"] == "both"]

        modified = []
        for _, row in both.iterrows():
            for field in compare_fields:
                if field not in df_a.columns:
                    continue
                col_a = field + "_A"
                col_b = field + "_B"
                if col_a not in row or col_b not in row:
                    continue
                va = row[col_a]
                vb = row[col_b]
                if pd.isna(va) and pd.isna(vb):
                    continue
                if str(va) != str(vb):
                    modified.append({
                        "key": {key: row[key]},
                        "field": field,
                        "value_a": str(va) if not pd.isna(va) else None,
                        "value_b": str(vb) if not pd.isna(vb) else None,
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
                "modified": len(modified)
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"total_a": len(df_a) if 'df_a' in locals() else 0, "total_b": len(df_b) if 'df_b' in locals() else 0, "added":0,"deleted":0,"modified":0,"error":str(e),"records":[]}
