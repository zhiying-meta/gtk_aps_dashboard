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
    io_keywords = ["料号主表", "排产结果", "结存表"]
    for kw in io_keywords:
        if kw.lower() in lower:
            return False
    # Skip very large unrelated files
    if "lager" in lower and "by sku" in lower:
        # This is likely not 6-sheet template, skip by default
        return False
    return True

def find_default_inputs():
    candidates = []
    demo = TEMPLATE_DIR / "input_demo.xlsx"
    if demo.exists():
        candidates.append(demo)
    return candidates

def process_file(filepath: Path, config: dict):
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

def generate_data_js(versions, output_path: Path, meta: dict, include_schema=True):
    print(f"💾 Generating {output_path} with {len(versions)} version(s)...")
    schema = None
    schema_file = TEMPLATE_DIR / "schema.json"
    if include_schema and schema_file.exists():
        try:
            with open(schema_file, "r", encoding="utf-8") as sf:
                schema = json.load(sf)
        except Exception as e:
            print(f"   ⚠️ Failed to load schema: {e}")
    db = {"versions": versions, "meta": meta, "schema": schema}
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("window.STATIC_DB = ")
        json.dump(db, f, ensure_ascii=False, default=str)
        f.write(";\n")
    size_kb = output_path.stat().st_size / 1024
    print(f"   ✅ Wrote {output_path.name} — {size_kb:.1f} KB")
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
                    for f in p.glob("*.xlsx"):
                        if is_plan_merge_file(f):
                            input_files.append(f)
    else:
        # default only demo
        demo = TEMPLATE_DIR / "input_demo.xlsx"
        if demo.exists():
            input_files.append(demo)

    # dedup
    seen=set()
    uniq=[]
    for f in input_files:
        rp=f.resolve()
        if rp not in seen:
            seen.add(rp)
            uniq.append(f)
    input_files=uniq
    input_files=[f for f in input_files if is_plan_merge_file(f)]

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
