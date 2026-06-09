"""① /v1/chat/completions 契约一致性（mock 与真后端同一套）。

对应 build-plan T0 通过标准的可执行部分（agentic tool calling 的全链路回归由
research/spikes/tool-calling/run.sh 经 PilotDeck 跑）。
"""

from __future__ import annotations

import json


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"ok", "degraded"}
    assert "ollama" in body["backends"]


def test_models_shape(client):
    r = client.get("/v1/models")
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "list"
    assert isinstance(body["data"], list)


def test_capabilities_shape(client):
    r = client.get("/v1/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "capabilities"
    assert "chat" in body["modalities"]
    assert "agent" in body


def test_chat_non_stream_shape(client):
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"


def test_chat_missing_messages_error_shape(client):
    r = client.post("/v1/chat/completions", json={"model": "x"})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["type"] == "invalid_request_error"
    assert "message" in err


def test_chat_stream_sse_format(client):
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
    )
    assert r.status_code == 200
    text = r.text
    assert "data:" in text
    assert "[DONE]" in text
    # 至少一帧是合法 chat.completion.chunk
    chunks = [
        line[len("data: "):]
        for line in text.splitlines()
        if line.startswith("data: ") and "[DONE]" not in line
    ]
    assert chunks
    parsed = json.loads(chunks[0])
    assert parsed["object"] == "chat.completion.chunk"
