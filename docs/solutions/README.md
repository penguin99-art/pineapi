# 行业方案线（solutions）——客户需求怎么落盘、怎么推进

> 配套：ToB 接口契约见 `../interfaces/`（已冻结 `contract-v1.0`），交付节奏见 `../build-plan.md`（T-D 交付线）。

这一层放**客户/行业方案资产**，与 `docs/interfaces/` 的平台契约是两种东西：

| | `docs/interfaces/`（契约） | `docs/solutions/`（方案） |
| --- | --- | --- |
| 生命周期 | 冻结 + 版本化（tag 仲裁） | 跟客户走，随谈随改 |
| 内容 | 端点形状/错误/限额 | 需求、映射、行业 skill、验收、交付记录 |
| 改动规则 | 只增不破，破坏升 v2 | 自由演进，但**不得反向修改契约** |

## 目录规范（一个客户一个目录）

```
docs/solutions/<customer-slug>/
  requirements.md         需求落盘：客户原始需求结构化 + 待澄清清单（第一步，先于一切分析）
  integration-plan.md     对接方案：需求→①②③映射 + 盒内/盒外切分 + 分期计划 + 缺口清单 + 承诺口径
  phaseN-design.md        分期详设：该期范围/链路/schema/里程碑/就绪标准（一期一份，启动时才写）
  scenarios.md            典型使用场景：看到什么→流程→怎么实现（评审与对客户讲方案用）
  skills/                 行业 skill 设计稿（落地走 ../interfaces/skill-contract.md）
  acceptance.md           验收样例集与实测记录（N/N，对应 skill-contract §2.5）
  delivery.md             交付/部署/运维记录（对应 build-plan T-D）
```

文件按阶段产生，没到的阶段不建空文件。

## 三条规则

1. **方案引用契约只指 Stable 端点**（`../interfaces/tob-overview.md` §7 矩阵），并注明契约 tag。方案不得依赖 Reserved 端点。
2. **映射出的平台缺口不在方案里解决**：记入 `integration-plan.md` 的缺口清单 → 评估后进 `../build-plan.md` 排期。客户需求不直接改契约。
3. **凡是承诺给客户的 AI 效果，必须有验收样例集兜底**（实测 N/N，不承诺 100%）——这是 SLA 边界（`../model-gateway.md` §6.6）的方案侧落点。

## 当前方案

| 方案 | 状态 | 目录 |
| --- | --- | --- |
| 肠菌健康管理系统（门店智能设备 + 店员工作台 + 总部平台 + 智能触达） | 一期（评估推荐线 + 设备端）详设已出，M0 待启动 | [`gut-health/`](gut-health/) |
