# Spike: STT 经 Model Gateway

> living doc。agent 边执行边回写。有边界——出结论就标 done 并把结论沉淀回 `docs/model-gateway.md`，然后退役。
> 方法见 `../../docs/agent-native-workflow.md`。

- **状态**: open
- **对应 build-plan 步**: 能力面 MVP 第 2 步（chat 透传后）；支撑"音频资料整理"skill
- **负责人 / agent**:

## 要回答的问题
能不能在本机用一个 whisper 类后端，经 Pinea Model Gateway 暴露 `POST /v1/audio/transcriptions`（OpenAI 兼容），把一段中文音频稳定、够快地转成文字，质量足以驱动"音频资料整理"skill？

## 约束（盒子真实约束，探索必须满足）
- 算力 / 功耗 / NPU: 端侧盒子，与 ollama(20B/MoE) 共享 GPU/显存；STT 不能把显存挤爆导致 LLM 掉线。优先可 CPU/小显存跑的 whisper 量化变体。
- 延迟预算: 资料整理是离线/准实时任务，单条 ≤ 音频时长的 ~0.5×（RTF≤0.5）可接受；非强实时。
- 隐私 / 出网: 全本地，零出网。

## 判定标准（什么算过）
- [ ] 网关 `POST /v1/audio/transcriptions`（multipart file + model 字段）返回 OpenAI 形状的 `{text}`。
- [ ] 中文识别 WER 主观可用（人读转写能还原原意，专名错可容忍）。
- [ ] 一段 ~1min 中文音频端到端 RTF ≤ 0.5，且不挤垮并行的 ollama 推理。
- [ ] 后端崩溃/超时时网关返回干净错误，不挂起。

## 候选后端
- **首选 speaches**（前 faster-whisper-server，CTranslate2）：原生 OpenAI `/v1/audio/transcriptions`，CPU/GPU 量化，挂上近透传，网关 adapter 几乎零工作量。
- whisper.cpp（CPU 友好，端侧最轻，退路）。
- vllm-omni + Qwen3-ASR（GPU 盒子可选实现，见 `vllm-omni-box.md`；同一网关 adapter 接口可替换）。
- ollama 侧 STT（当前 tags 无，待查）。

## 试验矩阵（agent 回写）

| # | 后端 / 模型 / 量化 | 音频样本 | RTF | 质量(主观) | 通过? | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | speaches / whisper-? / ? | 中文 ~1min |  |  |  | 首测 |

## 结论（done 时填）
<最终选哪个 STT 后端、量化、对显存/延迟的影响。沉淀回 docs/model-gateway.md §4/§8 后这里留指针。>
