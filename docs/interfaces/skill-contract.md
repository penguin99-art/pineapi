# L7 公共 Skill 契约（可复用行业能力）

> 配套：架构见 `../architecture.md` §7，能力面见 `capability-api.md`，Agent 面见 `agent-api.md`，总览见 `README.md`。
> 这是 **ToB 第三类接口**——把行业流程做成可复用 skill，跑在 ② Agent 面之上，发 B 端。
> 依据（PilotDeck 真实契约）：`vendor/pilotdeck/skills/*/SKILL.md`、`vendor/pilotdeck/src/extension/skills/types.ts`、gateway 的 `skillsList/skillRead/...` RPC（`src/gateway/protocol/types.ts`）。

## 0. 一句话

Skill = 一个目录，里面一个 **`SKILL.md`**（YAML frontmatter + markdown 正文）+ 可选脚本/资源。Runtime 扫描磁盘 skill 目录加载，agent 在合适时机按 `description` 触发。**零改核心**。

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

## 2. 放哪 / 怎么加载

| 位置 | 作用域 | 说明 |
| --- | --- | --- |
| `~/.pilotdeck/skills/<name>/` | 用户级 | runtime 默认扫描 |
| `<project>/.pilotdeck/skills/<name>/` | 项目级 | 随项目走 |
| 本仓 `skills/<name>/` 或 `products/<行业>/.../<name>/` | 我们的源 | 装配时投放到上面目录 |

加载零改核心：runtime 自动扫描；也可经 gateway RPC（`skillsList/skillRead/skillWrite/skillValidate/skillScan`）管理。

## 3. skill 怎么用"能力面"

skill 正文/脚本通过**能力面端点**（`capability-api.md`）拿多模态能力，而不是直接摸模型。例如 STT：

```bash
curl -s -X POST "$PINEA_GATEWAY/v1/audio/transcriptions" \
  -H "Authorization: Bearer $PINEA_KEY" \
  -F "file=@$f" -F "model=whisper-medium" -F "language=zh"
```

约定：能力面 base_url / key 经环境变量（如 `PINEA_GATEWAY` / `PINEA_KEY`）注入，skill 不写死地址。

## 4. 两种 skill

- **能力型 skill**：把一个能力包成 agent 可用动作（"转写这段音频"）。薄。
- **行业 workflow skill**：编排 能力 + 工具 + 记忆 成可复用作业（"音频资料整理"：批量 STT → 去重打标 → 归档入记忆）。厚，是卖点。

## 5. 铁律（决定能否发 B 端）

1. **只依赖**：能力面端点 + Runtime 的 skill/tool 契约。
2. **绝不依赖 soul**：不读 PineaState 总线、不碰感知/表达/认主。→ 天然可发 🔵 B 端（拆灵魂时 skill 不受影响）。
3. **路径/资源用约定的注入变量**，不写死本机路径（规避之前 spike 里的点目录/绝对路径坑）。

## 6. 给交付方的并行约定

- 先拿 `capability-api.md` 的 **mock 能力面**联调 skill 流程（STT 回固定文本即可验证编排），真模型后置；契约不变，skill 不返工。
- skill 质量验收：参考 `vendor/pilotdeck/skills/skill-creator/`（评测/对比/打分 agent）的方法建最小验收。
