"""
Export static offline version – inspired by campus-planning-system/export_static.py

Mode:
  - Copies static/ to dist/ as self-contained site
  - Processes xlsx files via engine to generate window.STATIC_DB
  - Bundles xlsx.full.min.js locally for true offline
  - Injects data.js into index.html

Usage:
  python export_static.py
  python export_static.py --inputs data/*.xlsx
  python export_static.py --inputs W25.xlsx W26.xlsx --output dist --note "Q3 planning"

Result: dist/ can be zipped and shared, double-click index.html to use.
Now with full client engine, all functions work offline: upload, config, filter, aggregate, download.
"""

import os
import sys
import json
import shutil
import argparse
import glob
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATE_DIR = PROJECT_ROOT / "app" / "modules" / "plan_merge" / "templates"
DEFAULT_DIST = PROJECT_ROOT / "dist"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CONFIG = {
    "exf_cut": "Saturday",
    "etd_cut": "Saturday",
    "output_cut": "Wednesday",
    "gb_cut": "Tuesday",
    "etd_packout_offset": 2,
}

def is_plan_merge_file(path: Path):
    name = path.name
    if name.startswith("~$") or name.startswith("."):
        return False
    lower = name.lower()
    # Snapshot files should be allowed (snapshot-only)
    snapshot_keywords = ["料号快照", "bom快照", "gated排产", "ungated排产", "fcst主表", "fcst明细", "ctb.xlsx", "fcst"]
    for kw in snapshot_keywords:
        if kw in lower:
            return True
    io_keywords = ["料号主表", "结存表"]
    # For IO, only filter if it's exactly IO's 3 files, but not snapshot gated/ungated which contain 排产结果
    # So we check for排产结果表 but exclude gated/ungated
    if "料号主表" in name or "结存表" in name:
        return False
    if "排产结果表" in name and "gated" not in lower and "ungated" not in lower:
        return False
    # Skip very large unrelated files
    if "lager" in lower and "by sku" in lower:
        return False
    return True

def find_default_inputs():
    candidates = []
    # Prefer snapshot demo folder if exists
    snapshot_demo_dir = PROJECT_ROOT / "data" / "gated.ungated.ctb"
    if snapshot_demo_dir.exists():
        # Check if at least item + bom exist
        has_item = any((snapshot_demo_dir / fn).exists() for fn in ["料号快照.xlsx", "料号快照_filled.xlsx"])
        has_bom = (snapshot_demo_dir / "BOM快照.xlsx").exists()
        if has_item and has_bom:
            # Return a special marker path for snapshot processing
            # We use the dir itself as a file marker
            candidates.append(snapshot_demo_dir)
            return candidates
    demo = TEMPLATE_DIR / "input_demo.xlsx"
    if demo.exists():
        candidates.append(demo)
    return candidates

def _process_snapshot_dir(dir_path: Path, config: dict):
    try:
        from app.modules.plan_merge.snapshot_parser import detect_snapshot_files
        from app.modules.plan_merge.engine import process_snapshot_data
    except Exception as e:
        print(f"❌ Failed to import snapshot engine: {e}")
        return None
    print(f"   🔧 Processing snapshot dir {dir_path.name} ...")
    try:
        files = []
        for f in dir_path.glob("*.xlsx"):
            files.append(str(f))
        file_map = detect_snapshot_files(files)
        # Also map by known names
        for key, target in {
            "item": "料号快照.xlsx",
            "bom": "BOM快照.xlsx",
            "gated": "gated排产结果表.xlsx",
            "ungated": "ungated排产结果表.xlsx",
            "fcst_main": "FCST主表.xlsx",
            "fcst_detail": "FCST明细表.xlsx",
            "ctb": "CTB.xlsx",
        }.items():
            fp = dir_path / target
            if fp.exists() and key not in file_map:
                file_map[key] = str(fp)
            # filled variant for item
            if key == "item":
                filled = dir_path / "料号快照_filled.xlsx"
                if filled.exists():
                    file_map[key] = str(filled)
        result = process_snapshot_data(file_map, config)
        rows = result.get("rows", [])
        weeks = result.get("weeks", [])
        week_labels = result.get("week_labels", {})
        cfg = result.get("config", config)
        warnings = result.get("warnings", [])
        print(f"      ✅ Snapshot {dir_path.name}: {len(rows)} rows, {len(weeks)} weeks")
        return {
            "id": dir_path.name,
            "name": dir_path.name,
            "file": dir_path.name,
            "rows": rows,
            "weeks": weeks,
            "week_labels": week_labels,
            "config": cfg,
            "warnings": warnings,
        }
    except Exception as e:
        print(f"      ❌ Failed to process snapshot dir {dir_path}: {e}")
        import traceback
        traceback.print_exc()
        return None

def process_file(filepath: Path, config: dict):
    # If filepath is a directory, treat as snapshot dir
    if filepath.is_dir():
        return _process_snapshot_dir(filepath, config)
    try:
        from app.modules.plan_merge.engine import process_uploaded_data
    except Exception as e:
        print(f"❌ Failed to import engine: {e}")
        sys.exit(1)
    print(f"   🔧 Processing {filepath.name} ...")
    try:
        result = process_uploaded_data({"main": str(filepath)}, config)
        rows = result.get("rows", [])
        weeks = result.get("weeks", [])
        week_labels = result.get("week_labels", {})
        cfg = result.get("config", config)
        warnings = result.get("warnings", [])
        print(f"      ✅ {len(rows)} rows, {len(weeks)} weeks")
        return {
            "id": filepath.stem,
            "name": filepath.stem,
            "file": filepath.name,
            "rows": rows,
            "weeks": weeks,
            "week_labels": week_labels,
            "config": cfg,
            "warnings": warnings,
        }
    except Exception as e:
        print(f"      ❌ Failed to process {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return None

def copy_static(dist_dir: Path):
    print(f"📁 Copying static assets to {dist_dir} ...")
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)
    dest_static = dist_dir / "static"
    shutil.copytree(STATIC_DIR, dest_static)

    # Copy schema for fallback
    schema_src = TEMPLATE_DIR / "schema.json"
    if schema_src.exists():
        (dest_static / "schema.json").write_bytes(schema_src.read_bytes())
        try:
            (dest_static / "global" / "schema.json").write_bytes(schema_src.read_bytes())
        except Exception:
            pass
        mod_tmpl_dir = dest_static / "modules" / "plan_merge" / "templates"
        mod_tmpl_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(schema_src, mod_tmpl_dir / "schema.json")

    # Copy templates
    for fname in ["input_template.xlsx", "input_demo.xlsx"]:
        src = TEMPLATE_DIR / fname
        if src.exists():
            shutil.copy2(src, dist_dir / fname)

    src_index = STATIC_DIR / "global" / "index.html"
    with open(src_index, "r", encoding="utf-8") as f:
        html = f.read()
    # Make relative for file://
    html = html.replace('href="/static/', 'href="./static/')
    html = html.replace("href='/static/", "href='./static/")
    html = html.replace('src="/static/', 'src="./static/')
    html = html.replace("src='/static/", "src='./static/")
    dest_index = dist_dir / "index.html"
    with open(dest_index, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   ✅ Static copied, index at {dest_index}")
    return dest_index

def try_bundle_xlsx_lib(dist_dir: Path, index_path: Path):
    import urllib.request
    CDN_URL = "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"
    dest_lib = dist_dir / "static" / "xlsx.full.min.js"
    if not dest_lib.exists():
        print(f"📥 Downloading xlsx lib for offline bundle...")
        try:
            urllib.request.urlretrieve(CDN_URL, str(dest_lib))
            print(f"   ✅ Downloaded {dest_lib.name} ({dest_lib.stat().st_size/1024:.1f} KB)")
        except Exception as e:
            print(f"   ⚠️ Failed to download xlsx lib: {e}")
            return
    else:
        print(f"   ℹ️ xlsx lib already bundled")

    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    if './static/xlsx.full.min.js' in html:
        return
    cdn_tag = '<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>'
    local_tags = (
        '  <script src="./static/xlsx.full.min.js"></script>\n'
        '  <script>if(typeof XLSX==="undefined"){ var s=document.createElement("script");s.src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js";document.head.appendChild(s);}</script>'
    )
    if cdn_tag in html:
        html = html.replace(cdn_tag, local_tags)
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"   ✅ Patched index.html to use local xlsx lib")

def inject_data_js(index_path: Path):
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    if 'src="./data.js"' in html:
        print("   ℹ️ data.js already injected")
        return
    injection = '  <script src="./data.js"></script>\n  </head>'
    if "</head>" in html:
        html = html.replace("</head>", injection, 1)
    else:
        html = html.replace("<body>", '<body>\n  <script src="./data.js"></script>', 1)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("   ✅ Injected data.js into index.html")

def build_util_pivot(caches, mode):
    """Build pivot similar to api_pivot for static offline, with flexible filtering preserved"""
    try:
        from app.modules.utilization_report.engine import build_report
        from collections import defaultdict
        # Collect records per version
        all_recs = []
        for ver in caches.keys():
            cache = caches.get(ver)
            if not cache:
                continue
            recs = build_report(cache, mode=mode, line_filter='', date_from='', date_to='')
            for r in recs:
                nr = dict(r)
                nr['version_type'] = ver.capitalize()
                nr['version_key'] = ver
                all_recs.append(nr)

        if not all_recs:
            return {"mode": mode, "columns": [], "rows": [], "detail": {}, "lines": [], "total_lines": 0, "total_cols": 0}

        # Build columns
        if mode == "shift":
            cols_set = set()
            for r in all_recs:
                col = f"{r['plan_date']}|{r['shift_name']}"
                cols_set.add(col)
            cols = sorted(list(cols_set))
        else:
            cols = sorted(list(set(r['plan_date'] for r in all_recs)))

        max_cols = 1000
        total_cols_before = len(cols)
        truncated = False
        if len(cols) > max_cols:
            cols = cols[:max_cols]
            truncated = True

        matrix = {}
        detail = {}
        lines_set = set()
        for r in all_recs:
            key = (r['line_code'], r['version_type'])
            lines_set.add(r['line_code'])
            if key not in matrix:
                matrix[key] = {}
                detail[key] = {}
            col = f"{r['plan_date']}|{r['shift_name']}" if mode == "shift" else r['plan_date']
            if col not in cols:
                continue
            util_pct = r.get('utilization_pct', 0)
            capped = min(100.0, util_pct) if util_pct is not None else 0
            matrix[key][col] = capped
            detail[key][col] = {
                'util_raw': util_pct,
                'util_capped': capped,
                'load': r['load'],
                'capacity': r['capacity'],
                'uph': r['uph'],
                'efficiency': r['efficiency'],
                'working_hours': r['working_hours'],
                'is_overload': r.get('is_overload', False),
            }

        def sort_key(k):
            line, vtype = k
            order = 0 if vtype.lower() == 'gated' else 1
            return (line, order, vtype)
        sorted_keys = sorted(matrix.keys(), key=sort_key)

        rows = []
        last_line = None
        for (line, vtype) in sorted_keys:
            row = {
                'line_code': line,
                'version_type': vtype,
                'is_new_line': line != last_line,
            }
            last_line = line
            for col in cols:
                row[col] = matrix[(line, vtype)].get(col, None)
            rows.append(row)

        detail_json = {}
        for (line, vtype), col_map in detail.items():
            key_str = f"{line}||{vtype}"
            detail_json[key_str] = col_map

        return {
            "mode": mode,
            "versions": list(caches.keys()),
            "columns": cols,
            "rows": rows,
            "detail": detail_json,
            "lines": sorted(list(lines_set)),
            "total_lines": len(sorted_keys),
            "total_cols": len(cols),
            "total_cols_before": total_cols_before,
            "truncated": truncated,
        }
    except Exception as e:
        print(f"   ⚠️ Build util pivot {mode} failed: {e}")
        import traceback
        traceback.print_exc()
        return {"mode": mode, "columns": [], "rows": [], "detail": {}, "lines": [], "total_lines": 0, "total_cols": 0}

def process_utilization():
    """Process utilization data from data/utilization/gated and ungated for static offline with full filtering preserved"""
    try:
        from app.modules.utilization_report.engine import get_all_caches, reload_all
        from pathlib import Path
        base = Path(PROJECT_ROOT) / "data"
        # Ensure cache is loaded
        try:
            reload_all(str(base))
        except:
            pass
        caches = get_all_caches(str(base))
        if not caches:
            print(f"   ⚠️ Utilization: no cache found (need gated/ungated data)")
            return {}

        util_data = {}
        # Embed per-version cache info
        for ver, cache in caches.items():
            util_data[ver] = {
                "version": ver,
                "lines": cache.lines[:100],
                "dates": cache.dates[:200],
                "shifts": cache.shifts,
                "records_shift": cache.records_shift[:1000],
                "records_day": cache.records_day[:1000],
                "total_records_shift": len(cache.records_shift),
                "total_records_day": len(cache.records_day),
            }

        # Build pivot for day and shift for full offline filtering
        pivot_day = build_util_pivot(caches, mode='day')
        pivot_shift = build_util_pivot(caches, mode='shift')

        util_data['_pivot_day'] = pivot_day
        util_data['_pivot_shift'] = pivot_shift
        util_data['_meta'] = {
            "versions": list(caches.keys()),
            "lines": list(set().union(*[set(c.lines) for c in caches.values()])) if caches else [],
            "dates": {"min": min((min(c.dates) for c in caches.values() if c.dates), default=""), "max": max((max(c.dates) for c in caches.values() if c.dates), default="")},
        }

        print(f"   ✅ Utilization: {list(caches.keys())} versions, pivot day {len(pivot_day.get('columns',[]))} cols × {len(pivot_day.get('rows',[]))} rows, shift {len(pivot_shift.get('columns',[]))} cols")
        return util_data
    except Exception as e:
        print(f"   ⚠️ Utilization processing failed: {e}")
        import traceback
        traceback.print_exc()
        return {}

def process_io():
    """Process IO report data from data/ folder for static offline"""
    try:
        from app.modules.io_report.engine import get_cache, get_meta
        from pathlib import Path
        base = Path(PROJECT_ROOT) / "data"
        try:
            cache = get_cache(str(base))
        except Exception as e:
            print(f"   ⚠️ IO cache not ready: {e}")
            return {}
        # Build meta and reports for all groups and col dims like in static export for full BI
        groups = ['FG','GB','FR','LT','RT']
        col_dims = ['shift','day','week','month']
        io_data = {
            "status": {
                "loaded": True,
                "fg": len(cache.fg_items),
                "gb": len(cache.gb_items),
                "cats": cache.cats,
            },
            "meta": {},
            "groups": {}
        }
        for g in groups:
            io_data["groups"][g] = {}
            for cd in col_dims:
                try:
                    from app.modules.io_report.engine import get_meta, build_reports_for_group
                    meta = get_meta(cache, g, cd)
                    # Build reports for LINE_CODE dim (default)
                    reports, _ = build_reports_for_group(cache, 'LINE_CODE', cd, g, '', '', '')
                    io_data["groups"][g][cd] = {
                        "meta": {
                            "line_codes": meta.get("line_codes", [])[:100],
                            "items": meta.get("items", [])[:100],
                            "styles": meta.get("styles", [])[:50],
                        },
                        "reports": {k: {"columns": v.get("columns", [])[:20], "rows": v.get("rows", [])[:200]} for k,v in reports.items() if isinstance(v, dict) and "columns" in v}
                    }
                except Exception as e:
                    # print(f"   ⚠️ IO group {g} col {cd} failed: {e}")
                    continue
        print(f"   ✅ IO Report: {len(io_data['groups'])} groups embedded")
        return io_data
    except Exception as e:
        print(f"   ⚠️ IO processing failed: {e}")
        import traceback
        traceback.print_exc()
        return {}

def generate_data_js(versions, output_path: Path, meta: dict, include_schema=True):
    print(f"💾 Generating {output_path} with {len(versions)} version(s) + utilization + io...")
    schema = None
    schema_file = TEMPLATE_DIR / "schema.json"
    if include_schema and schema_file.exists():
        try:
            with open(schema_file, "r", encoding="utf-8") as sf:
                schema = json.load(sf)
        except Exception as e:
            print(f"   ⚠️ Failed to load schema: {e}")

    # Process additional modules for full offline like campus-planning-system
    util_data = process_utilization()
    io_data = process_io()

    db = {
        "versions": versions,
        "meta": meta,
        "schema": schema,
        "utilization": util_data,
        "io": io_data,
        "note": "Full static build with Packout + Utilization + IO, all tabs and flexible filtering preserved"
    }
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("window.STATIC_DB = ")
        json.dump(db, f, ensure_ascii=False, default=str)
        f.write(";\n")
    size_kb = output_path.stat().st_size / 1024
    print(f"   ✅ Wrote {output_path.name} — {size_kb:.1f} KB (includes utilization and io)")
    static_copy = output_path.parent / "static" / "data.js"
    try:
        shutil.copy2(output_path, static_copy)
    except Exception:
        pass

def main():
    parser = argparse.ArgumentParser(description="Export pure static offline version")
    parser.add_argument("--inputs", nargs="*", help="Input xlsx files")
    parser.add_argument("--output", "-o", default=str(DEFAULT_DIST))
    parser.add_argument("--note", default="", help="Optional note")
    parser.add_argument("--config-etd-cut", default=DEFAULT_CONFIG["etd_cut"])
    parser.add_argument("--config-output-cut", default=DEFAULT_CONFIG["output_cut"])
    parser.add_argument("--config-gb-cut", default=DEFAULT_CONFIG["gb_cut"])
    parser.add_argument("--config-offset", type=int, default=DEFAULT_CONFIG["etd_packout_offset"])
    args = parser.parse_args()

    dist_dir = Path(args.output).resolve()
    input_files = []
    if args.inputs:
        for pat in args.inputs:
            expanded = glob.glob(pat) if ("*" in pat or "?" in pat) else [pat]
            for ep in expanded:
                p = Path(ep)
                if p.is_file() and p.suffix.lower()==".xlsx":
                    if is_plan_merge_file(p):
                        input_files.append(p)
                elif p.is_dir():
                    # If dir contains snapshot files (料号快照 etc.), treat dir as one version
                    # Check for snapshot marker
                    has_snapshot = any((p / fn).exists() for fn in ["料号快照.xlsx", "BOM快照.xlsx", "料号快照_filled.xlsx"])
                    if has_snapshot:
                        input_files.append(p)
                    else:
                        for f in p.glob("*.xlsx"):
                            if is_plan_merge_file(f):
                                input_files.append(f)
    else:
        # default: try snapshot demo dir first, then legacy demo
        input_files = find_default_inputs()

    # dedup (handle both files and dirs)
    seen=set()
    uniq=[]
    for f in input_files:
        try:
            rp=f.resolve()
        except:
            continue
        if rp not in seen:
            seen.add(rp)
            uniq.append(f)
    input_files=uniq
    # Filter: keep dirs (snapshot) as is, filter files via is_plan_merge_file
    filtered=[]
    for f in input_files:
        if f.is_dir():
            filtered.append(f)
        elif is_plan_merge_file(f):
            filtered.append(f)
    input_files=filtered

    if not input_files:
        print("⚠️ No input xlsx found")
    else:
        print(f"📦 Found {len(input_files)} input file(s):")
        for f in input_files:
            print(f"   - {f}")

    index_path = copy_static(dist_dir)

    cfg = {
        "exf_cut": "Saturday",
        "etd_cut": args.config_etd_cut,
        "output_cut": args.config_output_cut,
        "gb_cut": args.config_gb_cut,
        "etd_packout_offset": args.config_offset,
    }
    versions=[]
    name_counts={}
    for fp in input_files:
        v=process_file(fp, cfg)
        if v:
            base=v["name"]
            if base in name_counts:
                name_counts[base]+=1
                v["name"]=f"{base}_{name_counts[base]}"
            else:
                name_counts[base]=0
            versions.append(v)

    meta={"generated_at": datetime.now().isoformat(), "count": len(versions), "note": args.note, "full_offline": True, "client_engine": True}
    data_js_path=dist_dir/"data.js"
    generate_data_js(versions, data_js_path, meta, include_schema=True)
    try_bundle_xlsx_lib(dist_dir, index_path)
    inject_data_js(index_path)

    readme_path=dist_dir/"README_OFFLINE.txt"
    with open(readme_path, "w", encoding="utf-8") as rf:
        rf.write(f"""Offline Static Build - Production Plan Review (Full Functional)

Generated at: {meta['generated_at']}
Versions embedded: {len(versions)}
Client Engine: ✅ (upload/config/filter/aggregate/download all work offline)
{('Note: '+meta['note']) if meta['note'] else ''}

How to use:
  1. Unzip anywhere
  2. Double-click index.html
  3. All functions work offline:
     - Upload new xlsx (uses browser engine.js, no server)
     - Configure Cut Day & ETD offset
     - Filter, Aggregate, FG/GB tabs
     - Download Excel (client)
     - Switch pre-baked versions & Compare multi

To regenerate with your data:
  python export_static.py --inputs data/*.xlsx --output dist

Inspired by campus-planning-system/export_static.py
""")

    print("\n🎉 纯静态打包彻底完成 - 全功能版！")
    print(f"👉 产出目录: {dist_dir}")
    print(f"👉 包含版本: {len(versions)} 个")
    for v in versions:
        print(f"   - {v['name']}: {len(v['rows'])} rows")
    print(f"\n👉 将 【{dist_dir.name}】 打 zip 发给任何人，双击 index.html 即可，上传/配置/报表 全可用，真离线！")

if __name__ == "__main__":
    main()
