# Pinea Model Gateway

L2 单一前门：OpenAI 兼容多模态能力网关。**只路由 + schema 归一 + 治理，不做推理**
（推理在后端进程：ollama / whisper / TTS / 生图 / 视频）。设计见 `../docs/model-gateway.md`，
对外契约见 `../docs/interfaces/`。

## 现状（T0）

只有 ① 文本这条腿：`/v1/chat/completions` 薄透传到本机 ollama。后续 STT/TTS/图/视频/
② Agent 面只在 `pinea_gateway/routes/` + `pinea_gateway/backends/` 各加一块，契约不变。

| 端点 | 说明 |
| --- | --- |
| `POST /v1/chat/completions` | ① 文本/工具/视觉，透传 ollama |
| `GET /healthz` | 后端探活 |
| `GET /v1/models` | 模型列表（聚合 ollama） |
| `GET /v1/capabilities` | 三类 ToB 发现（T0 仅 chat 可用） |

## 跑起来

```bash
cd gateway
uv venv && uv pip install -e ".[test]"     # 或: pip install -e ".[test]"
cp .env.example .env                         # 按需改 OLLAMA_URL / PORT / API_KEY
uv run python -m pinea_gateway               # 起在 :8080
```

冒烟：

```bash
curl -s localhost:8080/healthz
curl -s localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"用一句话介绍你自己"}]}'
```

## 测试（conformance）

```bash
uv run pytest                                 # 进程内 mock 后端，离线可跑
PINEA_TEST_BASE_URL=http://localhost:8080 uv run pytest   # 打真网关，同一套用例
```

测试只认 `base_url`：mock 先绿，真后端后置替换还得绿 = 契约没破。

## T0 通过标准（agentic 回归）

把 PilotDeck `model.providers` 指向本网关，跑 tool-calling 回归不掉：

```bash
# deploy/pilot-home/pilotdeck.yaml: model.providers.ollama.url 改为 http://localhost:8080/v1
python -m pinea_gateway &                      # 先起网关
bash ../research/spikes/tool-calling/run.sh 20 # 期望 20/20
```
