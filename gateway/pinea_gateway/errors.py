"""OpenAI 风格统一错误形状（全端点一致，见 interfaces/capability-api.md §0）。"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class GatewayError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_type: str = "invalid_request_error",
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        self.code = code

    def to_body(self) -> dict:
        err: dict = {"message": self.message, "type": self.error_type}
        if self.code is not None:
            err["code"] = self.code
        return {"error": err}


async def gateway_error_handler(_: Request, exc: GatewayError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_body())


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    body = {"error": {"message": f"internal error: {exc}", "type": "server_error"}}
    return JSONResponse(status_code=500, content=body)
