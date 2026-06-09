"""ollama 后端：① chat/embeddings/视觉 的薄透传。

ollama 原生 OpenAI 兼容（:11434/v1），所以这里基本是反向代理 + 原样转发，
关键是**不碰 tool_calls / 流式分片**，保证 agentic tool calling 不被中间层弄坏
（tool-calling spike 经此回归 20/20 = T0 通过标准）。
"""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from ..errors import GatewayError


class OllamaBackend:
    name = "ollama"

    def __init__(self, base_url: str, *, timeout: float = 600.0) -> None:
        # base_url 形如 http://localhost:11434 ；其 OpenAI 端点在 /v1 下。
        self._v1 = base_url.rstrip("/") + "/v1"
        self._timeout = timeout

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._v1}/models")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def chat(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                r = await client.post(f"{self._v1}/chat/completions", json=payload)
            except httpx.HTTPError as exc:
                raise GatewayError(
                    f"ollama unreachable: {exc}", status_code=502, error_type="server_error"
                ) from exc
        if r.status_code >= 400:
            raise GatewayError(
                f"ollama error: {r.text}", status_code=r.status_code, error_type="server_error"
            )
        return r.json()

    async def chat_stream(self, payload: dict) -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", f"{self._v1}/chat/completions", json=payload
            ) as r:
                if r.status_code >= 400:
                    text = (await r.aread()).decode("utf-8", "replace")
                    raise GatewayError(
                        f"ollama error: {text}",
                        status_code=r.status_code,
                        error_type="server_error",
                    )
                async for chunk in r.aiter_raw():
                    if chunk:
                        yield chunk

    async def list_models(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{self._v1}/models")
        if r.status_code >= 400:
            raise GatewayError(
                f"ollama error: {r.text}", status_code=r.status_code, error_type="server_error"
            )
        return r.json().get("data", [])
