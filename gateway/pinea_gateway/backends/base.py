"""Backend 协议：吃 OpenAI 形状 → 调后端进程 → 吐 OpenAI 形状。

每个后端实现统一接口；加模态/换后端 = 加一个 adapter + 路由表一行，SI 侧无感
（见 docs/model-gateway.md §5）。T0 只用到 chat 透传，协议先定 chat + 健康。
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class ChatBackend(Protocol):
    name: str

    async def health(self) -> bool:
        """后端探活。"""

    async def chat(self, payload: dict) -> dict:
        """非流式：OpenAI chat.completion。"""

    def chat_stream(self, payload: dict) -> AsyncIterator[bytes]:
        """流式：透传后端 SSE（chat.completion.chunk + data: [DONE]）。"""

    async def list_models(self) -> list[dict]:
        """OpenAI /v1/models 的 data 列表。"""
