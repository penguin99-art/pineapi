"""网关设置 + 能力→后端 路由表。

T0 只有 ① 文本(chat/embeddings)这条腿，指向 ollama。后续 STT/TTS/图/视频/② Agent
面只在这里加一行路由 + 一个 backend adapter，对外契约不变（见 docs/model-gateway.md §5）。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PINEA_", env_file=".env", extra="ignore")

    # 默认只监听本机；如绑定 0.0.0.0 / LAN 地址，必须配置 api_key 作为设备门锁。
    host: str = "127.0.0.1"
    # :8080/:18790/:18791 在本机已被占；网关用 :18800（贴着 PilotDeck 18790 段）。
    port: int = 18800

    # 设备安全门锁：留空 = 本机封闭部署/开发不校验；外放时必须配置。
    api_key: str = ""

    # ① 文本/视觉/embed 后端（OpenAI 兼容）
    ollama_url: str = "http://localhost:11434"

    default_chat_model: str = "gpt-oss:20b"

    # 后端超时（秒）。agentic 多步 + 大模型，给足。
    backend_timeout: float = 600.0

    @model_validator(mode="after")
    def require_api_key_when_exposed(self) -> "Settings":
        """外放 Gateway 时必须配置设备门锁，避免把 agent/tool 能力裸露到网络。"""
        local_hosts = {"127.0.0.1", "localhost", "::1"}
        if self.host not in local_hosts and not self.api_key:
            raise ValueError("PINEA_API_KEY is required when PINEA_HOST is not localhost")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
