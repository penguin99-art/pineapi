# Pinea / Piny

> 私有代码仓。本仓承载 Piny（个人 AI 节点）与 Pinea Core 的落地实现。
> 架构与商业背景的完整版在文档仓 `~/work/doc/pineapi/`；本仓只放**开发需要的指导**。

## 一句话

Piny 是一台本地常驻的个人 AI 节点。技术上分两层：

- **🔵 Pinea Core（无头）**：执行 / 记忆 / 数据 / 安全 / SDK。**直接复用 PilotDeck**（自有开源产品）。B 端集成商也复用这一层。
- **🟠 Piny 灵魂层（C 端专属）**：感知（认主）/ 表达（灯带·voice）/ soul（主动的时机）。**自研**，通过扩展点挂进 Core，不进 Core。

模型层 = 自研 **Pinea Model Gateway**（OpenAI 兼容能力面：chat→ollama / STT / TTS / 生图 / 视频；详见 `docs/model-gateway.md`）。LocalAI 已弃用。

## 怎么做（核心判断）

**不从零搭 Core。PilotDeck 的 `src/` 就是 🔵Core 的现成实现。** 我们只做三件事：

1. 起模型层：ollama（文本，已验）+ 自研 Pinea Model Gateway（多模态能力面）。
2. 自研 🟠灵魂层（感知 / 表达）。
3. 在两个接缝把灵魂层接进去，**不改 PilotDeck 核心**。

## 文档导航

| 文档 | 看什么 |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | **开发指导原则（必读，含红线 + agent-native 工作法）** |
| [`docs/architecture.md`](docs/architecture.md) | 分层架构 · 全景图 · 四进程 · 两个接缝 · 事件 schema |
| [`docs/model-gateway.md`](docs/model-gateway.md) | L2 能力面网关设计（ToB 模型能力对外） |
| [`docs/interfaces/tob-overview.md`](docs/interfaces/tob-overview.md) | **ToB 接口总览（按层次）**——对外卖什么、怎么对接的唯一入口 |
| [`docs/interfaces/`](docs/interfaces/) | 各层接口契约全集（ToB 三类 + runtime · 总线） |
| [`docs/build-plan.md`](docs/build-plan.md) | 搭建顺序 · 每步通过标准 · 感知/表达细化 |
| [`docs/pilotdeck-integration.md`](docs/pilotdeck-integration.md) | 仓库结构 · 怎么融 PilotDeck · 零改核心接入地图 · 上游同步 |
| [`docs/agent-native-workflow.md`](docs/agent-native-workflow.md) | **怎么写这套代码**：人机分工 · living-doc 控制面 · skill 克制 · 知识注入 |
| [`research/spikes/`](research/spikes/) | 有边界的技术 spike（第一个：本地模型 tool calling 风险） |

## 现在从哪开始

读 `AGENTS.md` → 按 `docs/build-plan.md` §搭建顺序的第 0 步起手（先把 PilotDeck 跑起来 + 接本地模型，ollama 直连）。第 0 步已过，接口契约见 `docs/interfaces/`。
