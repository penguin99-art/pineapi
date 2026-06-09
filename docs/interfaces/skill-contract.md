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
description: 当用户要"整理/归档一批音频/录音"、把语音转成文字并分类入库时使用。
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
- `description`：**触发条件**，写清"用户说什么/想干什么时用"——这是 agent 选不选它的唯一依据，要具体。
- 正文：给 agent 的操作手册（何时用 / 步骤 / 注意），可引用同目录脚本。

## 2. 安装 / 加载

对外管理面（Gateway，默认本机；外放需 Bearer Token）：

| 操作 | 端点 | 说明 |
| --- | --- | --- |
| 列表 | `GET /v1/skills` | 返回已安装 skill、启停状态、描述 |
| 安装 | `POST /v1/skills/install` | 上传/提交 Skill 包；校验 `SKILL.md` 后落盘 |
| 读取 | `GET /v1/skills/{name}` | 读 `SKILL.md` 与元信息 |
| 启用 | `POST /v1/skills/{name}/enable` | 允许 agent 自动触发 |
| 禁用 | `POST /v1/skills/{name}/disable` | 保留文件但不触发 |
| 删除 | `DELETE /v1/skills/{name}` | 移除 skill |
| 扫描 | `POST /v1/skills/scan` | 重新扫描底层目录（调试/装配用） |

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
{ "name": "audio-archive", "enabled": true, "installed_at": "2026-06-09T00:00:00Z", "status": "installed" }
```

安装流程固定：

1. 解包/读取 → 校验 `SKILL.md` frontmatter 的 `name`、`description`。
2. 校验 `name` 为 kebab-case，且不与已安装 enabled skill 冲突。
3. 写入 `~/.pilotdeck/skills/<name>/`（项目级目录后置）。
4. 写 Gateway registry：`name / version? / enabled / source / installedAt / updatedAt`。
5. 触发 runtime skill scan；若 runtime 不支持热加载，返回 `status:"installed_restart_required"` 或等价提示。

启停只改 registry + runtime 可见性，不修改 `SKILL.md` 内容。删除先禁用再移除目录；失败时保持 registry 和磁盘一致。

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
