# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_all

playwright_datas, playwright_binaries, playwright_hidden = collect_all("playwright")
datas = playwright_datas + [
    ("tools/studio_sync/static", "tools/studio_sync/static"),
]
browser_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if browser_path and os.path.isdir(browser_path):
    datas += Tree(browser_path, prefix="ms-playwright")

a = Analysis(
    ["sincronizar_studio.py"],
    pathex=["."],
    binaries=playwright_binaries,
    datas=datas,
    hiddenimports=playwright_hidden,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="StudioSync",
    console=False,
    onefile=True,
    target_arch=None,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="Studio Sync.app",
        bundle_identifier="br.com.betha.studiosync",
        info_plist={"NSHighResolutionCapable": True},
    )
