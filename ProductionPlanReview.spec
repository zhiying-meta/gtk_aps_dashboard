# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['/Users/zhiyingchen/openhands_workspace/Projects/gtk-result-table/desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[('/Users/zhiyingchen/openhands_workspace/Projects/gtk-result-table/static', 'static'), ('/Users/zhiyingchen/openhands_workspace/Projects/gtk-result-table/app/modules/plan_merge/templates', 'app/modules/plan_merge/templates')],
    hiddenimports=['app', 'app.config', 'app.modules.plan_merge', 'app.modules.plan_merge.routes', 'app.modules.plan_merge.engine', 'app.modules.plan_merge.utils', 'openpyxl', 'flask', 'jinja2', 'werkzeug'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ProductionPlanReview',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Disabled to avoid antivirus false positive (UPX is major trigger)
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,  # Disabled
    upx_exclude=[],
    name='ProductionPlanReview',
)
