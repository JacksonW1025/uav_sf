# V8 中文实验计划与执行清单

本文是从当前 checkout 到论文主实验闭合的可编辑执行蓝图。它实现
[V8 研究叙事](NEW_NARRATIVE_v8.md)，但不把尚未实现的工具、预算或结果
写成既成事实。[英文版本](EXPERIMENT_PLAN.md) 必须与本文保持相同的步骤
编号、状态、产物、退出条件和停止条件。

## 0. 使用规则

状态只允许：

- `[x] COMPLETE`：产物存在、验收通过、证据链接已登记；
- `[>] NEXT`：唯一允许开始实现的下一步；
- `[ ] PENDING`：前置门未关闭；
- `[!] BLOCKED`：已记录阻塞原因，禁止绕过。

本计划中的命令分两类：

- **当前可运行**：文件已经存在；
- **待实现命令合同**：该步骤必须交付的未来入口，在文件存在且前置门
  关闭前禁止执行。命令名是接口要求，不是当前 readiness 声明。

每关闭一步，都必须同步更新：本文、英文镜像、
[CURRENT_STATUS.md](CURRENT_STATUS.md)、[V8_REPOSITORY_AUDIT.md](V8_REPOSITORY_AUDIT.md)
和 boundary validator。不得只改 checkbox。

## 1. 总体进度

| 步骤 | 状态 | 阶段 | formal launch 许可 |
| ---: | --- | --- | --- |
| 0 | `[x] COMPLETE` | V8 tracked-tree consolidation | 禁止 |
| 1 | `[>] NEXT` | Observation/evidence provenance contract | 禁止 |
| 2 | `[ ] PENDING` | Independent identity/effect observation | 禁止 |
| 3 | `[ ] PENDING` | Combined admissibility Gate | 禁止 |
| 4 | `[ ] PENDING` | V8 result/finding state machine | 禁止 |
| 5 | `[ ] PENDING` | Minimal patches, image, environment identity | 禁止 |
| 6 | `[ ] PENDING` | Early full-stack seeds and reachability | 禁止 |
| 7 | `[ ] PENDING` | Lifecycle × mechanism corpus freeze | 禁止 |
| 8 | `[ ] PENDING` | Semantic state and execution schemas | 禁止 |
| 9 | `[ ] PENDING` | Closed-loop generator and four methods | 禁止 |
| 10 | `[ ] PENDING` | Frozen benchmark and leakage control | 禁止 |
| 11 | `[ ] PENDING` | Component/replay qualification | 禁止 |
| 12 | `[ ] PENDING` | Runtime, safety, and interference qualification | 禁止 |
| 13 | `[ ] PENDING` | Non-formal pilot and budget estimation | 禁止 |
| 14 | `[ ] PENDING` | Formal preregistration freeze | 仅 dry-run |
| 15 | `[ ] PENDING` | Repeated formal campaigns | 有条件允许 |
| 16 | `[ ] PENDING` | Candidate confirmation and attribution | 独立 identity |
| 17 | `[ ] PENDING` | Representative full-stack consequence replay | 独立 identity |
| 18 | `[ ] PENDING` | Accounting closure and reporting | 禁止新增 |

## 2. 全局停止规则

出现以下任一条件立即停止当前步骤，不得把失败转成 SUT 结果：

- worktree、source、patch、image、schema、plan 或 environment identity 漂移；
- required evidence 缺失、hash/sequence 断裂、clock 无法闭合；
- identity 字段 provenance 不足，或 expected label 被用于自证 observed identity；
- allocator 与 writer/effect 共用一个原始证据边界；
- physical-validity、safety、cleanup 或 environment attestation 失败；
- live workload 与同一实验主机上的 offline processing 重叠；
- 新内容无法映射到 V8 RQ、method component 或 evidence obligation；
- 任一前置步骤不是 `COMPLETE`。

所有失败登记为 qualification failure、measurement failure、environment
failure、`INCONCLUSIVE` 或 blocked gate；不得补写为 PASS/VIOLATION。

---

## Step 0 — 整理 V8 tracked tree

**状态：`[x] COMPLETE`**

**目标**：删除与 V8 无关或会误导为当前方法的 tracked 内容，同时保留
V8 Motivation、measurement 和 bounded feasibility 证据。

**已完成**：

- 建立 retained-experiment allowlist；
- 删除零 formal 的旧 process-exit study 和未进入 V8 的 differential example；
- 删除旧三策略 plan/evaluator/runner/analysis 入口；
- 删除旧 patch bundle、patch lock、source-build 入口和 flight image；
- 保留低层 measurement/accounting/safety/workload primitives；
- 建立本中英文计划和 repository audit；
- validator 改为 V8 boundary validator。

**当前可运行**：

```bash
git status --short --branch
./scripts/validation/validate_repo.sh
```

**产物**：本文、英文镜像、`V8_REPOSITORY_AUDIT.md`、新 validator。

**退出条件**：tracked tree 只含 allowlisted evidence 和 V8 partial
components；验证通过；无 flight/formal entry point。

**停止条件**：发现删除会改变 retained ledger/result 内容时，停止并重新
区分冻结证据与 active implementation。

## Step 1 — 冻结 observation/evidence provenance contract

**状态：`[>] NEXT`**

**输入**：V8 Runtime Route Instance、保留 ULog 字段、当前 event skeleton、
Stage A1/A2 evidence gaps。

**执行**：

1. 列出每个 authority/lifecycle/effect event 及全部字段；
2. 为字段指定 source boundary、clock domain、cardinality 和
   `OBSERVED/DERIVED/INFERRED/CONSTANT`；
3. 明确哪些 derivation 可用于 correctness，哪些只能用于诊断；
4. 定义 registration、activation、revocation、owner、completion、fallback
   和 effect event 的完整 identity 要求；
5. 定义 allocator publication 与 writer/effect 的独立观测边界；
6. 用 retained examples 和反例进行 review，不运行 flight。

**待实现命令合同**：

```bash
python3 -m scripts.validation.validate_evidence_contract \
  --contract docs/EVIDENCE_CONTRACT.md \
  --schema data/schemas/observation_provenance.schema.json
```

**产物**：`docs/EVIDENCE_CONTRACT.md`、provenance schema、field/source
matrix、正反例 fixtures、validator tests。

**退出条件**：每个目标字段都有非循环 provenance；所有 authority-bearing
event 的 identity 要求明确；allocator/writer 边界独立。

**停止条件**：任一 correctness field 只能从 plan expectation、route name
或固定常量获得；此时缩小 claim 或增加 observation，不得进入 Step 2。

## Step 2 — 实现独立 identity/effect observation 与 trace closure

**状态：`[ ] PENDING`**

**输入**：Step 1 contract、locked upstream candidates、retained fixtures。

**执行**：

1. 设计最小 multirotor-only observation topics/events；
2. 实现 raw observation adapters，不添加结果预期；
3. 实现 clock-preserving normalized closure；
4. 为每个 normalized field 保留 source/provenance；
5. 实现独立 allocator 与 writer/effect events；
6. 对 repeated entry、restart、registration、completion、fallback 建立
   deterministic fixture replay；
7. 对 inferred/constant 字段验证其不会让 Oracle PASS。

**待实现命令合同**：

```bash
python3 -m scripts.validation.validate_observation_contract --fixtures tests/fixtures/v8
python3 -m unittest tests.test_v8_trace_closure -v
```

**产物**：V8 event schema、raw/normalized adapters、trace closure、fixtures、
field-level provenance tests。

**退出条件**：相同 evidence 产生 byte-stable normalized trace；完整 identity
来自允许的 observation/derivation；一个原始 event 不会伪造两个层级。

**停止条件**：field provenance 丢失、不同 route instance 被合并、跨 clock
排序超过 uncertainty，或 closure 需要预期结果才能完成。

## Step 3 — 建立 combined admissibility Gate

**状态：`[ ] PENDING`**

**输入**：V8 trace closure、physical contract、environment attestation。

**执行**：分别计算并统一汇总 trace integrity、required events、identity
provenance、clock closure、environment match 和 physical validity。保留各层
诊断，但只输出一个 `OVERALL_ADMISSIBLE` 或 `INCONCLUSIVE`。

**待实现命令合同**：

```bash
python3 -m scripts.validation.validate_admissibility --fixtures tests/fixtures/v8
```

**产物**：combined Gate schema/implementation、fail-closed truth table、
physical-validity fixtures、standalone evaluator protection tests。

**退出条件**：任何子门失败都不能产生 overall PASS/VIOLATION；单独调用
evaluation 也不能绕过 physical validity。

**停止条件**：runner 与 standalone evaluation 给出不同 admissibility，或
missing evidence 被默认为成功。

## Step 4 — 建立 V8 result/finding schema 与确认状态机

**状态：`[ ] PENDING`**

**输入**：combined Gate、contract clause results、V8 finding levels。

**执行**：

1. 分开 execution result、contract exposure、candidate 和 confirmed finding；
2. 记录 origin：historical、seeded、confirmed-current、new-natural；
3. 定义 reproduction、minimization、measurement check、cluster、attribution、
   source grounding 和 full-stack consequence 状态；
4. 定义稳定 cluster signature，避免逐 trace ID 和过粗 `oracle:clause`；
5. 禁止 violation 自动升级为 defect 或 safety-relevant finding。

**待实现命令合同**：

```bash
python3 -m scripts.validation.validate_finding_schema --fixtures tests/fixtures/findings
```

**产物**：result schema、candidate/finding schema、state machine、migration
boundary note、tests。

**退出条件**：四个 finding level 机器可区分；状态迁移 fail closed；同一
candidate 可复现聚类，不因重复 trace 膨胀 finding count。

**停止条件**：classification 依赖报告措辞而非 schema evidence，或 formal
新 candidate 能回填同一 campaign 的 frozen benchmark。

## Step 5 — 创建最小 V8 patch、image 与 environment identity

**状态：`[ ] PENDING`**

**输入**：Steps 1–4 contracts、exact upstream commits。

**执行**：

1. 将 instrumentation patch 与 controlled-stimulus patch 分目录和 lock；
2. 只修改 V8 multirotor Family A 所需文件；
3. 逐 patch 记录目的、source path、hash、observation/stimulus 分类；
4. 构建新 ARM64 runtime image；
5. 生成 binary/source/package/patch manifest；
6. 在 Thor 上生成新的 environment attestation。

**待实现命令合同**：

```bash
./scripts/setup/prepare_v8_sources.sh
docker buildx build --platform linux/arm64 \
  --file containers/family_a_v8_runtime/Dockerfile \
  --tag uav-sf-family-a-v8:candidate --load .
python3 -m scripts.runtime.attest_v8_environment --image uav-sf-family-a-v8:candidate
```

**产物**：minimal patch sets、patch lock、runtime Dockerfile、candidate
manifest、environment attestation。

**退出条件**：patch path allowlist 无 rover/额外 route family；fresh source
tree 可重复 apply/build；attestation 与 image/binary/patch digests 一致。

**停止条件**：patch 混合 observation 和 stimulus、source tree 有未登记
修改、镜像继承 host 环境，或当前 repo revision 未进入 identity。

## Step 6 — 早期接入完整上层栈并采集 seed/reachability

**状态：`[ ] PENDING`**

**输入**：新 V8 image、代表性 mission/behavior stack、combined Gate。

**执行**：冻结任务定义和软件版本；运行 non-formal normal missions；采集
mission trace、trajectory、parameter distribution、reachable lifecycle
transitions 和 adapter behavior；记录 reality distance 与 attribution boundary。

**待实现命令合同**：

```bash
python3 -m scripts.runtime.collect_full_stack_seeds \
  --plan qualification/full_stack_seed_plan.json --non-formal
python3 -m scripts.validation.validate_seed_corpus qualification/full_stack_seeds
```

**产物**：seed corpus、parameter ranges、reachability report、task/outcome
measure definitions、upper-stack/PX4 responsibility map。

**退出条件**：核心 route/lifecycle 候选至少有 public/source/real-trace
provenance 之一；上层栈不是仅在最终演示时出现。

**停止条件**：任务栈版本漂移、seed 无法绑定 provenance、异常责任边界
不清，或 physical task 本身不成立。

## Step 7 — 冻结 lifecycle × mechanism 核心 corpus

**状态：`[ ] PENDING`**

**输入**：source transitions、public interfaces、issues/commits、Step 6 seeds。

**执行**：建立 lifecycle（registration、activation、execution、completion、
replacement、fallback、re-entry）× mechanism（exit/restart、stall、delay、
health loss、rejection、takeover、adjacent request）inventory。逐 action 记录
precondition、effect marker、cleanup、安全边界、参数范围、reality distance、
benchmark/discovery 角色和 include/exclude 理由。

**待实现命令合同**：

```bash
python3 -m scripts.corpus.validate_action_inventory config/v8_action_inventory.json
python3 -m scripts.corpus.freeze_core_corpus \
  --inventory config/v8_action_inventory.json --output config/v8_core_corpus.json
```

**产物**：完整 inventory、最小代表性 core corpus、action grammar schema、
provenance manifest。

**退出条件**：corpus 由研究义务和现实 provenance 决定，不由已有 backend
便利决定；所有 included action 可达、可观测、可清理。

**停止条件**：action 无 provenance/cleanup、参数来自事后结果、或某策略
获得其他策略没有的 grammar 能力。

## Step 8 — 实现 semantic state 与 execution schemas

**状态：`[ ] PENDING`**

**输入**：Steps 1–7 contracts/corpus。

**执行**：实现 semantic-state extractor、campaign/episode/action-sequence/
reset/coverage schemas 和 plan builder。每个 action 后重新观测；campaign
从空 memory 开始；reset 完整撤销 external authority 并恢复安全 route。

**待实现命令合同**：

```bash
python3 -m scripts.validation.validate_v8_schemas
python3 -m scripts.state.replay --fixtures tests/fixtures/v8 --determinism-check
```

**产物**：semantic-state/schema、deterministic extractor、plan builder、reset
contract、state/transition/boundary coverage store。

**退出条件**：equivalent evidence 产生相同 state；route epoch、owner、
lifecycle、freshness、successor、motion context 和 bounded history 可区分。

**停止条件**：完整 sequence 被预先计算而不重观测，reset 泄漏 generator
memory/authority，或 raw telemetry coverage 被当作主 semantic feedback。

## Step 9 — 实现闭环 generator 与四个公平方法

**状态：`[ ] PENDING`**

**输入**：frozen grammar、semantic state、coverage store、combined Gate。

**执行**：在共同 grammar/bounds/seeds/reset/outcomes 下实现：grammar-aware
random、systematic enumeration、feedback-free state-conditioned、full
state/feedback-guided。Official/handwritten scenarios 使用独立 reference
runner 和独立报告，不进入强行等价的主比较。

**待实现命令合同**：

```bash
python3 -m scripts.generator.qualify_policies --config config/v8_methods.json
```

**产物**：四个 policy、共享 executor、decision log、seed replay、feedback
update tests、official reference adapter。

**退出条件**：同 seed 可重放；除 policy decision 外条件一致；只有
overall-admissible execution 更新 coverage；重复 candidate 不持续高奖励。

**停止条件**：策略拥有不同 action set/budget/visibility，feedback 读取
future/offline result，或 inadmissible execution 污染 coverage。

## Step 10 — 建立冻结 benchmark 与防泄漏合同

**状态：`[ ] PENDING`**

**输入**：historical provenance、confirmed-current candidates、seeded faults。

**执行**：分别建立 historical known defect、confirmed current natural、
mechanism-derived seeded 三个 formal 前集合；保留 held-out split；新发现
natural candidate 只进入独立确认队列，不回填当轮 benchmark。

**待实现命令合同**：

```bash
python3 -m scripts.benchmark.validate --manifest config/v8_benchmark.json
```

**产物**：benchmark manifest、origin labels、replay contract、held-out and
leakage rules、seeded/natural separated metrics。

**退出条件**：每个 benchmark item 可重放、有 ground-truth level 和固定
digest；训练/pilot/formal/held-out 输入边界清楚。

**停止条件**：不可复现 issue 被当 ground truth，seeded 与 natural 混成
defect count，或 formal 结果改变 primary benchmark。

## Step 11 — 组件、replay 与 reduced-observation qualification

**状态：`[ ] PENDING`**

**输入**：完整方法组件、retained traces、synthetic fixtures、benchmark。

**执行**：运行 schema、closure、Gate、Oracle、state、generator、reset、
accounting 的 unit/integration/replay tests；比较 full instrumentation 与
reduced-observation replay；验证旧 retained evidence 不被静默重解释。

**待实现命令合同**：

```bash
./scripts/validation/validate_repo.sh
python3 -m scripts.qualification.replay_suite --non-formal
python3 -m scripts.analysis.reduced_observation --non-formal
```

**产物**：qualification report、compatibility boundary、reduced-observation
dependence report、known limitations。

**退出条件**：determinism/fail-closed tests 通过；instrumentation dependence
量化；旧 frozen result 未被覆写。

**停止条件**：replay 不稳定、missing evidence 变 PASS、reduced observation
改变 primary classification 且未解释。

## Step 12 — runtime、安全、cleanup 与资源干扰 qualification

**状态：`[ ] PENDING`**

**输入**：candidate image、完整 executor、代表性最重 workload。

**执行顺序**：single-attempt smoke → repeated serial → serial-vs-parallel
matched qualification → live/offline host exclusion → safety stop → cleanup →
crash recovery。并发度从 1 开始提升，不继承旧 four-way 结论。

**待实现命令合同**：

```bash
python3 -m scripts.qualification.runtime --plan qualification/v8_runtime.json
python3 -m scripts.qualification.interference --plan qualification/v8_interference.json
```

**产物**：runtime/interference report、qualified concurrency、resource sets、
barrier proof、safety/cleanup/recovery evidence。

**退出条件**：matched timing/clock/outcome 无实质干扰；所有 live attempt
停止后才开始任何 offline processing；cleanup fail closed。

**停止条件**：clock margin、real-time factor、outcome 或 safety behavior 随
并发发生不可接受变化；此时降低并发或固定 serial。

## Step 13 — non-formal pilot 与预算估计

**状态：`[ ] PENDING`**

**输入**：qualified runtime、四方法、benchmark、candidate queue。

**执行**：使用与 formal 隔离的 pilot identity，估计 variance、admissible
yield、actions/episode、sequence length、reset cost、wall time、analysis cost、
safety interruption 和 candidate rate；只用于冻结预算/统计设计。

**待实现命令合同**：

```bash
python3 -m scripts.runtime.run_v8_pilot --matrix pilot/v8_matrix.json --non-formal
python3 -m scripts.analysis.pilot_design --root pilot/v8
```

**产物**：pilot ledger/report、variance/cost estimates、proposed budgets、
campaign repetitions、effect size、uncertainty 和 stopping-rule proposal。

**退出条件**：预算能覆盖 meaningful sequence behavior；campaign-level
variance 可估；所有 pilot attempt 明确排除 formal denominator。

**停止条件**：pilot 被用于调 primary result threshold，或达到预期结果后
才选择 stopping rule。

## Step 14 — 冻结 formal preregistration

**状态：`[ ] PENDING`**

**输入**：Steps 1–13 全部通过的 artifacts/digests。

**执行**：冻结 falsifiable thesis/RQ mapping、corpus、benchmark、四方法与
ablations、primary/secondary metrics、campaign/reset/paired seeds、execution
budget、max sequence、cost reporting、repetitions、effect sizes、uncertainty、
stopping rule、candidate confirmation 和 full-stack selection criteria。

**待实现命令合同**：

```bash
python3 -m scripts.validation.validate_preregistration \
  --plan experiments/v8_main/preregistration.json
python3 -m scripts.runtime.run_v8_campaign \
  --matrix experiments/v8_main/matrix.json --dry-run
```

**产物**：immutable preregistration、matrix、attestation、source/image/schema/
method/safety digests、empty formal ledger readiness proof。

**退出条件**：dry-run 只列出 exact attempts，不创建 ledger/launch；所有
identity/digest 一致；independent unit 明确为 campaign。

**停止条件**：任一预算/metric/stopping rule 仍待结果决定，或 preregistration
与 built artifact 不一致。

## Step 15 — 执行 repeated formal campaigns

**状态：`[ ] PENDING`**

**前置授权**：只有 Step 14 `COMPLETE` 才允许移除 dry-run。

**每批顺序**：preflight/accounting registration → environment attestation →
live execution → safety/cleanup → 全 live barrier → offline closure/Gate/Oracle
→ compact retention → ledger close。任何主机上的 offline work 不得与该主机
的 live attempt 重叠。

**待实现命令合同**：

```bash
python3 -m scripts.runtime.run_v8_campaign \
  --matrix experiments/v8_main/matrix.json \
  --attestation experiments/v8_main/environment-attestation.json
```

**产物**：campaign/episode/attempt ledgers、raw manifests、compact evidence、
coverage、candidate queue、interim accounting（不做 result-driven stopping）。

**退出条件**：达到 preregistered stopping rule；所有 launched attempts 都有
唯一 closure；denominator 可由 ledger 重算。

**停止条件**：identity drift、open attempt、barrier failure、safety stop、
environment/measurement failure 达到预注册 pause rule，或 cleanup 不完整。

## Step 16 — 独立确认、最小化、聚类与归因 candidates

**状态：`[ ] PENDING`**

**输入**：formal candidate queue；不得修改 formal primary data。

**执行**：新 identity 下独立 reproduction → sequence/timing minimization →
measurement/instrumentation check → clustering → source/spec attribution。

**待实现命令合同**：

```bash
python3 -m scripts.findings.confirm --queue experiments/v8_main/candidates.jsonl
```

**产物**：confirmation ledgers、minimal reproducers、cluster manifest、
attribution dossiers、finding-level labels。

**退出条件**：distinct finding count 只使用满足预注册确认级别的 clusters；
未确认 candidate 仍以 candidate 报告。

**停止条件**：不能排除 instrumentation/environment/upper-stack cause，或
source grounding 不足却升级为 PX4 defect。

## Step 17 — representative full-stack consequence replay

**状态：`[ ] PENDING`**

**输入**：Step 6 冻结的 task/outcome measures、Step 14 selection criteria、
Step 16 confirmed clusters。

**执行**：按预注册规则选择代表性 clusters；在完整上层栈闭环 SITL 中做
matched control/replay；测量 mission failure、progress loss、trajectory error、
recovery behavior 和 physical consequence；进行责任归因。

**待实现命令合同**：

```bash
python3 -m scripts.runtime.replay_full_stack \
  --selection experiments/v8_full_stack/selection.json
```

**产物**：独立 replay identity/ledger、matched outcomes、consequence report、
attribution boundary。

**退出条件**：代表性 finding 的可达性和后果可重复；task definition、
measures、thresholds、selection criteria 均在 replay 前冻结。

**停止条件**：upper-stack differential 未闭合、任务配置漂移，或只重放
最显著结果而违反 selection rule。

## Step 18 — 关闭 accounting、统计分析与报告

**状态：`[ ] PENDING`**

**输入**：所有 formal/confirmation/full-stack ledgers 与 frozen analysis plan。

**执行**：重算 denominator；按 campaign 统计 primary outcome；报告 effect
size/uncertainty、coverage、time/cost、admissible yield、安全中断；分开
historical/seeded/natural；生成 RQ/claim/evidence traceability；验证仓库。

**待实现命令合同**：

```bash
python3 -m scripts.analysis.v8_final --root experiments/v8_main
./scripts/validation/validate_repo.sh
```

**产物**：final report、machine-readable summary、claim-evidence matrix、
limitations、artifact manifest、closed ledgers。

**退出条件**：所有数值可由 ledger/artifacts 重算；没有 pooled launch-level
pseudoreplication；claims 不超过 evidence；repository validation 通过。

**停止条件**：open ledger、missing attempt、post-hoc metric 冒充 primary、
seeded/natural 混计、或 full-stack consequence 被外推为真机风险。

## 3. 计划维护清单

每次变更本计划时检查：

- [ ] 中英文步骤编号和状态完全一致；
- [ ] 当前 `NEXT` 只有一个；
- [ ] 新文件已映射到 V8 obligation；
- [ ] 命令标明当前可运行或待实现；
- [ ] 完成状态有 artifact/evidence link；
- [ ] formal denominator 未被 qualification/pilot 污染；
- [ ] `./scripts/validation/validate_repo.sh` 通过。
