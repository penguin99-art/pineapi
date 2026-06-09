# Spike: 盒子后端选型（杂牌轻量栈 vs vllm-omni vs 单 omni 模型）

> living doc。agent 边执行边回写。出结论就把"盒子最终挂什么后端"沉淀回 `docs/model-gateway.md`（§3 后端选型口径 / §6 资源仲裁），然后退役。
> 方法见 `../../docs/agent-native-workflow.md`。

- **状态**: open
- **对应 build-plan 步**: 能力面落地（与 STT/TTS/生图 各 spike 并行）
- **负责人 / agent**:

## 要回答的问题
目标盒子上，多模态能力面到底怎么挂最划算？三条路线对比：
1. **杂牌轻量栈**：ollama(文本/视觉) + speaches/whisper.cpp(STT) + Piper/Kokoro(TTS) + ComfyUI/sd.cpp(生图/视频)，各进程 CPU/小显存优先。
2. **vllm-omni 统一栈**：每模态一个 vllm-omni 实例，GPU 重、一实例一模型。
3. **Qwen3-Omni 单模型合并**：一个 omni 模型吃下 文本+视觉+音频理解+ASR，少起几个进程（TTS/生图/视频生成仍需另挂）。

## 约束（盒子真实约束，探索必须满足）
- 算力 / 显存: 目标盒子 GPU/VRAM（待填实际型号与显存）。文本(ollama)需常驻；不能因起多模态把 LLM 挤掉线。
- 延迟预算: 文本 tool-calling 回合保持现有水平（spike 已验 gpt-oss:20b ~12s/任务）；STT 离线 RTF≤0.5；生图/视频可异步慢。
- 功耗: 端侧常驻功耗预算（待填）。
- 隐私 / 出网: 全本地，零出网。

## 判定标准（什么算过）
- [ ] 给出目标盒子上"哪些后端能并发常驻、哪些必须按需起停/排队"的明确清单。
- [ ] 三条路线各自的：显存占用、冷启动时间、单请求延迟/RTF、对并行文本推理的干扰，测出数。
- [ ] 给出推荐挂法（可按盒子档位分：CPU 盒 / 入门 GPU 盒 / 富裕 GPU 盒）。
- [ ] 确认网关 adapter 接口能无缝切换所选后端（SI 侧无感）。

## 试验矩阵（agent 回写）

| # | 路线 | 后端/模型/量化 | 显存占用 | 冷启动 | 延迟/RTF | 干扰文本? | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 杂牌 | speaches whisper | | | | | STT |
| 2 | 杂牌 | Piper | | | | | TTS, 纯 CPU? |
| 3 | 杂牌 | ComfyUI + SD/Flux | | | | | 生图 |
| 4 | vllm-omni | Qwen3-ASR | | | | | STT 对照 #1 |
| 5 | 单 omni | Qwen3-Omni-30B | | | | | 文本+视觉+ASR 合并; tool-calling 需重测 |

## 待定输入（人填）
- 目标盒子 GPU 型号 / 显存 / 功耗预算：
- 是否接受文本从 ollama 迁到 vllm-omni（需重跑 tool-calling spike）：

## 结论（done 时填）
<盒子各档位最终挂法、为什么。沉淀回 docs/model-gateway.md 后这里留指针。>
