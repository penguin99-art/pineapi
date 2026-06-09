# 架构

> 配套：原则见 `../AGENTS.md`，搭建顺序见 `build-plan.md`，融合见 `pilotdeck-integration.md`，网关设计见 `model-gateway.md`，对外 ToB 入口见 `interfaces/tob-overview.md`，**各层接口契约见 `interfaces/`**。
> 术语：**"网关/单一前门" = 整个 Pinea Model Gateway（承载三类 ToB）**；**"能力面" 专指 ①（无状态模型层）**，勿混。
> 当前 ToB 形态：**卖一台松果派上的本机能力**。SI App / 容器优先跑在盒子本机，经 `127.0.0.1` 调 Gateway；Gateway 内置**简单 Bearer Token 门锁**，不做多租户/计费/配额。若绑定到 LAN/WAN，必须开启该门锁。

## 0. 全景图（整图）

🔵=Core(可发 B 端)，🟠=灵魂(C 端专属)。

```
                          ┌─────────────────────────────────────────────────────────────┐
                          │                      使用方 / 入口                              │
   🔵 ToB 本机前门 ─────► │  SI App(盒子本机)  Studio(UI)   桌伴(Mac)   Phone   外设         │
   (本机;外放需Bearer)    └───┬──────────────────┬───────────┬──────────────────────────────┘
   ①能力面 ②Agent面 ③Skills    │                  │           │
        ┌─────────────────────┘                  │ WS/HTTP   │  总线/HTTP(假数据可驱动)
        │  OpenAI 兼容 + 本机管理接口              │ gateway   │
        │  ①chat/STT/TTS/图/视频                  │ 契约      ▼
        │  ②/v1/agent(有状态)  ③/v1/skills        │
        ▼                                         │   ┌───────────────────────────────┐
╔══════════════════════════════════════╗         │   │ 🟠 Piny 灵魂层 (自研·C端专属)    │
║ 🔵 L2 模型层                           ║         │   │  感知: 级联门控→理解→认主         ║
║   Pinea Model Gateway (薄·FastAPI)    ║         │   │        发 presence/voice         │
║   路由 + schema归一 + 发现/健康/日志    ║         │   │  soul: 状态机(6态唯一真相源)      │
║   ┌──────────────────────────────┐   ║         │   │        主动时机(presence+记忆)   │
║   │ ollama   文本/视觉/embed (已验)│   ║         │   │  表达: 灯带/voice/桌伴渲染       │
║   │ speaches STT  ← MVP 首做       │   ║         │   └──────┬───────────────▲─────────┘
║   │ Piper/Kokoro  TTS             │   ║         │          │ voice/presence│ state
║   │ ComfyUI  生图/视频            │   ║         │          ▼               │
║   │ (任一腿可换 vllm-omni,按盒子)  │   ║         │   ╔══════════════════════╪═════════╗
║   └──────────────────────────────┘   ║         │   ║  PineaState 总线 (灵魂线)          ║
╚═══════════▲══════════╪═══════════════╝         │   ║  presence|voice|intent|lifecycle|state ║
   ①model.providers    │②/v1/agent 转发           │   ╚══════▲═══════════════╪═══════════╝
   (模型线,Runtime→网关)│(网关→api_server,有状态)   │          │接缝1 inbound  │接缝2 outbound
                 │      ▼                          │          │(submitTurn)   │(hook/WS事件)
╔════════════════╧════════════════════════════════╧══════════╧═══════════════╧═══════════╗
║ 🔵 L3 记忆 + L4 执行 = Agent Runtime 层  (当前实现: PilotDeck · submodule 锁版只读 · 可换) ║
║   agent loop · 工具/MCP · Skill/Workflow · 智能路由 · 白盒记忆(可看/改/回滚·WorkSpace隔离)  ║
║   扩展点(零改核心): api_server channel · 磁盘 hook · MCP · gateway SDK · model.providers   ║
║                                                                                          ║
║   🔵 ToB 公共 Skills ──► 本机管理接口安装, 内部落 skill 目录(只依赖网关能力+契约,不碰 soul) ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝
                 │ 配置 model.providers 指向网关
╔════════════════╧═════════════════════════════════════════════════════════════════════════╗
║ 🔵 L1 系统  OS · GPU/显存调度(资源仲裁) · 设备 adapter · LAN/mDNS · 物理开关                 ║
╠══════════════════════════════════════════════════════════════════════════════════════════╣
║ 🔵 L0 硬件  盒子 · 麦阵列 · 摄像头 · 灯带 · 传感器                                          ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝
```

两条线、两个接缝：
```
模型线:  Runtime ─model.providers─► Model Gateway ─OpenAI端点─► ollama/speaches/Piper/ComfyUI
ToB:     SI App(盒子本机/可选LAN) ─► Model Gateway ─┬ ①/v1/chat… (无状态,直打后端)
                                                     ├ ②/v1/agent… (有状态,转发 api_server)
                                                     └ ③/v1/skills… (本机管理;安装后由②的 agent 自动触发)
灵魂线:  感知 ──voice/presence──► PineaState → Soul ─[接缝1]→ gateway.submitTurn() → agent 回合
         agent ──[接缝2] hook脚本/WS事件──► PineaState(core.lifecycle) → Soul 写 state → 表达
```

### 0.1 ToC Piny 支撑图（局部图）

ToC 不另造一套 agent。Piny 只做"身体 + 关系 + 主动性"，复杂执行仍复用 Core 的 Agent Runtime。

```
桌伴 / Studio / Phone / 外设 / 麦克风 / 摄像头
        │
        │ 输入事件: click / voice / wake / motion / presence / interrupt
        ▼
┌────────────────────────────────────────────────────────────────────┐
│ 🟠 感知 Perception                                                  │
│  VAD / motion → ASR/视觉理解 → 认主 → 事件归一                       │
└───────────────┬────────────────────────────────────────────────────┘
                │ presence / voice / intent
                ▼
╔════════════════════════════════════════════════════════════════════╗
║ 🟠 PineaState 总线                                                  ║
║  事件: presence | voice | intent | core.lifecycle | state           ║
║  约束: 只有 Soul 状态机写最终 state                                 ║
╚═══════════════╤═══════════════════════════════════════▲════════════╝
                │                                       │ state
                ▼                                       │
┌───────────────────────────────────────────────────────┴────────────┐
│ 🟠 Soul                                                             │
│  - 关系/主人识别上下文                                               │
│  - 主动时机与打扰判断                                                │
│  - 是否触发 Core agent 回合                                          │
│  - 根据 Core 生命周期改写 6 态: idle/listening/thinking/speaking/     │
│    working/error                                                     │
└───────────────┬────────────────────────────────────────────────────┘
                │ submitTurn(input) / api_server channel
                ▼
╔════════════════════════════════════════════════════════════════════╗
║ 🔵 Core: Agent Runtime                                             ║
║  agent loop / memory / tools-MCP / skills / workspace / route       ║
╚═══════════════╤════════════════════════════════════════════════════╝
                │ hook / WS / GatewayEvent
                ▼
        core.lifecycle 回流到 PineaState
                │
                ▼
┌────────────────────────────────────────────────────────────────────┐
│ 🟠 表达 Expression                                                  │
│  订阅 state，只做渲染: 灯带 / TTS / 桌伴 / Phone / Studio / 外设反馈  │
└────────────────────────────────────────────────────────────────────┘
```

落地原则：

- `Perception` 只把世界翻译成事件，不直接驱动灯效，也不直接改 Core memory。
- `Soul` 是 ToC 的中枢：读 PineaState + Soul 私有记忆，决定是否发起 Core 回合，并且是 6 态唯一写入者。
- `Expression` 无脑订阅 `state` 渲染，不能自行判断"现在该亮什么/说什么"。
- `Core` 仍是 🔵：只处理 agent 执行、工具、skills、白盒记忆；不 import 感知/表达/soul。

> **Agent Runtime 是一层、可换**：L3/L4 当前用 PilotDeck，但自研件只依赖它的*契约/扩展点*（`model.providers` / api_server channel / 磁盘 hook / gateway SDK），**从不 import 其内部模块**。所以 runtime 是一个被抽象掉的可替换层——换掉 PilotDeck 只需重接这几个扩展点，🟠 灵魂层、🔵 能力面、Studio 全不动。这正是红线 1/5 的副产物。

> **预留：agent-native 调用（未来，非 MVP）**。现在三类 ToB 是"给人类开发者的 API 方言"。将来让**别的 agent 自己发现、自己派活**（agent 网络）= 在单一前门**再挂两个协议适配头**，agent 核（②+③）不变：
> - **MCP 头**：把 ①②③ 暴露成 MCP server，宿主 agent（Cursor/Claude 等）拿这台盒子当工具箱。最便宜的第一个 agent-native 赢。
> - **A2A 头**：发布 **Agent Card**（`/.well-known/agent-card.json`，skills 取自 ③、capabilities 取自 `/v1/capabilities`，可自动生成）+ 任务协议；复用 L1 的 **mDNS** 让局域网内盒子/agent 互相**发现并承接**。反向"委派给远端 agent"= runtime 的 tool/MCP 扩展点，零改核心。
> 架构在此**预留"前门协议适配器"格位**；具体实现待 spike（`research/spikes/agent-native.md`，未立），风险前置原则下先做网关本体。

## 1. ToB 本机集成模式（松果派）

当前 ToB 不是"云端 API 服务"，而是**卖一台装好 Pinea Core 的松果派设备**。SI 的应用 / 容器 / 服务优先部署在盒子本机，经 `127.0.0.1` 调 Pinea Model Gateway；如果业务需要，也可以把 Gateway 绑定到 LAN，但必须开启简单 Bearer Token。

```
行业用户 / SI 前端
        │
        ▼
SI App / 容器（跑在松果派本机）
        │  localhost
        ▼
Pinea Model Gateway（默认 127.0.0.1；外放需 Bearer Token）
        ├─ ① 能力面：/v1/chat · /v1/audio/* · /v1/images/* · /v1/video/* · /v1/embeddings
        ├─ ② Agent 面：/v1/agent/*（转发 runtime api_server，有状态）
        └─ ③ Skills 管理面：/v1/skills/*（安装/列表/启停；内部落 runtime skill 目录）
```

边界含义：

- **Pinea Gateway 是设备能力 daemon**，默认只监听 `127.0.0.1`。它内置一个简单 Bearer Token 门锁：本机开发/封闭部署可关闭；一旦绑定到 LAN/WAN，必须开启。
- **外部用户访问、业务登录、行业权限**由 SI App 负责；Pinea Core 只提供本机模型 / agent / skill 能力。
- Bearer Token 只解决"谁能调设备能力口"的安全问题，不承担多租户、计费、配额或 ①②③ 购买范围控制。那些属于商业治理，MVP 不做。

三类 ToB 在本机模式下的定位：

| 类 | SI 怎么用 | 落点 |
| --- | --- | --- |
| ① 能力面 | SI App 直接调本机 OpenAI 兼容端点 | Gateway → 模型后端 |
| ② Agent 面 | SI App 调 `/v1/agent/*`，用 `X-Session-Id` 维持会话 | Gateway → runtime `api_server` |
| ③ Skills | SI / 我们交付 `SKILL.md` 包；通过本机接口安装/启停 | Gateway 管理面 → runtime skill 目录 → agent 自动触发 |

`SKILL.md` 是交付物格式，磁盘目录是 runtime 实现细节。对 SI 暴露**本机 Skill 管理接口**更稳：可隐藏 PilotDeck 目录结构、做格式校验、版本/启停/升级；内部仍可落到 `~/.pilotdeck/skills/<name>/` 或项目级 `.pilotdeck/skills/<name>/`。

## 2. 两层

```
🔵 Pinea Core（无头 · 复用 PilotDeck · B 端也用）
   执行  模型推理 + Agent + Skill/Workflow + Tool/MCP
   记忆  白盒记忆 / 知识库 / context（可看可改可回滚）
   数据  文件/媒体服务 + 共享目录
   安全  权限 / 审计 / 数据隔离
   SDK   gateway API 契约 + 应用装配 + 部署
        │ Piny 在上面注入↓（不进 Core）
🟠 Piny 灵魂层（自研 · C 端专属）
   感知  持续级联 + 认主
   soul  6 态状态机 + 陪伴/主动时机（由感知 + 记忆校准）
   表达  灯带 / voice / 桌伴 / Studio / Phone 渲染
   总线  PineaState（presence / voice / intent / core.lifecycle / state）
```

## 3. 完整栈（自底向上）

| 层 | 是什么 | 复用 / 自研 |
| --- | --- | --- |
| L0 硬件 | 盒子 / 麦阵列 / 摄像头 / 灯带 / 传感器 | 自研硬件 |
| L1 系统 | OS + GPU 调度 + 设备 adapter + LAN/mDNS + 物理开关 | 标准件 + 自研 |
| L2 模型 | **Pinea Model Gateway**（OpenAI 兼容设备前门：chat→ollama / STT / TTS / 生图 / 视频）+ MiniCPM/Qwen/gpt-oss（LocalAI 已弃用） | 自研薄网关 + 复用后端（详见 `model-gateway.md`） |
| L3 记忆 | 白盒记忆（可看/改/回滚/WorkSpace 隔离）— 当前由 runtime 提供 | 自有护城河 |
| L4 执行 | **Agent Runtime**（agent loop / 工具 / Skill / Workflow / 智能路由 / Always-on）；当前实现 = PilotDeck，**可换** | 复用·可替换层 |
| L5 感知·表达 | VAD/MiniCPM-o/认脸 + 灯带/voice/PineaState | **自研（灵魂）** |
| L6 交互面 | Studio / 桌伴 / Phone / 外设 | 自研 + 复用 channel |
| L7 应用 | 资料 / 创作 / 家庭 / 行业 Workflow | 自研 + 生态 |

L3/L4 = Agent Runtime 层（当前实现 PilotDeck，只依赖契约故可换），L5 自研——L5 是 Piny 区别于"装应用的私有云"的灵魂，结构上别人没有。L2 自研薄网关（只路由+归一+发现/健康/日志，不做推理），是三类 ToB 的**本机单一前门**（① 能力面 / ② Agent 面 / ③ Skills 管理）；推理后端仍复用 ollama/whisper/comfy 等。

## 4. 五进程 + 一总线

> 进程用 `P1~P5` 编号，避免与 §0 的 ToB 三类 `①②③` 混淆。

```
P1 Pinea Model Gateway  Python/FastAPI  本机单一前门;OpenAI 兼容端点 + Skills 管理接口
P2 PilotDeck Gateway    核心,TS/Node    agent/记忆/路由/任务（gateway 默认 :18789，本项目 18790；web UI :3001）
P3 感知服务             Python          发 presence/voice 事件
P4 Soul 服务            任意            收 presence/voice/core.lifecycle, 写唯一 state, 必要时 submitTurn
P5 表达服务             任意            收 state,渲染灯带/TTS/桌伴/Studio/Phone
        P3 P4 P5 经 ──► PineaState 总线 ◄── 互联
   Studio / 桌伴 ──► P2 PilotDeck Gateway(WS/HTTP)
   SI App(本机/可选LAN) ──► P1 Model Gateway(默认localhost;外放需Bearer,ToB 三类: ①能力面/②Agent面/③Skills 管理)
```

两条连接线：**模型线**（P2 ─model.providers→ P1 OpenAI 端点；SI App 在盒子本机也打 P1）、**灵魂线**（P3/P4/P5 经总线 + P4 调 P2 `submitTurn`）。P1 详见 `model-gateway.md`。

## 5. 两个接缝（集成命门）

### 接缝 1 · Inbound（感知/桌伴 → 内核）

```
感知/桌伴 → PineaState 事件 → Soul 判断 → PilotDeck 内置 api_server channel → gateway.submitTurn() → agent 回合
```

依据：`gateway.submitTurn(input)` 返回 `AsyncIterable<GatewayEvent>`（见 `src/adapters/channel/*/`、`gateway/protocol/types.ts`）。MVP 走内置 `api_server` channel，零改核心。

### 接缝 2 · Outbound（内核 → 表达/Studio）

```
PilotDeck（hook 脚本 / gateway WS 事件）→ PineaState(core.lifecycle) → Soul 状态机写 state → 表达渲染器
```

两种挂法：
- 磁盘插件 hook（`SessionStart / PreModelRequest / Stop / PostToolUse`，见 `src/extension/hooks/protocol/events.ts`）跑脚本发 `core.lifecycle` 事件。
- Soul / Studio 作为 `GatewayWsClient` 消费流式事件（`assistant_text_delta` / `tool_call_*` / `error`）；表达状态仍只来自 PineaState 的 `state`。

## 6. PineaState 事件 schema

```json
{ "type": "presence|voice|intent|core.lifecycle|state",
  "ts": 0,
  "source": "mic|camera|pilotdeck|soul",
  "payload": {},
  "confidence": 0.0 }
```

感知发 `presence/voice/intent`；Core 生命周期事件回流为 `core.lifecycle`；Soul 状态机消费这些事件并写唯一 `state`；表达只消费 `state`。状态机 6 态：`idle / listening / thinking / speaking / working / error`。

## 7. 感知级联（被动流必经）

绝不把原始流灌进 agent。由轻到重，每级仅在上一级触发时跑：

```
L0 采集 → L1 门控(VAD/motion,常驻近零成本) → L2 理解(MiniCPM-o/Whisper,事件触发) → L3 识别(认脸/声纹) → L4 价值判断 → 发事件
```

MVP 只做 L1 + L2 + 最小 L3（认主），发 `presence` 和 `voice` 两类事件。

## 8. 扩展性（ToB / ToC 都靠它）

- 加场景/行业 → 加 Skill / Workflow
- 加入口/设备 → 加 channel（或走 api_server）
- 加客户/家庭成员 → 加 WorkSpace（记忆隔离）
- 加模型/模态 → 加 Model Gateway 的一个 backend adapter + 路由表一行
- ToB 三类接口（共用 Model Gateway 设备单一前门；默认 `127.0.0.1`，外放需 Bearer Token，自底向上叠）：
  - ① **能力面**（无状态）= Gateway OpenAI 兼容端点 `/v1/chat|audio|images|video`（卖算力+模态给 SI）→ `interfaces/capability-api.md`
  - ② **Agent 面**（有状态）= Gateway `/v1/agent/*`（OpenAI+session，转发 api_server，卖开箱即用 agent）→ `interfaces/agent-api.md`
  - ③ **公共 Skills** = Gateway 本机管理接口安装/启停，内部落 PilotDeck skill 目录（卖可复用行业能力）→ `interfaces/skill-contract.md`
  - 区分：① 给算力、② 给 agent、③ 给行业 agent。② 是把 runtime 的 api_server 接缝升格为对外产品，零改核心。
- ToB → 直接发 🔵Core（不含 🟠），单客户一盒子

核心永远不动，变化点单一。
