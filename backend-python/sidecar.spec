# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：把 FastAPI 后端打成单文件 sidecar exe。

输出文件名（onefile 模式）：dist/paperassistant-backend(.exe)

构建命令：
    pyinstaller --clean --noconfirm sidecar.spec

Tauri 端用 externalBin "binaries/paperassistant-backend" 引用，构建时
build_sidecar.ps1 会自动追加 target triple（x86_64-pc-windows-msvc）。
"""
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# fastapi / pydantic / uvicorn 都有 C 扩展和数据文件，需要 collect_all
hiddenimports = []
datas = []
binaries = []
for pkg in ("fastapi", "pydantic", "pydantic_core", "uvicorn", "starlette", "anyio", "sniffio"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "app",
        "app.main",
        "app.config",
        "app.storage",
        "app.api.health",
        "app.api.project",
        "app.api.literature",
        "app.api.citation",
        "app.api.typesetting",
        "app.api.settings",
        "app.api.ai",
        "app.api.knowledge",
        "app.api.temp_knowledge",
        "app.api.file_watcher",
        "app.api.selections",
        "app.stages",
        "app.stages.topic",
        "app.stages.review",
        "app.stages.writing",
        "app.stages.citation",
        "app.stages.typesetting",
        "app.stages.literature_review",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="paperassistant-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
