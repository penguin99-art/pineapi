# 架构

> 配套：原则见 `../AGENTS.md`，搭建顺序见 `build-plan.md`，融合见 `pilotdeck-integration.md`。

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
| L2 模型 | **LocalAI**（LLM/embed/STT/TTS/生图）+ MiniCPM/Qwen | 复用 |
| L3 记忆 | **PilotDeck 白盒记忆**（可看/改/回滚/WorkSpace 隔离） | 自有护城河 |
| L4 执行 | **PilotDeck** agent loop / 工具 / Skill / Workflow / 智能路由 / Always-on | 自有内核 |
| L5 感知·表达 | VAD/MiniCPM-o/认脸 + 灯带/voice/PineaState | **自研（灵魂）** |
| L6 交互面 | Studio / 桌伴 / Phone / 外设 | 自研 + 复用 channel |
| L7 应用 | 资料 / 创作 / 家庭 / 行业 Workflow | 自研 + 生态 |

L3/L4 复用 PilotDeck，L5 自研——L5 是 Piny 区别于"装应用的私有云"的灵魂，结构上别人没有。

## 3. 四进程 + 一总线

```
① LocalAI            模型,Python/Go    OpenAI 兼容端点
② PilotDeck Gateway  核心,TS/Node      agent/记忆/路由/任务（默认 :3001）
③ 感知服务            Python                  发 presence/voice 事件
④ 表达服务            任意                    收 state,渲染灯带/TTS
        ③④ 经 ──► PineaState 总线 ◄── 互联
   Studio / 桌伴 ──► ② Gateway(WS/HTTP)
```

两条连接线：**模型线**（②→① OpenAI 端点）、**灵魂线**（③④ 总线 + ② `submitTurn`）。

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
- 加模型 → 改 LocalAI 配置
- ToB → 直接发 🔵Core（不含 🟠），单客户一盒子

核心永远不动，变化点单一。
