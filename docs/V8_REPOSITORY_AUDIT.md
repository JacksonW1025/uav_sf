# V8 仓库边界审计

## 1. 审计结论

当前 tracked checkout 只保留两类内容：

1. V8 叙事明确依赖的已建立证据及其直接资格/解释材料；
2. 明确服务于 V8 目标方法、但尚未通过后续实现门的低层组件。

仓库允许“尚未实现”，不允许用旧计划、旧策略或旧 patch 冒充 V8
实现。Git 历史是被删除材料的恢复层，不是当前 checkout 的组成部分。

审计范围仅为 Git tracked tree。被忽略的 `runs/`、`external/`、
`ros2_ws/` 和本地虚拟环境未被整理、移动或删除。

## 2. 当前状态

- 仓库整理阶段：`Stage 0 COMPLETE`；
- 下一阶段：定义 observation/evidence provenance contract；
- flight runtime：不存在；
- formal runner/matrix：不存在；
- 新 formal campaign：禁止；
- repository validator：只判定 V8 tracked-tree 边界，不判定实验 readiness。

## 3. 实验保留白名单

以下目录完整保留，因为它们直接支撑 V8 Motivation、measurement
foundation、bounded feasibility 或这些证据的解释边界：

| 目录 | V8 角色 |
| --- | --- |
| `motivation_thor_v1` | Stage A1 primary Motivation evidence |
| `motivation_thor_remediation_v1` | Stage A1 independent remediation |
| `motivation_stage_a2_thor_v1` | Stage A2 primary、永久 `MEASUREMENT_INSUFFICIENT` |
| `motivation_stage_a2_thor_remediation_v1` | Stage A2 independent remediation |
| `posthoc_physical_execution_validity_v1` | 建立 physical validity 必须独立进入 admissibility 的依据 |
| `posthoc_oracle_ablation_v1` | 解释 Oracle 组件依赖，不作为新 finding count |
| `posthoc_threshold_sensitivity_v1` | 约束 research-threshold claims |
| `posthoc_finding_consequence_triage_v1` | 约束 finding 与 consequence 的归因边界 |
| `stage_a2_runtime_qualification_v1` | 直接支撑 Stage A2 observation/runtime 解释 |
| `concurrency_barrier_qualification` | 记录旧 workload 的资源隔离事实；不授权新 V8 并发度 |
| `main_strategy_comparison_thor_v1` | 仅为 timing/feedback feasibility slice，不是 V8 main evaluation |

这些冻结包中的旧 RQ 名称、旧 result schema、旧 strategy label 和旧
classification 是当时证据记录的一部分。它们不定义当前方法。恢复其
原始执行环境或代码时，必须 checkout 包内绑定的历史 revision。

## 4. 已删除的 tracked 内容

### 4.1 与 V8 证据链无关或不再成立的实验

- 删除零 formal launch、旧三策略设计的
  `experiments/main_process_exit_strategy_thor_v1/`；
- 删除未执行、未进入 V8 主评价合同的
  `experiments/matched_differential_analyzer_v1/`。

Process exit 仍可在未来 lifecycle × mechanism corpus 分析中成为候选
action，但必须重新建立 provenance、schema、identity 和 qualification。

### 4.2 旧方法入口

已删除旧 experiment template、旧 result/plan schemas、三策略 timing
policy、live strategy backend、plan builder、trace closure、evaluation、
campaign/formal/qualification runners、旧 post-hoc executable analysis 及其
专用测试。保留的冻结报告不因此变成新结果；需要复现时使用其绑定的
Git revision。

### 4.3 旧 patch 与 flight image

已删除整个 active patch bundle、patch lock、source preparation/build
入口和旧 Thor flight-runtime image。原因包括：

- route-observation patch 含 V8 multirotor scope 之外的 rover 修改；
- instrumentation 与 controlled stimulus 被放在同一 observation-only
  分类下；
- 当前 closure 对多个 identity 字段进行推导或常量填充；
- allocator publication 与 actuator write/effect 没有独立证据边界。

当前 checkout 因而不能构建或运行 flight experiment。这是有意的 stop
state，直到新的最小 V8 instrumentation/stimulus patch、image 和 attestation
在计划门内完成。

## 5. 保留的部分实现

| 组件 | 保留原因 | 当前限制 |
| --- | --- | --- |
| route event/model skeleton | V8 Runtime Route Instance 的代码骨架 | 未记录字段 provenance，authority-event coverage 不完整 |
| raw collector、clock bridge、ULog extractor | V8 measurement foundation 的可复用低层能力 | 没有 V8 normalized-trace closure |
| Route/Freshness/Successor/Registration Oracle primitives | V8 contract suite 的候选组件 | 尚未绑定独立 observation contract 和 combined Gate |
| accounting | campaign/attempt 不可变 accounting 的基础 | 新 campaign/episode schema 未实现 |
| safety/cleanup/physical-takeoff primitives | V8 safety 与 physical precondition 的基础 | 尚未进入统一 overall admissibility |
| artifact hashing/isolation | evidence retention 与资源隔离基础 | 并发度必须在新 runtime 上重新 qualification |
| Stage A2 workload helper、ROS/PX4 workload components | V8-cited workload 与未来 corpus 的候选构件 | 没有 active image/runner，不得直接执行 |

## 6. 尚未解决的科学门

1. 为每个 identity/effect 字段记录 `observed / derived / inferred /
   constant` provenance；正式 identity 字段不得由计划预期自证。
2. 分离 allocator publication 与 writer/effect observation。
3. 将 trace integrity、identity、clock、environment 和 physical validity
   合并为一个 overall admissibility 决策。
4. 新建 candidate → reproduction → minimization → cluster → attribution →
   consequence 的 finding schema/state machine。
5. 只有 overall-admissible execution 才能更新 semantic coverage。
6. 建立 campaign/episode/action-sequence schema、完整 semantic state、四个
   公平策略、真实上层栈 seed/reachability 和 repeated-campaign statistics。

以上均是 [中文实验计划](EXPERIMENT_PLAN.zh-CN.md) 中的未完成 gate，不能
被 repository validation 的 `PASS` 替代。

## 7. 新内容准入规则

任何新 tracked 文件至少满足一项：

- 映射到 V8 的 RQ、method component、evidence obligation 或 experiment
  plan gate；
- 是白名单证据包内不可分割的 preregistration、ledger、attestation、
  compact evidence 或 report；
- 是验证上述边界所必需的测试、schema、配置或文档。

新增 experiment 目录、runner、plan schema、patch、flight image 或 formal
matrix 时，必须同时：

1. 完成其前置计划门；
2. 更新中英文计划状态；
3. 更新本审计的映射；
4. 有意修改 validator allowlist；
5. 运行 `./scripts/validation/validate_repo.sh`。
