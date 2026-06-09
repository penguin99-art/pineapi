# L3/L4 Agent 面 API（有状态智能体 · OpenAI 兼容）

> 配套：能力面见 `capability-api.md`，runtime 接缝见 `runtime-contract.md`，总览见 `README.md`。
> 这是 **ToB 第二类接口**——把 agent runtime（记忆 + 工具 + 多步循环）做成对外端点，SI 套自己 UI 即用，不必自己搭 agent、也不必写 skill。
> **稳定性**：对外契约，破坏性变更走版本。当前 = `v1`（draft，未冻结）。
> 依据：`vendor/pilotdeck/src/adapters/channel/api-server/ApiServerChannel.ts`（内部 inbound 接缝，已升格为对外产品）。

## 0. 它和「能力面」的唯一区别：有状态 vs 无状态

同样是 OpenAI chat 协议，**靠 base_url 路径自解释**：

| | ① 能力面 `/v1/chat/completions` | ② Agent 面 `/v1/agent/chat/completions` |
| --- | --- | --- |
| 状态 | **无状态**：每次传全量 `messages` | **有状态**：`X-Session-Id` 串上下文 + 白盒记忆 |
| 工具 | 工具调用由调用方驱动多步 | **agent 自己用工具、自己多步循环**，一次请求出最终结果 |
| 记忆 | 无 | 跨回合记忆（runtime 提供） |
| 计量单位 | tokens | **agent 回合** |
| 给谁 | 想自己搭 agent 的 SI | 想直接要"会记事会用工具的 agent"的 SI |

一句话：① 给算力，② 给 agent。

## 1. 对话 — `POST /v1/agent/chat/completions`

OpenAI Chat Completions 兼容。与 ① 的差异只有两点：路径前缀 `/v1/agent`、用 `X-Session-Id` 维持会话。

请求头：

| 头 | 必填 | 说明 |
| --- | --- | --- |
| `Authorization: Bearer <key>` | ✓ | 同一客户 key（key 标了是否买了 Agent 面） |
| `X-Session-Id: <id>` | | 会话标识；缺省自动生成并在响应头回带。同 id 串接上下文 + 记忆 |

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

## 3. 会话管理

| 操作 | 端点 | 说明 |
| --- | --- | --- |
| 起/续会话 | 带 `X-Session-Id` 打 `/v1/agent/chat/completions` | 缺省自动建 |
| 读会话历史 | `GET /v1/agent/sessions/{id}/messages` | 只读，供 UI 回放（映射 runtime 会话读 API） |
| 列会话 | `GET /v1/agent/sessions` | 只读 |

> 会话读 API 映射到 `runtime-contract.md` §契约四（gateway SDK 数据面）。换 runtime 要求提供等价的会话只读能力。

## 4. 计量与双重计费规避

- ② 的计量单位 = **agent 回合**（一次 `/v1/agent/chat/completions` 完成算一回合，附 `turn_completed.usage` 里的 token 汇总）。
- ② 内部 agent 经 `model.providers` **回打 ① 网关**做推理：这些回环调用带 **internal 标记**（内部头/key），**只计 ② 的回合，不在 ① 侧重复计 tokens**。
- 用量写**同一条结构化用量日志**（与 ①③ 统一，见 `capability-api.md` §用量）。

## 5. 错误

OpenAI 风格，与 ① 统一：

```json
{ "error": { "message": "...", "type": "invalid_request_error|server_error|rate_limit_error", "code": "optional" } }
```

- session 冲突（并发回合）→ `429`，`type: rate_limit_error`。
- 未购买 Agent 面的 key 打 `/v1/agent/*` → `403`。

## 6. 版本

- 路径前缀 `v1`。OpenAI 兼容子集承诺向后兼容。
- 破坏性变更 → 升 `v2`，并行保留弃用周期。
- draft 未冻结前以本文件为准。

## 7. 给对接方的并行约定

- **先 mock**：Agent 面可先用一个"回固定多步结果 + 假 session"的 mock 立起来，SI 即可对 UI；真 runtime 后置接入，契约不变。
- SI 选 ① 还是 ②：要最大自由度自己搭 agent → 用 ①；要开箱即用的 agent → 用 ②。两者同 key、同前门，可混用。
