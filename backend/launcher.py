"""PyInstaller entry point for the Auto HR backend server."""
import os
import sys

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

# Explicit import so PyInstaller's static analysis collects the entire
# app package.  uvicorn is then passed the object, not a string.
from app.main import app as fastapi_app  # noqa: E402

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        fastapi_app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        access_log=False,
    )
