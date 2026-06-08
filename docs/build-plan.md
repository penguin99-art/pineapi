# 搭建顺序（施工图）

> 配套：架构见 `architecture.md`，原则见 `../AGENTS.md`，融合见 `pilotdeck-integration.md`。
> 规则：每步有「通过标准」，过了再下一步，不跳步。风险前置、假数据先行。

## 阶段总览

| 阶段 | 目标 | 标志 |
| --- | --- | --- |
| **P0 打通** | 本地模型 + 内核 + 总线骨架跑通 | 一句话进 → agent 用本地模型回 → 表达端亮灯 |
| **P1 灵魂** | 感知认主 + 表达 6 态 + 主动触发 | 人进屋,Piny 主动招呼,灯随状态变 |
| **P2 体验** | Studio 壳 + 桌伴 + 资料/记忆闭环 | 资料处理 + 记忆 + Workflow 复用成形 |

## 搭建顺序（6 步）

### 第 0 步 · 起跑线（最先做，验证最大风险）
- 把 PilotDeck 以 submodule 拉进 `vendor/pilotdeck`，`pnpm install && pnpm server` 跑起来。
- 配 LocalAI，起 MiniCPM / Qwen，暴露 OpenAI 兼容端点。
- 改 PilotDeck 配置 `model.providers`：指向 LocalAI（`protocol:"openai"`，`url` 指 LocalAI，填模型名）。
- **通过标准**：PilotDeck 用**本地模型**完成一次**带工具调用**的多步任务（读文件→总结→写回）。tool calling 不稳就先调模型/提示词/采样，别往下走。

### 第 1 步 · 总线骨架
- 起 PineaState 总线（Redis pub/sub 或 WebSocket 二选一，先简单）。
- 定义事件 schema（见 architecture §5），写收发两个最小 demo。
- **通过标准**：A 进程发事件，B 进程秒收，schema 校验通过。

### 第 2 步 · Outbound 接缝（先做出口，因为可全程假数据驱动）
- 写表达渲染器：订阅总线 `state` → 驱动灯带 / TTS（TTS 走 LocalAI）。
- 写一个 PilotDeck 磁盘 hook 脚本：`SessionStart/Stop/PreModelRequest` → 往总线发 `state`。
- **通过标准**：手动给内核发一句 → 灯带走 `thinking→speaking→idle`，无需感知就能演示。

### 第 3 步 · Inbound 接缝
- 用 PilotDeck 内置 `api_server` channel；写一个最小客户端，把「假 voice 事件」当输入调 `submitTurn`。
- **通过标准**：往总线丢一条假 `voice:{text}` → 内核起回合 → 出口灯带联动。**全链路闭环（仍假数据）打通**。

### 第 4 步 · 感知服务（替换假数据）
- Python 感知：L1 VAD/motion 门控（常驻）→ L2 MiniCPM-o/Whisper（事件触发）→ 最小 L3 认主 → 发 `presence/voice`。
- **通过标准**：真人说话 → 真 `voice` 事件 → 走第 3 步链路触发内核。第 2/3 步的假数据被真感知替换。

### 第 5 步 · soul 主动性
- 加状态机进程：综合 `presence`（认主）+ 记忆，决定主动招呼/沉默的时机，发 `state`。
- **通过标准**：主人进屋被认出 → Piny 主动招呼；陌生人 / 主人忙 → 不打扰。

### 第 6 步 · Studio + 桌伴 + 资料闭环
- Studio：全新 UI，套 `gateway/protocol` + `GatewayWsClient`（见 pilotdeck-integration §UI）。
- 桌伴：盒子侧 `ChannelAdapter`（仿 `api_server`），Mac 瘦客户端走 LAN WS + API key，先 T0（文件/通知）。
- 资料闭环：inbox 自动路由 + 记忆入库 + 一个可复用 Workflow。
- **通过标准**：丢资料进 inbox → 自动处理入记忆 → 之后能被记忆+Workflow 复用；Studio 看到全过程。

## 三个工程判断

1. **风险前置**：第 0 步的本地模型 tool calling 是成败点,死磕它再做别的。
2. **假数据先行**：第 2/3 步全程假数据,让四进程并行,不互相阻塞;第 4 步才换真感知。
3. **状态唯一真相源**：只有第 5 步的状态机往总线写目标态,所有表达端只订阅渲染。
