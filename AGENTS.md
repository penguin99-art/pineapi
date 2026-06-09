# 开发指导原则（必读）

本文件是本仓开发（含 AI 辅助编码）的最高约束。写代码前先读这里。违反红线的实现一律不接受。

## 1. 我们在做什么

Piny = 本地常驻的个人 AI 节点。两层：

- **🔵 Pinea Core（无头，复用 PilotDeck）**：执行 / 记忆 / 数据 / 安全 / SDK。B 端也复用。
- **🟠 Piny 灵魂层（自研，C 端专属）**：感知（认主）/ 表达（灯带·voice）/ soul（主动时机）。

模型层 = 自研 **Pinea Model Gateway**（OpenAI 兼容能力面：chat→ollama / STT / TTS / 生图 / 视频；只路由+归一+治理，不做推理；详见 `docs/model-gateway.md`）；LocalAI 已弃用，不再当门面。执行内核 = **Agent Runtime 层**，当前实现 = PilotDeck（自有，可商用可改）；自研只依赖其契约/扩展点，故 runtime 原则上可换（见 `docs/architecture.md` §0）。

## 2. 红线（违反即返工）

1. **不改 PilotDeck 核心。** 所有自研只走官方扩展点：`ChannelAdapter` / 磁盘插件 hook / MCP / `gateway` SDK / 配置。PilotDeck 以 submodule 锁版本，只读。必须改 → 改回上游再锁新版本，绝不在本地留补丁。
2. **🔵/🟠 边界不可漏。** 灵魂（认主 / 灯带 / 陪伴 / soul）绝不渗进 Core。Core 任何模块不得 import 感知 / 表达。否则 B 端发货要"拆灵魂"，架构就脏了。
3. **语言边界即接口。** Python（感知 / 模型）与 TS（PilotDeck）只通过「PineaState 总线 + `gateway.submitTurn`」「OpenAI 端点」交互，不混栈、不互相 import。
4. **状态机是表达的唯一真相源。** 只有一个状态机往总线写目标态（6 态）；灯带 / TTS / Studio / 桌伴只订阅渲染，自己不判断该显示什么。
5. **UI 只依赖 gateway 契约。** Studio 只 import `gateway/protocol` + `GatewayWsClient`（+ web 读 API），绝不 import `agent/` `context/` `tool/` 内部模块。

## 3. 工程纪律

1. **风险前置。** 最大不确定性是「本地模型能否稳定跑 agentic tool calling」。先死磕本地模型（ollama 直连）的 tool calling，再做其他（已过：gpt-oss:20b 20/20）。别先做灯效。
2. **假数据先行。** 总线两端先用假数据联调（手动发假 presence/voice 测 inbound，手动发假 state 测 outbound），让四个进程并行开发，不互相阻塞。
3. **每步可独立验证。** 按 `docs/build-plan.md` 的顺序走，每步过了「通过标准」再进下一步，不跳步。
4. **先 api_server，后专属 channel。** MVP 感知/桌伴走 PilotDeck 内置 `api_server` channel（零改核心）。专属 channel 要等明确必要，且作为通用特性加回 PilotDeck 上游，不在 fork 改。

## 4. 当前不做

- 不改 PilotDeck 核心代码。
- 不做被动流级联以外的复杂感知（MVP）。
- 不做桌伴 T2+ 高权限（截屏 / 写回 / 自动操作）。
- 不做完整插件市场 / 完整外设体系 / 完整家庭节点。
- 不承诺未 benchmark 的 SKU 能力、并发、tok/s。
- 不把医疗 / 教育等垂直场景写进 Core。

## 5. agent-native 工作法（怎么写这套代码）

详见 [`docs/agent-native-workflow.md`](docs/agent-native-workflow.md)。可执行约束：

1. **人只做三件事**：跨域激活（拿别的领域撞架构）/ 定 intent 与约束 / 古法分析（人工审关键产出，尤其两个接缝与 🔵🟠 边界的决策）。其余琐碎交给 agent。
2. **Living doc 是控制面**：每个技术未知数先在 `research/spikes/<name>.md` 立一张可回写的表（仿 testplan），agent 边跑边更新；spike 有边界、出结论就退役，不漫游。
3. **skill 要克制**：模型本来就强，别预造一堆 skill/rule；只为**真正分布外**的流程建 skill（实测 harness / 自纠错 / 设备测量）。规则越多越压制探索。
4. **知识注入先于动手**：写哪块前，先把权威源（PilotDeck 源码、MiniCPM/ollama·vllm-omni/MCP 文档）喂给 agent 蒸成 `research/knowledge/` 的 markdown，再实现。
5. **约束驱动**：把盒子真实约束（功耗 / NPU / 端侧延迟）喂进去，让方案只在可行域里探索，别选端侧跑不动的设计。
6. **风险前置即 spike**：build-plan 第 0 步（本地模型 tool calling）就是第一个 spike，见 `research/spikes/tool-calling.md`（已过），过了再写集成代码。

## 6. 提交前自检

- [ ] 没有改 `vendor/pilotdeck` 里的核心代码？
- [ ] 灵魂逻辑没有渗进 Core，Core 没 import 感知/表达？
- [ ] 跨语言只走总线 / OpenAI 端点，没有混栈 import？
- [ ] 表达端只订阅状态机，没有自行判态？
- [ ] 这一步有明确的「通过标准」且已验证？
- [ ] 涉及的技术未知数有对应 spike living doc，且结论已回写？
