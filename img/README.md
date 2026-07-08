# 投稿图表说明

这些图只使用已提交 campaign 报告中的聚合表格数字，外加锚点轨迹图的本地条件项 ULOG。未使用 `docs/smoke_2p3_*/archive.json` 或 `docs/validity_automation_*/archive.json` 里的 smoke/mock 数据。每个 `make_*.py` 运行时都会向 stdout 打印 `SOURCE` 和解析出的具体数值。

## `fig_multipolicy_severity_convergence.pdf` / `.png`

- 生成脚本：`img/make_fig_multipolicy_severity_convergence.py`
- 说明什么：支撑多 policy 差分 oracle 的收敛主张。P1/P2 是灾难性 S0->S3；P6/P7 虽然也 confirmed，但主要伴随 S3 翻机，而不是独立的纯行为退化。
- 怎么读：每根柱是一类 policy 的 positive eval；柱内分段是严重度转移。P6/P7 中 S0->S3 仍占主导，且报告明确写明 pure non-S3 confirmed P6/P7 groups = 0。
- 数据来源：`docs/multipolicy_differential_20260703.md` 的 `## Severity Split` 表，以及 Honest Conclusion 中的 pure non-S3 说明。解析值：P1 `{S0->S3:166, S1->S3:0, S0->S1:0, S1->S1:0}`；P2 `{377,0,0,0}`；P3 `{2,1,0,0}`；P6 `{360,10,4,1}`；P7 `{334,61,3,53}`，顺序为 `S0->S3, S1->S3, S0->S1, S1->S1`。
- 草稿 caption：Severity transitions for multi-policy positives converge on catastrophic S0-to-S3 switch transients; P6/P7 are confirmed signatures that ride with S3 outcomes rather than standalone behavior-only failures.
- 建议放哪节：RQ1 / multi-policy differential spectrum。
- 状态 / caveat：已出图。P3 只有 3 个未确认 single-eval positives；图展示 positive eval 转移分解，不展示 confirmed group 计数。

## `fig_rq2_search_efficiency_guided_random_grid.pdf` / `.png`

- 生成脚本：`img/make_fig_rq2_search_efficiency_guided_random_grid.py`
- 说明什么：支撑 RQ2 的搜索效率、照亮度和一致性主张。guided 使用差分 gap fitness + MAP-Elites，比 random/grid 产生更多 primary eval 和更高 QD score。
- 怎么读：柱是每个 120-eval run 的均值；空心点是逐 seed/run 原始值。guided 的 primary density 明显高于 random，且三颗 seed 更集中。
- 数据来源：`docs/switch_severity_campaign_20260629.md` 的 `## RQ2: Guided vs Random vs Grid` 逐臂逐种子表。解析值：guided seed0/1/2 primary evals `65,54,60`，QD `197.483,192.588,176.342`；random seed0/1/2 primary evals `12,16,12`，QD `107.991,158.386,89.708`；grid primary evals `19`，QD `122.540`。均值：guided primary `59.667`、QD `188.804`；random primary `13.333`、QD `118.695`；grid primary `19.000`、QD `122.540`。guided/random primary density ratio = `4.475`。
- 草稿 caption：Guided MAP-Elites increases primary-differential density and QD illumination relative to random and grid under equal per-run budgets, with per-seed points showing the residual stochastic variance.
- 建议放哪节：RQ2。
- 状态 / caveat：已出图。必须诚实表述：random 的首次命中时间优势不大；最严格的 3/3 confirmed top cells guided 与 random 均为 `6/10`。因此主张是密度、照亮和一致性，不是“找到 random 找不到的 bug”。

## `fig_rq3_holed_nonmonotonic_boundary.pdf` / `.png`

- 生成脚本：`img/make_fig_rq3_holed_nonmonotonic_boundary.py`
- 说明什么：支撑 RQ3 的非单调、带洞、高维边界主张。`mc_nn` 的失效不是一个简单标量阈值。
- 怎么读：每个子图是一根 sweep 轴，y 轴是 strict S0/S3 命中率。灰色区标出洞或恢复区；风 4-6 m/s 的恢复尤其反直觉。
- 数据来源：`docs/switch_severity_campaign_20260629.md` 的 `## RQ3: Controlled Dense Sweep` 四张表。姿态：28/31/34/36/38 deg = `0/3`，40 = `2/3`，42/45 = `3/3`，48 = `1/3`。requested rate：0.55/0.75/0.95/1.15/1.35 = `3/3`，1.55 = `1/3`，1.75 = `3/3`，2.05 = `2/3`，2.35 = `3/3`。wind：0/1/2/3 m/s = `3/3`，4/5/6 m/s = `0/3`。delay：0.00/0.03 = `3/3`，0.06 = `1/3`，0.09 = `3/3`，0.12 = `1/3`，0.15/0.18 = `3/3`。
- 草稿 caption：Controlled dense sweeps reveal a non-monotonic, holed switch-transient failure boundary: attitude, requested rate, wind, and delay each contain reproducible recoveries or holes.
- 建议放哪节：RQ3。
- 状态 / caveat：已出图。每个点约 3 seed，n 小；报告表名是 requested rate，实际角速率仍受 circle profile 可达性约束。

## `fig_two_sut_dense_sweep_boundary.pdf` / `.png`

- 生成脚本：`img/make_fig_two_sut_dense_sweep_boundary.py`
- 说明什么：在同一 route-A 切换密扫轴网格和同一 strict S0/S3 差分 oracle 下，`mc_nn` 呈现非单调、带洞的灾难失效边界，而 RAPTOR 在四条共享轴上全部为 0 strict hit。该图支撑 oracle 的区分力：它在脆弱的 `mc_nn` 上 fire，在受控的 RAPTOR 上正确沉默。
- 怎么读：四个子图分别是 attitude、requested rate、wind、delay；y 轴是 strict hit fraction。朱红线是 `mc_nn`，绿线是 RAPTOR；灰色区沿用 RQ3 图标出洞或恢复区。RAPTOR 绿线全程贴近 0，说明没有 strict S0/S3 命中。
- 数据来源：`docs/switch_severity_campaign_20260629.md` 的 `## RQ3: Controlled Dense Sweep` 四张表，以及 `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/summary.json` 的 `axes` 聚合。解析值：`mc_nn` 同 `fig_rq3_holed_nonmonotonic_boundary`：attitude `0/3,0/3,0/3,0/3,0/3,2/3,3/3,3/3,1/3`；requested rate `3/3,3/3,3/3,3/3,3/3,1/3,3/3,2/3,3/3`；wind `3/3,3/3,3/3,3/3,0/3,0/3,0/3`；delay `3/3,3/3,1/3,3/3,1/3,3/3,3/3`。RAPTOR 在这四条轴逐点均为 `0/3`，seeds `2026062940/2026062941/2026062942`，最高 neural severity 为 S1。
- 草稿 caption：Under an identical dense sweep grid and the same differential oracle, mc_nn exhibits a non-monotonic holed catastrophic boundary while RAPTOR stays at zero strict S0/S3 across every axis point (max neural severity S1) -- the oracle fires on the fragile controller and correctly stays silent on the robust one.
- 建议放哪节：RQ4 / two-SUT external validity，或 discriminative-power 小节。
- 状态 / caveat：已出图，CI 可复现。只画与 `mc_nn` RQ3 完全对齐的四条共享轴；RAPTOR summary 里的 approach phase 轴不纳入本图。

## `fig_anchor_trace_classical_vs_mcnn.pdf` / `.png`

- 生成脚本：`img/make_fig_anchor_trace_classical_vs_mcnn.py`
- 说明什么：方法/动机图。同一 pair2 anchor 下，classical 是 S0 clean recovery，`mc_nn` 是 S3 uncontrolled tumble。
- 怎么读：横轴按 switch 时刻对齐。classical 曲线始终低于 90 deg 和 8 rad/s 阈值；`mc_nn` 在 switch 后约 22.3 s 越过两条 S3 阈值。
- 数据来源：本地 gitignored ULOG 条件项，目录 `runs/route_a_anchor_regression/route_a_anchor_regression_20260629/evals/route_a_anchor_regression_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901/`。脚本读取该目录下 classical/mcnn 的 `.ulg`、`*_task.json`、`*_metrics.json` 和 `classical_record.json` / `mcnn_record.json`。解析值：classical severity `0 / S0_clean_recovery`，max attitude `58.851 deg`，max rate `4.019 rad/s`，未越过 90 deg 或 8 rad/s；`mc_nn` severity `3 / S3_uncontrolled_tumble_or_loc`，max attitude `178.748 deg`，max rate `20.090 rad/s`，first 90 deg crossing `22.332 s`，first 8 rad/s crossing `22.488 s`。
- 草稿 caption：In the same pair2 switch-transient anchor, the classical controller remains below the catastrophic attitude and angular-rate thresholds, while `mc_nn` crosses both S3 thresholds after the switch.
- 建议放哪节：Method / motivating example。
- 状态 / caveat：当前工作区已找到 pair2 的本地 ULOG 并已出图；pair1 本地目录缺 `mc_nn` ULOG，因此不用 pair1。ULOG 和 runs 产物不会被提交。若在干净 clone 或 CI 中没有该本地目录，脚本会打印 `BLOCKED`，需要提供锚点 ULOG 或定向重跑。

## `fig_anchor_trace_three_way.pdf` / `.png`

- 生成脚本：`img/make_fig_anchor_trace_three_way.py`
- 说明什么：方法/动机图的 two-SUT 版。同一个 `rp48_62_rate2p45_2p90_w6_r6_f045_confirm1` switch-transient anchor 下，classical 干净恢复，`mc_nn` 越过 S3 姿态和角速率阈值，RAPTOR 保持在两个阈值以下。
- 怎么读：横轴按各自 switch 事件对齐到 0 s。上图是 attitude tilt，下图是 angular-rate norm；虚线分别标出 90 deg 和 8 rad/s。蓝色 classical 与绿色 RAPTOR 都低于阈值，朱红虚线 `mc_nn` 在 switch 后约 22 s 先后越过两条阈值。
- 数据来源：classical/`mc_nn` 读取本地目录 `runs/route_a_anchor_regression/route_a_anchor_regression_20260629/evals/route_a_anchor_regression_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901/` 下的 `.ulg`、`*_task.json`、`*_metrics.json`、`classical_record.json` / `mcnn_record.json`；RAPTOR 读取 `runs/campaigns/raptor_gate0_anchor_recheck_20260705/evals/raptor_gate0_anchor_recheck_20260705_pair2_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901/` 下的 `.ulg`、`*_task.json`、`*_metrics.json`、`*_raptor_property.json`。解析值：classical seed `20261901`，severity `0 / S0_clean_recovery`，max attitude `58.851 deg`，max rate `4.019 rad/s`，未越过 90 deg 或 8 rad/s；`mc_nn` seed `20261901`，severity `3 / S3_uncontrolled_tumble_or_loc`，max attitude `178.748 deg`，max rate `20.090 rad/s`，first 90 deg crossing `22.332 s`，first 8 rad/s crossing `22.488 s`；RAPTOR seed `20261901`，severity `0 / S0_clean_recovery`，max attitude `57.355 deg`，max rate `4.124 rad/s`，未越过 90 deg 或 8 rad/s。
- 草稿 caption：In the identical rp48_62 switch-transient anchor, classical recovers cleanly (S0) and mc_nn crosses both S3 thresholds (tumble), while RAPTOR stays below both thresholds -- a three-way trace of the oracle's discriminative power across two learned controllers.
- 建议放哪节：Method / motivating example 的 two-SUT 版。
- 状态 / caveat：当前工作区已找到所需本地 ULOG 并已出图；ULOG 和 runs 产物不会被提交。若在干净 clone 或 CI 中没有这些 gitignored 本地目录，脚本会打印 `BLOCKED` 并干净退出。

## `fig_wave2_estimation_contam_negative.pdf` / `.png`

- 生成脚本：`img/make_fig_wave2_estimation_contam_negative.py`
- 说明什么：支撑 wave-2 估计污染轴是干净 negative：strict S0/S3 differential 没有扩散到非切换瞬态轴。
- 怎么读：左侧 gate pass fraction 接近或等于 1；右侧 strict differential 和 primary candidate 计数均为 0。
- 数据来源：`docs/wave2_statecontam_campaign_20260703.md` 的 `## Main Campaign` 和 `Validity gates over valid evals` 表。guided：evals `200`、valid `200`、strict differentials `0`、primary candidates `0`、best diagnostic gap `P2 gap 2.396`，delivery/fairness、identity、decontamination 均 `200/200`。random：evals `200`、valid `199`、strict differentials `0`、primary candidates `0`、best diagnostic gap `P2 gap 2.254`，三项 validity gate 均为 `199/199`。
- 草稿 caption：State-contamination wave-2 is a clean negative: validity gates pass on valid evaluations, while both guided and random arms produce zero strict S0/S3 differentials and zero primary candidates.
- 建议放哪节：Threats / negative result 或 RQ follow-up。
- 状态 / caveat：已出可选图。这个 null 结果也适合表格呈现；这里保留紧凑图是为了视觉上坐实 clean negative。不要把 P2/P4 diagnostic gap 当成 reportable strict failure。

## 暂时画不了的图（及原因）

- 两 SUT 对照图（RAPTOR vs `mc_nn` 在锚点处）：已解锁，见 `fig_two_sut_dense_sweep_boundary` / `fig_anchor_trace_three_way`。RAPTOR 全量 campaign 已入库（`aba86101`）。
- 图 D 在当前工作区不阻塞，已用 pair2 本地 ULOG 出图；但它依赖 gitignored `runs/` 产物。若要在只含已提交文件的环境中复现，需要补充锚点 ULOG 或按 pair2 定向重跑 classical 与 `mc_nn`。
