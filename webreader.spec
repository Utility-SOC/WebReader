# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the WebReader desktop app (Windows).
# Build: pyinstaller webreader.spec
# If a "tesseract_bundle" directory exists next to this spec (created by CI or
# manually copied from a Tesseract install), it is bundled for built-in OCR.

import os

datas = [("index.html", ".")]
if os.path.isdir("tesseract_bundle"):
    datas.append(("tesseract_bundle", "tesseract"))
if os.path.isdir("THIRD_PARTY_LICENSES"):
    datas.append(("THIRD_PARTY_LICENSES", "THIRD_PARTY_LICENSES"))

hiddenimports = [
    "backend.main",
    "backend.tasks",
    "backend.celery_app",
    # uvicorn loads these dynamically
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # celery/kombu dynamic imports (tasks run eagerly, but modules must exist)
    "celery.app.amqp",
    "celery.app.log",
    "celery.backends",
    "celery.backends.redis",
    "celery.fixups",
    "celery.fixups.django",
    "celery.loaders.app",
    "celery.worker.autoscale",
    "celery.worker.consumer",
    "kombu.transport.redis",
]

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WebReader",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
