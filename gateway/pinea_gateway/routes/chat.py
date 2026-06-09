"""① POST /v1/chat/completions — 文本/工具/视觉，薄透传到 ollama。

T0 端点。设计要点：**透传，不重写 messages/tools/tool_calls**，只做鉴权+路由+计量，
保证 tool calling 不被中间层破坏。
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..auth import Usage, meter, require_auth
from ..config import get_settings
from ..errors import GatewayError
from ..backends.ollama import OllamaBackend

router = APIRouter()


def _ollama() -> OllamaBackend:
    s = get_settings()
    return OllamaBackend(s.ollama_url, timeout=s.backend_timeout)


async def _parse_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise GatewayError(f"invalid JSON body: {exc}") from exc
    if not isinstance(body, dict):
        raise GatewayError("body must be a JSON object")
    if not body.get("messages"):
        raise GatewayError("'messages' is required", code="missing_messages")
    return body


@router.post("/v1/chat/completions", dependencies=[Depends(require_auth)])
async def chat_completions(request: Request):
    body = await _parse_body(request)
    body.setdefault("model", get_settings().default_chat_model)
    backend = _ollama()
    stream = bool(body.get("stream"))
    t0 = time.perf_counter()

    if stream:
        async def gen():
            async for chunk in backend.chat_stream(body):
                yield chunk
            meter(
                Usage(capability="chat", backend=backend.name, unit="tokens"),
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        return StreamingResponse(gen(), media_type="text/event-stream")

    result = await backend.chat(body)
    usage = result.get("usage") or {}
    meter(
        Usage(
            capability="chat",
            backend=backend.name,
            unit="tokens",
            amount=float(usage.get("total_tokens", 0) or 0),
        ),
        latency_ms=(time.perf_counter() - t0) * 1000,
    )
    return JSONResponse(result)
