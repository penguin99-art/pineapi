# L5 灵魂线 · PineaState 总线契约

> 配套：架构见 `../architecture.md` §3/§5/§6，runtime 接缝见 `runtime-contract.md`，总览见 `README.md`。
> 这是 **🟠 灵魂层自研契约**——感知、表达、soul 三进程靠它解耦并行。**Core 不消费它**（红线 2）。

## 0. 角色

```
感知服务 ──发 presence/voice/intent──► PineaState 总线 ──表达服务 收 state──► 灯带/TTS
                                              ▲                    │
                soul 状态机(唯一写 state) ─────┘                    └─ Studio/桌伴 也可订阅渲染
```

总线实现：Redis pub/sub 或 WebSocket 二选一（MVP 先简单，见 `build-plan.md` 第 1 步）。

## 1. 事件 schema（统一信封）

```json
{ "type": "presence|voice|intent|state",
  "ts": 1733700000000,
  "source": "mic|camera|pilotdeck|soul",
  "payload": {},
  "confidence": 0.0 }
```

| type | 谁发 | 谁收 | payload 例 |
| --- | --- | --- | --- |
| `presence` | 感知（认主/在场） | soul | `{ "who":"owner|stranger|unknown", "present":true }` |
| `voice` | 感知（VAD→ASR） | soul / inbound 桥 | `{ "text":"...", "lang":"zh" }` |
| `intent` | 感知（价值判断） | soul | `{ "kind":"greet|ask|...", "urgency":0.x }` |
| `state` | **仅 soul 状态机** | 表达 / Studio / 桌伴 | `{ "state":"thinking", "reason":"..." }` |

## 2. 状态机 6 态（表达的唯一真相源）

`idle | listening | thinking | speaking | working | error`

- **只有 soul 状态机往总线写 `state`**（红线 4）。表达端只订阅渲染，**自己不判态**。
- 表达端把 6 态映射到灯带/TTS 表现（映射表由表达层自定，不回写总线）。

## 3. 桥到 Runtime 两接缝（灵魂线 ↔ 模型线 的唯一通道）

灵魂层经 `runtime-contract.md` 的两接缝与 Core 交互，**不直接 import Core**：

### Inbound：`voice` → 起 agent 回合
```
感知发 voice:{text} → soul 决定要回应 → 调 api_server 的 POST /v1/chat/completions
                                          (X-Hermes-Session-Id = 主人会话)
                                       或 gateway.submitTurn({channelKey:"api_server", message:text})
```

### Outbound：runtime 生命周期 → `state`
runtime 的 hook/事件 → 映射成 `state` 发总线（建议默认映射）：

| runtime 信号（见 runtime-contract §三） | → state |
| --- | --- |
| `SessionStart` / `UserPromptSubmit` | `thinking` |
| `assistant_text_delta` 首块 / 开始 TTS | `speaking` |
| `PreToolUse` / `tool_call_started` | `working` |
| `Stop` / `turn_completed` | `idle` |
| `error{recoverable:false}` / `StopFailure` | `error` |
| 感知 `voice` 开始采集 | `listening` |

> 映射只有一处：soul 状态机。hook 脚本/订阅者把 runtime 信号喂给状态机，状态机决定目标态再发 `state`——避免多源判态。

## 4. 并行约定（假数据先行）

- **测 inbound**：手动往总线发假 `voice:{text}` → 看是否起回合 → 出口灯带联动（不需真感知）。
- **测 outbound**：手动给 runtime 发一句 → 看 hook→`state`→灯带走 `thinking→speaking→idle`（不需真感知）。
- 四进程（感知/表达/soul/runtime）各自照本契约对假数据开发，互不阻塞。

## 5. 红线落点

- Core **不订阅**总线、不 import 感知/表达；灵魂层经两接缝单向接入 → 发 B 端整块摘除 🟠，🔵 照跑。
- `state` 单写者 = soul 状态机。
- 跨语言（Python 感知 ↔ TS runtime）只经 总线 + OpenAI 端点，不混栈。
