"""Plan merge module: shared helper functions"""

def read_sheet(ws, key_col=None):
    """Read a worksheet → {PN: {date_str: value}}"""
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    if key_col is None:
        key_col = "PN" if "PN" in headers else ("SKU" if "SKU" in headers else headers[0])
    ki = headers.index(key_col) if key_col in headers else 0
    result = {}
    for r in range(2, ws.max_row + 1):
        pn = str(ws.cell(r, ki + 1).value or "").strip()
        if not pn: continue
        vals = {}
        for ci, h in enumerate(headers):
            if ci == ki: continue
            v = ws.cell(r, ci + 1).value
            h_str = str(h).strip() if h else ""
            if h_str and v is not None and isinstance(v, (int, float)):
                vals[h_str] = float(v)
        if vals:
            result[pn] = vals
    return result


def read_sku_master_from_ws(ws):
    """Read sku_master sheet → attributes dict"""
    headers = [str(ws.cell(1, c).value or "").strip() for c in range(1, ws.max_column + 1)]
    sku_attrs, sku_to_gb, sku_pallet, gb_style_color = {}, {}, {}, {}
    for r in range(2, ws.max_row + 1):
        row = {headers[ci]: ws.cell(r, ci + 1).value for ci in range(len(headers))}
        sku = str(row.get("SKU", "") or "").strip()
        if not sku: continue
        sku_attrs[sku] = {"Style": str(row.get("Style","") or ""),
                           "Color": str(row.get("Color","") or ""),
                           "Usage": str(row.get("Usage","") or "")}
        gb = str(row.get("GB_PN","") or "").strip()
        sku_to_gb[sku] = gb
        sku_pallet[sku] = int(row.get("Pallet_Qty", 864) or 864)
        if gb and row.get("Style") and row.get("Color"):
            gb_style_color[gb] = (str(row["Style"]), str(row["Color"]))
    return sku_attrs, sku_to_gb, sku_pallet, gb_style_color


def read_uploaded_xlsx(fp):
    """Read single xlsx with 6 sheets → dict of data"""
    import openpyxl
    wb = openpyxl.load_workbook(fp, data_only=True)
    sheet_names = [s.title for s in wb.worksheets]
    result = {}
    for sn in sheet_names:
        ws = wb[sn]
        if sn == "sku_master":
            result["sku"] = ws
        elif sn == "plan_output_gated":
            result["gated"] = read_sheet(ws)
        elif sn == "plan_output_ungated":
            result["ungated"] = read_sheet(ws)
        elif sn == "forecast":
            result["fcst"] = read_sheet(ws)
        elif sn in ("ctb_sku_cum", "ctb_cum"):
            result["ctb"] = read_sheet(ws, "SKU")
        elif sn in ("ctb_gb_cum", "ctb_gb"):
            result["ctb_gb"] = read_sheet(ws)
    return result
