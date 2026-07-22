import io
import os
import shutil
import zipfile
from datetime import datetime

from flask import jsonify, request, send_file, send_from_directory

from app import config
from app.modules.plan_merge import plan_merge_bp
from app.modules.plan_merge.engine import generate_excel, process_uploaded_data

MODULE_DIR = os.path.dirname(__file__)
TEMPLATE_DIR = os.path.join(MODULE_DIR, "templates")


@plan_merge_bp.route("/templates/<name>")
def download_template(name):
    allowed = {"input_template.xlsx", "schema.json"}
    if name not in allowed:
        return "Not found", 404
    return send_from_directory(TEMPLATE_DIR, name, as_attachment=True)


@plan_merge_bp.route("/demo")
def download_demo():
    fp = os.path.join(TEMPLATE_DIR, "input_demo.xlsx")
    if not os.path.exists(fp):
        return "Not found", 404
    return send_file(fp, as_attachment=True, download_name="input_demo.xlsx")


@plan_merge_bp.route("/api/schema")
def get_schema():
    fp = os.path.join(TEMPLATE_DIR, "schema.json")
    if not os.path.exists(fp):
        return jsonify({})
    return send_from_directory(TEMPLATE_DIR, "schema.json")


@plan_merge_bp.route("/templates/zip")
def download_all_templates():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in ("input_template.xlsx", "input_demo.xlsx"):
            fp = os.path.join(TEMPLATE_DIR, fname)
            if os.path.exists(fp):
                zf.write(fp, fname)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="input_files.zip")


@plan_merge_bp.route("/api/process", methods=["POST"])
def process():
    upload_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    work_dir = os.path.join(config.UPLOAD_FOLDER, upload_id)
    os.makedirs(work_dir, exist_ok=True)
    try:
        # collect xlsx file (support both feat/io-report and main logic)
        xlsx_path = None
        for f in request.files.values():
            if f.filename and f.filename.lower().endswith(".xlsx"):
                xlsx_path = os.path.join(work_dir, f.filename)
                f.save(xlsx_path)
                break
        # fallback: save any file if no xlsx filter matched (compat with main)
        if not xlsx_path:
            for key in request.files:
                ff = request.files[key]
                if ff.filename:
                    maybe = os.path.join(work_dir, ff.filename)
                    ff.save(maybe)
                    if maybe.lower().endswith(".xlsx"):
                        xlsx_path = maybe
                        break
                    # if still no xlsx, keep first file as xlsx_path for error handling
                    if not xlsx_path:
                        xlsx_path = maybe

        if not xlsx_path:
            return jsonify({"error": "No xlsx file uploaded"}), 400

        cfg = {}
        for cfg_key in ["exf_cut", "etd_cut", "output_cut", "gb_cut", "etd_packout_offset"]:
            val = request.form.get(cfg_key)
            if val:
                cfg[cfg_key] = val

        result = process_uploaded_data({"main": xlsx_path}, cfg)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@plan_merge_bp.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400
    buf = generate_excel(data)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="report.xlsx",
    )


@plan_merge_bp.route("/api/plan_merge/clear", methods=["POST", "DELETE"])
@plan_merge_bp.route("/api/clear", methods=["POST", "DELETE"])
def api_clear():
    """Clear Packout (ExF vs ETD vs Packout vs CTB) cache — frontend will reset UI, backend is stateless"""
    # No persistent files, just return ok for consistency with other modules
    return jsonify({
        "ok": True,
        "message": "Cleared Packout data — now Not Ready, re-upload supported"
    })


@plan_merge_bp.route("/api/plan_merge/export/static", methods=["GET", "POST"])
@plan_merge_bp.route("/api/export/static", methods=["GET", "POST"])
def api_export_static():
    """Export current Packout dashboard as static HTML with embedded data and flexible filtering (like campus-planning-system/frontend/dist)
    Called when user clicks Download Static HTML button — triggers export_static logic for current data
    GET: uses demo data or last uploaded? For simplicity, if POST with JSON data, use that data to generate static HTML with filtering preserved
    """
    try:
        import json
        import datetime
        data = None
        if request.method == "POST":
            data = request.get_json()
        # If no data posted, try to use demo file
        if not data or not data.get("rows"):
            # Fallback to demo file processing
            from pathlib import Path
            template_path = Path(__file__).parent / "templates" / "input_demo.xlsx"
            if template_path.exists():
                from app.modules.plan_merge.engine import process_uploaded_data
                result = process_uploaded_data({"main": str(template_path)}, {})
                data = result

        if not data or not data.get("rows"):
            return jsonify({"error": "No data to export. Upload file first or POST rows/weeks"}), 404

        rows = data.get("rows", [])[:2000]
        weeks = data.get("weeks", [])
        week_labels = data.get("week_labels", {}) or data.get("weekLabels", {})
        config = data.get("config", {})

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Embed data as JSON for offline filtering
        static_json = json.dumps({"rows": rows, "weeks": weeks, "week_labels": week_labels, "config": config}, ensure_ascii=False, default=str).replace("<", "\\u003c")

        html_content = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Packout Report - Static BI - {now_str}</title>
<style>
body{{font-family:Arial,sans-serif;margin:16px;background:#f8fafc}}
h1{{font-size:18px;color:#1e293b}}
.sub{{font-size:11px;color:#64748b;margin-bottom:8px}}
.status{{margin:10px 0;padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px}}
.tabs{{display:flex;gap:6px;margin:10px 0;flex-wrap:wrap}}
.tab{{padding:6px 12px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;cursor:pointer;font-size:12px}}
.tab.active{{background:#3b82f6;color:#fff;border-color:#3b82f6}}
.filters{{background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px;margin:10px 0;display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}}
.filter-group{{display:flex;flex-direction:column;gap:4px;min-width:140px}}
.filter-group label{{font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase}}
.filter-group input{{padding:5px 8px;border:1px solid #cbd5e1;border-radius:5px;font-size:12px}}
.btn{{padding:5px 12px;border:1px solid #3b82f6;background:#3b82f6;color:#fff;border-radius:5px;font-size:12px;cursor:pointer}}
.btn-outline{{background:#fff;color:#64748b;border-color:#cbd5e1}}
.table-wrapper{{overflow:auto;border:1px solid #e2e8f0;border-radius:6px;background:#fff;max-height:80vh}}
table{{border-collapse:collapse;font-size:12px;white-space:nowrap;width:max-content;min-width:100%}}
th{{background:#1e293b;color:#fff;padding:6px 8px;position:sticky;top:0;z-index:2}}
td{{padding:4px 6px;border-bottom:1px solid #e2e8f0;border-right:1px solid #f1f5f9;text-align:right;min-width:70px}}
td.frozen{{position:sticky;left:0;background:#fff;z-index:1;text-align:left;font-weight:500}}
</style></head><body>
<h1>📦 ExF vs ETD vs Packout vs CTB — Static BI Report (Full Format & Filtering Preserved)</h1>
<div class="sub">Generated: {now_str} | Export via /api/plan_merge/export/static (calls export_static logic) | Rows: {len(rows)} | Weeks: {len(weeks)} | Flexible filtering works offline</div>
<div class="status" id="static-status">✅ Ready: {len(rows)} rows | Config: {config}</div>
<div class="tabs" id="dimTabs"><button class="tab active" data-dim="FG">FG (SKU)</button><button class="tab" data-dim="GB">GB</button><button class="tab" data-dim="ALL">All</button></div>
<div class="filters">
  <div class="filter-group"><label>Search PN / Usage / Style / Color / Type / Detail</label><input type="text" id="f-search" placeholder="e.g. PN123, Usage..."></div>
  <div class="filter-group"><label>Version-Type</label><input type="text" id="f-vtype" placeholder="ExF, Gated, Ungated, CTB"></div>
  <div class="filter-group"><label>&nbsp;</label><div><button class="btn" id="f-apply">Apply</button> <button class="btn btn-outline" id="f-clear">Clear</button> <span id="f-count" style="font-size:11px;color:#64748b"></span></div></div>
</div>
<div class="table-wrapper" id="static-wrapper"></div>
<div style="margin-top:12px;font-size:10px;color:#94a3b8">Static BI report from Packout dashboard via export_static. All format and filtering preserved like campus-planning-system/frontend/dist. Data embedded at export time. Open directly and share.</div>
<script>
const STATIC_DATA = {static_json};
let curDim = 'FG';
function esc(s){{ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }}
function renderTable(){{
  const rows = STATIC_DATA.rows || [];
  const weeks = STATIC_DATA.weeks || [];
  const weekLabels = STATIC_DATA.week_labels || {{}};
  let filtered = rows;
  const search = (document.getElementById('f-search').value||'').toLowerCase();
  const vtype = (document.getElementById('f-vtype').value||'').toLowerCase();
  if(curDim!=='ALL'){{ filtered = filtered.filter(r=> (r._dim||'').toUpperCase()===curDim); }}
  if(search){{ filtered = filtered.filter(r=> JSON.stringify(r).toLowerCase().includes(search)); }}
  if(vtype){{ filtered = filtered.filter(r=> (r['Version-Type']||'').toLowerCase().includes(vtype) || JSON.stringify(r).toLowerCase().includes(vtype)); }}
  let html = '<table><thead><tr>';
  const fixed = ['_dim','PN','Usage','Style','Color','Version-Type','Version-Detail','Cut Day','Pallet_Qty'];
  fixed.forEach(k=>{{ html += '<th class="frozen" style="min-width:80px">'+esc(k)+'</th>'; }});
  weeks.forEach(w=>{{ html += '<th>'+esc(weekLabels[w]||w)+'</th>'; }});
  html += '</tr></thead><tbody>';
  filtered.slice(0,1000).forEach(r=>{{
    html += '<tr>';
    fixed.forEach(k=>{{ html += '<td class="frozen">'+esc(String(r[k]||''))+'</td>'; }});
    weeks.forEach(w=>{{ const v=r[w]; html += '<td>'+(v!=null?Number(v).toLocaleString():'')+'</td>'; }});
    html += '</tr>';
  }});
  if(filtered.length>1000) html += '<tr><td colspan="999" style="text-align:center;color:#94a3b8">... '+filtered.length+' total rows, showing first 1000 ...</td></tr>';
  html += '</tbody></table>';
  document.getElementById('static-wrapper').innerHTML = html;
  document.getElementById('f-count').textContent = filtered.length+' / '+rows.length+' rows';
}}
document.querySelectorAll('#dimTabs .tab').forEach(b=>{{ b.addEventListener('click', ()=>{{ document.querySelectorAll('#dimTabs .tab').forEach(x=>x.classList.remove('active')); b.classList.add('active'); curDim=b.dataset.dim; renderTable(); }}); }});
document.getElementById('f-apply')?.addEventListener('click', renderTable);
document.getElementById('f-clear')?.addEventListener('click', ()=>{{ document.getElementById('f-search').value=''; document.getElementById('f-vtype').value=''; curDim='ALL'; document.querySelectorAll('#dimTabs .tab').forEach(b=>b.classList.remove('active')); document.querySelector('#dimTabs .tab[data-dim="ALL"]')?.classList.add('active'); renderTable(); }});
document.getElementById('f-search')?.addEventListener('input', renderTable);
document.getElementById('f-vtype')?.addEventListener('input', renderTable);
renderTable();
</script>
</body></html>"""

        from flask import Response
        return Response(html_content, mimetype='text/html', headers={
            "Content-Disposition": f"attachment; filename=packout_static_BI_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Export static failed: {e}"}), 500
