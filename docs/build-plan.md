# 搭建顺序（施工图）

> 配套：架构见 `architecture.md`，原则见 `../AGENTS.md`，融合见 `pilotdeck-integration.md`，能力面/接口见 `model-gateway.md` + `interfaces/`。
> 规则：每步有「通过标准」，过了再下一步，不跳步。风险前置、假数据先行。
> 两条并行线：下面 6 步是 **🟠灵魂主线**；**🔵能力面/公共 Skills（ToB）** 是并行的 Core 线（不依赖灵魂），照 `interfaces/capability-api.md` + `interfaces/skill-contract.md` 推进，见本页末「ToB 并行线」。

## 阶段总览

| 阶段 | 目标 | 标志 |
| --- | --- | --- |
| **P0 打通** | 本地模型 + 内核 + 总线骨架跑通 | 一句话进 → agent 用本地模型回 → 表达端亮灯 |
| **P1 灵魂** | 感知认主 + 表达 6 态 + 主动触发 | 人进屋,Piny 主动招呼,灯随状态变 |
| **P2 体验** | Studio 壳 + 桌伴 + 资料/记忆闭环 | 资料处理 + 记忆 + Workflow 复用成形 |
| **TB ToB（并行）** | 能力面网关 + 公共 Skills | SI 经 OpenAI 端点用多模态；行业 skill 可复用发货 |

## 搭建顺序（6 步）

### 第 0 步 · 起跑线（最先做，验证最大风险）✅ 已过
- 把 PilotDeck 以 submodule 拉进 `vendor/pilotdeck`，`pnpm install && pnpm server` 跑起来。
- 起本地模型：**ollama 直连**（OpenAI 兼容 `:11434/v1`），跑 gpt-oss / MiniCPM / Qwen。（LocalAI 已弃用，见 `model-gateway.md` §1。）
- 改 PilotDeck 配置 `model.providers`：MVP 直指 ollama（`protocol:"openai"`，`url` 指 `:11434/v1`）；正式接 Pinea Model Gateway（能力面）后改指网关。
- **通过标准**：PilotDeck 用**本地模型**完成一次**带工具调用**的多步任务（读文件→总结→写回）。→ **已达成：gpt-oss:20b 经 PilotDeck 20/20=100%**（见 `../research/spikes/tool-calling.md`）。

### 第 1 步 · 总线骨架
- 起 PineaState 总线（Redis pub/sub 或 WebSocket 二选一，先简单）。
- 定义事件 schema（见 architecture §5），写收发两个最小 demo。
- **通过标准**：A 进程发事件，B 进程秒收，schema 校验通过。

### 第 2 步 · Outbound 接缝（先做出口，因为可全程假数据驱动）
- 写表达渲染器：订阅总线 `state` → 驱动灯带 / TTS（TTS 走能力面网关 `/v1/audio/speech`）。
- 写一个 PilotDeck 磁盘 hook 脚本：`SessionStart/Stop/PreModelRequest` → 往总线发 **`core.lifecycle`** 事件（hook 不直接写 `state`，红线 4）。
- 写一个**直通版 soul**（约 20 行）：订阅 `core.lifecycle`，按 `interfaces/pineastate-bus.md` §3 的默认映射机械写 `state`。第 5 步真 soul 替换它，桥与表达端契约不变。
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

## ToB 并行线（🔵Core，不依赖灵魂，可同时推进）

> 契约见 `interfaces/capability-api.md`（①）+ `interfaces/agent-api.md`（②）+ `interfaces/skill-contract.md`（③）。设计见 `model-gateway.md`。
> 三类 ToB 共用 Model Gateway 设备前门（默认本机，外放需 Bearer Token + TLS 规则）。
> 原则：**B 端的"扎实"不等于端点多，等于三件事——契约语义无歧义、每步有硬验收、SI 能自助对接。**

- **T0 网关骨架 + chat 透传（①）✅ 已过**：FastAPI（`gateway/`，:18800）起 `/v1/chat/completions`→ollama；PilotDeck `model.providers` 指过来。**通过标准**：经网关跑通带工具的多步任务。→ **已达成：经网关 tool-calling 19/20**，conformance `gateway/tests/` 6/6 绿。
- **T1 STT 端点（①）**：`/v1/audio/transcriptions` → speaches；见 `../research/spikes/stt-gateway.md`。**通过标准**：中文 ~1min 音频转写可用、RTF≤0.5；**且在 ollama 推理进行中调用，STT 延迟不明显劣化**（QoS 原则"交互类>批量类"的第一次实测，见 `model-gateway.md` §6.4）。
- **T2 Agent 面（②）**：`/v1/agent/chat/completions` 转发 api_server。**通过标准**：会话键按 `{app_id}:{session_id}:{gen}` 映射；带 session 多轮、agent 自用工具多步；同 session 并发 `429 session_busy`、设备级并发满 `429 queue_full`+`Retry-After`；usage 从 SSE 聚合回填非流式响应；agent 权限以 `network:false` 起跑；端口绑定表自检通过（api_server 锁 127.0.0.1、P2 web UI 关闭，见 `model-gateway.md` §6.1）。
- **T2.5 网关增值层（②）**：会话登记/回放（`GET /v1/agent/sessions*`）、`background` 异步聚合（`GET /v1/agent/turns/{id}`）、逻辑删除（`gen`+1 + 清网关侧数据）。**通过标准**：SI 全程只靠对外端点完成"开会话→异步跑长任务→轮询拿结果→回放历史→删会话"；P1 重启后登记/结果/`gen` 不丢。
- **T3 「音频资料整理」skill（③）**：Skill 包经 `/v1/skills/*` 安装，调网关 STT → 去重/打标/归档入记忆。**通过标准**：local_path/zip 安装均校验 `SKILL.md`，启停进 registry；**用 `skill` 字段确定性调用，丢 20 个真实音频文件 20/20 走完整归档工序**（不是"演示成功过一次"）；同步产出《skill 开发指南》初版（SI 能照着写自己的行业 skill）。
- **T4 按需扩模态（①）**：TTS → 生图 → 视频（异步）；盒子选型见 `../research/spikes/vllm-omni-box.md`。
- **T-D 交付线（与 T2/T3 并行，决定第一单能否交付）**：每项都小，但缺一不可（详见 `model-gateway.md` §6.6）：
  1. `PINEA_MOCK=1` mock 模式产品化；
  2. SI quickstart（一页：base_url+token+三段 curl+容器两种姿势）;
  3. 出厂验收脚本（conformance+端口自检+真回合+skill 样本，一键绿）；
  4. 诊断包（一条命令出包）；
  5. 装机/加固清单（开机自启、模型 `keep_alive` 常驻、token 开通、端口表落地）。

**首单就绪（ToB 线的终点标志，五条全绿才见客户）**：

1. Stable 子集全部实现，conformance（mock+真后端同套）绿；
2. 旗舰 skill 确定性调用 20/20；
3. 出厂验收脚本一键绿；
4. 没接触过项目的工程师拿 quickstart+mock，30 分钟跑通三段 curl；
5. 诊断包一条命令出包。

并行约定：每个能力先用 **mock 后端**立契约，SI/skill 同时对接，真模型后置替换（契约不变）。

## 三个工程判断

1. **风险前置**：第 0 步的本地模型 tool calling 是成败点,死磕它再做别的。
2. **假数据先行**：第 2/3 步全程假数据,让灵魂线四进程(感知/soul/表达/runtime,不含网关)并行,不互相阻塞;第 4 步才换真感知。
3. **状态唯一真相源**：只有状态机进程往总线写目标态（第 2 步先用直通版映射，第 5 步换真 soul，写者始终唯一）,所有表达端只订阅渲染。
