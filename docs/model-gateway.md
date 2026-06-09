# Pinea Model Gateway（能力面 · L2）

> 配套：架构见 `architecture.md`，原则见 `../AGENTS.md`，融合见 `pilotdeck-integration.md`。
> 定位：🔵Core 的模型层（L2）。无头、可发 B 端。**替代 LocalAI 作为"门面"**，LocalAI 降级为可选后端之一。

## 1. 为什么自研网关（弃用 LocalAI 当门面）

LocalAI 在本机现状 = 套在 ollama 前的转发层，自己不 serving，且在 tool-calling spike 里把原生 `tool_calls` 解析坏了（见 `research/spikes/tool-calling-localai.md`）。负债 > 价值：

- 多模态后端被它的封装卡死，换更好的 STT/视频后端要跟它抽象打架；
- 无干净的多租户鉴权/配额/计量（ToB 卖能力面的刚需）；
- tool calling 经它会坏。

**决策**：自研一个**薄**网关当统一能力面。LocalAI 不删，降级成网关背后的**可换后端之一**（某模态它够用就先挂着）。

> 这修订了早期"L2 = LocalAI"的约束。约束由人定（见 `agent-native-workflow.md`），已确认。

## 2. 一句话定义

一个 OpenAI 兼容的多模态能力网关，**只做三件事**：**路由 + schema 归一 + 治理（鉴权/配额/计量/日志/健康）**。
**绝不自己做推理**——推理永远在后端进程（ollama / whisper / TTS / 生图 / 视频）。这条线划死，避免背"重做 serving"的维护地狱。

技术栈：**Python / FastAPI**（与感知层同栈，多模态后端生态最全）。它是独立进程，只说 HTTP/OpenAI，PilotDeck(TS) 只配一个 provider URL——不混栈、不互相 import（AGENTS 红线 3）。

## 3. 拓扑

```
SI 集成方   +   PilotDeck(model.providers 指向网关)
        │  一个 base_url · 一套 key · OpenAI 兼容
        ▼
┌─────────────────────────────────────────────────────┐
│  Pinea Model Gateway (FastAPI · 薄)                    │
│  路由表 capability → backend adapter                   │
│  统一: 鉴权/配额/计量(MVP 留桩) · 日志 · /v1/models 聚合 · 健康 │
├──────────┬──────────────┬───────────┬───────────────┤
│/chat /embed│/audio/transcriptions│/audio/speech│/images /video│
│  →ollama  │  →speaches(whisper)│ →Piper/Kokoro│ →ComfyUI(图/视频)│
│ (薄透传,已验)│   (原生 OpenAI)    │            │  (adapter 翻译) │
└──────────┴──────────────┴───────────┴───────────────┘
   后端均为独立进程,经 adapter 接入,可热插拔、按能力逐个可换
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
| `GET /v1/models` | 模型列表 | 全后端聚合 | — | 跨后端注册表 |

**文本路径决策**：PilotDeck 文本走网关（薄透传），不直连 ollama——换取单一模型面 + 统一计量/日志 + "加模型只改一处"。
**视觉**：ollama 的 minicpm-v 已在跑，视觉理解零新后端。

## 5. 内部结构（薄、可换）

```
gateway/
├─ app.py                 # FastAPI 入口 + 路由注册
├─ config.py              # 能力→后端 路由表(yaml)
├─ auth.py                # 鉴权(MVP: 单 key) + 计量钩子(留桩)
├─ schema/                # OpenAI 请求/响应模型(pydantic)
├─ backends/
│  ├─ base.py             # Backend 协议: 输入OpenAI形状→后端→输出OpenAI形状
│  ├─ ollama.py           # chat/embeddings/视觉 透传
│  ├─ speaches.py         # STT (faster-whisper, 原生 OpenAI → 近透传)
│  ├─ piper.py            # TTS (轻量 CPU)
│  ├─ comfyui.py          # 生图/视频 (工作流图 → OpenAI 形状翻译)
│  └─ vllm_omni.py        # 可选: GPU 盒子统一栈, 同一 adapter 接口
└─ jobs.py                # 异步任务表(视频等慢生成)
```

每个 backend 实现统一接口：吃 OpenAI 形状 → 调后端进程 → 吐 OpenAI 形状。加模态/换后端 = 加一个 adapter + 路由表一行，**SI 侧无感**。**网关唯一会长肉的地方就是 backends/**，可控。同一能力可有多个 adapter（如 STT 的 speaches / vllm_omni），按盒子配置在路由表里选。

## 6. 治理（ToB 必备，MVP 留桩）

- **鉴权**：MVP 单 key（`Authorization: Bearer`）；后置升级为多租户 key。
- **配额/计量**：MVP 在 `auth.py` 留计量钩子（记录 tokens/秒数/张数），不强制限额；后置接计费。
- **日志**：每请求一条结构化日志（caller / capability / backend / 用量 / 延迟）。
- **健康**：`GET /healthz` 聚合各后端探活。
- **资源仲裁（盒子刚需）**：端侧 GPU/显存有限，不可能 文本+STT+TTS+生图+视频 全常驻。策略：轻量栈尽量 CPU/小显存（whisper.cpp/Piper/sd.cpp 不抢 ollama 的 VRAM）；重后端（生图/视频/vllm-omni）按需起停或排队。具体阈值与方案由 `research/spikes/vllm-omni-box.md` 实测后定。

## 7. 红线自检

- **不改 PilotDeck 核心**：网关在 PilotDeck *下面*，PilotDeck 只改 `model.providers` 配置。✅
- **🔵/🟠 边界**：网关纯 L2 模型层 = Core，零 soul 渗入，B 端可直接发。✅
- **语言边界**：独立服务，只走 HTTP/OpenAI，不混栈 import。✅

## 8. 落地节奏（与 soul 主线并行，互不阻塞）

1. **网关骨架 + chat 透传**：FastAPI 起 `/v1/chat/completions`→ollama，PilotDeck `model.providers` 指过来，跑通 tool-calling spike（回归不掉）。
2. **STT 端点**：`/v1/audio/transcriptions`→whisper 后端，跑通 STT spike（`research/spikes/stt-gateway.md`）。
3. **"音频资料整理"skill**：PilotDeck 磁盘 skill，调网关 STT → 去重/打标/归档入记忆。第一个公共行业 skill。
4. 之后按需：TTS → 生图 → 视频（异步）。
5. **盒子选型 spike**（与上并行）：`research/spikes/vllm-omni-box.md` 实测目标盒子上各后端的显存/延迟，定"杂牌轻量栈 vs vllm-omni vs Qwen3-Omni 单模型合并"的最终挂法。

## 9. 公共 Skills 面（第二类 ToB，简述）

复用 PilotDeck 磁盘 skill 扩展点（`SKILL.md` 格式）。两类：
- **能力型 skill**：把一个网关能力包成 agent 工具（"转写这段音频"）。
- **行业 workflow skill**：编排能力+工具成可复用作业（"音频资料整理"）。

铁律：skill **只依赖** 网关能力端点 + PilotDeck skill/tool 契约，**绝不依赖 soul** → 天然可发 B 端。放本仓 `skills/` 或 `products/<行业>/`，磁盘加载，零改核心。
