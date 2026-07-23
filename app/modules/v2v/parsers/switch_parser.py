"""
Switch Matrix parser - 切换矩阵快照表
Handles the special case where BEFORE_PN is in Unnamed column
Key: (LINE_CODE, BEFORE_PN, AFTER_PN)
Compare: SWITCH_DURATION
"""
import pandas as pd

def normalize_switch_df(df):
    """
    Normalize switch dataframe to handle Unnamed column containing BEFORE_PN
    """
    df = df.copy()
    # Check for Unnamed column that contains PN codes
    # In the file, column 5 (Unnamed:5) contains BEFORE_PN_CODE
    unnamed_cols = [c for c in df.columns if 'Unnamed' in str(c) or c == '' or c is None]
    # If we have BEFORE_PROJECT_CODE but empty, and Unnamed column has SK- values, use it as BEFORE_PN
    for uc in unnamed_cols:
        # Check if this column contains SK- or GB- values
        sample = df[uc].dropna().astype(str).head(10)
        if any('SK-' in str(v) or 'GB-' in str(v) for v in sample):
            # This is BEFORE_PN_CODE
            df['BEFORE_PN_CODE'] = df[uc]
            break
    
    # If BEFORE_PN_CODE still not exists, try BEFORE_PROJECT_CODE that contains PN
    if 'BEFORE_PN_CODE' not in df.columns:
        if 'BEFORE_PROJECT_CODE' in df.columns:
            # Check if it contains PN codes
            sample = df['BEFORE_PROJECT_CODE'].dropna().astype(str).head(10)
            if any('SK-' in str(v) for v in sample):
                df['BEFORE_PN_CODE'] = df['BEFORE_PROJECT_CODE']
            else:
                # BEFORE_PROJECT_CODE is empty, use Unnamed
                df['BEFORE_PN_CODE'] = None
        else:
            df['BEFORE_PN_CODE'] = None

    # Ensure AFTER_PN_CODE exists
    if 'AFTER_PN_CODE' not in df.columns:
        df['AFTER_PN_CODE'] = None

    return df

def parse_switch(file_path: str):
    df = pd.read_excel(file_path)
    df = normalize_switch_df(df)
    return df

def diff_switch(df_a, df_b):
    try:
        df_a = normalize_switch_df(df_a)
        df_b = normalize_switch_df(df_b)

        key_cols = ["LINE_CODE", "BEFORE_PN_CODE", "AFTER_PN_CODE"]
        # Filter rows where key not null?
        # For merge, ensure we have these cols
        for k in key_cols:
            if k not in df_a.columns:
                df_a[k] = None
            if k not in df_b.columns:
                df_b[k] = None

        # Drop rows where BEFORE_PN_CODE is NaN? Keep for diff detection of added/deleted
        # But for meaningful diff, we need valid keys
        df_a['_KEY'] = df_a['LINE_CODE'].astype(str) + '|' + df_a['BEFORE_PN_CODE'].astype(str) + '|' + df_a['AFTER_PN_CODE'].astype(str)
        df_b['_KEY'] = df_b['LINE_CODE'].astype(str) + '|' + df_b['BEFORE_PN_CODE'].astype(str) + '|' + df_b['AFTER_PN_CODE'].astype(str)

        merged = pd.merge(df_a, df_b, on='_KEY', how='outer', suffixes=('_A', '_B'), indicator=True)

        added = merged[merged["_merge"] == "right_only"]
        deleted = merged[merged["_merge"] == "left_only"]
        both = merged[merged["_merge"] == "both"]

        modified = []
        for _, row in both.iterrows():
            va = row.get('SWITCH_DURATION_A')
            vb = row.get('SWITCH_DURATION_B')
            if pd.isna(va) and pd.isna(vb):
                continue
            try:
                if pd.isna(va) or pd.isna(vb) or float(va) != float(vb):
                    modified.append({
                        "key": {
                            "LINE_CODE": row.get('LINE_CODE_A'),
                            "BEFORE_PN_CODE": row.get('BEFORE_PN_CODE_A'),
                            "AFTER_PN_CODE": row.get('AFTER_PN_CODE_A')
                        },
                        "field": "SWITCH_DURATION",
                        "value_a": float(va) if not pd.isna(va) else None,
                        "value_b": float(vb) if not pd.isna(vb) else None,
                        "delta": float(vb)-float(va) if not pd.isna(va) and not pd.isna(vb) else None,
                        "change_type": "MODIFY"
                    })
            except:
                if str(va) != str(vb):
                    modified.append({
                        "key": {
                            "LINE_CODE": row.get('LINE_CODE_A'),
                            "BEFORE_PN_CODE": row.get('BEFORE_PN_CODE_A'),
                            "AFTER_PN_CODE": row.get('AFTER_PN_CODE_A')
                        },
                        "field": "SWITCH_DURATION",
                        "value_a": str(va),
                        "value_b": str(vb),
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
        return {
            "total_a": len(df_a) if 'df_a' in locals() else 0,
            "total_b": len(df_b) if 'df_b' in locals() else 0,
            "added": 0,
            "deleted": 0,
            "modified": 0,
            "error": str(e),
            "records": []
        }
