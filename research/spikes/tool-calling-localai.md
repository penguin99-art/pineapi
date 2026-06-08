# Spike: LocalAI + 端侧模型的 agentic tool calling

> living doc。agent 边执行边回写。这是**全项目最大风险**：本地模型若不能稳定多步调工具，PilotDeck 的 agent loop 就跑不起来，后面全塌。过了再写任何集成代码。
> 方法见 `../../docs/agent-native-workflow.md`，背景见 `../../docs/build-plan.md` 第 0 步。

- **状态**: open（进行中）
- **对应 build-plan 步**: 第 0 步（起跑线）
- **负责人 / agent**: agent
- **环境**: LocalAI(ollama 后端) @ `http://192.168.11.155:8080/v1`；PilotDeck @7ec1f25，PILOT_HOME=`deploy/pilot-home`，gateway:18790，api_server:8642，router 关闭（单模型）。
- **可用模型**: `ollama-qwen3-32b` / `ollama-qwen3-coder-30b` / `qwen35-mtp` / `ollama-minicpm-v-latest`(视觉) / `ollama-nomic-embed-text-latest`(embed)。无纯文本版 MiniCPM。

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

> 延迟基线：OpenAI 层单工具 ~17-18s；qwen3-32b 直连最简对话 ~32s(慢且 thinking)；PilotDeck 多步端到端 80-180s。

## 阶段结论（2026-06-08，仍 open）

**风险已坐实**：本地模型经 PilotDeck agent loop 跑 agentic tool calling **当前不通过**。

- 已排除：「PilotDeck 没发 tools」——源码 `src/model/providers/openai/request.ts:69` 确认请求体带 `tools` + `tool_choice`。
- 核心矛盾：**直连 OpenAI 层 + 单个简单工具 → 三个 Qwen 都能发原生 `tool_calls`；进 PilotDeck（十几个工具 + 大 system prompt）→ 两个 Qwen 都退化成文本伪调用**（coder 用 `<xml>`，32b 用 markdown `tool_code`），harness 截不到 → 幻觉续写。
- 旁证约束：远端 LocalAI 走 **ollama** 后端，32B 慢（~32s/最简调用）且默认开 `<think>`；冷加载会 `fetch failed`。盒子目标 SKU 待定。

### 下一步排障（按优先级，未做）
1. **抓线**：在 PilotDeck 与 LocalAI 间挂日志代理，dump 真实 request/response —— 确认 tools 数量/schema、tool_choice 值、以及模型回包是原生 tool_calls 还是文本。（最高价值，定位"传了但没触发"还是"传了触发了但 ollama 模板没解析"）
2. **减工具**：单回合只暴露 `read_file`+`write_file`（PilotDeck 工具裁剪/allowedTools），看是否恢复原生 tool_calls。
3. **关 thinking**：Qwen3 `enable_thinking:false` / `/no_think`，避免推理干扰工具输出。
4. **换 serving/模型**：ollama 的 OpenAI 兼容 tool 解析可能弱；试 LocalAI 原生后端 + grammar/约束解码，或换专为 OpenAI function-calling 调教的模型（Hermes/functionary 类）。
5. **盒子算力**：32B 在目标盒子端侧能否实时跑要单独量（可能要降到更小但 tool-calling 稳的模型）。

## 排障方向（tool calling 不稳时按序试，别往下走）
1. 换模型 / 换量化精度
2. 调采样（温度、top-p）、约束解码 / grammar
3. 改工具 schema 描述与系统提示词
4. 减少单回合工具数 / 简化工具签名

## 结论（done 时填）
<选定的模型+量化+采样+提示词组合；端侧延迟基线；对 architecture.md L2/L4 的影响。沉淀后这里留指针。>
