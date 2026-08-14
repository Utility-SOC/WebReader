"""
WebReader Desktop - single-window app wrapping the local WebReader server.

Runs the FastAPI backend in-process (embedded mode: no Redis, no Celery
worker) and opens the reader UI in a native window via pywebview.

Build (Windows):  pyinstaller webreader.spec
"""

import os
import socket
import sys
import threading
import time
import urllib.request

# PyInstaller's windowed build (console=False) gives the process no
# console, so sys.stdout/stderr are None. Libraries that assume a real
# stream (uvicorn's logging setup calls sys.stderr.isatty()) crash with
# AttributeError on None. Give them a no-op stream instead.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def _base_dir() -> str:
    """Bundle dir when frozen by PyInstaller, source dir otherwise."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """User-writable dir for the database, uploads and saved layouts."""
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(root, "WebReader")
    os.makedirs(path, exist_ok=True)
    return path


BASE = _base_dir()

# Must be set BEFORE importing the backend
os.environ["WEBREADER_EMBEDDED"] = "1"
os.environ.setdefault("WEBREADER_DATA_DIR", _data_dir())

# Bundled Tesseract OCR (Apache License 2.0 - see THIRD_PARTY_LICENSES/)
_tess = os.path.join(BASE, "tesseract", "tesseract.exe")
if os.path.exists(_tess):
    os.environ.setdefault("TESSERACT_CMD", _tess)
    _tessdata = os.path.join(BASE, "tesseract", "tessdata")
    if os.path.isdir(_tessdata):
        os.environ.setdefault("TESSDATA_PREFIX", _tessdata)

import uvicorn  # noqa: E402
from backend.main import app  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> None:
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()

    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url + "health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)

    import webview
    webview.create_window("WebReader", url, width=1200, height=850, min_size=(900, 600))
    webview.start()

    server.should_exit = True


if __name__ == "__main__":
    main()
