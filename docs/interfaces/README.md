# 接口契约总览（各层之间怎么对接）

> 配套：架构见 `../architecture.md`，网关设计见 `../model-gateway.md`，原则见 `../../AGENTS.md`。
> **只看对外 ToB？** → 直接读 [`tob-overview.md`](tob-overview.md)（按层次汇总的三类 ToB 入口）。
> 目的：把每层之间的接口**先定死成契约**，让各层（含 ToB）照契约**并行开发、互不阻塞**（AGENTS §3「假数据先行」「每步可独立验证」）。

## 契约地图（按 `architecture.md` §0 分层）

三类 ToB 共用 **Pinea Model Gateway 单一前门**（一个 base_url + 一个 key），按"自己搭多少 vs 白嫖多少"自底向上叠：① 给算力、② 给 agent、③ 给行业 agent。

| 接缝 / 契约 | 谁定义 | 谁消费 | 文档 | 用途 |
| --- | --- | --- | --- | --- |
| **① L2 能力面 API**（无状态） | 我们（OpenAI 兼容） | SI 集成方 · Runtime(model.providers) | [`capability-api.md`](capability-api.md) | **ToB 第一类**：卖模型能力（算力+模态） |
| **② L3/L4 Agent 面 API**（有状态） | 我们（OpenAI+session，复用 api_server） | SI 集成方 | [`agent-api.md`](agent-api.md) | **ToB 第二类**：卖开箱即用 agent（记忆+工具+多步） |
| **③ L7 公共 Skill 契约** | PilotDeck（SKILL.md）+ 我们约定 | 行业交付 · SI | [`skill-contract.md`](skill-contract.md) | **ToB 第三类**：卖可复用行业能力 |
| **L3/L4 Runtime 契约** | PilotDeck（扩展点） | 灵魂层 · 能力面 · Studio | [`runtime-contract.md`](runtime-contract.md) | runtime 可换的边界；自研只碰这些 |
| **L5 灵魂线（PineaState 总线）** | 我们 | 感知 ↔ 表达 ↔ Runtime | [`pineastate-bus.md`](pineastate-bus.md) | 🟠 感知/表达；桥到 Runtime 两接缝 |

> ② Agent 面 = 把 Runtime 契约的 `api_server` inbound 接缝从"内部"升格为"对外产品"，零改核心（见 `agent-api.md` / `runtime-contract.md`）。

## 三类边界，三种稳定性

1. **对外契约（ToB，最稳）**：能力面 API + Agent 面 API + 公共 Skill 契约。一旦发出去给 SI，破坏性变更要走版本。`capability-api.md` / `agent-api.md` 标了 stability，OpenAI 兼容子集承诺永不破。
2. **对内可换契约**：Runtime 契约。我们只依赖 PilotDeck 的*扩展点*（不 import 内部），所以换 runtime = 重接这几个契约。
3. **自研内部总线**：PineaState。我们自己定，但两端（感知/表达）靠它解耦并行。

## 红线落到契约上

- 🔵/🟠 边界：灵魂层只经 **PineaState 总线 + Runtime 两接缝** 接 Core，Core 不 import 感知/表达 → 见 `runtime-contract.md` / `pineastate-bus.md`。
- 不改 PilotDeck 核心：能力面在 runtime *下面*（model.providers），skill 走*磁盘扩展点*，全是官方扩展点。
- 语言边界即接口：Python(感知/网关) ↔ TS(runtime) 只经 OpenAI 端点 / 总线，不混栈。

## ToB 怎么靠这些并行推进

- **① 能力面**：照 `capability-api.md` 先用假后端（mock STT/TTS/图）把 API 立起来，SI 可同时对接；后端真模型后置替换。
- **② Agent 面**：照 `agent-api.md` 先用"回固定多步结果 + 假 session"的 mock 立端点，SI 可同时对 UI；真 runtime 后置接入。
- **③ 公共 Skills**：照 `skill-contract.md` 写 SKILL.md + 调能力面端点，先用能力面 mock 联调，不等真模型。
