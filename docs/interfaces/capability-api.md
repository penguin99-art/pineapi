# L2 能力面 API（Pinea Model Gateway · OpenAI 兼容）

> 配套：设计见 `../model-gateway.md`，总览见 `README.md`，有状态 agent 见 `agent-api.md`。
> 这是 **ToB 第一类接口（无状态模型能力）**——SI 集成方照此对接，PilotDeck 也经 `model.providers` 消费同一份。
> Pinea Model Gateway 是**三类 ToB 的设备前门**：① 无状态模型能力（本文）、② 有状态 Agent 面（`agent-api.md`，路径 `/v1/agent/*`）、③ Skills 管理（`skill-contract.md`）。三类同一设备 base_url，同一安全门锁，同一发现/日志。
> **稳定性**：对外契约，破坏性变更走版本（见 §版本）。**`v1.0` 已冻结（2026-06-10）**；端点档位 + 实现状态见 `tob-overview.md` §7 矩阵。

## 0. 约定

- **Base URL**：`http://<host>:<port>`（本项目默认 `:18800`，`:8080` 本机已被占；默认绑定 `127.0.0.1`）。所有端点前缀 `/v1`。这是三类 ToB 的设备前门。
- **安全门锁**：`Authorization: Bearer <token>`。本机封闭部署可关闭；只要 Gateway 绑定到 LAN/WAN 就必须开启。Token 不表达 ①/②/③ 购买范围，不做多租户/计费/配额。实现上：`PINEA_HOST` 默认 `127.0.0.1`；当 `PINEA_HOST` 不是 `127.0.0.1`/`localhost`/`::1` 时，`PINEA_API_KEY` 必填，否则 Gateway 拒绝启动。
- **应用作用域（forward-compat，见 §0.1）**：可选请求头 `X-Pinea-App-Id: <app>`，缺省 `default`。MVP 是单作用域 no-op，但形状现在定死，后续要做「单盒多 SI 隔离」时不破 v1。
- **内容类型**：JSON 端点 `application/json`；音频上传 `multipart/form-data`。
- **错误形状 / 状态码**：见 §0.2（OpenAI 风格，全端点统一）。
- **限额**：见 §0.3（默认值，部署可调）。
- **能力发现**：`GET /v1/capabilities`（三类一起，见 §7）；`GET /v1/models` 聚合后端模型；`GET /healthz` 聚合后端探活。

### 0.1 应用作用域 `X-Pinea-App-Id`

设备可能同时被多个 SI App/容器使用（见 `../architecture.md` §1 部署模式）。为避免以后加隔离时破契约，**现在就预留一个作用域维度**：

- 所有端点接受可选头 `X-Pinea-App-Id`，缺省 `default`。
- 作用范围（v1 形状，MVP 不强制隔离）：
  - ② 的有效会话 = `(app_id, X-Session-Id)`，避免不同 SI 用同一 session 字符串串台。
  - ③ skill 命名空间与 workspace 绑定到 `app_id`。
  - 观测日志带 `app_id` 字段。
- **MVP 行为**：只接受/记录，单值 `default`，不做强隔离；调用方现在传不传都行。**正式做多 SI 隔离 = 把 `app_id` 提升为强隔离键**，端点形状不变。

### 0.2 错误形状 / 状态码

OpenAI 风格，全端点统一：

```json
{ "error": { "message": "human readable", "type": "invalid_request_error", "code": "optional_machine_code", "param": "optional" } }
```

`type` 与 HTTP 状态码映射（与 OpenAI 对齐，新增不破兼容）：

| HTTP | `type` | 典型 `code` | 何时 |
| --- | --- | --- | --- |
| 400 | `invalid_request_error` | `missing_field` / `unsupported_model` | 参数错/模型不认识 |
| 401 | `authentication_error` | `invalid_api_key` | 门锁开启但 token 缺失/错误 |
| 403 | `permission_error` | `admin_required` | 调了需管理权限的端点（如 ③ 安装）|
| 404 | `not_found_error` | `model_not_found` / `skill_not_found` / `session_not_found` | 资源不存在 |
| 413 | `invalid_request_error` | `payload_too_large` | 上传超限（见 §0.3）|
| 429 | `rate_limit_error` | `session_busy` / `queue_full` | 同 session 并发回合 / 重后端队列满 |
| 500 | `server_error` | `backend_error` | 后端异常 |
| 503 | `service_unavailable_error` | `backend_down` / `warming` | 后端未挂/未就绪 |
| 504 | `server_error` | `timeout` | 后端超时 |

调用方应按 HTTP 状态码 + `code` 编程，`message` 仅供人读。

### 0.3 限额（默认值，`PINEA_*` 可调）

| 项 | 默认上限 | 超限 |
| --- | --- | --- |
| 请求体（JSON） | 8 MB | 413 `payload_too_large` |
| STT 音频文件 | 25 MB | 413 `payload_too_large` |
| STT 音频时长 | 30 min | 413 `payload_too_large` |
| STT 音频格式 | `wav/mp3/m4a/flac/ogg/webm` | 400 `unsupported_format` |
| TTS 输入文本 | 4096 字符 | 400 `payload_too_large` |
| 重后端（生图/视频）队列 | 串行，队列深度可配 | 429 `queue_full` |
| chat 上下文 | 由模型决定，见 `/v1/models` | 400 `context_length_exceeded` |

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

响应：`{ "text": "...", "usage": {"type":"duration","seconds": N} }`（`verbose_json` 另带分段/时间戳）。后端默认 speaches(faster-whisper)。限额见 §0.3（文件 ≤25MB、时长 ≤30min、格式白名单），超限 413/400。

## 4. TTS — `POST /v1/audio/speech`

请求：
```json
{ "model":"piper", "input":"要合成的文字", "voice":"zh-CN-x", "response_format":"wav" }
```
响应：音频二进制（`Content-Type: audio/wav|mpeg|...`）。`stream` + `response_format:"pcm"` 可流式（后端支持时）。`input` 上限见 §0.3（默认 4096 字符）。

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
  "agent":  {
    "available": true,
    "tools": ["fs.read","fs.write","shell","web.fetch"],
    "permissions": { "filesystem": "workspace", "network": false }
  },
  "skills": [{ "name": "audio-archive", "description": "..." }],
  "limits": {
    "request_body_bytes": 8388608,
    "stt": { "max_file_bytes": 26214400, "max_seconds": 1800, "formats": ["wav","mp3","m4a","flac","ogg","webm"] },
    "tts": { "max_input_chars": 4096 }
  }
}
```

- `modalities.*` = ① 能力面各模态可用性 + 模型；`available:false` 表示这台盒子没挂该后端。
- `agent` = ② Agent 面（`agent-api.md`）：`available` 是否开启；`tools` / `permissions` 是 runtime **当前配置**的工具与权限边界的**只读声明**（SI 据此判断「这台盒子的 agent 能不能写盘/联网」）。Gateway 只暴露不修改；要改边界改 runtime 配置。
- `skills[]` = ③ 已装/已启用公共 skill（同 `GET /v1/skills`）。
- `limits` = §0.3 的机读版（部署可调）。
- 返回的是**这台设备当前可用能力**；不按商业 key 作用域过滤。未挂某后端时用 `available:false` 表示。

后置可向 `modalities.*` 追加 `status: "idle|busy|warming|down"`、`queue_depth` 等资源状态字段，调用方必须忽略未知字段。

### `GET /v1/models` / `GET /healthz`

- `GET /v1/models` → `{ "object":"list","data":[{"id","object":"model","owned_by","capabilities":["chat","tools","vision"]}] }`（跨后端聚合，每个 model 标自身 capability 标签）。
- `GET /healthz` → `{ "status":"ok|degraded","backends":{"ollama":"ok","speaches":"down",...} }`。

## 8. 用量（观测统一形状）

三类 ToB 用量写**同一条结构化日志**，响应里按模态回 `usage`，单位不同但形状统一。MVP 中 `usage` 用于本机观测、排障和资源仲裁，不作为多租户计费依据：

| 模态 | `usage` 形状 |
| --- | --- |
| chat/embeddings（①） | `{ "type":"tokens","prompt_tokens":N,"completion_tokens":N,"total_tokens":N }` |
| STT（①） | `{ "type":"duration","seconds":N }` |
| TTS（①） | `{ "type":"characters","count":N }` |
| 生图（①） | `{ "type":"images","count":N }` |
| 生视频（①） | `{ "type":"duration","seconds":N }`（产物时长） |
| Agent 回合（②） | `{ "type":"agent_turn","turns":1,"total_tokens":N }`（见 `agent-api.md` §4） |

> 商业计费/配额不在 MVP 范围；但 `usage` 形状现在定死，后置如需商业治理不破坏契约。

## 9. OpenAI 兼容边界（superset 矩阵）

我们是 OpenAI **超集**，不是逐字镜像。SI 用 OpenAI SDK 指到本 base_url 时，下表说明哪些可直接复用、哪些是 Pinea 扩展（标准客户端会忽略额外字段，但不要依赖标准里没有的端点）：

| 端点 | 兼容级别 | 说明 |
| --- | --- | --- |
| `POST /v1/chat/completions` | ✅ 镜像 | 标准请求/响应/SSE；`stream_options.include_usage:true` 时末块带 `usage`。 |
| `POST /v1/embeddings` | ✅ 镜像 | 标准。 |
| `POST /v1/audio/transcriptions` | ⊕ 超集 | 请求镜像；响应在标准上**附加** `usage:{type:"duration"}`（标准客户端忽略）。 |
| `POST /v1/audio/speech` | ✅ 镜像 | 标准。 |
| `POST /v1/images/generations` | ✅ 镜像 | 标准。 |
| `POST /v1/video/generations` | ⚠ 自定义 | OpenAI 的视频 API 仍在演进且形状不同；本端点是 **Pinea 私有异步契约**，勿假设与 OpenAI `videos` 一致。 |
| `/v1/agent/*` | ⚠ 自定义 | ② Agent 面，见 `agent-api.md`；chat 形状镜像，会话/异步/权限是 Pinea 扩展。 |
| `/v1/skills/*`、`/v1/capabilities` | ⚠ 自定义 | Pinea 私有。 |
| `X-Pinea-App-Id` / `X-Session-Id` 头 | ⊕ 超集 | 标准客户端不发也能用（缺省 `default`）。 |

约定：**带「✅ 镜像」的标准字段承诺永不破坏**；「⊕ 超集」只增字段、标准客户端可忽略；「⚠ 自定义」按 §版本 演进。

## 版本

- 路径前缀 `v1`。新增端点/字段 = 向后兼容，可直接加。
- **稳定性承诺**：OpenAI 兼容子集（chat/embeddings/audio/images 的标准字段）**承诺永不破坏**；自定义部分（`/v1/video`、`/v1/capabilities`、`usage` 扩展）按下方规则演进。
- 破坏性变更（删字段/改语义）→ 升 `v2` 并并行保留一个弃用周期。
- **`v1.0` 已冻结（2026-06-10）**：Stable 档位锁定；Reserved 端点（见 `tob-overview.md` §7）形状纳入 v1，但首版不保证可用，调用方不得依赖其存在。

## 给实现/对接方的并行约定

- **先 mock 后真模型**：每个端点可先返回固定假数据（STT 回固定文本、TTS 回一段静音 wav、图回占位图），SI 即可对接、skill 即可联调；真后端后置替换，契约不变。
- adapter 把非 OpenAI 形状的后端（如 ComfyUI）归一到上面形状，**调用方永远只看这份契约**。
