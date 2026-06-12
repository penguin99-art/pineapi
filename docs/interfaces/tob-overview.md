# ToB 接口总览（按层次）

> 这是卖给 B 端（SI 集成方 / 行业交付）的**设备能力入口**。详细契约见各层链接。
> 配套：契约地图见 `README.md`，网关设计见 `../model-gateway.md`，原则见 `../../AGENTS.md`。
> 不在本文范围：`runtime-contract.md`（对内可换边界）、`pineastate-bus.md`（🟠 灵魂线，C 端专属，绝不对 B 端）。

## 0. 一张图：单一前门 + 三层

三类 ToB **共用 Pinea Model Gateway 一个设备前门**。默认部署形态：SI App / 容器跑在松果派本机，经 `127.0.0.1` 调 Gateway；绑定到 LAN/WAN 时必须开启 Bearer Token 门锁。

```
B 端开发者 / SI App ── 设备 base_url + 可选 Bearer Token ──► Pinea Model Gateway（设备前门 · 路由/归一/发现/健康/日志）
   │
   ├─ ③ Skills 管理 (L7) = ② + 行业流程封装。交付 SKILL.md 包, 通过接口安装/启停
   ├─ ② Agent 面 (L3/L4) = ① + 记忆 + 工具 + 多步循环。不用自己搭 agent
   └─ ① 能力面   (L2)    = 无状态推理。你自带一切，我只给算力 + 模态
```

一句话：**① 给算力、② 给 agent、③ 给行业 agent。**

| 层 | 类 | 卖什么 | 入口 | 状态 | 观测单位 | 详细契约 |
| --- | --- | --- | --- | --- | --- | --- |
| L2 | ① 能力面 | 算力 + 多模态 | `/v1/chat\|embeddings\|audio\|images\|video` | 无状态 | tokens/秒/张 | [`capability-api.md`](capability-api.md) |
| L3/L4 | ② Agent 面 | 开箱即用 agent | `/v1/agent/*`（+`X-Session-Id`） | 有状态 | agent 回合 | [`agent-api.md`](agent-api.md) |
| L7 | ③ Skills | 可复用行业能力 | `/v1/skills/*` 管理接口；内部落 `SKILL.md` | — | 作业/启用状态 | [`skill-contract.md`](skill-contract.md) |

## 1. 共用约定（三类统一，定义"好"的关键）

- **前门**：一个设备 `base_url`（默认 `:18800`，绑定 `127.0.0.1`）。所有 HTTP 端点前缀 `/v1`。
- **安全门锁**：`Authorization: Bearer <token>`。本机封闭部署可关闭；绑定 LAN/WAN 必须开启。**经公网或不可信网络访问必须套 TLS**（反向代理或隧道）——Bearer 明文过网等于没有门锁，无 TLS 的公网暴露一律禁止。Token 只解决"谁能调设备口"，不表达购买范围。安装类 skill 端点是管理（admin）操作，不可暴露给不可信调用方（见 `skill-contract.md` §2）。
- **攻击面收口**：对外只开网关 `:18800` 一个口；runtime、模型后端、web UI 等其余进程端口一律只绑本机或关闭。端口绑定表见 `../model-gateway.md` §6.1。
- **应用作用域**：可选头 `X-Pinea-App-Id`（缺省 `default`），为「单盒多 SI 隔离」预留；MVP 单值 no-op（见 `capability-api.md` §0.1）。
- **能力发现**：`GET /v1/capabilities` 一次回三类（模态可用性 / agent 工具+权限边界 / 已装 skill / 限额）。盒子硬件不同，B 端必须程序化可查。
- **错误 / 状态码 / 限额**：OpenAI 风格全端点统一，见 `capability-api.md` §0.2 / §0.3。
- **OpenAI 兼容边界**：我们是 OpenAI **超集**而非逐字镜像，镜像/扩展的划分见 `capability-api.md` §9。
- **观测日志**：三类写同一条结构化用量日志（见 `capability-api.md` §8）。MVP 不做多租户/计费/配额。
- **稳定性**：破坏性变更走版本（`v1`→`v2` + 弃用周期），OpenAI 兼容子集承诺永不破。**`v1.0` 已冻结（2026-06-10）**。**2026-06-11 修订**：② 的会话/异步端点原标"Reserved·需上游"，重判为**网关侧实现**并升为 Stable·自定义（见 §7）——只增强承诺、不改形状，不破坏冻结。机读规格见 [`openapi.yaml`](openapi.yaml)。

## 2. ① 能力面（L2 · 无状态模型能力）

> 详见 [`capability-api.md`](capability-api.md)。给"想自己搭 agent/app"的 SI。

| 端点 | 能力 | 默认后端 |
| --- | --- | --- |
| `POST /v1/chat/completions` | 文本/工具/视觉（带 image_url） | ollama（tool calling 已验） |
| `POST /v1/embeddings` | 向量 | ollama nomic-embed |
| `POST /v1/audio/transcriptions` | STT（**MVP 首做**） | speaches(faster-whisper) |
| `POST /v1/audio/speech` | TTS | Piper/Kokoro |
| `POST /v1/images/generations` | 生图 | ComfyUI |
| `POST /v1/video/generations` | 生视频（**异步**：submit→poll/webhook） | ComfyUI |

特点：**无状态**——每次传全量 `messages`；工具调用由调用方驱动多步。完全标准 OpenAI，官方 SDK 直接打。

## 3. ② Agent 面（L3/L4 · 有状态智能体）

> 详见 [`agent-api.md`](agent-api.md)。给"想要开箱即用 agent、套自己 UI"的 SI。

| 端点 | 说明 | 排期 |
| --- | --- | --- |
| `POST /v1/agent/chat/completions` | OpenAI chat 兼容 + `X-Session-Id`；agent 自用工具、自己多步循环，一次出最终结果。可选 `skill` 字段确定性调用 skill、`background:true` 异步 | T2（`skill` T3） |
| `GET /v1/agent/turns/{id}` | 异步回合轮询（配 `background:true`） | T2.5 |
| `GET /v1/agent/sessions/{id}/messages` | 会话回放（网关登记的输入/回答对，供 UI） | T2.5 |
| `GET /v1/agent/sessions` | 列会话 | T2.5 |
| `DELETE /v1/agent/sessions/{id}` | 删会话：逻辑删除 + 网关侧数据清除（支撑「删除/被遗忘」承诺） | T2.5 |

实现分工（关键）：**runtime 只提供"单回合执行"**（sync + SSE）；**会话登记、回放、异步聚合、删除、并发闸门全部由网关增值层实现**（`../model-gateway.md` §6.3）。② 的完整产品形态因此不依赖 runtime 上游排期，唯二例外见 §7 的两条 Reserved。

agent 工具/权限边界（能否写盘/联网）由 runtime 配置，SI 可经 `GET /v1/capabilities` 的 `agent.{tools,permissions}` 只读查询。
本质：把 runtime 的 `api_server` 接缝**升格为对外产品**；网关把 `(app_id, session_id)` 翻译成内部会话键，**B 端不感知底层是不是 PilotDeck**（runtime 可换）。

## 4. ③ 公共 Skills（L7 · 可复用行业能力）

> 详见 [`skill-contract.md`](skill-contract.md)。给"想沉淀/交付行业 know-how"的交付方。

- 形态：一个 Skill 包，核心是 `SKILL.md`（YAML frontmatter + markdown 操作手册）+ 可选脚本。对齐 Agent Skills 开放标准，可移植。
- 安装：通过 Gateway 管理接口（`/v1/skills/install`）安装/启停，内部落 runtime skill 目录，**零改核心**。安装是 admin 操作；`requires` 声明能力依赖，装时按 `/v1/capabilities` 校验。MVP 不做签名/沙箱，skill 视为受信代码（`skill-contract.md` §2.4）。
- 触发：agent 按 `description` 自动触发；**行业交付要确定性时，② 请求体带 `skill` 字段指定调用**（`agent-api.md` §1，机制见 `skill-contract.md` §2.5）。
- 调能力：skill 经 ① 能力面端点拿多模态（注入的 `PINEA_GATEWAY`/`PINEA_TOKEN`，不写死地址）。
- 两类：**能力型**（把一个能力包成动作）、**行业 workflow**（编排能力+工具+记忆，是卖点）。
- 铁律：**只依赖**能力面端点 + runtime skill/tool 契约，**绝不依赖 soul** → 天然可发 🔵 B 端。

## 5. 红线对齐（为什么三类都能安全发 B 端）

- **不改 PilotDeck 核心**：① 在 runtime 下面（model.providers）；② 复用 api_server 官方扩展点；③ 走 Gateway 管理面、内部落磁盘 skill 扩展点。全是官方扩展点。
- **🔵/🟠 边界**：三类全是 🔵 Core，零 soul 渗入，发 B 端不用"拆灵魂"。
- **语言边界**：网关(Python) ↔ runtime(TS) 只走 HTTP/OpenAI，不混栈 import。

## 6. 并行推进（先 mock 后真）

每类先用假后端立契约，SI/skill 同时对接，真模型/真 runtime 后置替换，契约不变：

- ① 能力面：mock STT 回固定文本、TTS 回静音 wav、图回占位图。
- ② Agent 面：mock 回"固定多步结果 + 假 session"。
- ③ Skills：对 ① 的 mock 联调编排，不等真模型。

mock 不是临时脚手架而是产品功能：网关以 `PINEA_MOCK=1` 启动即全端点出 mock，SI 没拿到盒子也能开发（见 `../model-gateway.md` §6.6）。施工顺序见 `../build-plan.md`「ToB 并行线」（T0✅→T1 STT→T2 Agent 面→T2.5 网关增值层→T3 skill→T4 扩模态，另有并行的 T-D 交付线）。

## 7. 稳定性 + 实现状态矩阵（v1.0 冻结 2026-06-10 · 2026-06-11 修订）

冻结 = **形状定死，是开发的权威基线**。"形状冻结"≠"现在就能用"，两个维度分开看：

**稳定性档位**（契约会不会变）：

- **Stable·承诺**：OpenAI 标准子集的标准字段，**永不破坏**。
- **Stable·自定义**：我们定义的稳定契约，破坏走 `v2` + 弃用周期。
- **Reserved**：形状纳入 v1 命名空间，但首版不保证可用，调用方不得依赖。

**实现状态**：`已实现` / `排期(Tn)` / `需上游`（须给 PilotDeck 上游加能力，红线①：不在 fork 改）。

| 端点 | 档位 | 实现状态 |
| --- | --- | --- |
| ① `POST /v1/chat/completions`（标准字段） | Stable·承诺 | 已实现(T0) |
| ① `POST /v1/embeddings` | Stable·承诺 | 已实现(T0) |
| ① `POST /v1/audio/transcriptions` | Stable·承诺(+`usage` 超集) | 排期(T1) |
| ① `POST /v1/audio/speech` | Stable·承诺 | 排期(T4) |
| ① `POST /v1/images/generations` | Stable·承诺 | 排期(T4) |
| ① `POST /v1/video/generations` + 轮询 | Stable·自定义 | 排期(T4) |
| 发现 `GET /v1/capabilities`·`/v1/models`·`/healthz` | Stable·自定义 | 已实现(T0) |
| ② `POST /v1/agent/chat/completions`（sync+stream）+`X-Session-Id`+同session 429 | Stable·自定义 | 排期(T2) |
| ② 设备级并发闸门（429 `queue_full` + `Retry-After`） | Stable·自定义 | 排期(T2)·网关实现 |
| ② `background:true` + `GET /v1/agent/turns/{id}` | Stable·自定义 | 排期(T2.5)·网关实现 |
| ② `GET /v1/agent/sessions`·`/sessions/{id}/messages` | Stable·自定义 | 排期(T2.5)·网关实现 |
| ② `DELETE /v1/agent/sessions/{id}`（逻辑删除） | Stable·自定义 | 排期(T2.5)·网关实现 |
| ② `skill` 确定性调用字段 | Stable·自定义 | 排期(T3)·网关注入 |
| ② `DELETE /v1/agent/turns/{id}`（取消进行中回合） | **Reserved** | **需上游** |
| ② runtime 记忆**物理擦除** | **Reserved** | **需上游**（过渡走运维手册） |
| `X-Pinea-App-Id` 强隔离 | **Reserved** | 单 SI 下 no-op |

**2026-06-11 重判说明**：② 的会话/异步端点曾因"api_server 今天只有 sync+SSE"标为 Reserved·需上游。重判依据：网关本就是有状态控制面（`../model-gateway.md` §2），且 ② 的全部流量必经网关——会话登记、回放记录、异步聚合、逻辑删除都可在网关侧实现，runtime 无感。语义注意：回放数据是**网关视角**的输入/回答对（非 runtime 白盒记忆）；删除 = 不可达 + 网关侧清除（物理擦除 runtime 数据仍是运维程序）；取消进行中回合真正需要 runtime 配合，保持 Reserved。详见 `agent-api.md` §3/§4。

> 依据：② 的底座 `vendor/pilotdeck/.../api-server/ApiServerChannel.ts` 今天只支持 `POST /v1/chat/completions`（sync+SSE）+ `X-Hermes-Session-Id` + 同 session 429。
> 冻结边界：本次冻结**接口套**（capability/agent/skill + openapi）。`architecture.md` / `model-gateway.md` 是设计文档，随实现演进，不在冻结范围。
