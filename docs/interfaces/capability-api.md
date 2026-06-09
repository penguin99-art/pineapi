# L2 能力面 API（Pinea Model Gateway · OpenAI 兼容）

> 配套：设计见 `../model-gateway.md`，总览见 `README.md`，有状态 agent 见 `agent-api.md`。
> 这是 **ToB 第一类接口（无状态模型能力）**——SI 集成方照此对接，PilotDeck 也经 `model.providers` 消费同一份。
> Pinea Model Gateway 是**三类 ToB 的唯一对外前门**：① 无状态模型能力（本文）、② 有状态 Agent 面（`agent-api.md`，路径 `/v1/agent/*`）、③ Skills（`skill-contract.md`）。三类同 base_url、同 key、同发现/计量。
> **稳定性**：对外契约，破坏性变更走版本（见 §版本）。当前 = `v1`（draft，未冻结）。

## 0. 约定

- **Base URL**：`http://<host>:<port>`（默认 `:8080`，待定）。所有端点前缀 `/v1`。这是三类 ToB 的统一前门。
- **鉴权**：`Authorization: Bearer <key>`。一个客户一个 key，key 标了买了哪几类（① / ② / ③）。MVP 单 key；多租户后置（见 `../model-gateway.md` §6）。
- **内容类型**：JSON 端点 `application/json`；音频上传 `multipart/form-data`。
- **错误形状**（OpenAI 风格，全端点统一）：

```json
{ "error": { "message": "human readable", "type": "invalid_request_error|server_error|rate_limit_error", "code": "optional_machine_code" } }
```

- **能力发现**：`GET /v1/capabilities`（三类一起，见 §7）；`GET /v1/models` 聚合后端模型；`GET /healthz` 聚合后端探活。

## 1. 文本 / 工具 / 视觉 — `POST /v1/chat/completions`

OpenAI Chat Completions 透传到 ollama（tool calling 已验证）。视觉 = `content` 带 image_url；走 minicpm-v。

请求（节选关键字段）：
```json
{
  "model": "gpt-oss:20b",
  "messages": [{"role":"user","content":"..."}],
  "tools": [{"type":"function","function":{"name":"...","parameters":{}}}],
  "stream": false
}
```
响应：标准 `chat.completion`（含 `choices[].message.tool_calls`）。`stream:true` → SSE `chat.completion.chunk` + `data: [DONE]`。

| 字段 | 说明 |
| --- | --- |
| `model` | 见 `/v1/models`；默认 `gpt-oss:20b` |
| `tools` / `tool_choice` | 透传，工具调用由调用方驱动多步 |
| `stream` | SSE 流式 |

## 2. 向量 — `POST /v1/embeddings`

透传 ollama `nomic-embed-text`。请求 `{ "model": "...", "input": "..."|["..."] }` → `{ "object":"list","data":[{"embedding":[...],"index":0}] }`。

## 3. STT — `POST /v1/audio/transcriptions`  ← MVP 首做

`multipart/form-data`，对齐 OpenAI：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file` | binary | 音频（wav/mp3/m4a…） |
| `model` | string | 如 `whisper-medium` |
| `language` | string? | 如 `zh`，留空自动 |
| `response_format` | string? | `json`(默认)/`verbose_json`/`text` |

响应：`{ "text": "...", "usage": {"type":"duration","seconds": N} }`（`verbose_json` 另带分段/时间戳）。后端默认 speaches(faster-whisper)。

## 4. TTS — `POST /v1/audio/speech`

请求：
```json
{ "model":"piper", "input":"要合成的文字", "voice":"zh-CN-x", "response_format":"wav" }
```
响应：音频二进制（`Content-Type: audio/wav|mpeg|...`）。`stream` + `response_format:"pcm"` 可流式（后端支持时）。

## 5. 生图 — `POST /v1/images/generations`

对齐 OpenAI：
```json
{ "model":"sd-xl", "prompt":"...", "n":1, "size":"1024x1024", "response_format":"b64_json|url" }
```
响应：`{ "created":0, "data":[{"b64_json":"..."}|{"url":"..."}] }`。后端 ComfyUI，gateway adapter 把 prompt→工作流→图。

## 6. 生视频 — `POST /v1/video/generations`（自定义 · 异步）

OpenAI 无此标准。视频生成慢 → **异步任务**：

- 提交：`POST /v1/video/generations` `{ "model":"wan2.2","prompt":"...","seconds":4,"size":"720p" }` → `202` `{ "id":"vid_...","status":"queued" }`
- 轮询：`GET /v1/video/generations/{id}` → `{ "id","status":"queued|running|succeeded|failed","progress":0.0,"result":{"url":"..."}?,"error":{}? }`
- 可选 webhook：提交时带 `"callback_url"`，完成回调。

## 7. 发现：能力 / 模型 / 健康

盒子硬件不同（有的没 GPU 跑不了视频），B 端必须能**程序化问**这台盒子有什么。

### `GET /v1/capabilities` — 三类 ToB 一起发现

```json
{
  "object": "capabilities",
  "modalities": {
    "chat":          { "available": true,  "models": ["gpt-oss:20b","qwen3"] },
    "vision":        { "available": true,  "models": ["minicpm-v"] },
    "embeddings":    { "available": true,  "models": ["nomic-embed-text"] },
    "transcription": { "available": true,  "models": ["whisper-medium"] },
    "speech":        { "available": false },
    "image":         { "available": false },
    "video":         { "available": false }
  },
  "agent":  { "available": true },
  "skills": [{ "name": "audio-archive", "description": "..." }]
}
```

- `modalities.*` = ① 能力面各模态可用性 + 模型；`available:false` 表示这台盒子没挂该后端。
- `agent.available` = ② Agent 面（`agent-api.md`）是否开启。
- `skills[]` = ③ 已装公共 skill（同 `GET /v1/skills`）。
- 受 key 作用域过滤：只回该 key 买了的类别。

### `GET /v1/models` / `GET /healthz`

- `GET /v1/models` → `{ "object":"list","data":[{"id","object":"model","owned_by","capabilities":["chat","tools","vision"]}] }`（跨后端聚合，每个 model 标自身 capability 标签）。
- `GET /healthz` → `{ "status":"ok|degraded","backends":{"ollama":"ok","speaches":"down",...} }`。

## 8. 用量（计量统一形状）

三类 ToB 用量写**同一条结构化日志**，响应里按模态回 `usage`，单位不同但形状统一：

| 模态 | `usage` 形状 |
| --- | --- |
| chat/embeddings（①） | `{ "type":"tokens","prompt_tokens":N,"completion_tokens":N,"total_tokens":N }` |
| STT（①） | `{ "type":"duration","seconds":N }` |
| TTS（①） | `{ "type":"characters","count":N }` |
| 生图（①） | `{ "type":"images","count":N }` |
| 生视频（①） | `{ "type":"duration","seconds":N }`（产物时长） |
| Agent 回合（②） | `{ "type":"agent_turn","turns":1,"total_tokens":N }`（见 `agent-api.md` §4） |

> 计费 MVP 留桩（见 `../model-gateway.md` §6），但 `usage` 形状现在定死，后置接计费不破坏契约。

## 版本

- 路径前缀 `v1`。新增端点/字段 = 向后兼容，可直接加。
- **稳定性承诺**：OpenAI 兼容子集（chat/embeddings/audio/images 的标准字段）**承诺永不破坏**；自定义部分（`/v1/video`、`/v1/capabilities`、`usage` 扩展）按下方规则演进。
- 破坏性变更（删字段/改语义）→ 升 `v2` 并并行保留一个弃用周期。
- 本契约未冻结前（draft），以本文件为准；冻结时打 tag 并在此标注。

## 给实现/对接方的并行约定

- **先 mock 后真模型**：每个端点可先返回固定假数据（STT 回固定文本、TTS 回一段静音 wav、图回占位图），SI 即可对接、skill 即可联调；真后端后置替换，契约不变。
- adapter 把非 OpenAI 形状的后端（如 ComfyUI）归一到上面形状，**调用方永远只看这份契约**。
