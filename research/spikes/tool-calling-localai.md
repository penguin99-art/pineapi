# Spike: LocalAI + 端侧模型的 agentic tool calling

> living doc。agent 边执行边回写。这是**全项目最大风险**：本地模型若不能稳定多步调工具，PilotDeck 的 agent loop 就跑不起来，后面全塌。过了再写任何集成代码。
> 方法见 `../../docs/agent-native-workflow.md`，背景见 `../../docs/build-plan.md` 第 0 步。

- **状态**: open（核心问题已通过 gpt-oss:20b 验证；待补 ≥20 次正式跑 + qwen 复测 + 盒子算力）
- **对应 build-plan 步**: 第 0 步（起跑线）
- **负责人 / agent**: agent
- **环境（2026-06-08 起切换）**: **ollama 直连** @ `http://localhost:11434/v1`（去掉 LocalAI 代理层）；PilotDeck @7ec1f25，PILOT_HOME=`deploy/pilot-home`，gateway:18790（env `PILOTDECK_GATEWAY_PORT`，默认 18789 被本机无关 `openclaw-gateway`/app 占用），api_server:8642，router 关闭，`skipPermissions` 默认 true。
- **旧环境**: LocalAI(ollama 后端) @ `http://192.168.11.155:8080/v1`（同机，本质是 ollama 的代理壳）。
- **可用模型（ollama 本机）**: `gpt-oss:20b`(主，原生 tool calling 最稳) / `qwen3-coder:30b` / `qwen3:32b` / `qwen3.5:*`(2b~122b) / `qwen3.6:27b/35b` / `gemma4:*` / `minicpm-v:latest`(视觉) / `nomic-embed-text`(embed)。

## 要回答的问题
LocalAI 挂 MiniCPM（及备选 Qwen）暴露 OpenAI 兼容端点后，PilotDeck 能否用它**稳定**完成一次多步、带工具调用的任务（读文件 → 总结 → 写回），不靠云模型兜底？

## 约束（探索必须满足）
- 算力 / 功耗 / NPU: 目标盒子 SKU（Lite/Pro 待定）的端侧算力包络，不靠外接大卡。
- 延迟预算: 单次工具回合可接受的首 token / 完成延迟（待定，先量基线）。
- 隐私 / 出网: 默认全本地，不出网即可完成。

## 判定标准（什么算过）
- [ ] PilotDeck 配 `model.providers` 指向 LocalAI，能起会话。
- [ ] 用**本地模型**完成「读文件 → 总结 → 写回」多步任务，工具调用格式正确。
- [ ] 连续跑 N 次（建议 ≥20）成功率达标（先定 ≥80% 再迭代），失败模式可归类。
- [ ] 记录稳定可用的模型 / 量化 / 采样 / 提示词组合。

## 试验矩阵（agent 回写）

| # | 模型 | 层 | 任务 | 结果 | 通过? | 失败模式 |
| --- | --- | --- | --- | --- | --- | --- |
| 0a | qwen3-coder-30b | OpenAI 层直连 | 单工具 get_weather | 正确发 `tool_calls`(args 对) | ✅ | — |
| 0b | qwen3-32b | OpenAI 层直连 | 单工具 get_weather | 正确发 `tool_calls` | ✅ | — |
| 0c | qwen35-mtp | OpenAI 层直连 | 单工具 get_weather | 正确发 `tool_calls` | ✅ | — |
| 1 | qwen3-coder-30b | PilotDeck agent loop | 读文件→总结→写回 | **未走工具协议**：把工具调用当文本输出 `<read_skill>{...}</read_skill>`，且**编造文件内容**，summary.txt 未生成 | ❌ | 工具调用以 XML 文本伪输出(coder 模型为 qwen-code XML 格式调教)，harness 截不到→幻觉续写 |
| 2 | qwen3-32b | PilotDeck agent loop | 读文件→总结→写回 | **未走工具协议**：冷启首次 `fetch failed`(~35s,疑似 ollama 冷加载超时)；warm 重试输出文本伪调用 ` ```tool_code\nread_file({...})``` `，summary.txt 未生成 | ❌ | 同样把工具调用当文本输出(markdown tool_code 风格)；且 32B 慢(连"hi"也要~32s)、带 `<think>` 推理 |
| 3a | gpt-oss:20b | ollama 直连 OpenAI 层 | 单工具 get_weather | 正确发原生 `tool_calls`(args 对) | ✅ | — (~14s 含冷加载) |
| 3b | gpt-oss:20b | PilotDeck agent loop | 读文件→总结→写回 | **走原生工具协议**：`[read_file done][write_file done]`，summary.txt 写出且内容扣题(非幻觉) | ✅ | — (首跑冷启 ~78s) |
| 3c | gpt-oss:20b | PilotDeck agent loop ×8(唯一会话, 普通目录) | 读文件→总结→写回 | **8/8 通过**，输出均为真实总结 | ✅ | — (热态 10-19s/次) |
| 3d | gpt-oss:20b | PilotDeck agent loop ×6(点目录 `.spike/`) | 读文件→总结→写回 | 6/6 都发原生工具调用，但 ~3 次把 `.spike` 路径写歪(`\.spike`/` .spike`/`spike`) | ⚠️ | **非协议问题**：点目录路径被模型转义/篡改；另复用 session id 致 1 次"已完成"跳过 |

> 延迟基线：OpenAI 层单工具 ~17-18s；qwen3-32b 直连最简对话 ~32s(慢且 thinking)；PilotDeck 多步端到端 80-180s。
> **ollama 直连 + gpt-oss:20b**：单工具直连 ~14s；PilotDeck 多步首跑(冷) ~78s，热态 10-19s/次。

## 阶段结论（2026-06-08 晚，切 ollama 直连后 → 核心问题 PASS）

**突破**：把模型层从 LocalAI(代理) 切到 **ollama 直连 + `gpt-oss:20b`** 后，本地模型经 PilotDeck agent loop 的多步原生工具调用**稳定通过**。

- 「读文件→总结→写回」用普通目录 **8/8 通过**，输出均为真实总结（非幻觉），热态 10-19s/次。
- 加上单工具直连 + 首跑共 ~14 次尝试，**全部发原生 `tool_calls`**（不再退化成文本伪调用）。
- 残留抖动**非 tool-calling 协议问题**：① 点目录 `.spike/` 路径被模型转义/篡改 → 用普通目录名规避；② 复用 `X-Hermes-Session-Id` 致会话记忆残留、第二次"已完成"跳过 → 每跑用唯一 session。
- 旁证：PilotDeck 自带 `[autoOrch] toolsStripped=true, sysPromptSlim=true`（裁工具 + 精简 system prompt）在生效，正好对冲之前「多工具 + 大 prompt 导致退化」的诱因。

**为什么之前 LocalAI 不通、ollama 直连通**：两者后端都是 ollama，但 LocalAI 的 OpenAI 兼容层在工具解析/模板上多套一层、且之前用的是 qwen-coder(XML 调教)/qwen3-32b(thinking)。换成 ollama 原生 `/v1` + 专为 function-calling 调教的 `gpt-oss:20b`，原生 `tool_calls` 解析恢复。→ 印证排障方向 #1(serving 层) + #4(换模型)。

### 旧结论（2026-06-08 早，LocalAI 阶段，已被上面取代）
**风险曾坐实**：本地模型经 PilotDeck agent loop 跑 agentic tool calling **当时不通过**。

- 已排除：「PilotDeck 没发 tools」——源码 `src/model/providers/openai/request.ts:69` 确认请求体带 `tools` + `tool_choice`。
- 核心矛盾：**直连 OpenAI 层 + 单个简单工具 → 三个 Qwen 都能发原生 `tool_calls`；进 PilotDeck（十几个工具 + 大 system prompt）→ 两个 Qwen 都退化成文本伪调用**（coder 用 `<xml>`，32b 用 markdown `tool_code`），harness 截不到 → 幻觉续写。
- 旁证约束：远端 LocalAI 走 **ollama** 后端，32B 慢（~32s/最简调用）且默认开 `<think>`；冷加载会 `fetch failed`。盒子目标 SKU 待定。

### 下一步（核心已过，剩收尾 + 泛化）
- [x] ~~换 serving/模型~~ → **切 ollama 直连 + gpt-oss:20b，已恢复原生 tool_calls**（排障方向 #1/#4）。
- [ ] **正式跑 ≥20 次**（唯一 session + 普通目录）固化成功率数字，归类剩余失败（目前小样本 8/8）。
- [ ] **qwen 在 ollama 直连下复测**：`qwen3:32b` / `qwen3-coder:30b` / `qwen3.5:*`，看是否也恢复（之前的失败是 LocalAI 层 + 模型选择，未必是 qwen 本身不行）；关 thinking 对比。
- [ ] **更难的多步任务**：>2 步、链式工具（read→grep→edit→write），看 gpt-oss:20b 是否仍稳。
- [ ] **盒子算力**：20B/MXFP4 在目标盒子端侧的 tok/s 与延迟单独量；若不达标，找更小但 tool-calling 稳的模型。
- [ ] **路径鲁棒性**：给 agent 的 prompt/skill 约定「用绝对路径或非点目录」，规避点目录被篡改。

## 排障方向（tool calling 不稳时按序试，别往下走）
1. 换模型 / 换量化精度
2. 调采样（温度、top-p）、约束解码 / grammar
3. 改工具 schema 描述与系统提示词
4. 减少单回合工具数 / 简化工具签名

## 结论（done 时填）
<选定的模型+量化+采样+提示词组合；端侧延迟基线；对 architecture.md L2/L4 的影响。沉淀后这里留指针。>
