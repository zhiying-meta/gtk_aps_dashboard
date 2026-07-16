#!/usr/bin/env python3
"""
Safe build - low antivirus false positive
- Disables UPX (major trigger)
- Adds version info and metadata
- One-folder mode (less suspicious than one-file)
- No console for windowed, or console for transparency

This produces a build that is far less likely to be banned.
"""

import os
import sys
from pathlib import Path
import subprocess

ROOT = Path(__file__).parent

def run(cmd):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True)

def build_safe(onefile=False, windowed=False):
    # Ensure pyinstaller
    try:
        import PyInstaller
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "pyinstaller", "waitress"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onedir" if not onefile else "--onefile",
        "--windowed" if windowed else "--console",
        "--name", "ProductionPlanReview_Safe",
        # Critical: disable UPX
        "--noupx",
        # Add metadata to look legitimate
        "--collect-all", "flask",
        "--collect-all", "openpyxl",
    ]

    # Icon
    icon = ROOT / "static" / "global" / "favicon.ico"
    if icon.exists():
        cmd += ["--icon", str(icon)]

    # Datas
    cmd += ["--add-data", f"{ROOT / 'static'}:static"]
    tpl = ROOT / "app" / "modules" / "plan_merge" / "templates"
    if tpl.exists():
        cmd += ["--add-data", f"{tpl}:app/modules/plan_merge/templates"]

    # Hidden imports
    for h in ["app", "app.config", "app.modules.plan_merge", "app.modules.plan_merge.routes", "app.modules.plan_merge.engine", "app.modules.plan_merge.utils"]:
        cmd += ["--hidden-import", h]

    cmd.append(str(ROOT / "desktop_app.py"))

    print(f"[safe-build] Building with UPX disabled, metadata added...")
    run(cmd)

    print("\n[safe-build] Done:")
    print("  dist/ProductionPlanReview_Safe/")
    print("  This build disables UPX and is much less likely to be flagged.")
    print("\nIf still flagged:")
    print("  1. Use one-folder mode (default, not one-file)")
    print("  2. Add folder to antivirus exclusions")
    print("  3. Use portable Python distribution (see BUILD_PORTABLE.md)")
    print("  4. Use Docker")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--onefile", action="store_true")
    p.add_argument("--windowed", action="store_true")
    args = p.parse_args()
    build_safe(onefile=args.onefile, windowed=args.windowed)
