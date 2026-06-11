# Pinea Model Gateway（单一前门 · L2）

> 配套：架构见 `architecture.md`，原则见 `../AGENTS.md`，融合见 `pilotdeck-integration.md`，对外入口见 `interfaces/tob-overview.md`。
> 定位：🔵Core 的模型层（L2），三类 ToB 的**设备前门**。无头、可发 B 端。**替代 LocalAI 作为"门面"**（LocalAI 已弃用）。
> 术语：**"网关/单一前门" = 整个本服务**；**"能力面" 专指 ①**（无状态模型层），勿混。

## 1. 为什么自研网关（弃用 LocalAI 当门面）

LocalAI 在本机现状 = 套在 ollama 前的转发层，自己不 serving，且在 tool-calling spike 里把原生 `tool_calls` 解析坏了（见 `research/spikes/tool-calling.md`）。负债 > 价值：

- 多模态后端被它的封装卡死，换更好的 STT/视频后端要跟它抽象打架；
- 无干净的设备安全门锁、能力发现、结构化日志与资源仲裁（卖盒子能力的刚需）；
- tool calling 经它会坏。

**决策**：自研一个**薄**网关当统一能力面，**当前不用 LocalAI**（理论上它仍可作某模态后端，但默认不挂）。

> 这修订了早期"L2 = LocalAI"的约束。约束由人定（见 `agent-native-workflow.md`），已确认。

## 2. 一句话定义

一个 OpenAI 兼容的多模态能力网关，是**三类 ToB 的设备前门**（默认 `127.0.0.1`，外放需 Bearer Token）。

**"薄"的精确含义**（三条负面清单，划死不越）：

1. **绝不自己做推理**——不碰权重、不做 serving，推理永远在后端进程（ollama / whisper / TTS / 生图 / 视频）。避免背"重做 serving"的维护地狱。
2. **绝不实现 agent loop**——记忆/工具/多步循环永远在 Agent Runtime，② 只做转发 + 头翻译。
3. **绝不掺 soul**——纯 🔵 Core，零灵魂逻辑。

在这三条之内，网关是设备的**控制面**，允许有状态、允许长逻辑：路由 + schema 归一（含 ComfyUI 工作流翻译这类 adapter）+ 设备治理（安全门锁/发现/日志/健康）+ skills registry + 重后端队列/资源仲裁 + **② 的会话增值层（§6.3）** + wss 代理。"薄"约束的是**职责边界**，不是代码量。

三类 ToB（自底向上叠，详见 `interfaces/`）：① **能力面**（无状态推理，`/v1/chat|audio|images|video`，`interfaces/capability-api.md`）、② **Agent 面**（有状态 agent，`/v1/agent/*` 转发 PilotDeck api_server，`interfaces/agent-api.md`）、③ **Skills**（行业能力，`interfaces/skill-contract.md`）。一句话：① 给算力、② 给 agent、③ 给行业 agent。

技术栈：**Python / FastAPI**（与感知层同栈，多模态后端生态最全）。它是独立进程，只说 HTTP/OpenAI，PilotDeck(TS) 只配一个 provider URL——不混栈、不互相 import（AGENTS 红线 3）。

## 3. 拓扑

```
SI App/容器(本机优先,可选LAN)   +   PilotDeck(model.providers 指向网关)
        │  设备 base_url · 可选 Bearer Token · OpenAI 兼容（三类 ToB 同一前门）
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Pinea Model Gateway (FastAPI · 薄) — 设备前门                       │
│  路由表 capability → backend adapter                               │
│  统一: Bearer门锁(外放必开) · 日志 · /v1/capabilities 发现 · 健康      │
├──────────┬──────────────┬───────────┬───────────┬──────────────┤
│①/chat embed│①/audio/transcr│①/audio/speech│①/images video│②/v1/agent/* │
│  →ollama  │  →speaches    │ →Piper/Kokoro│ →ComfyUI     │→api_server   │
│ (薄透传,已验)│ (原生 OpenAI) │            │ (adapter翻译) │(有状态,带session)│
└──────────┴──────────────┴───────────┴───────────┴──────────────┘
   ①后端均为独立进程,经 adapter 接入,可热插拔、按能力逐个可换
   ②转发 PilotDeck api_server;其内部回 model.providers 打①做推理属于同设备模型线调用
   ③Skills 通过本机管理接口安装/启停;内部落磁盘 skill 扩展点,由②的 agent 自动触发
```

**后端选型口径**：默认 = **杂牌轻量栈**（各模态挑最成熟、CPU/小显存友好的项目）；**vllm-omni = GPU 富裕盒子上的可选实现**（一套引擎统一多模态，但重、一实例一模型）。这不是全局开关——网关 adapter 接口让后端**按能力逐个可换、甚至混用**（文本 ollama + STT speaches + 生图 ComfyUI；将来某条腿换 vllm-omni，SI 侧无感）。盒子最终挂什么，由 `research/spikes/vllm-omni-box.md` 实测后定。

## 4. 对外端点（有 OpenAI 标准就对齐，没有的自定义）

| 端点 | 能力 | 默认后端（轻量栈） | GPU 盒子可选 | 说明 |
| --- | --- | --- | --- | --- |
| `POST /v1/chat/completions` | 文本/对话/工具 | **ollama**（已验） | vllm-omni / Qwen3-Omni | **薄透传**，tool calling 已验证 |
| `POST /v1/embeddings` | 向量 | **ollama** nomic-embed（已在） | — | 透传 |
| chat 带图 | 视觉理解 | **ollama minicpm-v**（已在） | Qwen3-Omni | 零新后端，chat 带图即可 |
| `POST /v1/audio/transcriptions` | STT | **speaches**(faster-whisper)/whisper.cpp | vllm-omni Qwen3-ASR | **MVP 首做**；speaches 原生此端点、CPU 可跑 |
| `POST /v1/audio/speech` | TTS | **Piper**(极轻 CPU)/Kokoro | vllm-omni Qwen3-TTS | 表达层也复用 |
| `POST /v1/images/generations` | 生图 | **ComfyUI**(API)/退路 sd.cpp(CPU) | vllm-omni Flux/Qwen-Image | adapter 把 Comfy 工作流包成 OpenAI 形状 |
| `POST /v1/video/generations` | 生视频 | **ComfyUI**(Wan2.2/LTX) | vllm-omni 视频栈 | OpenAI 无此标准 → 自定义；**异步任务**(submit→poll/webhook) |
| `POST /v1/agent/chat/completions` | **② Agent 面**（有状态 agent） | PilotDeck api_server | 同 runtime | OpenAI+`X-Session-Id`；记忆+工具+多步，详见 `interfaces/agent-api.md` |
| `GET /v1/capabilities` | 三类 ToB 发现 | 全后端+runtime+skills 聚合 | — | 盒子有什么程序化可查 |
| `GET /v1/models` | 模型列表 | 全后端聚合 | — | 跨后端注册表 |

**文本路径决策**：PilotDeck 文本走网关（薄透传），不直连 ollama——换取单一模型面 + 统一观测日志 + "加模型只改一处"。
**视觉**：ollama 的 minicpm-v 已在跑，视觉理解零新后端。
**Agent 面（②）**：网关把 `/v1/agent/*` 转发到 PilotDeck `api_server`（默认 `127.0.0.1:8642`，由 `API_SERVER_HOST/PORT/KEY` 配置），对外用 `X-Session-Id`（内部翻译成会话键 `{app_id}:{session_id}:{gen}`，经 `X-Hermes-Session-Id` 传入），藏掉 runtime 细节。**转发之上是网关增值层（§6.3）**：会话登记/回放、`background` 异步聚合、逻辑删除、并发闸门——runtime 只做单回合执行，② 的产品形态由网关补齐，不依赖上游排期。agent 回打 ① 做推理是同设备模型线调用，不引入计费语义。详见 `interfaces/agent-api.md`。
**跨类约定**：错误 `type`↔HTTP 状态码、默认限额、`X-Pinea-App-Id` 作用域见 `interfaces/capability-api.md` §0；`/v1/capabilities` 额外暴露 `agent.{tools,permissions}` 权限边界与 `limits` 机读限额。

## 5. 内部结构（薄、可换）

```
gateway/                     # 独立 Python 服务(uv/pyproject), :18800
├─ pyproject.toml · .env.example · README.md
├─ pinea_gateway/
│  ├─ app.py              # FastAPI 入口 + 路由注册 + 异常处理 ✅
│  ├─ config.py           # 设置 + 能力→后端 路由表 ✅
│  ├─ auth.py             # Bearer Token 门锁(外放必开) + usage 日志钩子 ✅
│  ├─ errors.py           # OpenAI 风格错误形状 + handler ✅
│  ├─ routes/
│  │  ├─ chat.py          # ① /v1/chat/completions 透传 ✅(T0)
│  │  ├─ meta.py          # /healthz · /v1/models · /v1/capabilities ✅
│  │  ├─ audio.py         # ① STT/TTS (T1)
│  │  ├─ agent.py         # ② /v1/agent/* 转发 api_server (T2)
│  │  └─ skills.py        # ③ /v1/skills/* 本机管理接口 (T3)
│  └─ backends/
│     ├─ base.py          # Backend 协议: 输入OpenAI形状→后端→输出OpenAI形状 ✅
│     ├─ ollama.py        # chat/embeddings/视觉 透传 ✅
│     ├─ speaches.py      # STT (faster-whisper, 原生 OpenAI → 近透传) (T1)
│     ├─ piper.py         # TTS (轻量 CPU)
│     ├─ comfyui.py       # 生图/视频 (工作流图 → OpenAI 形状翻译)
│     ├─ agent.py         # ② 转发 PilotDeck api_server, session 头翻译 (T2)
│     └─ vllm_omni.py     # 可选: GPU 盒子统一栈, 同一 adapter 接口
└─ tests/                 # base_url 无关 conformance(mock 或真同一套) ✅
```
（✅ = T0 已落地；其余为后续 T 步的预留位）

每个 backend 实现统一接口：吃 OpenAI 形状 → 调后端进程 → 吐 OpenAI 形状。加模态/换后端 = 加一个 adapter + 路由表一行，**SI 侧无感**。**网关唯一会长肉的地方就是 backends/**，可控。同一能力可有多个 adapter（如 STT 的 speaches / vllm_omni），按盒子配置在路由表里选。

## 6. 设备治理（ToB 必备，MVP 收敛版）

- **安全门锁**：Bearer Token。默认本机封闭部署可关闭；只要 Gateway 绑定到 LAN/WAN，必须开启。它只解决"谁能调设备口"，不表达购买范围。
- **观测日志**：每请求记录 usage（① tokens/秒数/张数、② agent 回合，统一 usage 形状见 `interfaces/capability-api.md` §8），用于本机观测、排障和资源仲裁；MVP 不做多租户/计费/配额。
- **日志**：每请求一条结构化日志（caller / capability / backend / 用量 / 延迟）。
- **健康**：`GET /healthz` 聚合各后端探活。
- **资源仲裁（盒子刚需）**：端侧 GPU/显存有限，不可能 文本+STT+TTS+生图+视频 全常驻。策略：轻量栈尽量 CPU/小显存（whisper.cpp/Piper/sd.cpp 不抢 ollama 的 VRAM）；重后端（生图/视频/vllm-omni）按需起停或排队。具体阈值与方案由 `research/spikes/vllm-omni-box.md` 实测后定。

### 6.1 Gateway 启动配置（硬约束）

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `PINEA_HOST` | `127.0.0.1` | Gateway 监听地址。默认只给本机 SI App/容器调用 |
| `PINEA_PORT` | `18800` | 设备前门端口 |
| `PINEA_API_KEY` | 空 | Bearer Token。`PINEA_HOST` 不是 `127.0.0.1`/`localhost`/`::1` 时必须配置，否则拒绝启动 |
| `PINEA_OLLAMA_URL` | `http://localhost:11434` | ① chat/vision/embed 后端 |
| `PINEA_DEFAULT_CHAT_MODEL` | `gpt-oss:20b` | 默认文本模型 |

外放规则：绑定到 `0.0.0.0`、LAN IP 或公网地址时，所有 `/v1/*` 能力/管理端点都要求 `Authorization: Bearer <PINEA_API_KEY>`。`/healthz` 是否也要求 token 可由实现决定；MVP 可放行健康检查，但不得泄露敏感配置。

**TLS 规则（红线措辞）**：Bearer 是明文凭证，**经公网或不可信网络访问网关必须套 TLS**（前置反向代理或隧道）；无 TLS 的公网暴露一律禁止。LAN 内是否加 TLS 由部署方按风险自定，交付默认按"LAN ≈ 半可信"开启 token。

**端口绑定表（攻击面单一真相源）**：对外只开 P1 一个口，其余全部锁本机或关闭。ToB SKU 交付按此表自检（出厂验收脚本项，见 §6.6）：

| 进程 | 端口 | 绑定 | ToB SKU |
| --- | --- | --- | --- |
| P1 Pinea Gateway | 18800 | `127.0.0.1`（外放须 token + TLS 规则） | **唯一对外口** |
| P2 api_server | 8642 | `127.0.0.1` | 仅本机（只给 P1 转发） |
| P2 gateway WS | 18790 | `127.0.0.1` | 仅本机 |
| P2 web UI | 3001 | `127.0.0.1` | **关闭** |
| ollama | 11434 | `127.0.0.1` | 仅本机 |
| speaches / ComfyUI 等后端 | 各自默认 | `127.0.0.1` | 仅本机 |

**SI 容器怎么访问 Gateway（钦定姿势）**：容器默认网络下访问不到宿主机的 `127.0.0.1`，"容器经 127.0.0.1 调网关"只在 host network 模式下成立。两种部署姿势二选一：

1. **host network 模式（Linux 盒子推荐）**：`docker run --network host`，容器直接打 `127.0.0.1:18800`，仍算本机封闭部署，可不开 token。
2. **桥接网络**：Gateway 须额外绑定 docker 网桥地址（如 `172.17.0.1`）或用 `host.docker.internal`——此时 `PINEA_HOST` 已非 localhost，**按上述规则必须配置 `PINEA_API_KEY`**，容器经环境变量注入 token。

不要为了图省事直接绑 `0.0.0.0` 裸奔；交付脚本应默认姿势 1。

### 6.2 Skills 管理面（MVP）

`/v1/skills/*` 是 ToB 第三类入口。对 SI 暴露接口，内部落到 runtime skill 目录。**安装/启停/删除/扫描是管理(admin)操作**（装 skill = 注入 agent 会执行的指令），门锁开启时要求 token，非管理调用 → `403 admin_required`；MVP 复用设备 Bearer Token 作管理凭证，预留独立 admin scope。**MVP 不做签名/沙箱**，skill 视为受信代码（见 `interfaces/skill-contract.md` §2.4）。

MVP 安装请求先支持两种形态，二选一即可：

```json
{ "source": { "type": "local_path", "path": "/opt/pinea/skills/audio-archive" }, "enabled": true }
```

或上传 `multipart/form-data`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file` | zip/tar | 包内根目录必须包含 `SKILL.md` |
| `enabled` | bool? | 默认 `true` |

安装流程固定：

1. 解包/读取 → 校验 `SKILL.md` frontmatter 的 `name`、`description`。
2. 校验 `name` 为 kebab-case；同名按 `version` 走升级（旧版留存可回滚）。
3. **能力校验**：`requires.modalities/tools` 比对 `/v1/capabilities`，缺依赖默认拒绝或装为 `enabled:false` + `unmet_requirements`（`?force=true` 可覆盖）。
4. 写入 `~/.pilotdeck/skills/<name>/`（或项目级目录，后置）。
5. 写 Gateway registry：`name / version / enabled / source / requires / installedAt / updatedAt`。
6. 触发 runtime skill scan（若无热加载能力，返回需重启/下次扫描生效）。

启停 = 网关在 runtime 扫描路径和隔离区 `~/.pinea/skills.disabled/` 之间搬目录 + 刷新 registry（零改核心；机制与真相源收敛规则见 `interfaces/skill-contract.md` §2.1.1），不修改 `SKILL.md` 内容。删除先禁用再移除目录；失败时保持 registry 和磁盘一致。**registry 只是磁盘的索引，冲突时以磁盘为准**，`scan` 负责双向收敛（手拷目录补登记为 `unmanaged`）。详见 `interfaces/skill-contract.md` §2。

### 6.3 Agent 面运行边界 + 网关增值层

runtime 只提供单回合执行（sync+SSE）；② 的产品形态由网关补齐。该层有持久化状态（SQLite 足够），属控制面职责，不违反 §2 负面清单。

- **会话键映射（定死）**：有效会话 `(X-Pinea-App-Id, X-Session-Id)` → runtime 会话键 **`{app_id}:{session_id}:{gen}`**。`gen` 初始 0，`DELETE` 会话时 +1——旧上下文/记忆对该 session 永久不可达（逻辑删除）。
- **增值层四件事（T2/T2.5）**：
  1. 会话登记 + 回放记录（回合输入/最终回答/usage/时间戳）→ 服务 `GET /v1/agent/sessions*`；
  2. `background:true` 异步：网关代持 SSE、聚合事件、存结果 → 服务 `GET /v1/agent/turns/{id}`；
  3. usage 聚合回填：`turn_completed.usage` → 非流式响应 + 用量日志；
  4. 并发闸门：同 session 1 个进行中回合（runtime 行为，`429 session_busy`）+ 设备级上限（默认 2，`PINEA_AGENT_MAX_TURNS`）→ `429 queue_full` + `Retry-After`。
- **重启语义（定死）**：P1 重启 = 进行中回合断流，SI 重试；会话登记/回放/异步结果/`gen` 持久化不丢（逻辑删除不因重启复活）。
- 默认 workspace 用设备 ToB 工作区（部署时配置，如 `/srv/pinea/workspaces/default`），不暴露系统根目录；workspace 跨 session 共享的含义与 SI 责任见 `interfaces/agent-api.md` §4。
- 工具权限由 runtime 配置收口，**`network:false` 是安全默认**（② 的最终用户输入按不可信对待，见 `interfaces/agent-api.md` §4）；Gateway 不绕过 runtime 权限模型，边界经 `/v1/capabilities` 只读可见。

### 6.4 资源仲裁 MVP

先实现"保守可用"而不是复杂调度，但**优先级原则现在定死**：

> **交互类 > 批量类。** 交互类 = chat/STT/TTS/fast model（灵魂线实时反射 + SI 在线交互），延迟是产品命门；批量类 = 生图/视频/长 agent 后台回合，可排队可等。重后端的起停**不得抢占交互类常驻模型的显存**；批量任务只用交互类留下的余量。这条原则是后置一切调度方案（起停/排队/抢占/`priority` 字段）的前提，`vllm-omni-box.md` spike 的实测结论必须在它之内。

MVP 落法：

- chat/embedding 后端常驻（ollama）。
- STT/TTS 优先选 CPU/小显存后端（whisper.cpp/Piper 不抢 ollama 的 VRAM），可并发但要有超时。
- 生图/视频/vllm-omni 等重后端默认**串行队列**，队列满返回 `429 rate_limit_error`，单任务超时返回 `server_error`。
- `/v1/capabilities` 暴露每个模态的 `available`，后置可加 `status: idle|busy|warming|down`、`queue_depth` 与任务级 `priority`（预留语义：`interactive|batch`），但新增字段必须向后兼容。

### 6.5 ToC 流式前门（wss 透明代理）

设备前门除了三类 ToB 的 HTTP 接口，还为 **ToC UI（Studio/桌伴/Phone）**提供一个 wss 流式面：**透明代理** runtime（P2）的 `GatewayEvent` 事件流与会话只读 API，不改协议、不掺 soul。

- 目的：ToC 的流式 UI 也从同一设备前门进，不必各自直连 P2，统一收口安全门锁/日志。
- 边界：Gateway 转发 runtime 事件（`assistant_text_delta` / `tool_call_*` / `turn_completed` 等）。**对外契约是 Pinea 流式事件标准**（v1 = 当前 PilotDeck `GatewayEvent` 形状的快照，见 `interfaces/runtime-contract.md` 契约三 B）——MVP 实现恰好是透明转发，但"透明"是实现捷径不是承诺：换 runtime 后若事件形状不同，**由 P1 翻译成该标准**，Studio 仍只依赖 gateway 契约（AGENTS 红线 5），全不动。
- 与 🟠 Soul 无关：表达层的 `state` 仍只来自 PineaState 总线，不从这个流式面取（灵魂线见 `architecture.md` §0.3）。

### 6.6 交付与运维（ToB SKU 清单 · T-D 线）

卖盒子的生意，一半支撑在装机之后。以下交付物随 T2/T3 并行做（排期见 `build-plan.md` T-D 线）：

- **mock 模式产品化**：`PINEA_MOCK=1` 启动 → 全端点回 mock（chat 固定回复 / STT 固定文本 / agent 假多步 + 假 session），SI 没拿到盒子就能开发。契约里"先 mock 后真"的可执行形态。
- **出厂验收脚本**：一键跑 conformance（`gateway/tests/`，mock 与真后端同一套）+ 端口绑定表自检（§6.1）+ 一次真 agent 回合 + 旗舰 skill 样本作业，全绿才出货。同一脚本就是 SI 现场自检工具。
- **诊断包**：一条命令打包 `/healthz` 快照 + 最近 N 条用量日志 + 各进程版本 + 磁盘/显存状态；工单先发诊断包，避免每单都开远程会议。
- **升级姿势（MVP 不做 OTA）**：定义现场脚本升级网关与 skills（不动模型）的标准程序；`/healthz` 带 `gateway_version` 供远程确认版本。
- **SLA 边界明文**：承诺契约行为 + 网关/后端进程可用性；**不承诺模型输出质量**——行业效果由 skill 验收样本兜底（`interfaces/skill-contract.md` §6），售后据此分流工单。
- **模型常驻**：交互集（默认 chat 模型 + embed）`keep_alive` 锁定不被逐出，是 §6.4 QoS 原则落到 ollama 配置的形态；批量后端起停不得触碰这部分显存。

## 7. 红线自检

- **不改 PilotDeck 核心**：网关在 PilotDeck *下面*，PilotDeck 只改 `model.providers` 配置。✅
- **🔵/🟠 边界**：网关纯 L2 模型层 = Core，零 soul 渗入，B 端可直接发。✅
- **语言边界**：独立服务，只走 HTTP/OpenAI，不混栈 import。✅

## 8. 落地节奏（与 soul 主线并行，互不阻塞）

1. **网关骨架 + chat 透传（T0）** ✅：FastAPI（`gateway/`，:18800）起 `/v1/chat/completions`→ollama，PilotDeck `model.providers` 指过来，tool-calling 经网关回归 19/20（未弄坏 tool_calls）。
2. **STT 端点（T1）**：`/v1/audio/transcriptions`→whisper 后端，跑通 STT spike（`research/spikes/stt-gateway.md`）。
3. **Agent 面 + 增值层（T2/T2.5）**：`/v1/agent/*` 转发 api_server + §6.3 增值层（会话登记/回放/异步聚合/逻辑删除/并发闸门/usage 回填）。
4. **"音频资料整理"skill（T3）**：Skill 包经 `/v1/skills/*` 安装，调网关 STT → 去重/打标/归档入记忆；`skill` 字段确定性调用验收。第一个公共行业 skill。
5. **T-D 交付线（与 2-4 并行）**：mock 开关 → quickstart → 出厂验收脚本 → 诊断包 → 装机/加固清单（§6.6）。
6. 之后按需（T4）：TTS → 生图 → 视频（异步）。
7. **盒子选型 spike**（并行）：`research/spikes/vllm-omni-box.md` 实测各后端显存/延迟，定"杂牌轻量栈 vs vllm-omni"的最终挂法。

## 9. 公共 Skills 面（第三类 ToB，简述）

对外走 Gateway 本机管理接口，内部复用 PilotDeck 磁盘 skill 扩展点（`SKILL.md` 格式）。两类：
- **能力型 skill**：把一个网关能力包成 agent 工具（"转写这段音频"）。
- **行业 workflow skill**：编排能力+工具成可复用作业（"音频资料整理"）。

铁律：skill **只依赖** 网关能力端点 + PilotDeck skill/tool 契约，**绝不依赖 soul** → 天然可发 B 端。源文件可放本仓 `skills/` 或 `products/<行业>/`，交付时走 `/v1/skills/*` 管理接口，内部落盘加载，零改核心。
