#!/usr/bin/env python3
"""
Build script for Production Plan Review desktop app

- Installs pyinstaller if missing
- Supports --onefile (single exe) and --windowed (no console)
- Also builds with pywebview if --with-webview flag

Usage:
    python build.py                 # one-folder, console
    python build.py --onefile       # single file
    python build.py --windowed      # no console (Windows .exe)
    python build.py --with-webview  # bundle pywebview for native window
    python build.py --onefile --windowed --with-webview

Output:
    dist/ProductionPlanReview/  (one-folder)
    or dist/ProductionPlanReview(.exe) (one-file)

For macOS .app:
    python build.py --windowed --onedir
    # Then dist/ProductionPlanReview.app is created if you use --windowed spec tweak
    # Or: pyinstaller --windowed --name "Production Plan Review" desktop_app.py
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent

def run(cmd, check=True):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)

def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa
        print("[build] PyInstaller found")
    except ImportError:
        print("[build] Installing PyInstaller...")
        run([sys.executable, "-m", "pip", "install", "pyinstaller", "--upgrade"])

def build(onefile=False, windowed=False, with_webview=False):
    ensure_pyinstaller()

    # Install deps for building
    if with_webview:
        print("[build] Installing pywebview for native window support...")
        try:
            run([sys.executable, "-m", "pip", "install", "pywebview", "waitress", "--upgrade"])
        except Exception as e:
            print(f"[build] pywebview install failed (optional): {e}")

    # Always ensure waitress for better server
    try:
        import waitress  # noqa
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "waitress"])

    # Base command - safe defaults to avoid AV false positive
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--noupx"]

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if windowed:
        cmd.append("--windowed")
    else:
        cmd.append("--console")

    # Name
    cmd += ["--name", "ProductionPlanReview"]

    # Icon if exists
    icon_path = ROOT / "static" / "global" / "favicon.ico"
    if icon_path.exists():
        cmd += ["--icon", str(icon_path)]

    # Datas
    cmd += ["--add-data", f"{ROOT / 'static'}:static"]
    plan_tpl = ROOT / "app" / "modules" / "plan_merge" / "templates"
    if plan_tpl.exists():
        cmd += ["--add-data", f"{plan_tpl}:app/modules/plan_merge/templates"]

    io_tpl = ROOT / "app" / "modules" / "io_report" / "templates"
    if io_tpl.exists():
        cmd += ["--add-data", f"{io_tpl}:app/modules/io_report/templates"]

    # Hidden imports
    hidden = [
        "app", "app.config", "app.modules.plan_merge", "app.modules.plan_merge.routes",
        "app.modules.plan_merge.engine", "app.modules.plan_merge.utils", "openpyxl", "flask", "jinja2", "werkzeug"
    ]
    if (ROOT / "app" / "modules" / "io_report").exists():
        hidden += ["app.modules.io_report", "app.modules.io_report.routes", "app.modules.io_report.engine"]

    for h in hidden:
        cmd += ["--hidden-import", h]

    # Entry
    cmd.append(str(ROOT / "desktop_app.py"))

    # Clean previous
    print(f"[build] Running PyInstaller: {' '.join(cmd)}")
    run(cmd)

    # Post-build info
    dist = ROOT / "dist" / "ProductionPlanReview"
    if onefile:
        exe = ROOT / "dist" / "ProductionPlanReview"
        if sys.platform == "win32":
            exe = exe.with_suffix(".exe")
        print(f"\n[build] ✅ One-file build done: {exe}")
        if exe.exists():
            print(f"      Size: {exe.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print(f"\n[build] ✅ One-folder build done: {dist}")
        if dist.exists():
            # Count size
            total = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file())
            print(f"      Size: {total / 1024 / 1024:.1f} MB, {len(list(dist.rglob('*')))} files")

    print("\n[build] To distribute:")
    print("  - One-folder: zip dist/ProductionPlanReview and send to colleague")
    print("  - One-file: send dist/ProductionPlanReview(.exe) directly")
    print("  - Double-click to run, it will open browser at http://localhost:8502")
    print("\n[build] For macOS .app bundle:")
    print("  python -m PyInstaller --windowed --name 'Production Plan Review' --add-data 'static:static' --add-data 'app/modules/plan_merge/templates:app/modules/plan_merge/templates' desktop_app.py")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Production Plan Review desktop app")
    parser.add_argument("--onefile", action="store_true", help="Build single file executable")
    parser.add_argument("--windowed", action="store_true", help="No console window (Windows)")
    parser.add_argument("--with-webview", action="store_true", help="Include pywebview for native window")
    parser.add_argument("--name", default="ProductionPlanReview", help="Output name")
    args = parser.parse_args()
    build(onefile=args.onefile, windowed=args.windowed, with_webview=args.with_webview)
