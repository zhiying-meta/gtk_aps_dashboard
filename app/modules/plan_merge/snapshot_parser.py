"""
Snapshot parser for gated.ungated.ctb folder format
- Understands raw APS exports: 料号快照, BOM快照, gated/ungated排产结果表, FCST主表+明细, CTB.xlsx
- Converts them into the same intermediate structure as legacy input_demo.xlsx's 6 sheets
- Reuses pallet default 864
"""
import os
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from app.modules.plan_merge.config import DEFAULT_PALLET_QTY

def _norm_date(s):
    """Normalize date like 2026/6/2 or 2026-06-02 to YYYY-MM-DD"""
    if pd.isna(s):
        return ""
    try:
        # Use pandas to parse
        dt = pd.to_datetime(str(s), errors='coerce')
        if pd.isna(dt):
            return str(s).strip()
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(s).strip()

def _clean(v):
    if pd.isna(v):
        return ""
    return str(v).strip()

def _read_excel_safe(file_path, sheet_name=0):
    """
    Safe wrapper for pd.read_excel with explicit engine, to avoid
    'Excel file format cannot be determined, you must specify an engine manually'
    Tries multiple engines and gives detailed error with filename.
    Also includes openpyxl manual fallback that builds DataFrame from rows.
    """
    fp_str = str(file_path)
    base = os.path.basename(fp_str)
    # Basic existence/size check
    if not os.path.exists(fp_str):
        raise FileNotFoundError(f"File not found: {base} at {fp_str}")
    sz = os.path.getsize(fp_str)
    if sz == 0:
        raise ValueError(f"File {base} is empty (0 bytes) – upload may have failed or file is corrupted")
    # Check magic number: xlsx should be zip file (PK)
    try:
        with open(fp_str, 'rb') as fh:
            head = fh.read(4)
            if len(head) >= 2 and head[:2] == b'\xd0\xcf':
                raise ValueError(f"File {base} appears to be old .xls format (OLE2), please save as .xlsx (openpyxl cannot read .xls)")
            if len(head) >= 2 and head[:2] != b'PK':
                # Not a zip file, maybe csv or corrupted – we will still try, but warn
                # For files < 100 bytes, likely not valid
                if sz < 100:
                    raise ValueError(f"File {base} too small ({sz} bytes) and not a valid xlsx (no PK header), appears corrupted")
    except ValueError:
        raise
    except Exception:
        pass

    # Try openpyxl direct validation first for clearer error messages
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        wb.close()
    except Exception as oe:
        # If openpyxl fails, it's definitely not a valid xlsx
        # Provide specific hint based on error message
        oe_str = str(oe)
        if "no item named '[Content_Types].xml'" in oe_str.lower() or "file is not a zip file" in oe_str.lower():
            raise ValueError(
                f"File {base} ({sz} bytes) is not a valid .xlsx (openpyxl: {oe}). "
                f"It might be a .zip containing files, a .xls old format, or corrupted. "
                f"If it's a zip, please extract and upload the inner xlsx files separately. "
                f"If it's .xls, please save as .xlsx in Excel. Path: {fp_str}"
            ) from oe
        # Otherwise continue to try pandas engines, maybe it's still readable

    # Try engines in order: openpyxl first (most common for xlsx)
    last_err = None
    for eng in ("openpyxl", None):
        try:
            if eng:
                return pd.read_excel(file_path, sheet_name=sheet_name, engine=eng)
            else:
                return pd.read_excel(file_path, sheet_name=sheet_name)
        except Exception as e:
            # Filter out confusing pandas zip.reader error – treat as invalid xlsx
            e_str = str(e)
            if "io.excel.zip.reader" in e_str or "No such keys" in e_str:
                # This happens when a zip file (not xlsx) is passed with .xlsx extension and pandas tries to handle as zip
                last_err = ValueError(
                    f"File {base} appears to be a zip archive, not a valid xlsx (pandas zip handling failed). "
                    f"If you uploaded a .zip, please ensure it contains xlsx files and upload via zip option, "
                    f"or extract it first. Original error: {e}"
                )
            else:
                last_err = e
            continue

    # Final fallback: manual openpyxl to DataFrame (for files that openpyxl can open but pandas can't)
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        if isinstance(sheet_name, int):
            ws_name = sheet_names[sheet_name] if sheet_name < len(sheet_names) else sheet_names[0]
        else:
            ws_name = sheet_name if sheet_name in sheet_names else sheet_names[0]
        ws = wb[ws_name]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not rows:
            raise ValueError(f"Sheet {ws_name} is empty")
        header = [str(h).strip() if h is not None else "" for h in rows[0]]
        data_rows = rows[1:]
        df = pd.DataFrame(data_rows, columns=header)
        return df
    except Exception as oe:
        raise ValueError(
            f"Failed to read {base} ({sz} bytes): {last_err} – fallback openpyxl also failed: {oe} – "
            f"ensure it's a valid .xlsx file. Common causes: file is .xls old format, corrupted, or is actually a zip file. "
            f"Try opening in Excel and re-saving as .xlsx. Path: {fp_str}"
        ) from last_err

def parse_item_snapshot(file_path):
    """
    Parse 料号快照.xlsx -> sku_attrs, gb_style_color
    - sku_attrs: {SKU: {Style, Color, Usage}}
    - gb_style_color: {GB_PN: (Style, Color)}
    """
    df = _read_excel_safe(file_path, sheet_name=0)
    # Normalize columns
    sku_attrs = {}
    gb_style_color = {}
    fr_style_color = {}
    lt_style_color = {}
    rt_style_color = {}

    for _, row in df.iterrows():
        item_no = _clean(row.get("ITEM_NO"))
        if not item_no:
            continue
        style = _clean(row.get("STYLE"))
        color = _clean(row.get("COLOR"))
        # PURPOSE is Usage, fallback to PRODUCT_STYLE or TYPE
        purpose = _clean(row.get("PURPOSE")) or _clean(row.get("PRODUCT_STYLE")) or _clean(row.get("TYPE")) or "MP"
        # For style/color, fallback
        # ITEM_NO patterns
        if item_no.startswith("SK-"):
            sku_attrs[item_no] = {"Style": style, "Color": color, "Usage": purpose or "MP"}
        elif item_no.startswith("GB-"):
            gb_style_color[item_no] = (style, color)
        elif item_no.startswith("FR-"):
            fr_style_color[item_no] = (style, color)
        elif item_no.startswith("LT-"):
            lt_style_color[item_no] = (style, color)
        elif item_no.startswith("RT-"):
            rt_style_color[item_no] = (style, color)

    return sku_attrs, gb_style_color, fr_style_color, lt_style_color, rt_style_color


def parse_bom(file_path):
    """
    Parse BOM快照.xlsx -> parent -> children list, and also build parent mapping
    Returns: parent_to_children dict, child_to_parents
    """
    df = _read_excel_safe(file_path, sheet_name=0)
    parent_to_children = defaultdict(list)
    child_to_parent = {}
    for _, row in df.iterrows():
        parent = _clean(row.get("PARENT_PN_CODE"))
        child = _clean(row.get("ITEM_NO"))
        if not parent or not child:
            continue
        parent_to_children[parent].append(child)
        child_to_parent[child] = parent
    return parent_to_children, child_to_parent


def build_sku_master(item_path, bom_path):
    """
    Build sku_attrs, sku_to_gb, sku_pallet, gb_style_color from item + bom
    - Uses BFS to find GB descendant for each SKU
    """
    try:
        sku_attrs, gb_style_color, fr_sc, lt_sc, rt_sc = _safe_parse_wrapper(parse_item_snapshot, item_path, "料号快照")
    except Exception as e:
        raise
    try:
        parent_to_children, _ = _safe_parse_wrapper(parse_bom, bom_path, "BOM快照")
    except Exception as e:
        raise

    sku_to_gb = {}
    sku_to_fr = {}
    sku_to_lt = {}
    sku_to_rt = {}
    sku_pallet = {}

    # For each SKU, find its GB/FR/LT/RT by traversing children
    for sku in sku_attrs.keys():
        # BFS from sku to find components
        visited = set()
        queue = [sku]
        found_gb = []
        found_fr = []
        found_lt = []
        found_rt = []
        while queue:
            cur = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            children = parent_to_children.get(cur, [])
            for ch in children:
                if ch.startswith("GB-"):
                    found_gb.append(ch)
                elif ch.startswith("FR-"):
                    found_fr.append(ch)
                elif ch.startswith("LT-"):
                    found_lt.append(ch)
                elif ch.startswith("RT-"):
                    found_rt.append(ch)
                # Continue BFS if child itself has children (e.g., intermediate 30*/31* items)
                if ch in parent_to_children:
                    queue.append(ch)
        # Pick first found as primary
        if found_gb:
            # Prefer exact match by style/color later? For now first
            sku_to_gb[sku] = found_gb[0]
        if found_fr:
            sku_to_fr[sku] = found_fr[0]
        if found_lt:
            sku_to_lt[sku] = found_lt[0]
        if found_rt:
            sku_to_rt[sku] = found_rt[0]
        sku_pallet[sku] = DEFAULT_PALLET_QTY

    # gb_style_color already from item snapshot, but ensure all GB found in sku_to_gb have entry
    # If missing, try to infer from sku's style/color
    for sku, gb in sku_to_gb.items():
        if gb not in gb_style_color:
            # Use sku's own style/color as fallback
            attrs = sku_attrs.get(sku, {})
            gb_style_color[gb] = (attrs.get("Style",""), attrs.get("Color",""))

    return sku_attrs, sku_to_gb, sku_to_fr, sku_to_lt, sku_to_rt, sku_pallet, gb_style_color


def parse_plan_output(file_path):
    """
    Parse gated/ungated排产结果表.xlsx -> {PN: {date: value}}
    Filter PLAN_ITEM == OUTPUT, group by SKU + PLAN_DATE sum PLAN_VALUE
    """
    df = _read_excel_safe(file_path, sheet_name=0)
    # Expected columns: SKU, PLAN_DATE, PLAN_VALUE, PLAN_ITEM
    if "PLAN_ITEM" in df.columns:
        df = df[df["PLAN_ITEM"] == "OUTPUT"]
    if df.empty:
        return {}
    # Clean
    df["SKU"] = df["SKU"].astype(str).str.strip()
    df["PLAN_DATE_NORM"] = df["PLAN_DATE"].apply(_norm_date)
    df["PLAN_VALUE"] = pd.to_numeric(df["PLAN_VALUE"], errors="coerce").fillna(0)

    grouped = df.groupby(["SKU", "PLAN_DATE_NORM"])["PLAN_VALUE"].sum().reset_index()
    result = defaultdict(dict)
    for _, row in grouped.iterrows():
        sku = str(row["SKU"]).strip()
        if not sku or sku.lower() == "nan":
            continue
        date = row["PLAN_DATE_NORM"]
        if not date:
            continue
        val = float(row["PLAN_VALUE"])
        if val == 0:
            # Keep zero? In legacy read_sheet, only non-zero? But we keep zeros? Engine filters later
            # To match legacy, only keep if value is int/float, but we can keep all and engine will handle
            pass
        result[sku][date] = result[sku].get(date, 0) + val

    return dict(result)


def parse_fcst(fcst_main_path, fcst_detail_path):
    """
    Parse FCST主表 + FCST明细 -> {SKU: {date: value}}
    Logic validated:
    - main: ID, PN_CODE (SKU)
    - detail: MAIN_ID, ACTUALFIRSTDAYOFWEEK, ACTUALWEEKVALUE, ID
    - For each MAIN_ID group:
        skus = main[ID==MAIN_ID].PN_CODE list (order as appears)
        For each week (ACTUALFIRSTDAYOFWEEK):
            rows = detail[MAIN_ID==mid & ACTUALFIRSTDAYOFWEEK==week] sorted ID descending
            vals = rows.ACTUALWEEKVALUE list (len == len(skus))
            assign vals[i] to skus[i] in that sorted order
    """
    df_main = _read_excel_safe(fcst_main_path, sheet_name=0)
    df_detail = _read_excel_safe(fcst_detail_path, sheet_name=0)

    # Clean main: ensure PN_CODE exists
    df_main["PN_CODE"] = df_main["PN_CODE"].astype(str).str.strip()
    df_main = df_main[df_main["PN_CODE"].str.startswith("SK-")]

    # Group main by ID
    main_groups = df_main.groupby("ID")["PN_CODE"].apply(list).to_dict()

    # Prepare result
    fcst_dict = defaultdict(dict)

    # Group detail by MAIN_ID
    for mid, group in df_detail.groupby("MAIN_ID"):
        skus = main_groups.get(mid)
        if not skus:
            continue
        # Unique weeks
        # For each week
        for week_label, week_group in group.groupby("ACTUALFIRSTDAYOFWEEK"):
            # Normalize week label to YYYY-MM-DD
            norm_date = _norm_date(week_label)
            if not norm_date:
                continue
            # Sort rows by ID descending (critical for correct SKU assignment)
            week_sorted = week_group.sort_values("ID", ascending=False)
            vals = week_sorted["ACTUALWEEKVALUE"].tolist()
            # vals length should == len(skus), but if not, we try to handle
            # If vals length != skus length, it could be due to duplicate weeks? Actually per week, per MID we have exactly len(skus) rows
            # Pad if needed
            for i, sku in enumerate(skus):
                if i < len(vals):
                    v = vals[i]
                    try:
                        fv = float(v)
                    except:
                        fv = 0
                    if fv != 0:
                        # Accumulate if multiple entries for same sku+date (shouldn't happen, but sum)
                        fcst_dict[sku][norm_date] = fcst_dict[sku].get(norm_date, 0) + fv
                    else:
                        # Keep zero? For legacy, zero values were kept? In read_sheet, zero int is kept if present?
                        # We keep zero as explicit to preserve weeks, but engine will handle zeros
                        # To match legacy, we only store if value !=0? But we should store zero for completeness
                        # Let's store zero as well to preserve week existence, engine will aggregate
                        if norm_date not in fcst_dict[sku]:
                            fcst_dict[sku][norm_date] = fcst_dict[sku].get(norm_date, 0) + fv
                        # else keep existing
                # else no value

    return dict(fcst_dict)


def parse_ctb(file_path):
    """
    Parse CTB.xlsx -> ctb_sku, ctb_gb as {PN: {date: value}}
    CTB file has 2 sheets: ctb_sku_cum and ctb_gb_cum, already in matrix form
    Uses openpyxl directly for robustness (avoid pandas engine issues).
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    except Exception as e:
        raise ValueError(f"Failed to open CTB {os.path.basename(str(file_path))} with openpyxl: {e} – ensure it's valid .xlsx")

    ctb_sku = {}
    ctb_gb = {}

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        # Read header row
        try:
            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        except StopIteration:
            continue
        if not header_row:
            continue
        # Header is first row, first col is PN/SKU, rest are dates
        headers = [str(h).strip() if h is not None else "" for h in header_row]
        # Determine which dict to use based on sheet name
        is_sku_sheet = "sku" in sheet_name.lower() or "ctb_sku" in sheet_name.lower()

        # Iterate data rows
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            pn = _clean(row[0])
            if not pn:
                continue
            vals = {}
            for col_idx in range(1, len(headers)):
                if col_idx >= len(row):
                    break
                col_name = headers[col_idx]
                if not col_name:
                    continue
                norm_date = _norm_date(col_name)
                if not norm_date:
                    continue
                v = row[col_idx]
                try:
                    fv = float(v)
                    if pd.isna(fv):
                        continue
                except:
                    continue
                vals[norm_date] = fv
            if vals:
                if is_sku_sheet:
                    ctb_sku[pn] = vals
                else:
                    # Decide based on header first col name
                    first_col_name = headers[0].upper() if headers[0] else ""
                    if "SKU" in first_col_name:
                        ctb_sku[pn] = vals
                    else:
                        ctb_gb[pn] = vals
        # If sheet name explicitly indicates gb, ensure it goes to gb
        if "gb" in sheet_name.lower() and not is_sku_sheet:
            # Already handled, but ensure
            pass

    wb.close()

    # Fallback: if we didn't detect sku vs gb correctly, try to split by PN prefix or content
    # For now, if ctb_gb empty and ctb_sku has both, we keep as is
    # The original logic used sheet name to decide, we do similar:
    # Actually we already used is_sku_sheet logic, but we need to ensure correct assignment
    # Let's re-evaluate: if sheet name contains "sku", it's sku, else gb
    # We already did that

    return ctb_sku, ctb_gb


def _safe_parse_wrapper(parse_fn, file_path, label):
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"{label} file not found: {file_path}")
        sz = os.path.getsize(file_path)
        if sz == 0:
            raise ValueError(f"{label} file {os.path.basename(str(file_path))} is empty (0 bytes) – upload may have failed")
        return parse_fn(file_path)
    except Exception as e:
        # Enhance error with file info
        import traceback
        tb = traceback.format_exc()
        raise ValueError(f"Failed to parse {label} ({os.path.basename(str(file_path))}, {os.path.getsize(file_path) if os.path.exists(file_path) else 'missing'} bytes): {e}\n{tb}") from e

def parse_snapshot_folder(file_paths):
    """
    file_paths: dict with keys:
      item, bom, gated, ungated, fcst_main, fcst_detail, ctb
    values are file paths (str or Path)
    Returns dict compatible with engine's intermediate:
      sku_attrs, sku_to_gb, sku_to_fr, sku_to_lt, sku_to_rt, sku_pallet, gb_style_color,
      gated, ungated, fcst, ctb, ctb_gb
    """
    # Item + BOM -> sku master
    item_path = file_paths.get("item")
    bom_path = file_paths.get("bom")
    if not item_path or not bom_path:
        raise ValueError("Missing item snapshot or bom snapshot")

    try:
        sku_attrs, sku_to_gb, sku_to_fr, sku_to_lt, sku_to_rt, sku_pallet, gb_style_color = build_sku_master(item_path, bom_path)
    except Exception as e:
        # Try to provide which file failed
        raise ValueError(f"Failed building SKU master from item={os.path.basename(str(item_path))} bom={os.path.basename(str(bom_path))}: {e}") from e

    # Gated / Ungated
    gated = {}
    ungated = {}
    if "gated" in file_paths:
        gated = _safe_parse_wrapper(parse_plan_output, file_paths["gated"], "Gated排产")
    if "ungated" in file_paths:
        ungated = _safe_parse_wrapper(parse_plan_output, file_paths["ungated"], "Ungated排产")

    # FCST
    fcst = {}
    if "fcst_main" in file_paths and "fcst_detail" in file_paths:
        try:
            fcst = parse_fcst(file_paths["fcst_main"], file_paths["fcst_detail"])
        except Exception as e:
            raise ValueError(f"Failed parsing FCST main={os.path.basename(str(file_paths['fcst_main']))} detail={os.path.basename(str(file_paths['fcst_detail']))}: {e}") from e

    # CTB
    ctb_sku = {}
    ctb_gb = {}
    if "ctb" in file_paths:
        ctb_sku, ctb_gb = _safe_parse_wrapper(parse_ctb, file_paths["ctb"], "CTB")

    return {
        "sku_attrs": sku_attrs,
        "sku_to_gb": sku_to_gb,
        "sku_to_fr": sku_to_fr,
        "sku_to_lt": sku_to_lt,
        "sku_to_rt": sku_to_rt,
        "sku_pallet": sku_pallet,
        "gb_style_color": gb_style_color,
        "gated": gated,
        "ungated": ungated,
        "fcst": fcst,
        "ctb": ctb_sku,
        "ctb_gb": ctb_gb,
    }


def detect_snapshot_files(uploaded_files):
    """
    Given list of uploaded file paths, detect which is which by filename keyword
    Returns dict mapping keyword -> path
    """
    mapping = {}
    for fp in uploaded_files:
        name = os.path.basename(str(fp)).lower()
        # Item
        if "料号快照" in name or "item" in name or "料号" in name:
            # Prefer filled
            if "filled" in name or "filled" in str(fp).lower():
                mapping["item_filled"] = str(fp)
            if "item" not in mapping or "filled" in name:
                # Keep filled as primary
                pass
            # Use filled as item if exists
            mapping["item"] = str(fp) if "item" not in mapping else mapping["item"]
            # If filled exists, override
            if "filled" in name:
                mapping["item"] = str(fp)
        if "bom" in name:
            mapping["bom"] = str(fp)
        if "gated" in name and "ungated" not in name and ("排产" in name or "plan" in name or "output" in name or "gated" in name):
            # Distinguish gated vs ungated
            if "ungated" in name:
                mapping["ungated"] = str(fp)
            else:
                # Check if filename contains gated but not ungated
                if "gated" in name and "ungated" not in name:
                    # Could be gated
                    # If name has "gated" and not "ungated", assign gated
                    # Need to avoid overwriting if both contain gated
                    if "gated" in mapping and "ungated" not in mapping:
                        # already have gated, this might be ungated if name contains ungated?
                        pass
                    if "ungated" not in name:
                        mapping["gated"] = str(fp)
        if "ungated" in name:
            mapping["ungated"] = str(fp)
        if "fcst" in name and "主表" in name:
            mapping["fcst_main"] = str(fp)
        if "fcst" in name and "明细" in name:
            mapping["fcst_detail"] = str(fp)
        if "ctb" in name:
            mapping["ctb"] = str(fp)

    # Fallback: if we have item_filled, use it as item
    if "item_filled" in mapping:
        mapping["item"] = mapping["item_filled"]

    # Heuristics for gated/ungated when filenames are exactly "gated排产结果表.xlsx"
    # Must check ungated first because "ungated" contains "gated" substring
    for fp in uploaded_files:
        base = os.path.basename(str(fp)).lower()
        # Ungated first
        if "ungated排产" in base or base == "ungated排产结果表.xlsx":
            mapping["ungated"] = str(fp)
        elif "gated排产" in base or base == "gated排产结果表.xlsx":
            # Ensure not ungated (already handled)
            if "ungated" not in base:
                mapping["gated"] = str(fp)
            else:
                # If base is ungated but also contains gated排产, it was already set as ungated above
                # To be safe, if gated not yet set and base contains gated but not ungated, set gated
                pass
        # Fallback English simple
        if "ungated" in base and "gated" in base:
            # This is ungated file (since ungated contains gated)
            mapping["ungated"] = str(fp)
        elif "gated" in base and "ungated" not in base:
            # Only gated
            if "gated" not in mapping or "ungated" in mapping.get("gated","").lower():
                mapping["gated"] = str(fp)

    # Final pass: ensure gated not pointing to ungated file
    if "gated" in mapping and "ungated" in mapping:
        if mapping["gated"] == mapping["ungated"]:
            # Duplicate, try to find distinct
            gated_candidates = [f for f in uploaded_files if "gated" in os.path.basename(f).lower() and "ungated" not in os.path.basename(f).lower()]
            if gated_candidates:
                mapping["gated"] = str(gated_candidates[0])

    return mapping
