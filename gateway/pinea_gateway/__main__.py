"""python -m pinea_gateway → 起 uvicorn。"""

from __future__ import annotations

import uvicorn

from .config import get_settings


def main() -> None:
    s = get_settings()
    uvicorn.run("pinea_gateway.app:app", host=s.host, port=s.port, log_level="info")


if __name__ == "__main__":
    main()
