# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Auto HR backend.
Run from the repo root:
    pyinstaller backend.spec
Output: dist/backend/backend.exe
"""

a = Analysis(
    ["backend/launcher.py"],
    pathex=["backend"],
    binaries=[],
    datas=[
        # Bundle config.json alongside the executable
        ("config.json", "."),
    ],
    hiddenimports=[
        # uvicorn internals not auto-detected
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        # anyio backend
        "anyio._backends._asyncio",
        "anyio",
        # email (used internally by some HTTP libs)
        "email.mime.text",
        "email.mime.multipart",
    ],
    excludes=[
        # playwright is not wired into the main flow; excluding it saves ~200 MB
        "playwright",
        "pytest",
        "IPython",
        "matplotlib",
        "tkinter",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Hide the console window for end users.
    # Backend logs go to storage/logs/auto_hr.log instead.
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
