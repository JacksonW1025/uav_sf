# NEW_NARRATIVE_v8

# Route-State-Guided Testing of Authority Handoffs in PX4

## 0. 文档定位

本文档是当前仓库唯一的研究叙事源，记录经过研究者确认的论文方向，而不是把尚未验证的实验设计写成既定结论。

配套文档各自只承担一种职责：

- [CURRENT_STATUS.md](CURRENT_STATUS.md)：已经完成的实验、证据和实现边界；
- [RESEARCH_SCOPE.md](RESEARCH_SCOPE.md)：当前实现与论文的范围合同；
- [ROUTE_MODEL.md](ROUTE_MODEL.md)：Runtime Route Instance、语义状态和契约；
- [METHOD.md](METHOD.md)：目标方法、当前原型与实现义务；
- [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md)：下一阶段的决策门和执行顺序；
- [THOR_MIGRATION_REPORT.md](THOR_MIGRATION_REPORT.md)：Thor 环境与迁移事实。

冻结实验的 preregistration、ledger、summary 和 final report 始终优先于概括性文档。本文明确区分三种内容：

- **Established evidence**：当前仓库可复核的正式结果；
- **Research decision**：已经确认的研究方向和边界；
- **Hypothesis / obligation**：仍需实现或实验检验的主张。

## 1. 一句话叙事

PX4 的控制权交接不是一个 mode 值的变化，而是命令生产者、注册与激活实例、控制器、分配器、执行器写入端和 lifecycle owner 共同完成的跨层状态迁移。本文建立可判定的运行时 route/contract state，并研究如何利用该状态闭环生成现实、合法且有价值的 lifecycle action sequence 与 timing，从而比现有场景测试和无反馈搜索更有效地暴露控制权交接问题。

论文最终必须达到**方法型贡献**。问题发现、危险性证据和机制分析负责建立方法的必要性与设计依据，不能代替方法本身；完整验证负责闭合证据链，也不能被提前当成方法有效性的证明。

## 2. 核心研究假设

待检验的中心 thesis 是：

> PX4 authority handoff 是一个跨层、有状态且受 lifecycle 与 timing 共同影响的过程。相较于 official scenarios、grammar-aware random、deterministic enumeration 和 feedback-free state-conditioned generation，使用完整 route/contract semantic state 闭环选择 action sequence 与 timing，能够在相同预算下更有效地覆盖语义边界并命中不同、可确认的 handoff findings；代表性 finding 能在完整上层飞控栈的闭环仿真中重放，并产生可解释的任务或物理后果。

这是一项**研究假设**，不是当前结果。现有 18-launch vertical slice 只证明 live feedback plumbing 和 bounded timing coverage 可执行，尚未证明上述方法优势。

## 3. 为什么这个问题值得研究

### 3.1 现实自主任务不断替换控制路径

典型无人机任务会经历：

```text
Mission / Planner / Behavior Tree
    -> Companion integration and action adapters
    -> DDS or MAVLink transport
    -> PX4 Commander / mode management / failsafe
    -> Setpoint routing and VehicleControlMode
    -> Position / attitude / rate controller
    -> Allocator
    -> Actuator writer
```

Takeoff、external autonomy、Hold、RTL、Land、manual/GCS takeover、failsafe 和任务恢复都可能改变当前真正产生 actuator effect 的路径。Mode Executor 还会把多个 external mode 组织成具有 completion、failure 和 successor 语义的 lifecycle。

上层任务软件可能因 node crash、callback stall、executor starvation、CPU/GPU overload、DDS delay/reconnect、planner deadlock、heartbeat 与 setpoint 分离或 process restart 产生 partial failure。这些事件不一定立即改变公开 mode，却可能改变命令新鲜度、owner、successor 或下游 lineage。

### 3.2 Mode 与 terminal outcome 观测不足

以下推断均不成立：

```text
mode changed
    != target route completely installed

target activated
    != target command reached the actuator writer

vehicle eventually landed
    != every intermediate authority handoff was correct
```

相同 mode 名可以对应不同 producer session、registration、activation 或 route epoch。新的 mode 也可能已经声明成功，但旧 writer 尚未撤销、新的 command lineage 尚未贯通，或者 lifecycle completion 没有推进正确 successor。

### 3.3 真正困难在跨层与异步边界

重复执行普通 enter/release happy path 不能充分覆盖以下条件：

- completion 与相邻 authority request 的竞态；
- external route 退出时 failsafe、GCS 或人工接管；
- heartbeat 存活但 setpoint 停止更新；
- producer restart、rapid re-entry 与同名 route 的新实例；
- registration、activation、owner 和 successor 不同步；
- target 声明成功但 controller/allocator/writer lineage 尚未完整安装。

因此，测试对象必须从 mode label 提升为跨层运行时 route state，测试输入也必须从固定单事件扩展为受状态约束的 action sequence 与 timing。

## 4. 研究对象、系统边界与真实上层栈

### 4.1 核心 SUT

核心被测系统是 PX4 中与 route management、command validity 和 lifecycle progression 有关的机制，包括：

- PX4 internal routes；
- Legacy Offboard；
- Dynamic External Mode；
- Mode Executor；
- internal Hold、RTL、Land 和 Recovery；
- 与这些路径有关的 registration、activation、health、setpoint consumption、controller/allocator/writer lineage、completion、successor 和 fallback。

论文的核心实证必须在这一 connected route system 内独立成立。

### 4.2 上层飞控栈不是 SUT

真实的 mission、planner、behavior 和 companion integration stack 承担三种角色：

1. 提供现实任务 trace、轨迹、参数和事件 seed；
2. 证明生成的 action sequence 在真实软件执行上下文中可达；
3. 重放代表性 finding，测量任务失败、轨迹偏差、进度损失或恢复异常。

本文不以发现上层软件自身缺陷为目标。上层栈异常必须通过 differential replay 与责任归因，区分 PX4 mechanism、adapter、任务软件、instrumentation 和环境问题。

### 4.3 外部有效性边界

必要的端到端验证环境是 PX4 SITL 加完整上层软件栈，即 full-stack closed-loop simulation。HITL、真机、额外 route family、第二个 autopilot 或更多 PX4 revision 可以增强外部有效性，但不是核心论文成立的依赖。

一般性首先来自状态抽象、action grammar 和方法设计，不能在没有跨系统实证时声称已经跨 autopilot 验证。

## 5. 已建立的 Motivation 与测量基础

### 5.1 Stage A1

当前 Thor Stage A1 的 primary 与 independent supplemental studies 共关闭 200 次 formal launch，得到 151 份 accepted/admissible evidence，其中 94 overall PASS、57 overall VIOLATION。各 study 保留独立 identity、ledger 和 denominator；这些数值不是 PX4 defect rate。

当前证据支持以下有边界结论：

- mode 与 terminal outcome 不能证明完整 handoff；
- Route correctness 与 Freshness 是独立维度；
- successor 最终安装与 completion/request timing-order 是独立事实；
- 同名 route 的重复进入需要 epoch 与 activation identity；
- observability、clock 或环境失败必须独立于 SUT PASS/VIOLATION。

Post-hoc physical-validity audit 发现 151 份 admissible trace 中有 12 次没有达到 0.08 m 以上，其中 3 PASS、9 VIOLATION。这不修改冻结结果，但证明 evidence admissibility 不自动等于物理任务已经有效执行。后续实验必须使用独立 physical-validity contract。

### 5.2 Stage A2 realism bridge

Stage A2 primary 在 51 次 launch 后因 measurement closure 问题保持 `MEASUREMENT_INSUFFICIENT`。独立 remediation 完成 26/26 accepted/admissible launch：10 条 normal trace overall PASS，16 条 deliberate healthy-stall trace 只违反 freshness。

移动任务没有产生新 violation class，但使物理后果可解释：healthy stall 后飞机继续运动约 1.0 m，并相对完整任务产生约 0.46--0.47 m 的进度 shortfall。该结果支持 bounded physical interpretability，不支持机制优劣、flyaway、真机危险或一般 defect claim。

### 5.3 当前 generation vertical slice

Setpoint-stall comparison 共 18 次独立 formal launch。Official 覆盖一个 timing bin，bounded random 与 current state-aware prototype 各覆盖三个；三者第一发都触发同一 deliberate freshness signature，random 与 prototype 打平。

因此当前结果只证明：

- action decision、schedule、live-state gating 与执行记录能闭合；
- 先前执行得到的 coverage 能影响同一 cell 中的后续选择；
- 一项 bounded timing action 能在统一 runtime 中比较。

它不证明完整 semantic state 已实现，也不证明 state-aware generation 优于 random 或 systematic search。

Process-exit backend 已完成 18/18 non-formal qualification，并有零 formal launch 的 preregistered candidate matrix。Readiness 不是执行授权；是否复用该设计必须由新的共同 corpus 与评价合同决定。

完整数字、study identity 和证据入口见 [CURRENT_STATUS.md](CURRENT_STATUS.md)。

## 6. Runtime Route Instance 与语义状态

### 6.1 稳定运行时身份

Runtime Route Instance 的稳定身份是：

```text
(route, route_epoch, producer_session, registration_id, activation_id,
 controller_id, allocator_id, writer_id, lifecycle_owner, executor_owner)
```

`command_subject_ns` 是每次 command consumption 与 downstream effect 的动态 freshness evidence，不是稳定 identity 字段。

### 6.2 完整 generator state

最终方法不能只使用 route name 或 `route_active`。目标语义状态至少包括：

1. route family、route identity 和 epoch；
2. 当前 authority owner 与 command lineage；
3. registration、activation、execution、completion、replacement、fallback 和 re-entry phase；
4. health 与 command freshness；
5. successor request、installation 和 ownership progression；
6. 粗粒度 motion/mission context；
7. 当前 sequence 中的 bounded action history。

原始 telemetry、uORB observation 和 instrumented events 是推导语义状态的证据来源，而不是论文直接声称的状态抽象。方法采用灰盒观测，并通过 reduced-observation replay 检查是否过度依赖专用 instrumentation。

当前 B 级 route/timing state 是 prototype；完整语义状态是正式方法的必要组成，而不是可选增强。

## 7. Evidence Gate、Contracts 与 Finding 语义

### 7.1 Evidence Admissibility Gate

任何 correctness 判断之前必须确认：

- trace identity、sequence 与 hash chain 完整；
- collection window 闭合；
- 关键事件存在且 clock domain 可映射；
- authority-bearing event 具有完整 route identity；
- execution environment 与 preregistered plan attestation 一致；
- 研究要求的物理执行前提成立。

不满足这些条件的 attempt 是 `INCONCLUSIVE` 或 measurement/environment failure，不能转换成 SUT PASS 或 VIOLATION。

### 7.2 Contract suite

- **Route Conformance**：source revocation、target installation、writer exclusivity 和 actuation continuity；
- **Freshness and Lineage**：完整 target-authority window 内的 command age 与 producer-to-writer lineage；
- **Successor Progression**：completion 后 successor、fault observation 和预期 safe fallback 的完整安装；
- **Registration and Activation**：预注册负面条件下的显式 rejection，不能用“没有 activation”代替 rejection evidence。

### 7.3 Finding 分层

所有结果必须使用以下层级，不能合并为一个 bug count：

1. **Research-contract exposure**：触及研究者定义的边界，但未必违反 PX4 公开 policy；
2. **Cross-layer contract violation**：在冻结研究合同下可重复违反一个或多个 obligation；
3. **Source-grounded PX4 defect**：经过最小化和责任归因，并由规范、源码不变量或维护者证据支撑；
4. **Safety-relevant finding**：在完整飞控栈闭环仿真中具有可重复的任务或物理后果。

来自真实上层栈但原因未知的事件只是高优先级 candidate。它必须通过独立复现、measurement 检查、最小化、clustering 和 attribution 后才能晋级。

## 8. 目标方法：Route-State-Guided Generation

### 8.1 闭环

```text
observe semantic state
    -> filter admissible actions
    -> select an action and timing
    -> execute through a reachable public or owned-process mechanism
    -> observe the next semantic state
    -> update coverage and corpus
    -> continue, terminate, or reset
```

Stateful 不仅意味着排除非法 action。Generator 必须在每一步执行后重新观测状态，并让此前覆盖影响后续 action/timing selection。

### 8.2 Action corpus 的来源

核心 action 不能由“当前 backend 最容易实现什么”决定。候选 action 按两条轴组织：

- lifecycle：registration、activation、steady execution、completion、replacement、fallback、re-entry；
- failure/authority mechanism：process exit、callback/setpoint stall、communication delay、health loss、capacity rejection、manual/GCS/failsafe takeover、adjacent request 和 restart。

真实 mission trace、公开接口、源码 transition、issue/commit 与已知 incident 为 action 和参数提供 provenance。未经解释的真实事件具有更高调查权重，但不会直接成为 ground truth。

### 8.3 Workload realism

采用两阶段搜索与一阶段确认：

1. 从真实上层任务提取 seed、trajectory、parameter distribution 和 reachable behavior；
2. 在可控 harness 中搜索、重放和最小化；
3. 将代表性 finding 放回 full-stack closed-loop simulation，验证可达性与后果。

Synthetic workload 可以用于机制隔离，但必须标注 reality distance。真实栈不能仅作为最终演示。

### 8.4 Feedback

在线反馈按以下逻辑组织：

1. 只有 admissible execution 才进入有效 coverage；
2. 主要奖励新的 `state--action/timing--next-state` semantic transition；
3. 对尚未覆盖的 contract boundary 提供次级优先级；
4. finding 进入独立确认队列，重复触发同一 signature 不持续获得高奖励。

运行时统计 state、transition、boundary 和 action visitation count。最终评价统计 finding quality、coverage、efficiency、evidence yield 与 cost；不能把在线 reward 与论文 outcome 混为一谈。

## 9. Research Questions

### RQ1: Representation and Oracle

跨层 Runtime Route Instance、semantic state 与 contract suite 是否能识别 mode-level 或 terminal-outcome testing 遗漏的 authority、freshness、continuity 和 successor 问题？

### RQ2: Generation Effectiveness

在共同 grammar、seed corpus、reset contract 和预算下，route-state- and feedback-guided generation 是否比 grammar-aware random、deterministic enumeration 和 feedback-free state-conditioned generation 更有效地命中已知或可确认 finding，并覆盖新的 semantic transition 与 contract boundary？

### RQ3: Findings and Consequences

发现可分为哪些语义层级、依赖哪些 mechanism/state/timing 条件，哪些代表性 finding 能在完整上层飞控栈的闭环仿真中重放并产生任务或物理后果？

## 10. Evaluation Contract

### 10.1 Baselines

核心因果比较包括：

- grammar-aware bounded random；
- budget-matched deterministic/systematic enumeration；
- state-conditioned but feedback-free generation；
- full state- and feedback-guided generation。

Official/handwritten scenarios 是现实测试实践参照，不与四个生成策略强行做完全等价的统计竞争。外部相关方法只有在共享 subject、grammar、budget 和 outcome 时才是可执行 baseline，否则只用于 related-work positioning。

### 10.2 Ground truth 与自然 finding

受控评价组合使用：

- 可重放的 historical known defects；
- 当前版本的 natural candidates，经确认后进入 benchmark；
- mechanism-derived seeded faults，与自然 finding 分开统计；
- 新发现的 natural findings，作为最强但不由偶然性决定的附加证据。

仅反复触发 deliberate stall/process-exit 的预期 violation 不能证明 finding effectiveness。

### 10.3 指标层级

- **主指标**：固定预算下命中的 distinct confirmed findings / known defects；
- **解释指标**：semantic state、transition 与 contract-boundary coverage；
- **效率指标**：executed actions、episodes 和 time to finding；
- **诊断指标**：admissible evidence yield、reset cost、analysis cost 和 safety interruption。

### 10.4 统计单位与公平预算

一次完整 adaptive campaign 是独立统计单位。每个 campaign 从清空 generator memory 开始，包含多个 episode；不同策略使用 paired seeds、共同 corpus、共同 reset semantics 和预注册预算。

正式评价以固定 execution budget 为主，并报告 wall-clock time 与计算/重置开销。具体 campaign 数、episode 数、action budget、最大 sequence length、effect size、uncertainty 与 stopping rule 必须在 pilot 后冻结，不能从正式结果反推。

### 10.5 核心消融

- 去掉 semantic feedback，只保留 admissible-action filtering；
- route-identity-only prototype state 对比完整 semantic state；
- timing-only 对比 action-sequence + timing；
- 仅对关键 Oracle 做 targeted ablation。

不预设大而全的消融数量。每个消融必须对应一个明确的因果问题。

## 11. 预期贡献

如果研究假设成立，论文贡献为：

1. 将 PX4 authority handoff 形式化为跨层 route-replacing state transition，而非 mode change；
2. Runtime Route Instance、完整 semantic state、Evidence Gate 与分层 contract suite；
3. 使用语义状态闭环选择 lifecycle action sequence 与 timing 的 generation method；
4. 具有 provenance、ground truth 分层、campaign-level statistics 和 full-stack replay 的评价方法；
5. 一组经过确认、分级并具有明确 claim boundary 的 PX4 handoff findings。

贡献 3--5 尚未由当前 vertical slice 建立，必须由后续实现和主实验支持。

## 12. 成功门槛与失败处理

最低方法成功门槛是：

- 完整 semantic-state generator 可执行并产生 admissible evidence；
- 在 historical/seeded/natural benchmark 上，相对合理 baseline 获得可重复的 finding 或效率增益；
- 增益能由 semantic transition/boundary coverage 解释；
- 至少一组代表性 finding 完成 full-stack closed-loop replay。

发现此前未知的自然 finding 是明确追求的强证据，但不是唯一硬门槛。如果完整方法不能超过 baseline，应重新设计 generator 或收缩主张，不能用 Motivation 结果代替方法有效性。

## 13. Claims 与非目标

### 当前可以声称

- 控制权交接需要 mode/terminal 之外的跨层 route evidence；
- 当前仓库已建立可复核的 Thor SITL measurement foundation；
- Stage A1/A2 支持有边界的 Motivation 与物理可解释性；
- 当前一项 live action vertical slice 证明 bounded feedback execution 可行；
- 完整 stateful method 和 general effectiveness 仍待实现与评价。

### 当前不能声称

- 57 条 violation 等于 57 个 PX4 bugs；
- 当前 prototype 优于 bounded random；
- 200 ms research threshold 是所有接口的 PX4 public policy；
- 295 次 launch 属于一个 pooled sample；
- SITL 结果已经证明真机危险；
- 方法已经跨 autopilot、airframe 或 route family 泛化。

### 明确非目标

- 修改 PX4 核心控制逻辑；
- 构建在线运行时保护或自动恢复系统；
- 把所有 contract violation 称为安全漏洞；
- 将上层 mission/planner 软件本身作为 fuzzing SUT；
- 为了显得完整而预先扩张到多平台、HITL 或真机。

## 14. 下一阶段执行门

下一阶段按 [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md) 推进。核心顺序是：

1. 实现完整语义状态与状态抽取；
2. 用 lifecycle、failure mechanism 和真实 provenance 冻结核心 corpus；
3. 实现闭环 sequence/timing generation 与 feedback；
4. 建立 historical/natural/seeded benchmark 和确认协议；
5. 接入真实上层栈，获得 seed 与 replay contract；
6. 实现公平 baseline，pilot 预算与方差；
7. preregister 并执行正式 repeated campaigns；
8. 重放、最小化、聚类和归因代表性 findings。

已有 process-exit candidate 的 readiness 不授权立即执行。只有当它进入新的共同 corpus、共享 baseline 和统计合同时，才能在新的或经确认仍有效的 identity 下开始 formal denominator。

## 15. 推荐论文结构

1. Introduction：mode-level testing 的盲区与方法概览；
2. Background：PX4 authority stack、route replacement 和现实故障来源；
3. Motivation Study：Stage A1/A2 与证据边界；
4. Runtime Route Model and Contracts；
5. Route-State-Guided Generation；
6. Implementation and Evidence Discipline；
7. Evaluation；
8. Findings、full-stack consequences 与 attribution；
9. Discussion、limitations 与 related work；
10. Conclusion。

## 16. Repository Evidence Anchors

- Stage A1 primary: [final report](../experiments/motivation_thor_v1/FINAL_REPORT.md)
- Stage A1 supplemental: [final report](../experiments/motivation_thor_remediation_v1/FINAL_REPORT.md)
- Physical-validity audit: [final report](../experiments/posthoc_physical_execution_validity_v1/FINAL_REPORT.md)
- Oracle ablation: [final report](../experiments/posthoc_oracle_ablation_v1/FINAL_REPORT.md)
- Threshold sensitivity: [final report](../experiments/posthoc_threshold_sensitivity_v1/FINAL_REPORT.md)
- Finding/consequence triage: [final report](../experiments/posthoc_finding_consequence_triage_v1/FINAL_REPORT.md)
- Stage A2 primary: [final report](../experiments/motivation_stage_a2_thor_v1/FINAL_REPORT.md)
- Stage A2 remediation: [final report](../experiments/motivation_stage_a2_thor_remediation_v1/FINAL_REPORT.md)
- Setpoint-stall vertical slice: [final report](../experiments/main_strategy_comparison_thor_v1/FINAL_REPORT.md)
- Process-exit candidate: [preregistration](../experiments/main_process_exit_strategy_thor_v1/preregistration.md)

## 17. v8 相对旧叙事的决策

v8 保留问题驱动的 PX4 stack、partial failure、input realism 和 attribution 逻辑，同时保留当前仓库的证据纪律、Thor 结果、Family A core boundary 与 prototype 限制。

v8 不接受两个极端：

- 不把论文停留在 measurement、机制发现或负面结果；
- 不把尚未实现、尚未比较的完整 stateful generation 预写成已经成立的贡献。

本工作的逻辑顺序固定为：发现问题、建立 Motivation、验证 PX4 风险语境、分析机制、提出方法、比较评价、消融和 full-stack consequence validation。最终交付目标始终是方法型论文。
