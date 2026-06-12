"""conformance 夹具：测试只认 base_url，可打 mock 也可打真网关。

- 默认起一个进程内的 TestClient（真 app + mock ollama 后端），离线可跑。
- 设 PINEA_TEST_BASE_URL=http://localhost:18800 则打真网关（真后端），同一套用例。

这就是"先 mock 后真，契约不变"的执行体（interfaces/capability-api.md §并行约定）。
"""

from __future__ import annotations

import os

import httpx
import pytest


@pytest.fixture
def base_url() -> str | None:
    return os.environ.get("PINEA_TEST_BASE_URL")


@pytest.fixture
def client(base_url, monkeypatch):
    """真网关 client（base_url 给定）或进程内 TestClient（mock 后端）。"""
    if base_url:
        return httpx.Client(base_url=base_url, timeout=30.0)

    # 进程内：用 mock ollama 后端替换，避免依赖真 ollama。
    from fastapi.testclient import TestClient

    import pinea_gateway.backends.ollama as ollama_mod

    class _MockOllama:
        name = "ollama"

        def __init__(self, *_a, **_kw):
            pass

        async def health(self):
            return True

        async def chat(self, payload):
            return {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "model": payload.get("model", "mock"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "mock reply"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        async def chat_stream(self, payload):
            for piece in ["mock", " reply"]:
                yield (
                    'data: {"object":"chat.completion.chunk","choices":'
                    '[{"index":0,"delta":{"content":"' + piece + '"}}]}\n\n'
                ).encode()
            yield b"data: [DONE]\n\n"

        async def list_models(self):
            return [{"id": "gpt-oss:20b", "object": "model", "owned_by": "ollama"}]

    monkeypatch.setattr(ollama_mod, "OllamaBackend", _MockOllama)
    # 路由模块在导入时已绑定符号，逐个补丁。
    import pinea_gateway.routes.chat as chat_mod
    import pinea_gateway.routes.meta as meta_mod

    monkeypatch.setattr(chat_mod, "OllamaBackend", _MockOllama)
    monkeypatch.setattr(meta_mod, "OllamaBackend", _MockOllama)

    from pinea_gateway.app import create_app

    return TestClient(create_app())
