# 架构

> 配套：原则见 `../AGENTS.md`，搭建顺序见 `build-plan.md`，融合见 `pilotdeck-integration.md`，网关设计见 `model-gateway.md`，对外 ToB 入口见 `interfaces/tob-overview.md`，**各层接口契约见 `interfaces/`**。
> 术语：**"网关/单一前门" = 整个 Pinea Model Gateway（承载三类 ToB）**；**"能力面" 专指 ①（无状态模型层）**，勿混。
> 当前 ToB 形态：**卖一台松果派上的本机能力**。SI App / 容器优先跑在盒子本机，经 `127.0.0.1` 调 Gateway；Gateway 内置**简单 Bearer Token 门锁**，不做多租户/计费/配额。若绑定到 LAN/WAN，必须开启该门锁。

## 0. 全景图（整图）

🔵=Core（可无头发 B 端），🟠=Piny 灵魂层（C 端专属）。先看清一个原则：

> **Pinea Core 是能力底座；Piny toC 是把 Core 变成"有身体、有关系、有主动性"的产品层。**  
> ToB 只拿 🔵 Core；ToC = 🔵 Core + 🟠 Piny 灵魂层。

### 0.1 分层总图：谁在上面用，谁在下面支撑

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 使用方 / 产品入口                                                             │
│                                                                              │
│  ToB: SI App / 容器(盒子本机优先)                                             │
│  ToC: 桌伴 / PineaStudio / Phone / 外设                                       │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │                                              │
                │ HTTP: ①能力面 ②Agent面 ③Skills管理           │ WS/HTTP/设备事件
                ▼                                              ▼
┌──────────────────────────────────────┐        ┌──────────────────────────────┐
│ 🔵 Pinea Model Gateway                │        │ 🟠 Piny 灵魂层                │
│  设备前门，默认 127.0.0.1              │        │  感知 / Soul / 表达           │
│  OpenAI 兼容 + Agent 转发 + Skill 管理 │        │  只存在于 C 端产品            │
│  + wss 流式代理(透传 runtime 事件)     │        │                              │
│  路由 / schema归一 / 发现 / 健康 / 日志 │        │                              │
└───────────────┬──────────────────────┘        └──────────────┬───────────────┘
                │                                              │
                │ ②/v1/agent 转发                              │ 接缝1 submitTurn
                ▼                                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 🔵 Agent Runtime 层（当前实现：PilotDeck，可换）                              │
│  agent loop / 白盒记忆 / tools-MCP / skills / workspace / 路由策略             │
│  扩展点：api_server channel / hook / MCP / gateway SDK / model.providers      │
└───────────────┬──────────────────────────────────────────────▲───────────────┘
                │                                              │
                │ model.providers                              │ 接缝2 hook/WS 生命周期
                ▼                                              │
┌──────────────────────────────────────┐        ┌──────────────┴───────────────┐
│ 🔵 模型后端                            │        │ 🟠 PineaState 总线             │
│  ollama: 文本/视觉/embed               │        │  presence / voice / intent     │
│  speaches: STT                         │        │  core.lifecycle / state         │
│  Piper/Kokoro: TTS                     │        │  只有 Soul 写最终 state         │
│  ComfyUI: 生图/视频                     │        └──────────────────────────────┘
└──────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ 🔵 L1 系统：OS / GPU显存调度 / 设备 adapter / LAN-mDNS / 物理开关              │
├──────────────────────────────────────────────────────────────────────────────┤
│ 🔵 L0 硬件：盒子 / 麦阵列 / 摄像头 / 灯带 / 传感器                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

这张图只表达位置关系：

- `Gateway` 是**设备单一前门**：ToB 走它的 OpenAI/Agent/Skill 接口；ToC 的 Studio/桌伴/Phone 也走它的 wss 流式面拿 runtime 事件、发输入、看状态。Gateway 对流式只做**透明代理**（转发 runtime `GatewayEvent`，不改协议、不掺 soul），所以 Studio 仍只依赖 gateway 契约（红线 5）。
- `Agent Runtime` 是大脑执行层：记忆、工具、skills、workspace、agent loop 都在这里。
- `Piny 灵魂层` 是 C 端产品层：感知世界、判断关系和主动时机、把 Core 生命周期翻译成表达状态。麦克风/摄像头/传感器等**设备感知输入**直接进感知层，不经 Gateway。
- `PineaState` 是灵魂层内部总线，不是 ToB 接口，也不是 Core memory。

### 0.2 ToB 逻辑：SI 只集成 Core，不碰 Soul

```
SI App / 容器（盒子本机优先）
        │
        │ base_url = http://127.0.0.1:18800
        │ 外放 LAN/WAN 时加 Authorization: Bearer <token>
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 🔵 Pinea Model Gateway                                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│ ① 能力面      /v1/chat · /v1/audio · /v1/images · /v1/video · /v1/embeddings  │
│               无状态，直达模型后端                                            │
│                                                                              │
│ ② Agent 面    /v1/agent/* + X-Session-Id                                      │
│               有状态，转发 runtime api_server，使用记忆/工具/skills             │
│                                                                              │
│ ③ Skills 管理 /v1/skills/*                                                    │
│               安装/列表/启停；内部落 runtime skill 目录，由②的 agent 自动触发    │
└──────────────────────────────────────────────────────────────────────────────┘
        │                    │                              │
        ▼                    ▼                              ▼
  模型后端 adapter      Agent Runtime api_server       runtime skill 目录
```

ToB 的产品边界：

- SI 的用户登录、业务权限、行业 UI 都在 SI App；Pinea Core 只提供本机模型 / agent / skill 能力。
- `Bearer Token` 是设备安全门锁，只解决"谁能调设备口"，不做多租户、计费、配额或购买范围控制。
- ToB 公共 Skills 只依赖 Gateway 能力端点 + runtime skill/tool 契约，绝不依赖 🟠 Soul，所以能随 Core 发 B 端。

### 0.3 ToC 逻辑：Piny 用 Soul 把 Core 变成产品体验

```
桌伴 / Studio / Phone / 外设 / 麦克风 / 摄像头
        │
        │ click / wake / speech / motion / presence / interrupt
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 🟠 Perception 感知                                                            │
│  VAD / motion / ASR / 视觉理解 / 认主 → 归一成 presence、voice、intent 事件      │
└───────────────┬──────────────────────────────────────────────────────────────┘
                ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║ 🟠 PineaState 总线                                                           ║
║  输入事件：presence / voice / intent                                         ║
║  Core 回流：core.lifecycle                                                   ║
║  输出状态：state（idle/listening/thinking/speaking/working/error）             ║
╚═══════════════╤══════════════════════════════════════════════▲═══════════════╝
                │                                              │
                ▼                                              │
┌──────────────────────────────────────────────────────────────┴───────────────┐
│ 🟠 Soul                                                                        │
│  1. 读 PineaState + Soul 私有记忆（主人、关系、节律、打扰偏好）                  │
│  2. 实时反射层：规则/fast model 先判 ignore / listen / reply / escalate          │
│  3. 可即时写 state 或触发短表达；只有 escalate 才升级到 Core agent 回合           │
│  4. 消费 core.lifecycle，并写唯一 state                                         │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ 仅 escalate 走接缝1：submitTurn(input) / api_server channel
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 🔵 Agent Runtime                                                              │
│  复杂任务、工具调用、skills、白盒记忆、workspace 执行                            │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ 接缝2：hook / WS / GatewayEvent → core.lifecycle
                ▼
        回到 PineaState → Soul 写 state → Expression 渲染

Expression 表达：灯带 / TTS / 桌伴动效 / Phone / Studio / 外设反馈
约束：表达只订阅 state，不自行判断"现在该亮什么/说什么"。
```

ToC 的产品边界：

- `Perception` 只把世界翻译成事件，不直接驱动灯效，也不直接改 Core memory。
- `Soul` 是 ToC 中枢：它有自己的 Soul memory，负责关系、主动时机、打扰判断、实时响应路由和 6 态状态机。
- `fast model` 是实时反射层的一条腿，用于低延迟判断和短表达；它不是 agent loop，不调用工具，不写 Core memory。
- 需要长期上下文、白盒记忆、工具/MCP、skills、多步计划或文件 workspace 时，Soul 才把事件升级（escalate）为 Core agent 回合。
- **escalate 必须带上下文**：fast path 的短交互不进 Core memory，agent 不知道"刚才聊了什么"。Soul 升级时把近期 fast-path 交互摘要随 `submitTurn` 的 `message` 前缀或 `attachments` 一并传入（见 `interfaces/pineastate-bus.md` §3 Inbound），保证对话连续性。
- `Core` 仍然只做 agent 执行、工具、skills、白盒记忆；不 import 感知/表达/soul。
- `Expression` 只渲染 Soul 写入的 `state`。状态机只有一个，避免 Studio、灯带、TTS 各自判态。

实时响应路由（Soul 的快/慢分流）：

| 判断 | 延迟目标 | 动作 | 进 Agent Runtime？ |
| --- | --- | --- | --- |
| `ignore` | 近实时 | 不响应，只更新 presence/节律 | 否 |
| `listen` | 近实时 | 切 `listening`，等用户继续说 | 否 |
| `reply` | 低延迟 | fast model / 模板生成短回复，表达层播报 | 否 |
| `escalate` | 可慢 | Soul 调 `submitTurn` 进入 agent loop | 是 |

`fast model` 的模型能力仍属于 🔵 L2（可以是 Gateway 后面的轻量模型/分类器/小 LLM）；区别在**控制权在 🟠 Soul**：Soul 只拿它做路由和短反应，不能让它绕过状态机直接控制表达。

### 0.4 三条线 + 两个接缝

```
模型线:
  Agent Runtime ─model.providers─► Gateway ─OpenAI端点─► ollama/speaches/Piper/ComfyUI

ToB 线:
  SI App ─► Gateway ─┬─ ① 能力面: 无状态模型能力
                     ├─ ② Agent 面: 有状态 agent
                     └─ ③ Skills 管理: 行业能力安装/启停

灵魂线:
  Perception ─► PineaState ─► Soul ─fast path─► state / 短表达
                                  └─slow path: [接缝1 submitTurn]─► Agent Runtime
  Agent Runtime ─[接缝2 hook/WS]─► PineaState(core.lifecycle) ─► Soul 写 state ─► Expression
```

两条接缝是命门：

- **接缝 1 · Inbound**：只有 Soul 判定 `escalate` 时才触发 Core agent 回合。MVP 走 PilotDeck 内置 `api_server` channel / `gateway.submitTurn()`，零改核心。
- **接缝 2 · Outbound**：Core 生命周期回到 Soul。可用 hook 脚本或 `GatewayWsClient` 消费 runtime 事件，统一写入 `core.lifecycle`，最终仍由 Soul 写 `state`。

> **Agent Runtime 是一层、可换**：L3/L4 当前用 PilotDeck，但自研件只依赖它的*契约/扩展点*（`model.providers` / api_server channel / 磁盘 hook / gateway SDK），**从不 import 其内部模块**。所以 runtime 是一个被抽象掉的可替换层——换掉 PilotDeck 只需重接这几个扩展点，🟠 灵魂层、🔵 能力面、Studio 全不动。这正是红线 1/5 的副产物。

> **预留：agent-native 调用（未来，非 MVP）**。现在三类 ToB 是"给人类开发者的 API 方言"。将来让**别的 agent 自己发现、自己派活**（agent 网络）= 在单一前门**再挂协议适配头**，agent 核（②+③）不变：
>
> - **MCP 头**：把 ①②③ 暴露成 MCP server（MCP 已是业界事实标准，现行规格 **2025-11-25**，OpenAI/Google/Microsoft 均已采用），宿主 agent（Cursor/Claude/Codex 等）拿这台盒子当工具箱。最便宜的第一个 agent-native 赢。
> - **A2A 头**：A2A 协议已发布 **v1.0** 并由 **Linux Foundation** 托管。发布 **Agent Card**（`/.well-known/agent-card.json`，skills 取自 ③、capabilities 取自 `/v1/capabilities`，可自动生成）+ 任务协议；复用 L1 的 **mDNS** 让局域网内盒子/agent 互相**发现并承接**。反向"委派给远端 agent"= runtime 的 tool/MCP 扩展点，零改核心。
> - **Responses 头**：OpenAI Responses API 已是其推荐的有状态 agent 原语；若其形状成为跨厂事实标准，加 `/v1/agent/responses` 翻译头映射到 ② 同一接缝（见 `interfaces/agent-api.md` §0.1），核不动。
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


| 类         | SI 怎么用                                       | 落点                                          |
| --------- | -------------------------------------------- | ------------------------------------------- |
| ① 能力面     | SI App 直接调本机 OpenAI 兼容端点                     | Gateway → 模型后端                              |
| ② Agent 面 | SI App 调 `/v1/agent/`*，用 `X-Session-Id` 维持会话 | Gateway → runtime `api_server`              |
| ③ Skills  | SI / 我们交付 `SKILL.md` 包；通过本机接口安装/启停           | Gateway 管理面 → runtime skill 目录 → agent 自动触发 |


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

### 2.1 记忆分层（Core memory vs Soul memory）

两套记忆，**物理与职责都分开**，是 🔵/🟠 边界在数据面的体现：

| | 🔵 Core memory（白盒记忆） | 🟠 Soul memory（灵魂私有） |
| --- | --- | --- |
| 存什么 | 对话历史、用户教的知识、任务上下文、工具记录、workspace 长期记忆 | 主人身份特征、关系状态、出现/离开节律、打扰偏好、表达偏好、主动冷却 |
| 谁拥有 | Agent Runtime（当前 PilotDeck，可看/改/回滚/WorkSpace 隔离） | Soul 进程自己的存储 |
| 谁能读 | ToB ② Agent 面、ToC 经 agent 回合 | 只有 Soul（绝不进 Core） |
| 发 B 端 | 随 Core 发 | 不发（拆灵魂时整块拿掉） |

一句话：**Core memory 让它会做事；Soul memory 让它像"你的 Piny"。** Soul 可以把"该让 agent 记住的事实"通过一次 agent 回合写进 Core memory，但反过来 Core 永不读 Soul memory。

### 2.2 主动性：Soul 时机引擎 vs Core 调度

ToC 的"主动"有两个来源，别混：

- **🟠 Soul 时机引擎**（关系驱动）：由 presence + Soul memory 决定"现在要不要主动招呼/陪伴/提醒"。它只**决定时机**并发起一次 agent 回合或短表达，不自己实现 agent loop。
- **🔵 Core always-on / cron**（任务驱动）：runtime 自带的文件系统触发（always-on）和定时（cron），用于项目类后台作业。ToB 也用得到。

两者都通过同一个接缝 1 触发 Core 回合，互不替代：Soul 管"陪人"，always-on/cron 管"干活"。

## 3. 完整栈（自底向上）


| 层        | 是什么                                                                                                         | 复用 / 自研                             |
| -------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| L0 硬件    | 盒子 / 麦阵列 / 摄像头 / 灯带 / 传感器                                                                                   | 自研硬件                                |
| L1 系统    | OS + GPU 调度 + 设备 adapter + LAN/mDNS + 物理开关                                                                  | 标准件 + 自研                            |
| L2 模型    | **Pinea Model Gateway**（OpenAI 兼容设备前门：chat→ollama / STT / TTS / 生图 / 视频）+ MiniCPM/Qwen/gpt-oss（LocalAI 已弃用） | 自研薄网关 + 复用后端（详见 `model-gateway.md`） |
| L3 记忆    | 白盒记忆（可看/改/回滚/WorkSpace 隔离）— 当前由 runtime 提供                                                                  | 自有护城河                               |
| L4 执行    | **Agent Runtime**（agent loop / 工具 / Skill / Workflow / 智能路由 / Always-on）；当前实现 = PilotDeck，**可换**            | 复用·可替换层                             |
| L5 感知·表达 | VAD/MiniCPM-o/认脸 + 灯带/voice/PineaState                                                                      | **自研（灵魂）**                          |
| L6 交互面   | Studio / 桌伴 / Phone / 外设                                                                                    | 自研 + 复用 channel                     |
| L7 应用    | 资料 / 创作 / 家庭 / 行业 Workflow                                                                                  | 自研 + 生态                             |


L3/L4 = Agent Runtime 层（当前实现 PilotDeck，只依赖契约故可换），L5 自研——L5 是 Piny 区别于"装应用的私有云"的灵魂，结构上别人没有。L2 自研网关（"薄"= 三条负面清单：不做推理 / 不做 agent loop / 不掺 soul，其余作为设备控制面允许有状态，见 `model-gateway.md` §2），是三类 ToB 的**本机单一前门**（① 能力面 / ② Agent 面 / ③ Skills 管理）；推理后端仍复用 ollama/whisper/comfy 等。

## 4. 五进程 + 一总线

> 进程用 `P1~P5` 编号，避免与 §0 的 ToB 三类 `①②③` 混淆。

```
P1 Pinea Model Gateway  Python/FastAPI  本机单一前门;OpenAI 兼容端点 + Skills 管理接口 + wss 流式代理
P2 PilotDeck Gateway    核心,TS/Node    agent/记忆/路由/任务（gateway 默认 :18789，本项目 18790；api_server channel 默认 :8642；web UI :3001）
P3 感知服务             Python          发 presence/voice 事件
P4 Soul 服务            任意            收 presence/voice/core.lifecycle, 写唯一 state, 必要时 submitTurn
P5 表达服务             任意            收 state,渲染灯带/TTS/桌伴/Studio/Phone
        P3 P4 P5 经 ──► PineaState 总线 ◄── 互联
   Studio / 桌伴 / Phone ──► P1 Model Gateway(wss 流式面;P1 透明代理 P2 的 GatewayEvent)
   SI App(本机/可选LAN)   ──► P1 Model Gateway(默认localhost;外放需Bearer,ToB 三类: ①能力面/②Agent面/③Skills 管理)
```

连接线：**模型线**（P2 ─model.providers→ P1 OpenAI 端点；SI App 在盒子本机也打 P1）、**前门线**（ToC UI 经 P1 wss 流式面，P1 透明代理 P2 的 api_server/事件流；P2 api_server 默认 :8642）、**灵魂线**（P3/P4/P5 经总线 + P4 调 P2 `submitTurn`）。P1 详见 `model-gateway.md`。

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

`intent` 事件可带路由建议，例如 `{ "route": "ignore|listen|reply|escalate" }`；最终是否进入 Agent Runtime 仍由 Soul 决定（见 §0.3 实时响应路由）。

## 7. 感知级联（被动流必经）

绝不把原始流灌进 agent，也不把每个语音事件都灌进 Agent Runtime。被动流先过感知级联，再交 Soul 的实时反射层做路由。由轻到重，每级仅在上一级触发时跑：

```
L0 采集 → L1 门控(VAD/motion,常驻近零成本)
       → L2 理解(ASR/视觉/fast model,事件触发)
       → L3 识别(认脸/声纹)
       → L4 Soul 路由(ignore/listen/reply/escalate)
       → 仅 escalate 进入 Agent Runtime
```

MVP 只做 L1 + L2 + 最小 L3（认主）+ L4 简单路由规则。fast model 可后置替换规则路由，但定位不变：低延迟判断/短反应，不承担工具调用、长记忆和多步执行。

## 8. 扩展性（ToB / ToC 都靠它）

- 加场景/行业 → 加 Skill / Workflow
- 加入口/设备 → 加 channel（或走 api_server）
- 加客户/家庭成员 → 加 WorkSpace（记忆隔离）
- 加模型/模态 → 加 Model Gateway 的一个 backend adapter + 路由表一行
- ToB 三类接口（共用 Model Gateway 设备单一前门；默认 `127.0.0.1`，外放需 Bearer Token，自底向上叠）：
  - ① **能力面**（无状态）= Gateway OpenAI 兼容端点 `/v1/chat|audio|images|video`（卖算力+模态给 SI）→ `interfaces/capability-api.md`
  - ② **Agent 面**（有状态）= Gateway `/v1/agent/`*（OpenAI+session，转发 api_server，卖开箱即用 agent）→ `interfaces/agent-api.md`
  - ③ **公共 Skills** = Gateway 本机管理接口安装/启停，内部落 PilotDeck skill 目录（卖可复用行业能力）→ `interfaces/skill-contract.md`
  - 区分：① 给算力、② 给 agent、③ 给行业 agent。② 是把 runtime 的 api_server 接缝升格为对外产品，零改核心。
- ToB → 直接发 🔵Core（不含 🟠），单客户一盒子

核心永远不动，变化点单一。