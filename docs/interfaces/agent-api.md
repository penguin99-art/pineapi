# L3/L4 Agent 面 API（有状态智能体 · OpenAI 兼容）

> 配套：能力面见 `capability-api.md`，runtime 接缝见 `runtime-contract.md`，总览见 `tob-overview.md`。
> 这是 **ToB 第二类接口**——把 agent runtime（记忆 + 工具 + 多步循环）做成对外端点，SI 套自己 UI 即用，不必自己搭 agent。
> **稳定性**：`v1.0` 已冻结（2026-06-10）。**2026-06-11 修订**：会话/异步端点重判为网关侧实现，升为 Stable·自定义（排期 T2.5）；矩阵见 `tob-overview.md` §7。
> **实现分工**：runtime（PilotDeck `api_server`）只提供单回合执行（sync+SSE）；会话登记、回放、异步聚合、删除、并发闸门由**网关增值层**实现（`../model-gateway.md` §6.3）。

## 0. 它和「能力面」的唯一区别：有状态 vs 无状态

同样是 OpenAI chat 协议，**靠 base_url 路径自解释**：

| | ① 能力面 `/v1/chat/completions` | ② Agent 面 `/v1/agent/chat/completions` |
| --- | --- | --- |
| 状态 | **无状态**：每次传全量 `messages` | **有状态**：`X-Session-Id` 串上下文 + 白盒记忆 |
| 工具 | 工具调用由调用方驱动多步 | **agent 自己用工具、自己多步循环**，一次请求出最终结果 |
| 记忆 | 无 | 跨回合记忆（runtime 提供） |
| 观测单位 | tokens | **agent 回合** |
| 给谁 | 想自己搭 agent 的 SI | 想直接要"会记事会用工具的 agent"的 SI |

一句话：① 给算力，② 给 agent。

### 0.1 为什么是 Chat Completions + 会话头，而不是 OpenAI Responses API

2026 年现状：OpenAI 推荐新项目用 Responses API（`previous_response_id` / `store` / `background`），但 Chat Completions **未弃用、长期支持**（落日的是 Assistants API，2026-08-26），且仍是本地推理栈（ollama/vLLM/llama.cpp）的通用基线协议。我们的选择：

- ② 走 **Chat Completions 形状 + `X-Session-Id` 头**：任何 OpenAI SDK 零改动可用，与 ① 同一协议族，本地生态全兼容。
- Responses 的两个核心价值已有等价形状：服务端状态 ↔ session 头 + 白盒记忆；`background` ↔ 我们的 `background:true` + 轮询（§3）。
- 预留 `/v1/agent/responses` 协议适配头（不在 v1 冻结命名空间内）：若 Responses 形状成为事实标准，加一个翻译头映射到同一接缝即可，agent 核不动（同 `architecture.md` §0.4 的 MCP/A2A 适配头格位）。

## 1. 对话 — `POST /v1/agent/chat/completions`

OpenAI Chat Completions 兼容。与 ① 的差异：路径前缀 `/v1/agent`、用 `X-Session-Id` 维持会话。

请求头：

| 头 | 必填 | 说明 |
| --- | --- | --- |
| `Authorization: Bearer <token>` | 视部署 | Gateway 安全门锁；本机封闭部署可关闭，绑定 LAN/WAN 必填 |
| `X-Session-Id: <id>` | | 会话标识；缺省自动生成并在响应头回带。同 id 串接上下文 + 记忆 |
| `X-Pinea-App-Id: <app>` | | 应用作用域，缺省 `default`（`capability-api.md` §0.1）。**有效会话 = `(app_id, X-Session-Id)`** |

**会话键映射（定死）**：网关把有效会话翻译成 runtime 会话键 **`{app_id}:{session_id}:{gen}`**（`gen` 初始为 0，删除会话时 +1，见 §4），经 `X-Hermes-Session-Id` 头传给 runtime。B 端永远不感知底层是不是 PilotDeck（runtime 可换）。

请求体（OpenAI 子集 + Pinea 扩展）：
```json
{
  "model": "gpt-oss:20b",
  "messages": [{"role":"user","content":"把 ~/inbox 里的音频转写并归档"}],
  "stream": false,
  "skill": "audio-archive"
}
```

| 字段 | 说明 |
| --- | --- |
| `messages` | 取最后一条用户消息为本回合输入；历史由 session + 记忆维护，不需要重传全量（传了也兼容） |
| `content` | string 或 `[{type:text\|input_text,text}]` |
| `tools` | **不需要传**——agent 用 runtime 侧已装的工具/skill；传了忽略 |
| `stream` | `true` → SSE，见 §2 |
| `skill` | **Pinea 扩展（可选，T3）**：指定本回合必须使用的已启用 skill。网关在转发前把该 skill 的调用指令注入回合输入，使触发从"按 description 概率命中"变为近确定——行业交付保证工序就靠它。skill 不存在 → `400 skill_not_found`；已禁用 → `400 skill_disabled`。runtime 级硬强制为后置上游能力，验收以实测命中率为准（`skill-contract.md` §2.5） |
| `background` | **Pinea 扩展（可选，T2.5）**：异步长回合，见 §3 |

响应（非流式）：标准 `chat.completion`，`choices[].message.content` = agent 多步跑完后的最终回答。

**并发（两级，都返回 `429`，按 `code` 区分）**：

- 同一 session 同时只允许一个进行中回合 → `429` `session_busy`（runtime 行为）。
- 设备级进行中回合上限（默认 2，`PINEA_AGENT_MAX_TURNS` 可配）→ `429` `queue_full`，带 `Retry-After` 头。盒子算力有限，SI 必须能编程处理"设备忙"，而不是只看到变慢。

## 2. 流式 — `stream: true`

SSE，对齐 OpenAI `chat.completion.chunk` + 结尾 `data: [DONE]`。

- **基线（默认）**：只发标准 chunk（`delta.content` 文本增量）——任何 OpenAI SDK 直接能用，**默认流里永远不出现非标准帧**。
- **扩展事件（显式开启）**：请求头 `X-Pinea-Events: extended` 时，网关在同一 SSE 流里**插入**扩展帧，形状定死：

```
data: {"object":"pinea.agent.event","type":"tool_call_started","data":{"toolCallId":"...","name":"fs.read"}}
```

`object` 恒为 `"pinea.agent.event"`（与 `chat.completion.chunk` 区分的判别键），`type`/`data` 取 runtime 的 `GatewayEvent` 子集（`tool_call_started/finished`、`turn_completed{usage}`、`context_budget` 等，v1 形状 = `runtime-contract.md` §契约三 B 的快照）。消费方按 `object` 分流，未知 `type` 必须忽略。

## 3. 异步长回合 — `background: true`（Pinea 扩展 · T2.5 · 网关侧实现）

Agent 多步循环可能跑很久，超出 SI 的 HTTP 超时。两条路：

1. **流式（首版可用）**：`stream:true` 长连边跑边回，拿到 `[DONE]` 即结束。
2. **异步提交/轮询（T2.5）**：请求体加 `"background": true`：
   - 提交：`POST /v1/agent/chat/completions` → `202` `{ "id":"turn_...","status":"queued" }`（响应头带 `X-Session-Id`）。
   - 轮询：`GET /v1/agent/turns/{id}` → `{ "id","status":"queued|running|succeeded|failed","result":<chat.completion>?,"error":{}? }`。

**实现机制（为什么不需要上游）**：网关收到 `background:true` 后，自己对 runtime 开 SSE 长连代持回合，聚合事件、存储最终结果，对 SI 立即返回 202。runtime 完全无感。结果保留期部署可配（默认 24h），过期后 `404 turn_not_found`。

**取消是例外**：`DELETE /v1/agent/turns/{id}` 为 **Reserved·需上游**——网关只能断开代持连接，无法保证 runtime 停止执行；真取消需 runtime 支持中止进行中回合。SI 首版不得依赖取消。

同一 session 的并发约束对异步回合同样生效；异步回合也占设备级并发额度。

## 4. 会话管理（T2.5 · 网关侧实现）

| 操作 | 端点 | 状态 |
| --- | --- | --- |
| 起/续会话 | 带 `X-Session-Id` 打 `/v1/agent/chat/completions` | Stable，T2 |
| 读会话回放 | `GET /v1/agent/sessions/{id}/messages` | Stable·自定义，T2.5 |
| 列会话 | `GET /v1/agent/sessions` | Stable·自定义，T2.5 |
| 删会话 | `DELETE /v1/agent/sessions/{id}` | Stable·自定义，T2.5（逻辑删除） |

响应形状（定死）：

```json
// GET /v1/agent/sessions
{ "object":"list", "data":[ { "id":"sess_x","app_id":"default","created_at":"...","last_active_at":"...","turns":12 } ] }

// GET /v1/agent/sessions/{id}/messages
{ "object":"list", "data":[ { "turn_id":"turn_...","role":"user|assistant","content":"...","usage":{...}?,"created_at":"..." } ] }
```

语义（对 SI 要讲清楚的三件事）：

- **回放的数据源是网关登记**：网关为每个会话记录「回合输入 + 最终回答 + usage + 时间戳」，回放返回的是这份记录，**不是 runtime 白盒记忆**。对"SI 套 UI 做会话回放"足够；要工具中间过程，用流式扩展帧（§2）自行记录。
- **删除 = 不可达 + 网关侧清除**：① 会话键 `gen` +1，旧上下文/记忆对该 session 永久不可达；② 清除网关侧登记与回放数据。幂等（不存在回 `404 session_not_found`）。**runtime 侧旧数据的物理擦除是运维程序**（交付手册：停 runtime 清理数据目录），原生支持为 Reserved·需上游。SI 对最终用户的"删除/被遗忘"承诺应按此措辞：立即不可达，物理擦除随运维周期。
- **生命周期**：MVP 会话持久化、不自动淘汰；SI 负责显式 `DELETE` 回收。后置可加 TTL/LRU（部署可配），删除语义不变。

### 安全与权限边界（对 SI 可见）

- **② 的最终用户输入按不可信对待**。转写文本、用户消息、文件名都可能携带注入指令（indirect prompt injection），这是 ② 的主要攻击面。SI 不要把未过滤的高权限指令通道暴露给最终用户。
- **`agent.permissions.network:false` 是安全默认**，不是普通配置项：agent 不能联网时，注入最多影响本回合输出；能联网则可能外带数据。开启联网前先评估注入后果。
- **⚠ workspace 跨 session 共享**：记忆按 `(app_id, session_id)` 隔离，但 MVP 的文件 workspace 是 app 级共享目录——用户 A 让 agent 写盘的文件，用户 B 的回合能读到。**跨最终用户的文件隔离由 SI 负责**。v1 预留 per-session workspace（路径按 `(app_id, session_id)` 派生），落地不破契约。
- Gateway 为 ② 配置设备级 ToB 工作区（如 `/srv/pinea/workspaces/default`），不得暴露系统根目录。
- 工具/MCP/Skills 权限由 runtime 配置收口；Gateway 只转发，不绕过 runtime 权限模型。SI 经 `GET /v1/capabilities` 的 `agent.{tools,permissions}` 只读查询边界，据此设计 UI 与用户告知。

## 5. 用量

- ② 的观测单位 = **agent 回合**。
- **token 用量**：真实用量在 runtime 的 `turn_completed.usage` 事件里（`api_server` 非流式响应的 `usage` 是 0 占位）。**T2 起网关从 SSE 聚合回填**：非流式响应与用量日志都给真实 `usage`，SI 可直接用。
- ② 内部 agent 经 `model.providers` 回打 ① 做推理，属同设备模型线调用，不引入计费语义。
- 三类写同一条结构化用量日志（`capability-api.md` §8）。

## 5.1 限额（② 特有）

| 项 | 值 | 超限 |
| --- | --- | --- |
| 请求体 | **1 MB**（底座 `MAX_REQUEST_BYTES`，小于 ① 的 8 MB） | 413。大输入走文件/工具，别塞 `messages` |
| 回合超时 | 底座默认 **5 min** | 504。长任务用流式或 `background` |
| 同 session 并发 | 1 个进行中回合 | 429 `session_busy` |
| 设备级并发 | 默认 2 个进行中回合（可配） | 429 `queue_full` + `Retry-After` |

其余错误/状态码同 `capability-api.md` §0.2。

## 6. 错误

OpenAI 风格，与 ① 统一（`capability-api.md` §0.2）。② 特有：

- 同 session 并发回合 → `429` `rate_limit_error` `code:session_busy`。
- 设备并发满 → `429` `rate_limit_error` `code:queue_full`，带 `Retry-After`。
- `skill` 字段指定的 skill 不存在/禁用 → `400` `invalid_request_error` `code:skill_not_found` / `skill_disabled`。
- 回合/会话不存在 → `404` `not_found_error` `code:turn_not_found` / `session_not_found`。
- 门锁开启且 token 缺失/错误 → `401` `authentication_error`。

## 7. 版本

- 路径前缀 `v1`，OpenAI 兼容子集承诺向后兼容。**`v1.0` 已冻结（2026-06-10）**。
- `background`、会话管理、`skill`、`X-Pinea-App-Id` 均为 Pinea 扩展，按 superset 规则演进（`capability-api.md` §9）。
- 仍为 Reserved 的只有两条：取消进行中回合、runtime 记忆物理擦除（均需上游，见 `tob-overview.md` §7）。
- 破坏性变更 → 升 `v2`，并行保留弃用周期。

## 8. 给对接方的并行约定

- **先 mock**：网关 `PINEA_MOCK=1` 启动即回"固定多步结果 + 假 session"，SI 可先对 UI；真 runtime 后置接入，契约不变。
- SI 选 ① 还是 ②：要最大自由度自己搭 agent → ①；要开箱即用 agent → ②。同一前门，可混用。
