# agent-native 工作法

> 这是**怎么写这套代码**的方法，不是写什么（写什么见 `architecture.md` / `build-plan.md`）。
> 可执行版在 `../AGENTS.md` §5。本仓是产品实现仓——这里的"研究"都是**为实现服务的有边界 spike**，不是开放式漫游。

## 0. 一句话

人负责"想得对"（跨域激活、定约束、审关键产出），agent 负责"做得多"（实现、自纠错、覆盖测试）。用模型扩张你能同时比较的因子数。

## 1. 人机分工

| | 人做 | agent 做 |
| --- | --- | --- |
| 决策 | 定 intent / 约束 / 验收标准 | 在约束内探索实现方案 |
| 知识 | 选权威源、做跨域激活 | 蒸知识、查文档、写实现 |
| 质量 | **古法分析**关键产出 | 跑测试、自纠编译错、重试 |

**人只在三处亲自下场**（其余别插手，插手越多越压制 agent）：
1. **跨域激活**——拿别的领域的结构撞架构（这是你比模型强的地方）。
2. **定 intent 与约束**——尤其盒子的真实约束（功耗 / NPU / 端侧延迟 / 记忆隐私）。
3. **古法分析**——人工审两个接缝、🔵🟠 边界、记忆/安全这些**改了会脏架构**的决策。其余实现信任 agent。

## 2. Living doc = 控制面

每个技术未知数，先在 `research/spikes/<name>.md` 立一张可回写的表（仿 testplan.md），agent 边执行边更新状态。文档即编排状态机。

纪律：
- spike **有边界**：开头写清「要回答的问题」和「判定标准」，得到结论就**退役**（标 done，结论沉淀回 `architecture.md` 或代码注释），不无限跑。
- `build-plan.md` 的「通过标准」本身就是 living doc 的轻量形态，沿用同一套。

模板见 `research/spikes/_template.md`，第一个实例见 `research/spikes/tool-calling.md`。

## 3. skill 克制原则

模型本来就会很多（让它 reset GPU / 调 ffmpeg / 写测试都直接能干）。**不要预造一堆 skill 和 rule**——规则越多越把人的偏见塞进去、越压制探索。

只为**真正分布外**的流程建 skill：
- 设备实测 harness（灯带 / 麦阵列 / 功耗测量的固定流程）；
- 失败自纠错与重试约定；
- 我们自有的、模型训练集里没有的协议（PineaState schema、桌伴 channel 协议）。

判据：这件事**每次都要照同一套非显然步骤做**，才值得写 skill；否则交给模型即兴发挥。

## 4. 知识注入流程

写哪块前先注入，别让 agent 凭记忆瞎写：

```
权威源(PilotDeck 源码 / MiniCPM·Qwen / ollama·vllm-omni·whisper·扩散后端 / MCP / PilotDeck hook&channel 协议)
   → agent 蒸成 research/knowledge/<topic>.md(摘要 + 关键接口 + 我们怎么用)
   → 实现时引用这份语料,而不是重新猜
```

`research/knowledge/` 是可复用资产：换人、换 agent、升级 PilotDeck 后，先更这里再改代码。

## 5. 约束驱动探索

把盒子的真实约束当一等输入喂进去，让 agent 的方案落在**端侧能跑**的可行域：
- 算力 / 功耗包络 / NPU 算子支持 → 决定感知用多大模型、跑几级级联；
- 端侧延迟预算 → 决定哪些走本地网关后端、哪些走云、哪些预计算；
- 记忆隐私 → 决定什么留盒子、什么能出网。

约束写进对应 spike 的开头，agent 探索时必须满足。

## 6. 怎么和 build-plan 衔接

`build-plan.md` 的每一步，凡是带"不确定能不能成"的，先开一个 spike 把它打掉，再写正式代码：

| build-plan 步 | 对应 spike（示例） |
| --- | --- |
| 第 0 步 本地模型 tool calling | `research/spikes/tool-calling.md`（已过） |
| 第 4 步 感知级联成本 | `research/spikes/perception-cost.md`（需要时立） |
| SKU 选型 | `research/spikes/sku-codesign.md`（需要时立） |

spike 过了 → 结论回写架构/代码 → spike 退役 → 进下一步。
