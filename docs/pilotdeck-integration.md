# 仓库结构 & 融 PilotDeck

> 配套：架构见 `architecture.md`，原则见 `../AGENTS.md`。
> 核心原则：PilotDeck 锁版本只读，自研只走扩展点，绝不改核心（见 AGENTS 红线 1）。

## 1. 仓库结构（本仓 = pinea 私有 monorepo）

```
pineapi/                        ← 本仓（私有）
├─ AGENTS.md / README.md / docs/
├─ vendor/
│  └─ pilotdeck/                ← git submodule,锁版本,只读(= 🔵Core 实现)
├─ gateway/                     ← Pinea Model Gateway(L2 能力面,FastAPI,见 docs/model-gateway.md)
├─ models/                      ← 后端/模型配置(ollama / speaches / TTS / ComfyUI 端点)
├─ soul/                        ← 🟠灵魂层(自研)
│  ├─ perception/               ← 感知服务(Python):级联 + 认主,发 presence/voice
│  ├─ expression/               ← 表达服务:状态机 + 灯带/TTS 渲染器
│  └─ bus/                      ← PineaState 总线 + 事件 schema
├─ adapters/                    ← 接 Core 的扩展件
│  ├─ hooks/                    ← PilotDeck 磁盘 hook 脚本(outbound 发态)
│  ├─ channels/                 ← 桌伴等自定义 ChannelAdapter(仿 api_server)
│  └─ mcp/                      ← 设备反控 MCP server
├─ studio/                      ← 全新 UI 壳(套 gateway SDK)
└─ deploy/                      ← 盒子装配:五进程(网关/runtime/感知/soul/表达) + 总线编排(compose/脚本)
```

为什么两仓：PilotDeck 保持通用、可对外开源、可同步上游；pinea 私有，放灵魂 + 装配。边界 = submodule。

## 2. 接 PilotDeck 的脚手架

```bash
# 在本仓
git submodule add <PilotDeck repo> vendor/pilotdeck
git submodule update --init --recursive
cd vendor/pilotdeck && pnpm install && pnpm server   # gateway 默认 :18789(本项目 18790,见 deploy/pilot-home)；web UI :3001
```

> submodule 锁 commit。升级 = 进 submodule 切 tag/commit → 在本仓提交新指针。**永远不在 submodule 里留本地改动。**

## 3. 零改核心接入地图（这些都是 PilotDeck 官方扩展点）

| 自研件 | 接哪个扩展点 | 依据(PilotDeck 路径) |
| --- | --- | --- |
| 感知 inbound | 内置 `api_server` channel → `gateway.submitTurn()` | `src/adapters/channel/`、`gateway/protocol/types.ts` |
| 表达 outbound（脚本） | 磁盘 hook：`SessionStart/PreModelRequest/Stop/PostToolUse` | `src/extension/hooks/protocol/events.ts` |
| 表达/Studio（订阅流） | `GatewayWsClient` 消费 `GatewayEvent` | `src/gateway/`（导出 client/RemoteGateway） |
| 桌伴 channel | 自定义 `ChannelAdapter`，仿 `ApiServerChannel` | `src/adapters/channel/.../ApiServerChannel.ts` |
| 设备反控 | MCP server | `src/mcp/` |
| 模型 | 配置 `model.providers`（protocol:"openai" → Pinea Model Gateway；MVP 可直指 ollama） | 配置层,不碰代码 |
| Studio 数据 | gateway 契约 + web 读 API（listProjects / readSessionMessages） | `src/gateway/protocol`、`src/web/server` |

**已知摩擦**：`loadEnabledChannels.ts` 的 `CHANNEL_LOADERS` 是硬编码注册表。MVP 不碰它——感知/桌伴都走内置 `api_server`。确需专属 channel → 作为**通用特性**提交回 PilotDeck 上游，不在 fork 里改。

## 4. Studio（全新 UI，套 gateway SDK）

UI 从零做 Piny 体验，但**后端零重写**：把 PilotDeck 的 `gateway/protocol`（类型）+ `GatewayWsClient`（连接/流）+ `src/web/server` 读 API 当「后端 SDK」用。

红线：Studio 只 import 上述 gateway 边界，**绝不** import `agent/` `context/` `tool/` 内部模块（见 AGENTS 红线 5）。这样 PilotDeck 升级不震 UI。

## 5. 上游同步流程

1. 进 `vendor/pilotdeck`，`git fetch` 上游，切到目标 tag/commit。
2. 跑 `pnpm install && pnpm server` + 本仓 smoke（第 0 步通过标准）验证未回归。
3. 回本仓 `git add vendor/pilotdeck && git commit`（提交新 submodule 指针）。
4. 若本仓某扩展点因上游接口变动而坏 → 改 `adapters/` / `studio/` 适配，**不改 submodule**。

## 6. B 端发货

发货 = 🔵Core（`vendor/pilotdeck` + Pinea Model Gateway + 后端 + 配置 + Skill/Workflow），**不含** `soul/`。因为灵魂从未渗进 Core（AGENTS 红线 2），拆分是配置级,不是重构。
