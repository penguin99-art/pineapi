# tool-calling 复现 harness

第 0 步最大风险点的实测脚本：**本地模型经 PilotDeck agent loop 能否稳定走原生 `tool_calls` 完成多步工具任务**。
叙事 / 试验矩阵 / 结论在上一层的 living doc：[`../tool-calling-localai.md`](../tool-calling-localai.md)。本目录只放「可复跑的实测」。

## 一键跑

```bash
bash run.sh            # 默认 8 次
bash run.sh 20         # 正式 20 次固化成功率
KEEP_SERVER=1 bash run.sh 3   # 跑完不关 server，连续调试
bash run.sh --stop     # 停掉本 harness 起的 server
```

脚本会：preflight（ollama 可达 + tsx 就绪）→ 起 PilotDeck server（自管 pid，cwd=`workspace/`）→ 批量发 `读 source.txt → 一句中文总结 → 写 out_N.txt` → 统计 `N/M 通过` + 内容扣题数 + 平均延迟 → 默认跑完关 server。

## 目录

```
run.sh              一键脚本(自管 server 生命周期)
fixtures/source.txt 固定输入素材
workspace/          agent 工作区(自带 .git，gitignore，每次重写)
results/            out_*.txt / resp_*.json / server.log(gitignore，只留 .gitkeep)
```

## 怎么判定「真过」

不看模型嘴上说不说 "done"，看三条硬证据：
1. `results/resp_*.json` 里有 `[read_file done]` / `[write_file done]`（真走了工具，非文本伪调用）；
2. `workspace/out_N.txt` 实际写出来了；
3. 内容是对 `source.txt` 的真实总结（脚本用关键词做轻量扣题检查）。

## 看 server 日志

```bash
tail -f results/server.log
grep -iE "tool|read_file|write_file|autoOrch|error" results/server.log
```

## 已知坑（脚本已内置规避）

- **点目录**：让 agent 写 `.spike/x.txt` 这种点开头路径，模型会把路径写歪（`\.spike`/带空格/丢点）→ 用普通文件名。
- **会话复用**：复用同一个 `X-Hermes-Session-Id`，会话记忆残留 → 模型第二次"已完成"跳过 → 每次用唯一 session。
- **工作根**：`workspace/` 必须自己是 git 根，否则 PilotDeck 向上找到外层仓库当项目根 → 写到仓库根。
