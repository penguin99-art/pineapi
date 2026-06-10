# ToB 接口总览（按层次）

> 这是卖给 B 端（SI 集成方 / 行业交付）的**设备能力入口**。详细契约见各层链接。
> 配套：契约地图见 `README.md`，网关设计见 `../model-gateway.md`，原则见 `../../AGENTS.md`。
> 不在本文范围：`runtime-contract.md`（对内可换边界）、`pineastate-bus.md`（🟠 灵魂线，C 端专属，绝不对 B 端）。

## 0. 一张图：单一前门 + 三层

三类 ToB **共用 Pinea Model Gateway 一个设备前门**。默认部署形态是 SI App / 容器跑在松果派本机，经 `127.0.0.1` 调 Gateway；如果业务需要，也可绑定到 LAN/WAN，但必须开启简单 Bearer Token 门锁。

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

- **前门**：一个设备 `base_url`（本项目默认 `:18800`；默认绑定 `127.0.0.1`）。所有 HTTP 端点前缀 `/v1`。
- **安全门锁**：`Authorization: Bearer <token>`。本机封闭部署可关闭；只要 Gateway 绑定到 LAN/WAN 就必须开启。Token 只解决"谁能调设备口"，不表达购买范围。**安装类 skill 端点是管理(admin)操作**，不可暴露给不可信调用方（见 `skill-contract.md` §2）。
- **应用作用域**：可选头 `X-Pinea-App-Id`（缺省 `default`），为「单盒多 SI 隔离」预留作用域维度；MVP 单值 no-op（见 `capability-api.md` §0.1）。
- **能力发现**：`GET /v1/capabilities` 一次回三类（哪些模态可用 / agent 面工具+权限边界 / 装了哪些 skill / 限额）。盒子硬件不同，B 端必须程序化可查。
- **错误 / 状态码 / 限额**：OpenAI 风格全端点统一，`type`↔HTTP 状态码映射与默认限额见 `capability-api.md` §0.2 / §0.3。
- **OpenAI 兼容边界**：我们是 OpenAI **超集**而非逐字镜像，哪些镜像/哪些是 Pinea 扩展见 `capability-api.md` §9。
- **观测日志**：三类写**同一条结构化用量日志**，单位不同形状统一（见 `capability-api.md` §8）。MVP 不做多租户/计费/配额，`usage` 先用于本机观测与排障。
- **稳定性**：均为对外契约，破坏性变更走版本（`v1`→`v2` + 弃用周期）。**OpenAI 兼容子集承诺永不破**。当前 `v1` draft 未冻结。机读规格见 [`openapi.yaml`](openapi.yaml)。

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

| 端点 | 说明 |
| --- | --- |
| `POST /v1/agent/chat/completions` | OpenAI chat 兼容 + `X-Session-Id` 串上下文+记忆；agent 自用工具、自己多步循环，一次出最终结果。可选 `background:true` 异步长回合 |
| `GET /v1/agent/turns/{id}` | 异步回合轮询（配 `background:true`） |
| `GET /v1/agent/sessions/{id}/messages` | 会话历史只读（供 UI 回放） |
| `GET /v1/agent/sessions` | 列会话 |
| `DELETE /v1/agent/sessions/{id}` | 删会话 + 记忆作用域（被遗忘权抓手） |

agent 工具/权限边界（能否写盘/联网）由 runtime 配置，SI 可经 `GET /v1/capabilities` 的 `agent.{tools,permissions}` 只读查询。

与 ① 唯一区别：**有状态**（session + 白盒记忆 + 工具多步）。靠路径 `/v1/agent` 和 `X-Session-Id` 区分。
本质：把 runtime 的 `api_server` 接缝**升格为对外产品**，网关把 `X-Session-Id` 翻译成内部 `X-Hermes-Session-Id`，**B 端不感知底层是不是 PilotDeck**（runtime 可换）。

## 4. ③ 公共 Skills（L7 · 可复用行业能力）

> 详见 [`skill-contract.md`](skill-contract.md)。给"想沉淀/交付行业 know-how"的交付方。

- 形态：一个 Skill 包，核心是 `SKILL.md`（YAML frontmatter `name`/`description` + markdown 操作手册）+ 可选脚本。
- 安装：SI / 我们通过 Gateway 本机管理接口（如 `/v1/skills/install`）安装/启停；内部落到 runtime skill 目录，② 的 agent 按 `description` 自动触发。**零改核心**。安装是 admin 操作；frontmatter 用 `requires` 声明能力依赖，装时按 `/v1/capabilities` 校验。MVP 不做签名/沙箱，故 skill 视为受信代码（见 `skill-contract.md` §2.4）。
- 调能力：skill 通过 ① 能力面端点拿多模态（经注入的 `PINEA_GATEWAY`/`PINEA_TOKEN`，不写死地址；本机封闭部署可省略 token）。
- 两类：**能力型**（把一个能力包成动作）、**行业 workflow**（编排能力+工具+记忆，如"音频资料整理"，是卖点）。
- 铁律：**只依赖** 能力面端点 + runtime 的 skill/tool 契约，**绝不依赖 soul** → 天然可发 🔵 B 端。

## 5. 红线对齐（为什么三类都能安全发 B 端）

- **不改 PilotDeck 核心**：① 在 runtime 下面（model.providers）；② 复用 api_server 官方扩展点；③ 对外走 Gateway 管理面、内部落 runtime 磁盘 skill 扩展点。全是官方扩展点。
- **🔵/🟠 边界**：三类全是 🔵 Core，零 soul 渗入，发 B 端不用"拆灵魂"。
- **语言边界**：网关(Python) ↔ runtime(TS) 只走 HTTP/OpenAI，不混栈 import。

## 6. 并行推进（先 mock 后真）

每类先用假后端立契约，SI/skill 同时对接，真模型/真 runtime 后置替换，契约不变：

- ① 能力面：mock STT 回固定文本、TTS 回静音 wav、图回占位图。
- ② Agent 面：mock 回"固定多步结果 + 假 session"。
- ③ Skills：对 ① 的 mock 联调编排，不等真模型。

施工顺序见 `../build-plan.md` 的「ToB 并行线」（T0 chat→T1 STT→T2 Agent 面→T3 音频 skill→T4 扩模态）。
