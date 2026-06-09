# L3/L4 Agent Runtime 契约（可换的边界）

> 配套：架构见 `../architecture.md` §0，融合见 `../pilotdeck-integration.md`，总览见 `README.md`。
> 当前实现 = PilotDeck。**自研只依赖以下 4 个契约，从不 import 内部模块** → 换 runtime = 重接这 4 个。
> 依据（已核对 submodule 源码）：路径见各节。

## 契约一 · 模型层接入（`model.providers`）

Runtime 经配置把模型请求打到我们的能力面（OpenAI 协议）。

- 依据：`deploy/pilot-home/pilotdeck.yaml` → `model.providers.<name>{ protocol: openai, url, apiKey, models }`。
- 我们填：`url` 指向 Pinea Model Gateway（`capability-api.md`），`protocol: openai`。
- 换 runtime 要求：新 runtime 能配「OpenAI 兼容 provider URL」。

## 契约二 · Inbound 接缝（外部 → runtime 起回合）

两种等价入口，灵魂层/桌伴用其一：

### A) 内置 `api_server` channel（HTTP，MVP 用这个）
依据：`vendor/pilotdeck/src/adapters/channel/api-server/ApiServerChannel.ts`。

> **此接缝已升格为 ② Agent 面**（`agent-api.md`）：网关 `/v1/agent/*` 转发到这里，对外用 `X-Session-Id`（网关内部翻译成下方 `X-Hermes-Session-Id`），并在 Gateway 层统一加设备安全门锁（Bearer Token，外放必开）。对内仍是灵魂/桌伴的 inbound 接缝。两个角色同一机制，零改核心。

- `POST /v1/chat/completions`（OpenAI 兼容；默认 `127.0.0.1:8642`，env `API_SERVER_PORT/HOST/KEY`）。
- 会话：请求头 `X-Hermes-Session-Id: <id>`（缺省自动生成；同 id 串接上下文）。**同一 session 同时只允许一个进行中回合**（并发返回 `429`）。
- 鉴权：`Authorization: Bearer <API_SERVER_KEY>`（配了才校验）。
- 流式：`"stream": true` → SSE `chat.completion.chunk` + `data: [DONE]`；否则返回完整 `chat.completion`。
- 其它：`GET /health`、`GET /v1/models`。
- 取最后一条 message 的文本为输入（`content` 支持 string 或 `[{type:text|input_text,text}]`）。

### B) 编程入口 `gateway.submitTurn`（同进程/SDK）
依据：`vendor/pilotdeck/src/gateway/protocol/types.ts`。

```ts
submitTurn(input: GatewaySubmitTurnInput): AsyncIterable<GatewayEvent>
```
`GatewaySubmitTurnInput`（关键字段）：
| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `sessionKey` | ✓ | 会话标识 |
| `channelKey` | ✓ | 来源，如 `"api_server"` |
| `message` | ✓ | 用户文本 |
| `attachments?` | | `{type:file\|image\|text, path?, content?, mimeType?}[]` |
| `mode?` | | `default\|plan\|acceptEdits\|bypassPermissions` |
| `workspaceCwd?` / `projectKey?` / `runId?` / `maxTurns?` | | 可选 |

## 契约三 · Outbound 接缝（runtime → 外部/表达）

### A) 磁盘 Hook（脚本，发态首选）
依据：`vendor/pilotdeck/src/extension/hooks/protocol/{events,input,output}.ts`。

- 事件（节选，全量见源码 `PILOTDECK_HOOK_EVENTS`）：`SessionStart` `SessionEnd` `UserPromptSubmit` `PreModelRequest` `PreToolUse` `PostToolUse` `PostToolUseFailure` `Stop` `StopFailure` `Notification` `SubagentStart/Stop` `PreCompact/PostCompact` `PermissionRequest/Denied` …
- 输入（喂给 hook 脚本，camelCase；另有 snake_case legacy 镜像）：
```jsonc
{ "hookEventName":"SessionStart", "sessionId":"...", "transcriptPath":"...", "cwd":"...",
  "permissionMode":"...", "agentId":"...", "agentType":"...", /* + 各事件附加字段 */ }
```
- 用途：表达层挂 `SessionStart→thinking`、`Stop→idle` 等，往 PineaState 总线发 `state`（见 `pineastate-bus.md`）。

### B) Gateway 事件流（订阅，Studio/表达用）
依据：`GatewayEvent`（`src/gateway/protocol/types.ts`），经 `GatewayWsClient`/`RemoteGateway` 消费。

`GatewayEvent` 变体（节选）：
| type | 含义 |
| --- | --- |
| `turn_started{runId}` | 回合开始 |
| `assistant_text_delta{text}` | 流式正文 |
| `assistant_thinking_delta{text}` | 流式思考 |
| `tool_call_started{toolCallId,name,argsPreview?}` | 工具开始 |
| `tool_call_finished{toolCallId,ok,resultPreview?,images?,errorCode?,data?}` | 工具结束 |
| `permission_request` / `elicitation_request` | 需宿主交互 |
| `context_budget{used,total,ratio,state}` | 上下文预算 |
| `turn_completed{usage,finishReason}` | 回合完成 |
| `error{message,code?,recoverable}` | 错误 |

## 契约四 · gateway SDK（Studio 数据面）

依据：`src/gateway/protocol`（类型）+ `GatewayWsClient`/`RemoteGateway` + web 读 API。
- Studio **只 import** 这些（红线 5），消费 `GatewayEvent` + `readSessionMessages`/`listProjects` 等只读 RPC。
- 换 runtime 要求：提供等价的「事件流 + 会话/项目读 API」。

## 换 runtime 的验收清单

替换 PilotDeck，新 runtime 必须提供：
- [ ] OpenAI 兼容 model provider 配置（契约一）
- [ ] inbound：HTTP OpenAI 端点 **或** `submitTurn`-等价编程入口（契约二）
- [ ] outbound：生命周期 hook **或** 等价事件流（契约三）
- [ ] 事件流 + 会话只读 API 供 Studio（契约四）
- [ ] **白盒记忆 + Skill/Workflow 的对等能力**（护城河，迁移代价主要在这）

> 只要这 4+1 对齐，灵魂层、能力面、Studio 全不动——这就是"runtime 可换"的具体含义。
