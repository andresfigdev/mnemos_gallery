"""Entry point used by the packaged Electron application."""

import uvicorn

from src_python.main import app
from src_python.shared.config import settings


def main() -> None:
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
