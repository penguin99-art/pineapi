"""设备安全门锁（Bearer Token）+ usage 观测日志。

治理在前门统一收口（见 docs/model-gateway.md §6）。usage 先只结构化记一条日志，
形状对齐 interfaces/capability-api.md §8；MVP 不做多租户/计费/配额。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fastapi import Request

from .config import get_settings
from .errors import GatewayError

logger = logging.getLogger("pinea_gateway.metering")


def require_auth(request: Request) -> None:
    """校验 Authorization: Bearer <token>。api_key 留空则放行（本机封闭部署/开发）。"""
    expected = get_settings().api_key
    if not expected:
        return
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if token != expected:
        raise GatewayError(
            "invalid api key",
            status_code=401,
            error_type="invalid_request_error",
            code="invalid_api_key",
        )


@dataclass
class Usage:
    """统一用量形状（interfaces/capability-api.md §8）。"""

    capability: str  # chat / transcription / agent_turn ...
    backend: str
    unit: str  # tokens / duration / images / agent_turn
    amount: float = 0.0
    internal: bool = False  # 设备内模型线调用；仅用于日志区分，不承载计费语义。


def meter(usage: Usage, *, latency_ms: float, caller: str = "anon") -> None:
    """usage 观测钩子：现在只记结构化日志。"""
    logger.info(
        "usage caller=%s capability=%s backend=%s unit=%s amount=%s internal=%s latency_ms=%.0f ts=%d",
        caller,
        usage.capability,
        usage.backend,
        usage.unit,
        usage.amount,
        usage.internal,
        latency_ms,
        int(time.time()),
    )
