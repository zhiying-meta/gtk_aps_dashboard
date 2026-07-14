"""
Process uploaded xlsx files → report data
"""
import openpyxl, io, csv
from datetime import datetime, timedelta
from collections import defaultdict

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

def read_uploaded_xlsx(fp):
    """Read single xlsx with 6 sheets → dict of data"""
    wb = openpyxl.load_workbook(fp, data_only=True)
    sheet_names = [s.title for s in wb.worksheets]
    result = {}
    # Map known sheet names
    for sn in sheet_names:
        ws = wb[sn]
        if sn == "sku_master":
            result["sku"] = ws  # special: read separately
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

def _to_saturday_label(ds):
    """Map any date string to the Saturday of its ISO week (Mon~Sun)"""
    try: dt = datetime.strptime(ds, "%Y-%m-%d")
    except: return ds
    dow = dt.weekday()
    sat = dt + timedelta(days=5 - dow)  # Mon(0)→Sat(5), Sun(6)→Sat(-1)
    return sat.strftime("%Y-%m-%d")

def aggregate_cumulative(daily, cut_day):
    """Compute cumulative sum up to each cut_day.
    Generates ALL week labels between first and last data point,
    carrying forward the cumulative value even for weeks with no new data.
    """
    dow_map = {"Monday":0,"Tuesday":1,"Wednesday":2,"Thursday":3,"Friday":4,"Saturday":5,"Sunday":6}
    td = dow_map.get(cut_day, 5)
    date_list = sorted(daily.keys())
    if not date_list:
        return {}

    # Determine week range: from first data point's week to last data point's week
    def date_to_week_label(ds):
        dt = datetime.strptime(ds, "%Y-%m-%d")
        cd = dt.weekday()
        diff = (td - cd) % 7
        week_end = dt + timedelta(days=diff)
        return _to_saturday_label(week_end.strftime("%Y-%m-%d"))

    first_dt = datetime.strptime(date_list[0], "%Y-%m-%d")
    last_dt = datetime.strptime(date_list[-1], "%Y-%m-%d")

    first_wl = date_to_week_label(date_list[0])
    last_wl = date_to_week_label(date_list[-1])

    # Build week label → list of dates in that week
    weeks = defaultdict(list)
    for ds in date_list:
        wl = date_to_week_label(ds)
        weeks[wl].append(ds)

    # Generate all week labels from first to last
    all_weeks = []
    cur = datetime.strptime(first_wl, "%Y-%m-%d")
    end = datetime.strptime(last_wl, "%Y-%m-%d")
    while cur <= end:
        all_weeks.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=7)

    result = {}
    running = 0.0
    for wl in all_weeks:
        for ds in weeks.get(wl, []):
            running += daily.get(ds, 0)
        if running > 0:
            result[wl] = round(running, 0)
    return result

def extract_weekly_cum(daily, cut_day):
    """For already-cumulative data (CTB): take the value at each week end.
    Weeks labeled by Saturday."""
    dow_map = {"Monday":0,"Tuesday":1,"Wednesday":2,"Thursday":3,"Friday":4,"Saturday":5,"Sunday":6}
    td = dow_map.get(cut_day, 5)
    date_list = sorted(daily.keys())
    weeks = defaultdict(list)
    for ds in date_list:
        try: dt = datetime.strptime(ds, "%Y-%m-%d")
        except: continue
        cd = dt.weekday()
        diff = (td - cd) % 7
        week_end = dt + timedelta(days=diff)
        sat_label = _to_saturday_label(week_end.strftime("%Y-%m-%d"))
        weeks[sat_label].append(ds)
    result = {}
    for wl in sorted(weeks.keys()):
        dl = weeks[wl]
        dl.sort()
        if dl and daily.get(dl[-1]):
            result[wl] = round(daily[dl[-1]], 0)
    return result

def process_uploaded_data(file_map, config):
    cfg = {
        "exf_cut": config.get("exf_cut", "Saturday"),
        "etd_cut": config.get("etd_cut", "Saturday"),
        "output_cut": config.get("output_cut", "Wednesday"),
        "gb_cut": config.get("gb_cut", "Tuesday"),
    }

    # Read single xlsx
    fp = file_map.get("main") or file_map.get("sku") or next(iter(file_map.values()), None)
    if not fp:
        raise ValueError("No file uploaded")
    
    sheets = read_uploaded_xlsx(fp)
    
    # Read master from the workbook directly
    wb = openpyxl.load_workbook(fp, data_only=True)
    sku_ws = wb["sku_master"] if "sku_master" in [s.title for s in wb.worksheets] else wb.active
    sku_attrs, sku_to_gb, sku_pallet, gb_style_color = read_sku_master_from_ws(sku_ws)
    all_skus = set(sku_attrs.keys())

    plan_gated = sheets.get("gated", {})
    plan_ungated = sheets.get("ungated", {})
    plan_fcst = sheets.get("fcst", {})
    ctb_sku = sheets.get("ctb", {})
    ctb_gb = sheets.get("ctb_gb", {})

    # Only process SKUs from master that have data
    all_pns = set(sku_attrs.keys())
    for d in [plan_gated, plan_ungated, plan_fcst, ctb_sku]:
        all_pns.update(k for k in d if k in sku_attrs)
    all_skus = sorted(s for s in all_pns if s in sku_attrs)

    # Aggregate
    agg = {}
    for label, data, cut in [("GATED_ETD", plan_gated, cfg["etd_cut"]),
                              ("UNGATED_ETD", plan_ungated, cfg["etd_cut"]),
                              ("GATED_PACK", plan_gated, cfg["output_cut"]),
                              ("UNGATED_PACK", plan_ungated, cfg["output_cut"]),
                              ("FCST", plan_fcst, cfg["exf_cut"])]:
        agg[label] = {}
        for sku in all_skus:
            daily = data.get(sku, {})
            agg[label][sku] = aggregate_cumulative(daily, cut)

    # Collect all weeks
    all_weeks = set()
    for a in agg.values():
        for v in a.values():
            all_weeks.update(v.keys())
    # Also from CTB
    for sku in all_skus:
        if sku in ctb_sku:
            w = extract_weekly_cum(ctb_sku[sku], cfg["etd_cut"])
            all_weeks.update(w.keys())
    all_weeks = sorted(all_weeks)

    def fill(vals): return {w: vals.get(w, None) for w in all_weeks}
    def diff(b, s):
        ks = set(list(b.keys()) + list(s.keys()))
        return {k: ((b.get(k) or 0) - (s.get(k) or 0)) for k in ks}

    rows = []
    for sku in all_skus:
        a = sku_attrs.get(sku, {})
        style, color, usage = a.get("Style",""), a.get("Color",""), a.get("Usage","")
        gb = sku_to_gb.get(sku, "")
        pallet = sku_pallet.get(sku, 864)

        ue = agg["UNGATED_ETD"].get(sku, {})
        up = agg["UNGATED_PACK"].get(sku, {})
        ge = agg["GATED_ETD"].get(sku, {})
        gp = agg["GATED_PACK"].get(sku, {})
        exf = agg["FCST"].get(sku, {})

        ue = {w: (int(v)//pallet)*pallet for w,v in ue.items() if v and v > 0}
        ge = {w: (int(v)//pallet)*pallet for w,v in ge.items() if v and v > 0}

        ctb = {}
        if sku in ctb_sku:
            ctb = extract_weekly_cum(ctb_sku[sku], cfg["etd_cut"])

        base = {"PN": sku, "Usage": usage, "Style": style, "Color": color,
                "GB_PN": gb, "Pallet_Qty": pallet, "_dim": "FG"}
        rows.append({**base, "Version-Type": "ExF", "Version-Detail": "", "Cut Day": cfg["exf_cut"], **fill(exf)})
        rows.append({**base, "Version-Type": "Ungated", "Version-Detail": "ETD", "Cut Day": cfg["etd_cut"], **fill(ue)})
        rows.append({**base, "Version-Type": "Ungated", "Version-Detail": "ETD vs ExF", "Cut Day": cfg["etd_cut"], **fill(diff(ue, exf))})
        rows.append({**base, "Version-Type": "Ungated", "Version-Detail": "Packout", "Cut Day": cfg["output_cut"], **fill(up)})
        rows.append({**base, "Version-Type": "Ungated", "Version-Detail": "Packout vs ExF", "Cut Day": cfg["output_cut"], **fill(diff(up, exf))})
        rows.append({**base, "Version-Type": "Gated", "Version-Detail": "ETD", "Cut Day": cfg["etd_cut"], **fill(ge)})
        rows.append({**base, "Version-Type": "Gated", "Version-Detail": "ETD vs ExF", "Cut Day": cfg["etd_cut"], **fill(diff(ge, exf))})
        rows.append({**base, "Version-Type": "Gated", "Version-Detail": "Packout", "Cut Day": cfg["output_cut"], **fill(gp)})
        rows.append({**base, "Version-Type": "Gated", "Version-Detail": "Packout vs ExF", "Cut Day": cfg["output_cut"], **fill(diff(gp, exf))})
        rows.append({**base, "Version-Type": "CTB", "Version-Detail": "", "Cut Day": "", **fill(ctb)})

    # GB dimension
    gb_groups = defaultdict(list)
    for sku in all_skus:
        g = sku_to_gb.get(sku, "")
        if g: gb_groups[g].append(sku)

    sku_data = {(r["PN"], r["Version-Type"], r["Version-Detail"]): {w: r.get(w) for w in all_weeks} for r in rows}

    for gb, skus in gb_groups.items():
        sc = gb_style_color.get(gb, ("",""))
        # GB Usage = take first SKU's Usage
        gb_usage = ""
        for s in skus:
            u = sku_attrs.get(s, {}).get("Usage", "")
            if u: gb_usage = u; break
        base = {"PN": gb, "Usage": gb_usage, "Style": sc[0], "Color": sc[1],
                "GB_PN": gb, "Pallet_Qty": 864, "_dim": "GB"}
        # GB: no ETD modules, only Packout
        for vt, vd in [("ExF",""),
                       ("Ungated","Packout"), ("Ungated","Packout vs ExF"),
                       ("Gated","Packout"), ("Gated","Packout vs ExF"),
                       ("CTB","")]:
            if vt == "CTB":
                sc_key = sc
                if sc_key and sc_key in ctb_gb:
                    vals = {w: round(ctb_gb[sc_key].get(w,0),0) for w in all_weeks if ctb_gb[sc_key].get(w)}
                else:
                    vals = {}
                    for w in all_weeks:
                        s = sum(sku_data.get((s,"CTB",""),{}).get(w,0) or 0 for s in skus)
                        if s > 0: vals[w] = round(s,0)
            else:
                vals = {}
                for w in all_weeks:
                    s = sum(sku_data.get((s,vt,vd),{}).get(w,0) or 0 for s in skus)
                    if s > 0: vals[w] = round(s,0)
            cd = "" if vt == "CTB" else cfg["gb_cut"]
            rows.append({**base, "Version-Type": vt, "Version-Detail": vd, "Cut Day": cd, **fill(vals)})

    # Week labels
    wl = {}
    for w in all_weeks:
        try:
            dt = datetime.strptime(w, "%Y-%m-%d")
            wk = (dt.day - 1) // 7 + 1
            wl[w] = f"{dt.strftime('%b')} Wk{wk} ({dt.strftime('%b %d')})"
        except:
            wl[w] = w
    return {"rows": rows, "weeks": all_weeks, "week_labels": wl, "config": cfg}

def generate_excel(data):
    """Generate formatted xlsx from report data"""
    import openpyxl as xl
    from openpyxl.styles import Font as F, PatternFill as PF, Border as B, Side as S, Alignment as A

    rows, weeks = data["rows"], data["weeks"]
    wb = xl.Workbook()
    ws = wb.active
    ws.title = "Report"

    hf = F(name="微软雅黑", bold=True, color="FFFFFF", size=11)
    hfl = PF("solid", fgColor="1E293B")
    hb = B(left=S(style='thin'),right=S(style='thin'),top=S(style='thin'),bottom=S(style='thin'))
    cf = F(name="微软雅黑", size=10)
    cb = B(left=S(style='thin'),right=S(style='thin'),top=S(style='thin'),bottom=S(style='thin'))
    nf = '#,##0'
    fills = {"ExF": PF("solid", fgColor="F0F9FF"), "Ungated": PF("solid", fgColor="F0FDF4"),
             "Gated": PF("solid", fgColor="FFFBEB"), "CTB": PF("solid", fgColor="FAF5FF")}

    fixed = ["_dim","PN","Usage","Style","Color","Version-Type","Version-Detail","Cut Day","Pallet_Qty"]
    flabels = ["Dim","PN","Usage","Style","Color","Version-Type","Version-Detail","Cut Day","Pallet"]
    from datetime import datetime as dt2
    wlabels = []
    for w in weeks:
        try:
            d = dt2.strptime(w, "%Y-%m-%d")
            wk = (d.day - 1)//7 + 1
            wlabels.append(f"{d.strftime('%b')} Wk{wk} ({d.strftime('%b %d')})")
        except:
            wlabels.append(w)

    for ci, lab in enumerate(flabels + wlabels, 1):
        c = ws.cell(1, ci, lab)
        c.font = hf; c.fill = hfl; c.border = hb
        c.alignment = A(vertical='center', wrap_text=True)
    ws.row_dimensions[1].height = 28

    last_pn = None
    for ri, r in enumerate(rows, 2):
        vals = []
        for k in fixed:
            if k == "_dim": vals.append(r.get("_dim",""))
            elif k == "Pallet_Qty": vals.append(r.get("Pallet_Qty") or "")
            else: vals.append(str(r.get(k,"") or ""))
        for w in weeks:
            v = r.get(w)
            vals.append(v if v is not None else "")
        for ci, val in enumerate(vals, 1):
            cell = ws.cell(ri, ci, val)
            cell.font = cf; cell.border = cb
            cell.alignment = A(vertical='center')
            if ci > len(fixed) and isinstance(val, (int, float)):
                cell.number_format = nf
                cell.alignment = A(horizontal='right', vertical='center')
                if val > 0: cell.font = F(name="微软雅黑", size=10, color="059669")
                elif val < 0: cell.font = F(name="微软雅黑", size=10, color="DC2626")
        ft = fills.get(r.get("Version-Type"))
        if ft:
            for ci in range(1, len(fixed) + len(weeks) + 1):
                ws.cell(ri, ci).fill = ft
        is_new = r.get("PN") != last_pn
        if is_new and ri > 2:
            for ci in range(1, len(fixed) + len(weeks) + 1):
                c = ws.cell(ri, ci)
                c.border = B(left=S(style='thin'),right=S(style='thin'),
                              top=S(style='medium', color="94A3B8"), bottom=S(style='thin'))
        last_pn = r.get("PN")

    ws.freeze_panes = ws.cell(2, len(fixed) + 1)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
