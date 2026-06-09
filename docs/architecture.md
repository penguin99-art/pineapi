# 架构

> 配套：原则见 `../AGENTS.md`，搭建顺序见 `build-plan.md`，融合见 `pilotdeck-integration.md`，能力面见 `model-gateway.md`，**各层接口契约见 `interfaces/`**。

## 0. 全景图（整图）

🔵=Core(可发 B 端)，🟠=灵魂(C 端专属)。

```
                          ┌─────────────────────────────────────────────────────────────┐
                          │                      使用方 / 入口                              │
   🔵 ToB 能力面 ───────► │  SI 集成方        Studio(UI)   桌伴(Mac)   Phone   外设         │
   (OpenAI 兼容,卖能力)   └───┬──────────────────┬───────────┬──────────────────────────────┘
                              │                  │           │
        ┌─────────────────────┘                  │ WS/HTTP   │  总线/HTTP(假数据可驱动)
        │  OpenAI 兼容                            │ gateway   │
        │  (chat/STT/TTS/图/视频)                 │ 契约      ▼
        ▼                                         │   ┌───────────────────────────────┐
╔══════════════════════════════════════╗         │   │ 🟠 Piny 灵魂层 (自研·C端专属)    │
║ 🔵 L2 模型层                           ║         │   │  感知: 级联门控→理解→认主         ║
║   Pinea Model Gateway (薄·FastAPI)    ║         │   │        发 presence/voice         │
║   路由 + schema归一 + 治理(鉴权/计量)  ║         │   │  表达: 状态机(6态唯一真相源)      │
║   ┌──────────────────────────────┐   ║         │   │        →灯带/voice 渲染          │
║   │ ollama   文本/视觉/embed (已验)│   ║         │   │  soul: 主动时机(presence+记忆)   │
║   │ speaches STT  ← MVP 首做       │   ║         │   └──────┬───────────────▲─────────┘
║   │ Piper/Kokoro  TTS             │   ║         │          │ voice/presence│ state
║   │ ComfyUI  生图/视频            │   ║         │          ▼               │
║   │ (任一腿可换 vllm-omni,按盒子)  │   ║         │   ╔══════════════════════╪═════════╗
║   └──────────────────────────────┘   ║         │   ║  PineaState 总线 (灵魂线)          ║
╚════════════════▲═════════════════════╝         │   ║  presence|voice|intent|state      ║
                 │ OpenAI 端点(模型线)            │   ╚══════▲═══════════════╪═══════════╝
                 │                                │          │接缝1 inbound  │接缝2 outbound
                 │                                │          │(submitTurn)   │(hook/WS事件)
╔════════════════╧════════════════════════════════╧══════════╧═══════════════╧═══════════╗
║ 🔵 L3 记忆 + L4 执行 = Agent Runtime 层  (当前实现: PilotDeck · submodule 锁版只读 · 可换) ║
║   agent loop · 工具/MCP · Skill/Workflow · 智能路由 · 白盒记忆(可看/改/回滚·WorkSpace隔离)  ║
║   扩展点(零改核心): api_server channel · 磁盘 hook · MCP · gateway SDK · model.providers   ║
║                                                                                          ║
║   🔵 ToB 公共 Skills ──► 磁盘 skill 扩展点 (只依赖 网关能力端点 + skill契约, 不碰 soul)     ║
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
         SI 也直接打 Gateway(这就是 ToB 能力面)
灵魂线:  感知 ──voice/presence──► [接缝1] api_server channel → gateway.submitTurn() → agent 回合
         agent ──[接缝2] hook脚本/WS事件──► PineaState 总线 → 表达(灯带/TTS/Studio/桌伴)
```

> **Agent Runtime 是一层、可换**：L3/L4 当前用 PilotDeck，但自研件只依赖它的*契约/扩展点*（`model.providers` / api_server channel / 磁盘 hook / gateway SDK），**从不 import 其内部模块**。所以 runtime 是一个被抽象掉的可替换层——换掉 PilotDeck 只需重接这几个扩展点，🟠 灵魂层、🔵 能力面、Studio 全不动。这正是红线 1/5 的副产物。

## 1. 两层

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
   表达  灯带 6 态 + voice + PineaState 总线
   soul  陪 / 主动的时机（由感知 + 记忆校准）
```

## 2. 完整栈（自底向上）

| 层 | 是什么 | 复用 / 自研 |
| --- | --- | --- |
| L0 硬件 | 盒子 / 麦阵列 / 摄像头 / 灯带 / 传感器 | 自研硬件 |
| L1 系统 | OS + GPU 调度 + 设备 adapter + LAN/mDNS + 物理开关 | 标准件 + 自研 |
| L2 模型 | **Pinea Model Gateway**（OpenAI 兼容能力面：chat→ollama / STT / TTS / 生图 / 视频）+ MiniCPM/Qwen/gpt-oss（LocalAI 已弃用） | 自研薄网关 + 复用后端（详见 `model-gateway.md`） |
| L3 记忆 | 白盒记忆（可看/改/回滚/WorkSpace 隔离）— 当前由 runtime 提供 | 自有护城河 |
| L4 执行 | **Agent Runtime**（agent loop / 工具 / Skill / Workflow / 智能路由 / Always-on）；当前实现 = PilotDeck，**可换** | 复用·可替换层 |
| L5 感知·表达 | VAD/MiniCPM-o/认脸 + 灯带/voice/PineaState | **自研（灵魂）** |
| L6 交互面 | Studio / 桌伴 / Phone / 外设 | 自研 + 复用 channel |
| L7 应用 | 资料 / 创作 / 家庭 / 行业 Workflow | 自研 + 生态 |

L3/L4 = Agent Runtime 层（当前实现 PilotDeck，只依赖契约故可换），L5 自研——L5 是 Piny 区别于"装应用的私有云"的灵魂，结构上别人没有。L2 自研薄网关（只路由+归一+治理，不做推理），是对外卖的「能力面」ToB 接口；推理后端仍复用 ollama/whisper/comfy 等。

## 3. 四进程 + 一总线

```
① Pinea Model Gateway 能力面,Python/FastAPI  OpenAI 兼容端点(chat→ollama/STT/TTS/生图/视频)
② PilotDeck Gateway   核心,TS/Node           agent/记忆/路由/任务（gateway 默认 :18789，本项目 18790；web UI :3001）
③ 感知服务             Python                       发 presence/voice 事件
④ 表达服务             任意                         收 state,渲染灯带/TTS
        ③④ 经 ──► PineaState 总线 ◄── 互联
   Studio / 桌伴 ──► ② Gateway(WS/HTTP)
   SI 集成方   ──► ① Model Gateway(OpenAI 兼容,ToB 能力面)
```

两条连接线：**模型线**（②→① OpenAI 端点；SI 也直接打 ①）、**灵魂线**（③④ 总线 + ② `submitTurn`）。①详见 `model-gateway.md`。

## 4. 两个接缝（集成命门）

### 接缝 1 · Inbound（感知/桌伴 → 内核）

```
感知/桌伴 → (PineaState 总线 / HTTP) → PilotDeck 内置 api_server channel → gateway.submitTurn() → agent 回合
```

依据：`gateway.submitTurn(input)` 返回 `AsyncIterable<GatewayEvent>`（见 `src/adapters/channel/*/`、`gateway/protocol/types.ts`）。MVP 走内置 `api_server` channel，零改核心。

### 接缝 2 · Outbound（内核 → 表达/Studio）

```
PilotDeck（hook 脚本 / gateway WS 事件）→ PineaState 总线 → 表达渲染器(灯带/TTS/Studio/桌伴)
```

两种挂法：
- 磁盘插件 hook（`SessionStart / PreModelRequest / Stop / PostToolUse`，见 `src/extension/hooks/protocol/events.ts`）跑脚本发态。
- 表达 / Studio 作为 `GatewayWsClient` 消费流式事件（`assistant_text_delta` / `tool_call_*` / `error`）。

## 5. PineaState 事件 schema

```json
{ "type": "presence|voice|intent|state",
  "ts": 0,
  "source": "mic|camera|pilotdeck",
  "payload": {},
  "confidence": 0.0 }
```

感知发 `presence/voice/intent`；表达消费 `state`。状态机 6 态：`idle / listening / thinking / speaking / working / error`。

## 6. 感知级联（被动流必经）

绝不把原始流灌进 agent。由轻到重，每级仅在上一级触发时跑：

```
L0 采集 → L1 门控(VAD/motion,常驻近零成本) → L2 理解(MiniCPM-o/Whisper,事件触发) → L3 识别(认脸/声纹) → L4 价值判断 → 发事件
```

MVP 只做 L1 + L2 + 最小 L3（认主），发 `presence` 和 `voice` 两类事件。

## 7. 扩展性（ToB / ToC 都靠它）

- 加场景/行业 → 加 Skill / Workflow
- 加入口/设备 → 加 channel（或走 api_server）
- 加客户/家庭成员 → 加 WorkSpace（记忆隔离）
- 加模型/模态 → 加 Model Gateway 的一个 backend adapter + 路由表一行
- ToB 两类接口：① **能力面** = Model Gateway 的 OpenAI 兼容端点（卖模型能力给 SI）；② **公共 Skills** = PilotDeck 磁盘 skill 扩展点（卖可复用行业能力）
- ToB → 直接发 🔵Core（不含 🟠），单客户一盒子

核心永远不动，变化点单一。
