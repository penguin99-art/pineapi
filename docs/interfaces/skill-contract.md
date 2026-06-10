# L7 公共 Skill 契约（可复用行业能力）

> 配套：架构见 `../architecture.md` §8，能力面见 `capability-api.md`，Agent 面见 `agent-api.md`，总览见 `README.md`。
> 这是 **ToB 第三类接口**——把行业流程做成可复用 skill，跑在 ② Agent 面之上，发 B 端。
> 依据（PilotDeck 真实契约）：`vendor/pilotdeck/skills/*/SKILL.md`、`vendor/pilotdeck/src/extension/skills/types.ts`、gateway 的 `skillsList/skillRead/...` RPC（`src/gateway/protocol/types.ts`）。

## 0. 一句话

Skill = 一个可安装的行业能力包，核心是 **`SKILL.md`**（YAML frontmatter + markdown 正文）+ 可选脚本/资源。对 SI 暴露的是 Gateway 本机管理接口；内部仍落到 runtime skill 目录，agent 在合适时机按 `description` 触发。**零改核心**。

## 1. SKILL.md 格式（PilotDeck 现行）

```markdown
---
name: audio-archive
version: 1.0.0
description: 当用户要"整理/归档一批音频/录音"、把语音转成文字并分类入库时使用。
requires:
  modalities: [transcription]   # 声明依赖的 ① 能力面模态
  tools: [fs.read, fs.write]    # 声明依赖的 runtime 工具（可选）
---

# 音频资料整理

## 何时用
- 用户给一个目录的录音/音频，要转写、去重、打标、归档。

## 步骤
1. 列目录音频文件。
2. 对每个文件调能力面 STT（见下）得到文字。
3. 去重/摘要/打标。
4. 写回结构化结果 + 入记忆。
```

- `name`：唯一标识（kebab-case）。
- `version`：语义化版本（可选但推荐）；同名再装按 §2.2 走升级/回滚。
- `description`：**触发条件**，写清"用户说什么/想干什么时用"——这是 agent 选不选它的唯一依据，要具体。**安全相关，见 §2.3 触发边界**。
- `requires`：能力依赖声明（可选）。`modalities` 对应 ① 能力面模态，`tools` 对应 runtime 工具。安装时按此校验「这台盒子能不能跑」，见 §2.1。
- 正文：给 agent 的操作手册（何时用 / 步骤 / 注意），可引用同目录脚本。

### 1.1 渐进披露（三级加载 · 对齐开放 Agent Skills 标准）

这是 skill 机制的核心，**对盒子的本地小模型尤其重要**：装一堆 skill 几乎不吃上下文，命中才加载，省下的 token 全留给推理。三级：

| 级 | 内容 | 何时进上下文 | 成本 |
| --- | --- | --- | --- |
| 1 | frontmatter（`name`+`description`） | **启动即载**入 system prompt，供 agent 判断何时用 | 每 skill ~100 词，可放心装很多 |
| 2 | `SKILL.md` 正文 | **命中才读**（agent 判定本回合相关时） | 全文进上下文 |
| 3 | 正文引用的文件 / 脚本 | **按需读**：引用文件随用随取；脚本**执行**而非读入 | 脚本代码**永不进上下文**，只回执行输出 |

含义与约束：

- `description` 要**具体**——它是第 1 级、是唯一的触发依据，写宽泛会误触发（也是 §2.3 的安全面）。
- 把详细文档/大表/schema 拆到同目录文件，正文按名引用，别全塞进 `SKILL.md` 正文（控制第 2 级体积）。
- 重逻辑写成脚本让 agent 执行，只回结果——既省上下文又避免小模型"看着代码瞎改"。
- 这套机制与 Anthropic 开放的 Agent Skills 标准一致，故同一个 `SKILL.md` 包在其它兼容 runtime 也可复用（可移植，不锁定我们）。

## 2. 安装 / 加载

对外管理面（Gateway，默认本机）。**安装类操作是管理权限操作（admin scope）**，因为装一个 skill = 往设备注入 agent 会执行的代码/指令：

| 操作 | 端点 | 权限 | 说明 |
| --- | --- | --- | --- |
| 列表 | `GET /v1/skills` | 读 | 返回已安装 skill、启停状态、描述、`unmet_requirements` |
| 安装 | `POST /v1/skills/install` | **admin** | 上传/提交 Skill 包；校验 `SKILL.md` + `requires` 后落盘 |
| 读取 | `GET /v1/skills/{name}` | 读 | 读 `SKILL.md` 与元信息 |
| 启用 | `POST /v1/skills/{name}/enable` | **admin** | 允许 agent 自动触发 |
| 禁用 | `POST /v1/skills/{name}/disable` | **admin** | 保留文件但不触发 |
| 删除 | `DELETE /v1/skills/{name}` | **admin** | 移除 skill |
| 扫描 | `POST /v1/skills/scan` | **admin** | 重新扫描底层目录（调试/装配用） |

**权限模型（MVP）**：

- 标记 **admin** 的端点是管理面，**不应暴露给不可信的 SI 业务调用方**。门锁开启时它们要求 `Authorization: Bearer <token>`；无 token/非管理调用 → `403` `permission_error` `code:admin_required`。
- MVP 复用同一个设备 Bearer Token 作为管理凭证（单盒单租户假设）；**预留**独立管理 scope（如 `X-Pinea-Admin` 或区分 token），等真出现「SI 自助装 skill」需求时再细分，端点形状不变。
- 读类端点（列表/读取）走普通门锁即可。
- **作用域**：管理端点也接受 `X-Pinea-App-Id`（缺省 `default`，见 `capability-api.md` §0.1）。MVP skill 是全局命名空间；v1 预留按 `app_id` 隔离 skill 与 workspace，端点形状不变。

### 安装请求（MVP）

先支持两种形态，二选一即可：

```json
{
  "source": { "type": "local_path", "path": "/opt/pinea/skills/audio-archive" },
  "enabled": true
}
```

或 `multipart/form-data` 上传压缩包：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file` | zip/tar | 包内根目录必须包含 `SKILL.md` |
| `enabled` | bool? | 默认 `true` |

安装响应：

```json
{
  "name": "audio-archive",
  "version": "1.0.0",
  "enabled": true,
  "installed_at": "2026-06-09T00:00:00Z",
  "status": "installed",
  "unmet_requirements": []
}
```

安装流程固定：

1. 解包/读取 → 校验 `SKILL.md` frontmatter 的 `name`、`description`；缺失/格式错 → `400` `invalid_request_error`。
2. 校验 `name` 为 kebab-case；同名见 §2.2 升级规则。
3. **能力校验**：把 `requires.modalities/tools` 比对 `GET /v1/capabilities`。缺依赖时不静默装坏：要么 `400` 拒绝，要么装但 `enabled:false` 且 `unmet_requirements:[...]`，由 `?force=true` 决定（默认拒绝）。
4. 写入 `~/.pilotdeck/skills/<name>/`（项目级目录后置）。
5. 写 Gateway registry：`name / version / enabled / source / requires / installedAt / updatedAt`。
6. 触发 runtime skill scan；若 runtime 不支持热加载，返回 `status:"installed_restart_required"` 或等价提示。

启停只改 registry + runtime 可见性，不修改 `SKILL.md` 内容。删除先禁用再移除目录；失败时保持 registry 和磁盘一致。

### 2.2 版本 / 升级 / 回滚

- 同名再装：若带更高 `version` → 视为**升级**，旧版本目录留存为 `<name>@<old_version>` 以便回滚；registry `updatedAt` 刷新。
- 同名同版本再装 → 默认拒绝（`409`/`invalid_request_error`），`?force=true` 覆盖。
- 回滚：`POST /v1/skills/{name}/rollback`（后置）切回保留的上一版本。MVP 可只保最近一版。

### 2.3 触发边界（prompt-injection 风险）

`description` 是 agent 自动选用 skill 的唯一依据，等价于一段会进 system 上下文的指令，**有被滥用/注入风险**：

- 安装方（admin）对 `description` 内容负责；写**具体**触发条件，别写「任何时候都用」之类的宽泛/抢占式描述。
- Gateway 安装时可做基本卫生检查（长度、禁止显式越权指令片段）；这是尽力而非沙箱。
- 启用即授信：禁用态的 skill 不进 agent 触发候选。最小权限——只 enable 当前需要的 skill。

### 2.4 信任模型（MVP 边界，明说不兜底）

- skill 是**受信任的代码/指令**，运行在 runtime 的工具权限下（见 `agent-api.md` §4 权限边界）。MVP **不做签名校验、不做沙箱隔离**。
- 因此安装必须是 admin 操作（§2 权限模型），不可把 `install` 暴露给不可信网络/调用方。
- 预留演进位（不破契约）：包签名 + 校验、按 `requires` 收敛的能力沙箱、来源白名单。出现「第三方 skill 市场」需求前不实现，但接口已为其留好 `source` / `version` / `requires` 字段。

内部落点仍是 runtime 的磁盘扩展点：

| 位置 | 作用域 | 说明 |
| --- | --- | --- |
| `~/.pilotdeck/skills/<name>/` | 用户级 | runtime 默认扫描 |
| `<project>/.pilotdeck/skills/<name>/` | 项目级 | 随项目走 |
| 本仓 `skills/<name>/` 或 `products/<行业>/.../<name>/` | 我们的源 | 出厂预装/产品装配来源 |

接口安装不是为了绕开磁盘，而是为了隐藏实现细节、做格式校验、支持启停/升级/回滚。直接拷目录只作为出厂预装或调试手段。

## 3. skill 怎么用"能力面"

skill 正文/脚本通过**能力面端点**（`capability-api.md`）拿多模态能力，而不是直接摸模型。例如 STT：

```bash
curl -s -X POST "$PINEA_GATEWAY/v1/audio/transcriptions" \
  -H "Authorization: Bearer $PINEA_TOKEN" \
  -F "file=@$f" -F "model=whisper-medium" -F "language=zh"
```

约定：能力面 base_url / token 经环境变量（如 `PINEA_GATEWAY` / `PINEA_TOKEN`）注入，skill 不写死地址；本机封闭部署关闭门锁时可省略 token。

## 4. 两种 skill

- **能力型 skill**：把一个能力包成 agent 可用动作（"转写这段音频"）。薄。
- **行业 workflow skill**：编排 能力 + 工具 + 记忆 成可复用作业（"音频资料整理"：批量 STT → 去重打标 → 归档入记忆）。厚，是卖点。

## 5. 铁律（决定能否发 B 端）

1. **只依赖**：能力面端点 + Runtime 的 skill/tool 契约。
2. **绝不依赖 soul**：不读 PineaState 总线、不碰感知/表达/认主。→ 天然可发 🔵 B 端（拆灵魂时 skill 不受影响）。
3. **路径/资源用约定的注入变量**，不写死本机路径（规避之前 spike 里的点目录/绝对路径坑）。
4. **交付走接口，内部可落盘**：SI/产品侧不依赖 PilotDeck 目录结构；换 runtime 时重接管理接口即可。

## 6. 给交付方的并行约定

- 先拿 `capability-api.md` 的 **mock 能力面**联调 skill 流程（STT 回固定文本即可验证编排），真模型后置；契约不变，skill 不返工。
- skill 质量验收：参考 `vendor/pilotdeck/skills/skill-creator/`（评测/对比/打分 agent）的方法建最小验收。
