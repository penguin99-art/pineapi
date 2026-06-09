"""FastAPI 入口 + 路由注册 + 统一异常处理。

启动：
    uvicorn pinea_gateway.app:app --host 0.0.0.0 --port 8080
或：
    python -m pinea_gateway   （见 __main__.py）
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from . import __version__
from .errors import GatewayError, gateway_error_handler, unhandled_error_handler
from .routes import chat, meta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app() -> FastAPI:
    app = FastAPI(title="Pinea Model Gateway", version=__version__)
    app.add_exception_handler(GatewayError, gateway_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(meta.router)
    app.include_router(chat.router)
    return app


app = create_app()
