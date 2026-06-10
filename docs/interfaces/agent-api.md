# L3/L4 Agent 面 API（有状态智能体 · OpenAI 兼容）

> 配套：能力面见 `capability-api.md`，runtime 接缝见 `runtime-contract.md`，总览见 `README.md`。
> 这是 **ToB 第二类接口**——把 agent runtime（记忆 + 工具 + 多步循环）做成对外端点，SI 套自己 UI 即用，不必自己搭 agent、也不必写 skill。
> **稳定性**：对外契约，破坏性变更走版本。**`v1.0` 已冻结（2026-06-10）**；端点档位 + 实现状态见 `tob-overview.md` §7（注意：本面多个端点为 **Reserved·需上游**，首版不可用）。
> 依据：`vendor/pilotdeck/src/adapters/channel/api-server/ApiServerChannel.ts`（内部 inbound 接缝，已升格为对外产品）。

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

## 1. 对话 — `POST /v1/agent/chat/completions`

OpenAI Chat Completions 兼容。与 ① 的差异只有两点：路径前缀 `/v1/agent`、用 `X-Session-Id` 维持会话。

请求头：

| 头 | 必填 | 说明 |
| --- | --- | --- |
| `Authorization: Bearer <token>` | 视部署而定 | Gateway 安全门锁；本机封闭部署可关闭，绑定 LAN/WAN 时必填 |
| `X-Session-Id: <id>` | | 会话标识；缺省自动生成并在响应头回带。同 id 串接上下文 + 记忆 |
| `X-Pinea-App-Id: <app>` | | 应用作用域，缺省 `default`，见 `capability-api.md` §0.1。**有效会话 = `(app_id, X-Session-Id)`**——避免不同 SI 用同一 session 字符串串台。MVP 单值不强隔离 |

> 网关内部把 `X-Session-Id` 翻译成 runtime 的 `X-Hermes-Session-Id`——**B 端永远不感知底层是不是 PilotDeck**（呼应 runtime 可换）。

请求体（OpenAI 子集）：
```json
{
  "model": "gpt-oss:20b",
  "messages": [{"role":"user","content":"把 ~/inbox 里的音频转写并归档"}],
  "stream": false
}
```

- `messages`：取最后一条用户消息为本回合输入；历史上下文由 session + 记忆维护，**不需要每次重传全量**（传了也兼容）。
- `content`：支持 string 或 `[{type:text|input_text,text}]`。
- `tools`：**不需要传**——agent 用的是 runtime 侧已装的工具/skill；传了忽略。
- `stream:true` → SSE，见 §2。

响应（非流式）：标准 `chat.completion`，`choices[].message.content` = agent 多步跑完后的最终回答。

并发：**同一 session 同时只允许一个进行中回合**，并发请求返回 `429`（依据 api_server 行为）。

## 2. 流式 — `stream: true`

SSE，对齐 OpenAI `chat.completion.chunk` + 结尾 `data: [DONE]`。

- **基线（OpenAI 兼容）**：只发 `delta.content` 文本增量——任何 OpenAI SDK 直接能用。
- **扩展事件（可选订阅，富语义）**：如需 plan / 工具过程 / 上下文预算等，网关可在 SSE 里**附加** runtime 的 `GatewayEvent`（`tool_call_started/finished`、`assistant_thinking_delta`、`turn_completed{usage}` 等，见 `runtime-contract.md` §契约三 B）。基线消费方忽略这些扩展帧即可，不破坏 OpenAI 兼容。

## 3. 异步长回合（可选 · Pinea 扩展 · **Reserved·需上游**）

> **冻结状态：Reserved。** 本节形状纳入 v1，但底座 `api_server` 今天不支持异步任务（只有 sync + SSE）；落地需给 PilotDeck 上游加能力（红线①：不在 fork 改）。**首版请用流式（路 1）**，勿依赖 `background`。

Agent 多步循环 + 工具可能跑很久，超出 SI 的 HTTP 超时。两条路：

1. **流式（推荐，首版可用）**：`stream:true`，SSE 长连边跑边回（见 §2），SI 拿到 `[DONE]` 即结束。
2. **异步提交/轮询**（Reserved，无法长连时）：请求体加 Pinea 扩展字段 `"background": true`：
   - 提交：`POST /v1/agent/chat/completions` `{...,"background":true}` → `202` `{ "id":"turn_...","status":"queued" }`（响应头带 `X-Session-Id`）。
   - 轮询：`GET /v1/agent/turns/{id}` → `{ "id","status":"queued|running|succeeded|failed","result":<chat.completion>?,"error":{}? }`。
   - 取消：`DELETE /v1/agent/turns/{id}` → 尽力中止进行中回合。

> `background` 是 Pinea 扩展（见 `capability-api.md` §9 superset 矩阵）；不传 = 同步行为，OpenAI 客户端无感。同一 session 的并发约束对异步回合同样生效。

## 4. 会话管理

| 操作 | 端点 | 冻结状态 | 说明 |
| --- | --- | --- | --- |
| 起/续会话 | 带 `X-Session-Id` 打 `/v1/agent/chat/completions` | Stable·首版可用 | 缺省自动建（`api_server` 已支持 session 头 + 新建命令） |
| 读会话历史 | `GET /v1/agent/sessions/{id}/messages` | **Reserved·需上游** | 只读，供 UI 回放（映射 runtime 会话读 API） |
| 列会话 | `GET /v1/agent/sessions` | **Reserved·需上游** | 只读 |
| 删会话 | `DELETE /v1/agent/sessions/{id}` | **Reserved·需上游** | 删除会话及其记忆作用域；幂等（不存在回 `404` `session_not_found`） |

> 起/续会话首版即可用；读/列/删为 Reserved——`api_server` 今天无这些路由，需上游加（红线①）。

- **生命周期**：MVP 会话**持久化、不自动淘汰**；SI 负责显式 `DELETE` 回收。后置可加 TTL/LRU 淘汰策略（部署可配），删除语义不变。
- 删除会连带清理该 `(app_id, session_id)` 在 runtime 的白盒记忆作用域；这是「让用户行使被遗忘权」的对外抓手。

> 会话读/删 API 映射到 `runtime-contract.md` §契约四（gateway SDK 数据面）。换 runtime 要求提供等价的会话只读 + 删除能力。

### 默认 workspace / 权限边界（对 SI 可见）

- `X-Session-Id` 缺省时由 Gateway 生成并在响应头回带；SI App 应为每个最终用户/业务对象维护稳定 session。
- Gateway 为 ② Agent 面配置一个设备级 ToB 工作区（部署时配置，建议类似 `/srv/pinea/workspaces/default`），不得把系统根目录暴露给 agent。多 app 场景下 workspace 按 `app_id` 隔离（v1 预留，MVP 单 workspace）。
- 同一 session 同时只允许一个进行中回合；并发返回 `429` `session_busy`。
- Agent 可用的工具/MCP/Skills 与权限边界由 runtime 配置决定；Gateway 只转发回合，不绕过 runtime 权限模型。
- **权限可见**：SI 可读 `GET /v1/capabilities` 的 `agent.{tools,permissions}`（见 `capability-api.md` §7）了解「这台盒子的 agent 被允许做什么」（能否写盘/联网），据此设计自己的 UI 与告知用户。该声明只读，Gateway 不会因调用方而放宽。

## 5. 用量与内部回打

- ② 的观测单位 = **agent 回合**（一次 `/v1/agent/chat/completions` 完成算一回合）。
- **token 用量来源**：真实 token 汇总在 runtime 的 `turn_completed.usage` 事件里。`api_server` 的**非流式响应当前 `usage` 字段为 0**（占位）——要拿真实用量需消费 SSE 扩展事件流（§2）或网关从事件聚合后回填。SI 不应依赖非流式响应里的 `usage` 数值。
- ② 内部 agent 经 `model.providers` **回打 ① 网关**做推理；这是同一台设备内的模型线调用，不引入额外商业计费语义。
- 用量写**同一条结构化用量日志**（与 ①③ 统一，见 `capability-api.md` §用量），用于本机观测、排障和资源仲裁。

## 5.1 限额（② 特有）

- **请求体上限**：② 经 `api_server` 转发，当前底座上限 **1 MB**（`MAX_REQUEST_BYTES`），小于 ① 能力面的 8 MB。SI 不要在 `messages` 里塞大附件；大输入走文件/工具。
- 回合超时：底座默认 **5 min**（`REQUEST_TIMEOUT_MS`）；长任务请用流式保持连接。
- 其余错误/状态码同 `capability-api.md` §0.2。

## 6. 错误

OpenAI 风格，与 ① 完全统一——`type`/HTTP 状态码/`code` 见 `capability-api.md` §0.2。② 特有的：

- 同 session 并发回合 → `429` `rate_limit_error` `code:session_busy`。
- `GET /v1/agent/turns/{id}` / `DELETE /v1/agent/sessions/{id}` 目标不存在 → `404` `not_found_error` `code:session_not_found`（或 `turn_not_found`）。
- 门锁开启且 token 缺失/错误 → `401` `authentication_error`。

## 7. 版本

- 路径前缀 `v1`。OpenAI 兼容子集承诺向后兼容。**`v1.0` 已冻结（2026-06-10）**。
- `background` 异步、会话删除、`X-Pinea-App-Id` 均为 Pinea 扩展，按 superset 规则演进（`capability-api.md` §9）。
- 冻结后：Stable 端点（sync/stream chat + `X-Session-Id` + 429）锁定；**Reserved 端点（异步/读/列/删会话）形状纳入 v1 但首版不保证可用**（见 `tob-overview.md` §7）。
- 破坏性变更 → 升 `v2`，并行保留弃用周期。

## 8. 给对接方的并行约定

- **先 mock**：Agent 面可先用一个"回固定多步结果 + 假 session"的 mock 立起来，SI 即可对 UI；真 runtime 后置接入，契约不变。
- SI 选 ① 还是 ②：要最大自由度自己搭 agent → 用 ①；要开箱即用的 agent → 用 ②。两者同一设备前门，可混用。
