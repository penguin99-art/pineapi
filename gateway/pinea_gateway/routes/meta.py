"""发现/健康：/healthz · /v1/models · /v1/capabilities（见 interfaces/capability-api.md §7）。"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..backends.ollama import OllamaBackend

router = APIRouter()


def _ollama() -> OllamaBackend:
    s = get_settings()
    return OllamaBackend(s.ollama_url, timeout=s.backend_timeout)


@router.get("/healthz")
async def healthz():
    ollama_ok = await _ollama().health()
    status = "ok" if ollama_ok else "degraded"
    return JSONResponse(
        {"status": status, "backends": {"ollama": "ok" if ollama_ok else "down"}}
    )


@router.get("/v1/models")
async def list_models():
    data = await _ollama().list_models()
    # 给每个 model 标 capability（T0：来自 ollama 的都按 chat 处理）。
    for m in data:
        m.setdefault("capabilities", ["chat"])
    return JSONResponse({"object": "list", "data": data})


@router.get("/v1/capabilities")
async def capabilities():
    """三类 ToB 一起发现。T0：仅 ① chat 可用，其余 false。"""
    ollama_ok = await _ollama().health()
    return JSONResponse(
        {
            "object": "capabilities",
            "modalities": {
                "chat": {"available": ollama_ok},
                "embeddings": {"available": ollama_ok},
                "vision": {"available": ollama_ok},
                "transcription": {"available": False},
                "speech": {"available": False},
                "image": {"available": False},
                "video": {"available": False},
            },
            "agent": {"available": False},
            "skills": [],
        }
    )
