from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = APP_DIR.parent

if getattr(sys, "frozen", False):
    # PyInstaller bundle: user data lives next to backend.exe (or in the
    # directory specified by Electron via AUTHR_DATA_DIR env var so that
    # data survives app updates).
    _data_root = os.environ.get("AUTHR_DATA_DIR") or str(Path(sys.executable).parent)
    PROJECT_ROOT = Path(_data_root)
else:
    PROJECT_ROOT = BACKEND_DIR.parent

DATA_DIR = PROJECT_ROOT / "storage"
LOG_DIR = PROJECT_ROOT / "logs"
RUNTIME_STATE_PATH = DATA_DIR / "runtime_state.json"
APP_LOG_PATH = LOG_DIR / "auto_hr.log"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
