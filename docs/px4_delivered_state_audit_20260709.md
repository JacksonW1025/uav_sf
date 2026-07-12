# Delivered Handoff State & RQ3 Reconstruction (Round 5)

## 0. 判定摘要

证据命令与落盘产物：

- A0/RQ3: `python3 scripts/px4_delivered_state_round5.py --population mcnn_dense --workers 4` -> `docs/round5_delivered_state_20260709/mcnn_dense_delivered_state.csv` 120 行数据、`mcnn_dense_summary.json`、`mcnn_dense_actual_nav23_scatter.png`。
- A0/926 表: `python3 scripts/px4_delivered_state_round5.py --population raptor_v8 --workers 8` -> `raptor_v8_delivered_state.csv` 926 行数据、`raptor_v8_summary.json`。
- A0.6 图: `python3 scripts/px4_rq3_redraw_round5.py` -> `mcnn_dense_nominal_grid_summary.csv`、`mcnn_dense_nominal_vs_actual.png`、`mcnn_dense_local_consistency.png`。
- A2: `python3 scripts/px4_mixer_fingerprint_round5.py` -> `mixer_fingerprint_summary.json`、`mixer_fingerprint_mcnn_detail.csv`、`mixer_fingerprint_queue_rates.csv`。
- A2.4 辅助: `python3 scripts/px4_actuator_attribution_audit.py | tee docs/round5_delivered_state_20260709/actuator_timestamp_rate_audit.csv`。
- A5: `python3 scripts/archive_campaign_provenance.py --output docs/round5_delivered_state_20260709/provenance_snapshot.json`。

- A0.1 谓词定义 / 进程 / 频率 / topic: ROS 2 offboard 节点 `scripts/m1_offboard_task.py` 内求值；订阅 `/fmu/out/vehicle_attitude_groundtruth` 与 `/fmu/out/vehicle_angular_velocity_groundtruth`；谓词在 fixed ROS timer `tick()` 内检查，dense/switch 任务为 `rate_hz=80` 且 `PX4_SIM_SPEED_FACTOR=1.25`，所以 wall timer 约 100 Hz；公式是 `max(abs(roll), abs(pitch))`。
- A0.2 延迟分解，mcnn dense 120: L1(raw) median/p95 = 0.104/0.126 s；configured delay median/p95 = 0.090/0.121 s；L1-minus-configured median/p95 = 0.014/0.026 s；L2(PX4) median/p95 = 0.028/0.036 s；L_total median/p95 = 0.132/0.161 s。
- A0.2 主导来源: 按定义 raw L1 主要是 harness 的有意 `switch_delay_s`；扣除有意延迟后，非配置延迟由 PX4 side 略主导。它不是 100-300 ms 级别的平台滞后。
- A0.4 状态漂移: `delta roll_pitch_abs` median/p95 = 1.35/2.68 deg；`delta tilt` median/p95 = 0.19/1.82 deg；`delta yaw` median/p95 = -2.14/-0.57 deg。`||omega|| * L_total` 拟合 `abs(delta roll_pitch_abs)` 的 slope = 0.213、R2 = 0.224；对 tilt 的 R2 = 0.012。最坏情况角速度乘延迟显著过预测实际 handoff 漂移。
- A0.5 标签保真度: mcnn dense 的 nav23 实测状态落在标签盒内 118/120 = 98.33%；自由轴 `abs` 分布 n/min/p05/p25/median/p75/p95/max = 120/0.019/0.612/2.314/4.404/7.628/11.518/14.188 deg。RAPTOR 926 表为 796/926 = 85.96%，用于交付表，不用于 S3 边界裁决。
- A0.6.1 洞在实测坐标下是否仍存在: 否，不能作为 `{roll_pitch_abs, ||omega||}` 的确定性洞/边界存在。旧 nominal axes 上仍有非单调 S3 fraction，但 measured 2D handoff 坐标中相近点结局冲突。
- A0.6.2 局部一致率: epsilon=1 的 S3-vs-non-S3 一致率为 0.670（3246 pairs）。结局不是 measured 2D theta 的确定性函数。
- A0.6.3 最佳特征集: `{roll,pitch,yaw,omega_xyz,v_norm,position_error,w,r,f}` balanced accuracy = 0.795；但 A0.6.4 天花板约 0.782，所以这个数字应看作接近/略超重复性噪声上界，不可当作稳定可分边界。最关键隐变量是 yaw、omega_z、v_norm；未发现一个变量把洞变成光滑边界。
- A0.6.4 重复性天花板: mcnn dense same-scenario + same-seed pair consistency = 401/513 = 0.7817，Wilson 95% CI = [0.7439, 0.8153]。
- A2 RAPTOR race: 无法判定。clean classical fit 成功，但 mcnn self-check 与 value-match labels 一致率只有 87.34% < 95% stop line，所以按任务规则不把 fingerprint 用到 RAPTOR。
- A3 原 campaign `PX4_SIM_SPEED_FACTOR`: relevant task JSON 与 campaign metadata 均指向 1.25；mcnn dense `sweep_config.json` 自身未写该字段，但 6149 个 task JSON 中 5991 个是 1.25，且相关 switch/raptor metadata 为 1.25。
- A4 同标签同 seed 重跑一致率: mcnn dense 的 same-scenario + same-seed pair consistency = 0.7817；RAPTOR 926 为 one-class S0/S1，无 S3，repeatability=1 对 RQ3 S3 边界无信息。
- A5 行为等价 binary 已重建: 否。已建立归档脚本与当前 snapshot；未 rebuild。Docker image inspect 因 socket permission denied 未能确认 `uav_sf:phase1` digest。

## 0.1 ⚠️ RQ3 的裁决

**RQ3_REFUTED**，针对原文中把 RQ3 表述成 measured 2D state admission set 的版本。

必须删除或改写的句子/主张：

- 删除: "RQ3 刻画了 `{roll_pitch_abs, ||omega||}` 上的非凸/带洞准入集。"
- 删除: "边界宽度只有 3-6 deg，42/45/48 deg 构成清晰几何边界。"
- 删除: "高风恢复、rate 洞、delay 洞可解释为同一 measured handoff state space 中的洞。"
- 改写: "dense sweep 在 nominal scenario axes 上呈现非单调 S3 fraction；但在实测 handoff 坐标 `{max(|roll|,|pitch|), ||omega||}` 下，S3 不是确定性函数，至少依赖 yaw/phase/omega components/velocity 等隐变量。"

## 0.2 ⚠️ 对 v8 各实验的逐条影响

| 实验 | 影响 |
|---|---|
| F1 | 不受主要结论影响；若文字引用 "交付状态边界"，改为 "nominal switching campaign 中的 productive region"。 |
| F2 | 改措辞。保留 guided 更高效定位切换失效区；不要说 archive 独立刻画了完整边界。 |
| F2a | 改措辞。可保留多种子/确认策略价值；需承认边界锚点有非确定性。 |
| RQ3 | 需重写。由 "高维带洞准入集" 改为 "nominal axes 非单调，measured 2D state 下不可确定，存在隐变量/过程随机性"。 |
| B1 | 若只比较 mc_nn vs classical 的 failure existence，不受影响；若引用 RQ3 geometry，改措辞。 |
| B2 | 同 B1。 |
| B3 | 同 B1；不要把 RQ3 作为 smooth boundary 证据。 |
| S1 | 加 deterministic replay caveat；不必重跑。 |
| S2 | 加 deterministic replay caveat；不必重跑。 |
| D1 | 需补 provenance caveat。R4 已覆盖原 binary，A5 本轮未能确认 Docker digest，也未重建 bit-equivalent binary。 |

## 1. A0.1

代码证据：

- `nl -ba scripts/m1_offboard_task.py | sed -n '180,215p'`: publishers/subscribers/timer。`VehicleCommand` 发到 `/fmu/in/vehicle_command`；truth topics 是 `/fmu/out/vehicle_attitude_groundtruth` 与 `/fmu/out/vehicle_angular_velocity_groundtruth`；timer 是 `create_timer(1.0 / self.wall_timer_hz, self.tick)`。
- `nl -ba scripts/m1_offboard_task.py | sed -n '40,130p'`: `wall_timer_hz = rate_hz * PX4_SIM_SPEED_FACTOR`，受 `max_wall_timer_hz` cap。
- `nl -ba scripts/m1_offboard_task.py | sed -n '360,630p'`: `truth_state_snapshot()`、`trigger_condition_met()`、`mode_command` 与 `tick()`。

精确公式代码：

```python
roll = math.atan2(2.0 * (q0 * q1 + q2 * q3), 1.0 - 2.0 * (q1 * q1 + q2 * q2))
sin_pitch = max(-1.0, min(1.0, 2.0 * (q0 * q2 - q3 * q1)))
pitch = math.asin(sin_pitch)
yaw = math.atan2(2.0 * (q0 * q3 + q1 * q2), 1.0 - 2.0 * (q2 * q2 + q3 * q3))
"roll_pitch_abs_deg": max(abs(math.degrees(roll)), abs(math.degrees(pitch)))
```

`rp36_44_rate1p55_2p15` 是窗口，不是目标点。`scripts/fuzz1c_severity_scan.py:104-112` 给出 rp `[36,44]`、rate `[1.55,2.15]`。`scripts/theta_genome.py:1131-1135` 对 dense sweep 使用 target +/- 4 deg 与 rate +/- 0.35 rad/s。

Seed 用法：固定 dense sweep 的 genome 由 `run_switch_dense_sweep.py:80-91` 和 `random.Random(0)` 生成；`seed` 传给 `theta_from_genome()` 并写入 `theta["seed"]`，但 wind 是 `SIH_WIND_N/E` boot params，由 `theta_genome.py:623-654` 从 speed/direction 确定，不是运行时随机风相位。

## 2. A0.2

mcnn dense 延迟分布来自 `mcnn_dense_summary.json`：

| delay | n | min | p05 | p25 | median | p75 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| configured switch_delay | 120 | 0.000 | 0.0585 | 0.090 | 0.090 | 0.090 | 0.1215 | 0.180 |
| L1 cmd-pred raw | 120 | 0.000 | 0.0634 | 0.096 | 0.104 | 0.108 | 0.1258 | 0.196 |
| L1 minus configured | 120 | 0.000 | 0.002 | 0.006 | 0.014 | 0.018 | 0.026 | 0.034 |
| L2 nav23-cmd | 120 | 0.016 | 0.020 | 0.024 | 0.028 | 0.032 | 0.036 | 0.044 |
| L_total nav23-pred | 120 | 0.032 | 0.084 | 0.124 | 0.132 | 0.136 | 0.161 | 0.220 |
| ack-cmd | 120 | 0.004 | 0.008 | 0.012 | 0.016 | 0.020 | 0.024 | 0.032 |
| nav23-ack | 120 | 0.012 | 0.012 | 0.012 | 0.012 | 0.012 | 0.012 | 0.016 |

926-row RAPTOR table has similar PX4-side latency: L2 median/p95 = 0.028/0.036 s, ack-cmd median/p95 = 0.016/0.024 s. It has L1/L_total max outliers over 10 s, so the p95 should be used for headline, not max.

Conclusion: the pipeline does not show a measured 100-300 ms PX4 switch delay in these logs. R1/R2's 10 Hz and 300 ms mechanisms remain code-level possible stale-cache/cadence limits, but the actual nav23 transition after `VehicleCommand` is tens of milliseconds here.

## 3. A0.3-A0.5

CSV outputs:

- `mcnn_dense_delivered_state.csv`: `wc -l` = 121, i.e. 120 data rows + header.
- `raptor_v8_delivered_state.csv`: `wc -l` = 927, i.e. 926 data rows + header.

Each row contains scenario parameters (`trigger_rp_min/max`, `trigger_rate_min/max`, `wind`, `radius`, `frequency`) separately from delivered state at `t_pred` and `t_nav23` (`roll`, `pitch`, `yaw`, `tilt`, `roll_pitch_abs`, `omega_xyz`, `||omega||`, velocity, position error, setpoint).

mcnn dense drift distributions:

| metric | n | min | p05 | p25 | median | p75 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| delta roll_pitch_abs deg | 120 | 0.023 | 0.322 | 0.865 | 1.349 | 1.955 | 2.681 | 3.365 |
| delta tilt deg | 120 | -0.379 | -0.246 | 0.016 | 0.188 | 0.492 | 1.823 | 2.463 |
| delta yaw deg | 120 | -4.146 | -3.480 | -2.555 | -2.145 | -1.692 | -0.570 | 4.543 |
| delta ||omega|| rad/s | 120 | -0.153 | -0.066 | 0.046 | 0.100 | 0.142 | 0.236 | 0.336 |

`||omega|| * L_total` translated to degrees does not explain the drift well: `abs(delta roll_pitch_abs)` R2 = 0.224, `abs(delta tilt)` R2 = 0.012. The observed handoff drift is much smaller than the back-of-envelope `2 rad/s * 100 ms = 11.5 deg` worst-case because the scalar angular-rate norm does not map directly to the `max(|roll|,|pitch|)` coordinate during this controlled circle.

标签保真度:

- mcnn dense: 118/120 in label box. Outside distance distribution: rp max = 0.334 deg, rate max = 0.
- RAPTOR 926: 796/926 in label box; rp p95/max outside distance = 1.411/4.745 deg; rate max outside distance = 0.173 rad/s.
- mcnn trigger axis: roll 115, pitch 5. RAPTOR trigger axis: roll 815, pitch 111.
- Free variables at mcnn nav23 span wide ranges: yaw min/p95/max = -10.99/-0.589/8.645 deg, velocity norm min/p95/max = 2.357/4.633/6.355 m/s, position error min/p95/max = 1.795/3.674/4.495 m.

## 4. A0.6

Nominal axes still show the old non-monotonic campaign phenomenon. From `mcnn_dense_nominal_grid_summary.csv`: attitude 42 and 45 deg are 3/3 S3, attitude 48 deg is 1/3 S3; wind 0-3 m/s are 3/3 S3 while wind 4-6 m/s are 0/3 S3; delay 0.12 s is 1/3 S3 while 0.15/0.18 s return to 3/3.

But measured handoff coordinates refute the strong RQ3 claim:

- Side-by-side artifact: `mcnn_dense_nominal_vs_actual.png`.
- Local consistency curve artifact: `mcnn_dense_local_consistency.png`.

Local consistency in measured `{roll_pitch_abs(nav23), ||omega||(nav23)}`:

| epsilon normalized | pairs | consistency |
|---:|---:|---:|
| 0.5 | 1218 | 0.677 |
| 1 | 3246 | 0.670 |
| 2 | 5524 | 0.643 |
| 3 | 6222 | 0.634 |
| 5 | 6900 | 0.610 |

Classifier balanced accuracy, S3 vs non-S3:

| feature set | balanced accuracy | main importance |
|---|---:|---|
| `{roll_pitch_abs, ||omega||}` | 0.600 | split roughly evenly |
| + yaw | 0.757 | yaw 0.587 |
| + omega xyz | 0.750 | omega_z 0.391, omega_x 0.250 |
| roll/pitch + omega xyz | 0.753 | omega_z, pitch |
| + velocity and position error | 0.774 | yaw, omega_z, v_norm |
| + w/r/f | 0.795 | yaw, omega_z, v_norm, wind |

The best model is at or slightly above the same-scenario/same-seed repeatability ceiling (0.782, CI [0.744, 0.815]); treat it as "hidden variables improve but do not rescue a deterministic set", not as a new boundary.

RAPTOR 926 has severity counts S0=427, S1=499, S3=0. Its local consistency is trivially 1 because there is no positive S3 class, so it is useful as negative control but cannot adjudicate RQ3's S3 boundary.

## 5. A2

Clean classical fit:

- Command: `python3 scripts/px4_mixer_fingerprint_round5.py`.
- Fit on 30 classical logs, 60000 fitted frames, held out 15 classical logs / 30000 frames.
- Held-out residual RMSE distribution n/min/p05/p25/median/p75/p95/max = 30000/0.000063/0.00330/0.00772/0.01254/0.01918/0.03142/0.32231.

mcnn self-check against value-match labels failed the required gate:

- value labels: allocator_or_other 28802, neural_value_match 197802.
- best residual threshold = 0.116.
- confusion: allocator_as_allocator=122, allocator_as_neural=28680, neural_as_allocator=15, neural_as_neural=197787.
- agreement = 0.8734 < 0.95, so the method is not applied to RAPTOR.

Interpretation: R4's "fit on polluted mcnn nav23" residual gap does not survive the stricter "fit on pure classical baseline, validate on mcnn" protocol. RAPTOR writer attribution by this fingerprint is **无法判定**.

Queue coverage:

- `ActuatorMotors.msg` has no `ORB_QUEUE_LENGTH`; generated `actuator_motors.cpp` has `ORB_DEFINE(..., 1)`, so queue depth is 1.
- `vehicle_torque_setpoint` nominal rate in timestamp audit logs is 50.0 Hz.
- mcnn dense timestamp-sample allocator surviving rate distribution = n/min/p05/p25/median/p75/p95/max = 15/24.35/25.30/26.51/26.81/27.37/28.35/28.79 Hz, roughly 49-58% of nominal 50 Hz.
- R4 anchor timestamp audit still shows mcnn allocator-tag fractions around 0.088-0.160 and RAPTOR timestamp tags near 100% RAPTOR-tag, but because fingerprint self-check failed, I do not use this to conclude RAPTOR "no race".

## 6. A3

Original speed factor:

- `scripts/campaign_runner.py:62` default is 1.25.
- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/sweep_config.json` stores `sim_speed_factor=1.25`; raptor guided/random/grid metadata also store 1.25.
- mcnn dense `sweep_config.json` lacks the field, but task JSON scan in `speed_factor_summary.json` found 6149 task JSONs, 5991 at 1.25 and 158 at 1.0. Relevant switch/raptor campaign metadata inspected were 1.25.
- Therefore R4 using `PX4_SIM_SPEED_FACTOR=1.25` is not itself evidence of a changed speed factor.

SIH timing:

- `sih.cpp:122-158` under lockstep scheduler advances `_current_simulation_time_us` by fixed sim intervals, calls `px4_clock_settime`, then waits for lockstep components after first actuator output.
- `sih.cpp:168-188` non-lockstep realtime loop uses `hrt_call_every` and semaphore wakeups.
- `sensor_step()` uses `dt = hrt_absolute_time() - _last_run` (`sih.cpp:209-217`).

Non-determinism sources:

| source | evidence | conclusion |
|---|---|---|
| `PX4_SIM_SPEED_FACTOR` | original relevant configs use 1.25 | not R4-only difference |
| ROS 2 / DDS timing | offboard predicate and command are ROS timer/DDS path | plausible dominant source |
| offboard spin/timer | `create_timer`, wall_timer_hz 100 Hz | plausible 0-10 ms quantization plus scheduling |
| EKF2 init | not directly randomized in this audit | not proven dominant |
| wind model | fixed `SIH_WIND_N/E`; no seed-driven phase found | not random for fixed theta |
| host scheduling | SIH + ROS + DDS + logger all host scheduled | plausible |

Conclusion: the harness should not be treated as deterministic replay under original configuration. The best direct evidence is A4's same-scenario/same-seed inconsistency in original mcnn dense artifacts.

## 7. A4

Command/source: repeatability groups are generated in `mcnn_dense_summary.json` by `scripts/px4_delivered_state_round5.py --population mcnn_dense --workers 4`.

- same-scenario + same-seed groups: 3 groups, each n=19, all are the repeated baseline point across dense axes.
- pair consistency = 401/513 = 0.7817.
- Wilson 95% CI = [0.7439, 0.8153].
- This is a ceiling for classifiers over those repeated conditions. It also means same scenario + same seed does not imply deterministic S3/non-S3 replay in the current artifacts.

RAPTOR 926 repeatability is one-class with no S3, so its 513/513 same-pair consistency is not informative for an S3 boundary.

## 8. A5

Current provenance snapshot: `docs/round5_delivered_state_20260709/provenance_snapshot.json`.

- PX4 SHA: `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`.
- Docker image inspect for `uav_sf:phase1`: failed with `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`; digest not confirmed.
- Patch hashes: `m2b_state_shim.patch` = `1921be84...de0d1bd`; `raptor_unclipped.patch` = `d714f0c2...9be0b`.
- Current binary hashes include `px4_sitl_mcnn_sih/bin/px4` = `b2266659...8f61f40d`, `px4_sitl_raptor_sih/bin/px4` = `6829b029...fe4dde20`, and others in the snapshot.
- Toolchain: gcc/g++ 11.4.0, cmake 3.22.1, ninja 1.10.1.
- The PX4 worktree is dirty, including module and submodule modifications. I did not revert or edit PX4 tracked files.

Archival script established: `scripts/archive_campaign_provenance.py`. It records git SHA/status, Docker image inspect result, env snapshot, patch hashes, model/module source hashes, and binary hashes. It does not make builds reproducible by itself.

Bit-reproducibility: not implemented. Known suspects remain build-id/path/timestamp/compiler nondeterminism and dirty source/submodule state. Since R4 reports original campaign binary was overwritten, A5 cannot reconstruct the exact original artifact from this workspace.

## 9. 我不确定的地方

- The mcnn 120-row dense sweep is the correct dataset for RQ3 S3 adjudication; the requested "926 rows" correspond to RAPTOR v8, which has no S3 class. I produced both, but they answer different questions.
- The same-scenario/same-seed repeats in dense sweep are repeated baseline theta under different nominal axis tags; I treat them as replay evidence because scenario_key and seed match, but they are not a dedicated rerun campaign.
- The A2 fingerprint failure might be caused by using an insufficient setpoint topic or a value-match label that is too strict. Under the task's own 95% self-check rule, that uncertainty means "do not use on RAPTOR."
- Docker image digest could not be verified from this user due socket permission; A5 image state remains unconfirmed.

## 10. 与项目笔记（v8 / EXPERIMENT_INDEX / R1-R4）冲突之处

- v8 says RQ3 is a "高维带洞失效边界"; this audit says the nominal dense sweep is non-monotonic, but measured 2D handoff state does not define a deterministic boundary.
- v8 reports dense sweep "120 eval 81 strict"; current `sweep_results.jsonl`/delivered-state extraction gives severity counts S0=22, S1=11, S3=87. I used the current artifact fields and did not silently reconcile that mismatch.
- R1/R2 code-level 10 Hz / 300 ms platform cadence remains true, but measured `t_nav23 - t_cmd` here is median 28 ms, p95 36 ms. The code-level stale-cache mechanism does not appear as a 100-300 ms measured mode-transition delay in these logs.
- R4's RAPTOR attribution remained unable to decide; the proposed clean setpoint-fingerprint method also cannot be used because the mcnn self-check fails at 87.34%.
- R4's GATE_FAIL is consistent with this audit's repeatability ceiling, but R4's rebuilt binary/environment is not the same as the original overwritten campaign binary, so I do not merge those reruns into the original 120/926 tables.
