"""Pinea Model Gateway — L2 单一前门。

只做三件事：路由 + schema 归一 + 治理（鉴权/计量/日志/健康）。
绝不自己做推理——推理永远在后端进程（ollama / whisper / TTS / 生图 / 视频）。
详见 docs/model-gateway.md。
"""

__version__ = "0.0.1"
