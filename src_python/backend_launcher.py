"""Entry point used by the packaged Electron application."""

import sys

import uvicorn

from src_python.main import app
from src_python.shared.config import settings


def main() -> None:
    # PyInstaller hereda cp1252 en algunos entornos Windows. Los logs de la
    # aplicación contienen texto Unicode y deben escribirse sin generar miles
    # de errores durante un escaneo grande.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
