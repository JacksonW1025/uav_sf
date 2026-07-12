# PX4 Provenance & Handoff Semantics Audit (Round 2)

PX4 HEAD: `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`   Worktree clean?: `no`   Date: `2026-07-09`

Evidence convention: PX4 source conclusions below state whether they come from pristine `HEAD` (`git show HEAD:<path>` / clean working-tree file) or from the current working tree. `external/PX4-Autopilot/src/modules/commander/` is clean, so commander line references are both pristine `HEAD` and working tree.

## 0. 判定摘要（每条一行）

- T1 ModeManagement stale-config 来源： `UPSTREAM`. Pristine `HEAD` contains the stale-config code; `src/modules/commander/` is `CLEAN`; the introducing commit is `0eb14d64d5f90b50ae752ef6101faa69d7a8e1b2` by `sbenchabane <sbenchabane@axon.com>`, committed by Beat Kung.
- T2 mcnn board 上 mc_raptor 归属： `ISOLATED` at runtime. `mcnn_sih.px4board` compiles `MC_RAPTOR`, but no startup script starts it and `raptor_status` is absent from all `*_mcnn.ulg` found by the current scan.
- T3 source_id 行为： `NEVER_ACCEPTED`. In 20 mcnn + 20 RAPTOR valid nav-23 ULOGs, `vehicle_control_mode.source_id` is `[0]` for the whole `nav_state==23` interval.
- T3.2 模块 config 是否结构上永远 stale： `YES` for these modules. Both modules publish `config_control_setpoints` once after registration; commander marks cached configs stale on each later nav-state activation.
- T4 actuator_motors 写者： `RACE`. `control_allocator` remains enabled and publishes `actuator_motors`, while `mc_nn_control` / `mc_raptor` publish the same topic instance directly.
- T5 未初始化 reply 字段： `GARBAGE` for RAPTOR runtime observation; mcnn runtime observation is `INCONCLUSIVE` because the existing mcnn SITL binary requires GLIBC 2.38 on a GLIBC 2.35 host. Static code shows the same uninitialized pattern in both modules.
- T6 can_run 位的最坏陈旧上界： about `1350 ms` after the last good reply for an established component that stops replying; about `400 ms` for a still-responding component.
- T7 mc_att_control 有无积分项： `无`. MC attitude control is proportional attitude control plus yaw feed-forward and setpoint memory; no attitude integral state exists.
- T8 各小项： `mode_req_wind_and_flight_time_compliance` and `mode_req_offboard_signal` are not fields of `ArmingCheckReply.msg`; external mode IDs are hash-reuse-first, otherwise first free external slot; `MC_RAPTOR_OFFB` defaults false and project scripts/config set it to `0`; `flag_control_termination_enabled=true` in module configs is ignored on the stale safe-default path.

## 0.1 ⚠️ 必须撤回的 Round 1 结论

- 撤回 Round 1 中“没找到姿态控制器的 I 重置”作为发现的表述。`mc_att_control` 结构上没有积分项：`AttitudeControl.hpp:103-109` contains only `_proportional_gain`, `_rate_limit`, `_yaw_w`, `_attitude_setpoint_q`, and `_yawspeed_setpoint`; `AttitudeControl.cpp:55-113` computes proportional quaternion attitude error plus yaw feed-forward.
- 不撤回 Round 1 的 `source_id=0` / safe-defaults 解释。T1 shows the stale-config logic is in pristine PX4 `HEAD`, and T3 shows the behavior persists over the entire external-mode interval in the sampled logs.
- 不撤回 Round 1 的 `rate_ctrl_status` 持续发布事实，但必须改写语义：T4 shows this is not only “classical rate controller still computes”; it is part of a broader `actuator_motors` same-instance multi-writer race because `control_allocator` remains enabled.

## 0.2 ⚠️ 对 v8 已有 926 eval 效度的影响

The v8 identity/baseline claim is not invalidated by RAPTOR running on mcnn: runtime evidence supports `ISOLATED`, and sampled mcnn approach phases include `NAVIGATION_STATE_OFFBOARD=14` before `EXTERNAL1=23`.

The 926 evals must not be described as clean single-writer external-mode actuator-control runs. T3/T4 show both mcnn and RAPTOR external modes ran under commander safe-default control flags, never accepted their intended `config_control_setpoints`, and had a potential same-instance `actuator_motors` race with the classical control allocator. If the project’s RAPTOR 0-S3 result is correct, the shared race is not sufficient by itself to explain mcnn-only S3, because the same race appears in sampled RAPTOR logs; still, paper text should explicitly own this as a threat to causal attribution.

## 1. T1 — Provenance

### T1.1 全量脏文件清单

Command:

```bash
git -C external/PX4-Autopilot rev-parse HEAD
git -C external/PX4-Autopilot status --short
git -C external/PX4-Autopilot diff --stat
git -C external/PX4-Autopilot diff --stat --cached
git -C external/PX4-Autopilot status --short --untracked-files=all | head -100
```

Output summary:

```text
3042f906abaab7ab59ae838ad5a530a9ef3df9a6

 M ROMFS/px4fmu_common/init.d-posix/airframes/CMakeLists.txt
 m Tools/simulation/flightgear/flightgear_bridge
 M Tools/simulation/gazebo-classic/sitl_gazebo-classic
 m Tools/simulation/jmavsim/jMAVSim
 m Tools/simulation/jsbsim/jsbsim_bridge
 M boards/modalai/voxl2/libfc-sensor-api
 m boards/modalai/voxl2/src/lib/mpa/libmodal-json
 M boards/modalai/voxl2/src/lib/mpa/libmodal-pipe
 m src/drivers/actuators/vertiq_io/iq-module-communication-cpp
 M src/drivers/cyphal/legacy_data_types
 M src/drivers/cyphal/libcanard
 m src/drivers/cyphal/public_regulated_data_types
 M src/drivers/ins/microstrain/mip_sdk
 m src/drivers/ins/sbgecom/sbgECom
 m src/drivers/uavcan/libdronecan/dsdl
 M src/drivers/uavcan/libdronecan/libuavcan/dsdl_compiler/pydronecan
 m src/lib/crypto/monocypher
 M src/modules/ekf2/EKF2.cpp
 M src/modules/ekf2/EKF2.hpp
 M src/modules/ekf2/EKF2Selector.cpp
 M src/modules/ekf2/EKF2Selector.hpp
 M src/modules/mc_raptor/mc_raptor.cpp
 M src/modules/mc_raptor/module.yaml
 M src/modules/sensors/vehicle_angular_velocity/VehicleAngularVelocity.cpp
 M src/modules/sensors/vehicle_angular_velocity/VehicleAngularVelocity.hpp
 M src/modules/uxrce_dds_client/dds_topics.yaml
 M src/modules/zenoh/zenoh-pico
 M test/fuzztest
?? ROMFS/px4fmu_common/init.d-posix/airframes/10046_sihsim_x500_v2
?? boards/px4/sitl/mcnn_sih.px4board
?? boards/px4/sitl/raptor_sih.px4board
?? boards/px4/sitl/raptor_unclipped_sih.px4board
```

`git diff --stat` output summary: `28 files changed, 969 insertions(+), 19 deletions(-)`. The tracked source modifications are in EKF2, `mc_raptor`, `VehicleAngularVelocity`, DDS topics, ROMFS CMake, and submodule pointers. `git diff --stat --cached` was empty. The `head -100` status output is identical to the full `status --short` listing above because the list is under 100 lines.

### T1.2 逐目录判定

Command form for each path: `git -C external/PX4-Autopilot diff -- <path>`.

| # | Path | Verdict | Evidence |
|---|---|---|---|
| 1 | `src/modules/commander/` | `CLEAN` | `git diff -- src/modules/commander/` empty. |
| 2 | `src/modules/commander/ModeManagement.cpp` | `CLEAN` | `git diff -- .../ModeManagement.cpp` empty. |
| 3 | `src/modules/commander/ModeManagement.hpp` | `CLEAN` | `git diff -- .../ModeManagement.hpp` empty. |
| 4 | `src/modules/commander/Commander.cpp` | `CLEAN` | `git diff -- .../Commander.cpp` empty. |
| 5 | `src/modules/commander/HealthAndArmingChecks/` | `CLEAN` | `git diff -- .../HealthAndArmingChecks/` empty. |
| 6 | `src/modules/mc_nn_control/` | `CLEAN` | `git diff -- src/modules/mc_nn_control/` empty. |
| 7 | `src/modules/mc_raptor/` | `MODIFIED` | Diff below. |
| 8 | `src/modules/mc_pos_control/` | `CLEAN` | `git diff -- src/modules/mc_pos_control/` empty. |
| 9 | `src/modules/mc_rate_control/` | `CLEAN` | `git diff -- src/modules/mc_rate_control/` empty. |
| 10 | `src/modules/mc_att_control/` | `CLEAN` | `git diff -- src/modules/mc_att_control/` empty. |
| 11 | `src/modules/control_allocator/` | `CLEAN` | `git diff -- src/modules/control_allocator/` empty. |
| 12 | `msg/` and `msg/versioned/` | `CLEAN` | `git diff -- msg/ msg/versioned/` empty. |
| 13 | `boards/px4/sitl/` | `LOCAL UNTRACKED` | `git diff -- boards/px4/sitl/` empty, but status shows `mcnn_sih.px4board`, `raptor_sih.px4board`, `raptor_unclipped_sih.px4board` untracked. |
| 14 | `ROMFS/` | `MODIFIED + UNTRACKED` | `CMakeLists.txt` adds `10046_sihsim_x500_v2`; that airframe file is untracked. |

`src/modules/mc_raptor/` diff content:

```diff
diff --git a/src/modules/mc_raptor/mc_raptor.cpp b/src/modules/mc_raptor/mc_raptor.cpp
index cdf2b2af23..abd8c46bab 100644
--- a/src/modules/mc_raptor/mc_raptor.cpp
+++ b/src/modules/mc_raptor/mc_raptor.cpp
@@ -385,9 +385,9 @@ void Raptor::observe(...)
-		observation.position[0] = clip(pt[0], max_position_error, -max_position_error);
-		observation.position[1] = clip(pt[1], max_position_error, -max_position_error);
-		observation.position[2] = clip(pt[2], max_position_error, -max_position_error);
+		observation.position[0] = pt[0];
+		observation.position[1] = pt[1];
+		observation.position[2] = pt[2];
@@ -396,9 +396,9 @@ void Raptor::observe(...)
-		observation.linear_velocity[0] = clip(vt[0], max_velocity_error, -max_velocity_error);
-		observation.linear_velocity[1] = clip(vt[1], max_velocity_error, -max_velocity_error);
-		observation.linear_velocity[2] = clip(vt[2], max_velocity_error, -max_velocity_error);
+		observation.linear_velocity[0] = vt[0];
+		observation.linear_velocity[1] = vt[1];
+		observation.linear_velocity[2] = vt[2];
diff --git a/src/modules/mc_raptor/module.yaml b/src/modules/mc_raptor/module.yaml
@@ -41,3 +41,207 @@ parameters:
+    - group: M2B State Shim
+      definitions:
+        M2B_EN:
+            description:
+                short: Enable M2b adversarial shared-state injection shim
+            type: boolean
+            default: false
+            category: System
+        ...
+        M2B_A_Y:
+            description:
+                short: Attitude shim yaw amplitude
+            type: float
+            unit: rad
+            default: 0.0
+            category: System
```

The full command output adds only the M2B shim parameters shown above; no commander files are touched.

`ROMFS/` tracked diff content:

```diff
diff --git a/ROMFS/px4fmu_common/init.d-posix/airframes/CMakeLists.txt b/ROMFS/px4fmu_common/init.d-posix/airframes/CMakeLists.txt
@@ -107,6 +107,7 @@ px4_add_romfs_files(
 	10043_sihsim_standard_vtol
 	10044_sihsim_hex
 	10045_sihsim_rover_ackermann
+	10046_sihsim_x500_v2
```

The untracked airframe `ROMFS/px4fmu_common/init.d-posix/airframes/10046_sihsim_x500_v2:13-77` contains only defaults/params; it does not start `mc_raptor` or `mc_nn_control`.

### T1.3 ModeManagement stale-config provenance

Pristine `HEAD` command:

```bash
git -C external/PX4-Autopilot show HEAD:src/modules/commander/ModeManagement.cpp | grep -n "stale\|_last_served_change_us\|config_control_setpoint"
```

Output summary:

```text
544: _last_served_change_us = hrt_absolute_time();
551: // Refuse a cached config_control_setpoints entry that predates the current
553: const bool stale = (mode.config_control_setpoint.timestamp == 0)
554:     || (mode.config_control_setpoint.timestamp + 10_ms < _last_served_change_us);
556: if (stale) {
565: control_mode = mode.config_control_setpoint;
632-636: cached config_control_setpoint copied and timestamp overwritten with hrt_absolute_time()
```

Line references in the clean working tree match pristine `HEAD`: `ModeManagement.cpp:536-568` contains the stale branch; `ModeManagement.cpp:626-637` caches config updates.

Introducing commit command:

```bash
git -C external/PX4-Autopilot log -1 --format='%H | %an | %ae | %ad | %s' -L 530,570:src/modules/commander/ModeManagement.cpp
```

Output summary:

```text
0eb14d64d5f90b50ae752ef6101faa69d7a8e1b2 | sbenchabane | sbenchabane@axon.com | Fri May 15 22:20:05 2026 +0200 | fix(commander): refuse stale config_control_setpoints cache on activation
Commit: Beat Küng <beat-kueng@gmx.net>, Thu May 21 07:53:03 2026 +0200
```

`git blame -L 530,570 src/modules/commander/ModeManagement.cpp` attributes lines `536`, `540-566` to `0eb14d64d5f` by `sbenchabane`; surrounding older lines are by PX4 authors including Matthias Grob and Beat Kung. `git remote -v` shows `origin https://github.com/PX4/PX4-Autopilot.git`, and `git branch -a --contains 0eb14d64d5f...` includes `main` and `origin/main`.

Declaration and assignment:

```text
ModeManagement.hpp:203-204: uint8_t _last_served_nav_state{0xff}; hrt_abstime _last_served_change_us{0};
ModeManagement.cpp:540-545: on activation, set _last_served_nav_state and _last_served_change_us = hrt_absolute_time();
```

Project patch audit:

```bash
ls patches/px4/
git -C /mnt/nvme/uav_sf log --oneline -- patches/
grep -H '^+++' patches/px4/*.patch
```

Output summary:

```text
m2b_state_shim.patch
raptor_unclipped.patch

1cbbaa3 Add RAPTOR unclipped ablation workflow
2515aa6 Run wave2 state-contamination campaign
84d8bd5 Add RAPTOR closeout artifacts
adb7d68 Add M2b diagnostics and artifacts

patches/px4/m2b_state_shim.patch:+++ b/src/modules/ekf2/EKF2.cpp
patches/px4/m2b_state_shim.patch:+++ b/src/modules/ekf2/EKF2.hpp
patches/px4/m2b_state_shim.patch:+++ b/src/modules/ekf2/EKF2Selector.cpp
patches/px4/m2b_state_shim.patch:+++ b/src/modules/ekf2/EKF2Selector.hpp
patches/px4/m2b_state_shim.patch:+++ b/src/modules/mc_raptor/module.yaml
patches/px4/m2b_state_shim.patch:+++ b/src/modules/sensors/vehicle_angular_velocity/VehicleAngularVelocity.cpp
patches/px4/m2b_state_shim.patch:+++ b/src/modules/sensors/vehicle_angular_velocity/VehicleAngularVelocity.hpp
patches/px4/raptor_unclipped.patch:+++ b/src/modules/mc_raptor/mc_raptor.cpp
```

T1 verdict: `UPSTREAM`. The stale-config logic is in pristine `3042f906` and is not introduced by this project’s `patches/px4`.

## 2. T2 — 运行时归属

### T2.1 编译期

Command:

```bash
rg -n '^CONFIG_MODULES_.*=y' external/PX4-Autopilot/boards/px4/sitl/mcnn_sih.px4board
```

Key output:

```text
24:CONFIG_MODULES_AIRSHIP_ATT_CONTROL=y
...
51:CONFIG_MODULES_MC_ATT_CONTROL=y
52:CONFIG_MODULES_MC_AUTOTUNE_ATTITUDE_CONTROL=y
53:CONFIG_MODULES_MC_HOVER_THRUST_ESTIMATOR=y
54:CONFIG_MODULES_MC_NN_CONTROL=y
55:CONFIG_MODULES_MC_POS_CONTROL=y
56:CONFIG_MODULES_MC_RAPTOR=y
57:CONFIG_MODULES_MC_RATE_CONTROL=y
...
74:CONFIG_MODULES_VTOL_ATT_CONTROL=y
```

Command:

```bash
rg -n '^CONFIG_MODULES_.*=y' external/PX4-Autopilot/boards/px4/sitl/raptor_sih.px4board external/PX4-Autopilot/boards/px4/sitl/raptor_unclipped_sih.px4board external/PX4-Autopilot/boards/px4/sitl/raptor.px4board
```

Output summary: `raptor_sih.px4board`, `raptor_unclipped_sih.px4board`, and `raptor.px4board` all include `CONFIG_MODULES_MC_RAPTOR=y` and do not include `CONFIG_MODULES_MC_NN_CONTROL=y`. Therefore:

- `mcnn_sih` compiles `mc_raptor`: yes.
- `raptor_sih` / `raptor_unclipped_sih` compile `mc_nn_control`: no.

The board files are local/untracked per T1, so this is working-tree board behavior, not pristine PX4.

### T2.2 运行时启动

Command:

```bash
rg -n "mc_raptor|mc_nn_control" external/PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/rcS external/PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/airframes -S
```

Output: no matches. `rcS` starts commander/sim/estimator/navigator through the normal script path (`rcS:206-221`, `rcS:238-286`, `rcS:288`), but there is no `mc_raptor start` or `mc_nn_control start`.

Project custom startup evidence:

```text
scripts/m1_diff_runner.py:189 appends "mc_raptor start"
scripts/mcnn_gate1_bringup.py:65 appends "mc_nn_control start"
scripts/mcnn_gate3_position_error_probe.py:200 appends "mc_nn_control start" for mcnn
scripts/m0_run_experiment.sh:98 sets MC_RAPTOR_OFFB 0, line 100 starts mc_raptor
```

Conclusion: `CONFIG_MODULES_*=y` means the module is compiled into the binary, not auto-started. Runtime ownership is determined by shell/script `start` commands.

### T2.3 ULOG 取证

All-log topic-presence commands:

```bash
find runs/campaigns docs -name '*_mcnn.ulg' -type f | wc -l
find runs/campaigns docs -name '*_raptor.ulg' -type f | wc -l
rg -a -l --glob '*_mcnn.ulg' 'raptor_status' runs/campaigns docs | wc -l
rg -a -l --glob '*_mcnn.ulg' 'neural_control' runs/campaigns docs | wc -l
rg -a -l --glob '*_raptor.ulg' 'neural_control' runs/campaigns docs | wc -l
rg -a -l --glob '*_raptor.ulg' 'raptor_status' runs/campaigns docs | wc -l
```

Current output:

```text
*_mcnn.ulg total: 1977
*_raptor.ulg total: 971
mcnn raptor_status: 0
mcnn neural_control: 1963
raptor neural_control: 0
raptor raptor_status: 965
```

Some suffix-matching logs are partial/no-topic logs; for logs that actually enter external mode, the 40-log pyulog scan below has `neural_control` in mcnn samples and `raptor_status` in RAPTOR samples. Sample paths:

```text
runs/campaigns/switch_severity_random_confirm_20260630/.../mcnn_gate3_..._mcnn.ulg
runs/campaigns/raptor_gate0_stability_20260705/.../m1_raptor_gate0_stability_..._raptor.ulg
```

`register_ext_component_request` / `_reply`: binary string search is not decisive because it can hit message metadata. Direct pyulog sample loads for selected mcnn/RAPTOR logs had data topics `['neural_control', 'vehicle_status']` or `['raptor_status', 'vehicle_status']`, not decoded registration request/reply data. Therefore nav-23 ownership is inferred from startup scripts plus identity topics, not from request/reply topic rows.

40-log pyulog scan output:

```text
GROUP mcnn_f1_anchor selected 5
GROUP mcnn_f2_guided selected 5
GROUP mcnn_dense selected 5
GROUP mcnn_wave2 selected 5
GROUP raptor_anchor selected 5
GROUP raptor_guided selected 5
GROUP raptor_dense selected 5
GROUP raptor_unclipped selected 5

AGG mcnn logs 20 source_values [0]
PRENAV_HAS_14 20 of 20 PRENAV_VALUES_UNION [4, 14, 17]
RATE mcnn neural_control min/median/max 228.08 229.67 241.64
RATE mcnn raptor_status none

AGG raptor logs 20 source_values [0]
PRENAV_HAS_14 20 of 20 PRENAV_VALUES_UNION [4, 14, 17]
RATE raptor raptor_status min/median/max 233.8 240.07 240.95
RATE raptor neural_control none
```

Thus approach includes `NAVIGATION_STATE_OFFBOARD=14` before `NAVIGATION_STATE_EXTERNAL1=23` in all 40 selected logs.

### T2.4 参数

Working-tree `mc_raptor` code and module config:

```text
mc_raptor.cpp:254-263 sets enable_replace_internal_mode = _param_mc_raptor_offboard.get(), replace_internal_mode = NAVIGATION_STATE_OFFBOARD, request_offboard_setpoints = true.
module.yaml:22-30 defines MC_RAPTOR_OFFB, default false.
```

Project grep:

```text
config/*.json and scripts/*.py/sh set MC_RAPTOR_OFFB: 0
scripts/smoke_px4_raptor.sh:20 param set MC_RAPTOR_OFFB 0
scripts/m0_run_experiment.sh:98 param set MC_RAPTOR_OFFB 0
```

T2 verdict: `ISOLATED`. Compile-time co-residence exists on the local mcnn board, but runtime logs/scripts show `mc_raptor` is not started, not producing `raptor_status`, and not replacing OFFBOARD in mcnn logs.

## 3. T3 — source_id 时序

### T3.1 语义

Pristine/clean source evidence:

```text
msg/versioned/VehicleControlMode.msg:21-22: uint8 source_id # Mode ID (nav_state)
ModeManagement.hpp:90-100: safe defaults enable position, velocity, altitude, climb-rate, acceleration, attitude, rates, allocation.
Commander.cpp:2760-2775: commander zeroes vehicle_control_mode, applies nav-state control mode, calls ModeManagement::updateControlMode, recomputes flag_multicopter_position_control_enabled, then publishes.
```

`source_id=0` is not an external mode ID in the `EXTERNAL1..8` range (`VehicleStatus.msg:55-62` are `23..30`). In the observed `nav_state==23` intervals, it means commander did not publish the module’s accepted external-mode config; the flags match safe-default behavior.

Module assignments:

```text
mc_nn_control.cpp:181-194 ConfigureNeuralFlightMode(): source_id = mode_id; allocation=false; termination=true; publish config_control_setpoints.
mc_raptor.cpp:475-486: source_id = ext_component_mode_id; allocation=false; termination=true; publish config_control_setpoints.
```

Registration returns `mode_id`; `ModeManagement.cpp:95-178` reuses a matching name hash if present, otherwise allocates the first unused/free external slot and returns `new_mode_idx + FIRST_EXTERNAL_NAV_STATE`.

### T3.2 模块什么时候发布 config

`mc_nn_control` working-tree evidence:

```text
mc_nn_control.cpp:181-194 ConfigureNeuralFlightMode() publishes config_control_setpoints.
mc_nn_control.cpp:221-232 CheckModeRegistration() calls ConfigureNeuralFlightMode(_mode_id) after successful registration.
mc_nn_control.cpp:472-482 Run() registers once, then checks registration until mode id exists.
No call in Run() on nav-state activation; no periodic config republish.
```

`mc_raptor` working-tree evidence:

```text
mc_raptor.cpp:464-488 after register_ext_component_reply succeeds, state REGISTERED publishes config once and changes to CONFIGURED.
mc_raptor.cpp:416-438 only replies to arming checks later; it does not republish config on activation.
```

Commander stale logic:

```text
ModeManagement.cpp:540-545 sets _last_served_change_us whenever nav_state changes.
ModeManagement.cpp:551-565 rejects cached config when timestamp == 0 or timestamp + 10_ms < _last_served_change_us.
ModeManagement.cpp:632-636 overwrites the cached config timestamp with receipt time when config_control_setpoints is received.
```

Cross-reasoning verdict: `YES`, structurally stale for these modules. If registration/config happens before takeoff or before the later user switch to external mode, then activation time is later than cached config timestamp by much more than 10 ms. Because neither module republishes config on activation, the intended `allocation=false`/`source_id=mode_id` config is never accepted in ordinary runs. The stale-guard itself is upstream; the one-shot publish behavior is local module behavior.

### T3.3 ULOG 整区间扫描

Command: pyulog scan over 20 mcnn and 20 RAPTOR logs covering four mcnn groups and four RAPTOR groups:

```text
mcnn_f1_anchor: docs/fuzz1c_severity_20260625
mcnn_f2_guided: runs/campaigns/switch_severity_guided_0_20260629
mcnn_dense: runs/campaigns/switch_severity_dense_sweep_20260630
mcnn_wave2: runs/campaigns/wave2_statecontam_guided_20260703
raptor_anchor: runs/campaigns/raptor_gate0_anchor_boundary_20260705
raptor_guided: runs/campaigns/raptor_switch_severity_guided_0_20260705
raptor_dense: runs/campaigns/raptor_switch_severity_dense_sweep_20260705
raptor_unclipped: runs/campaigns/raptor_unclipped_ablation_20260707
```

Aggregate output:

```text
AGG mcnn logs 20 source_values [0]
FLAGS mcnn {
  flag_control_rates_enabled: [1],
  flag_multicopter_position_control_enabled: [1],
  flag_control_allocation_enabled: [1],
  flag_control_position_enabled: [1],
  flag_control_attitude_enabled: [1],
  flag_control_climb_rate_enabled: [1],
  flag_control_termination_enabled: [0]
}

AGG raptor logs 20 source_values [0]
FLAGS raptor {
  flag_control_rates_enabled: [1],
  flag_multicopter_position_control_enabled: [1],
  flag_control_allocation_enabled: [1],
  flag_control_position_enabled: [1],
  flag_control_attitude_enabled: [1],
  flag_control_climb_rate_enabled: [1],
  flag_control_termination_enabled: [0]
}
```

There was no observed `source_id` transition from `0` to module `mode_id`. Delay distribution is empty; verdict `NEVER_ACCEPTED`.

### T3.4 失效对齐

Not applicable because T3.3 is `NEVER_ACCEPTED`, not `TRANSIENT`. There is no accepted-config delay window to compare to the F1 S3 failure timestamps.

## 4. T4 — actuator 写者

### T4.1 代码

`control_allocator` gate and publish path, clean working tree:

```text
ControlAllocator.cpp:363-367: _publish_controls = vehicle_control_mode.flag_control_allocation_enabled.
ControlAllocator.cpp:707-711: publish_actuator_controls() returns if !_publish_controls.
ControlAllocator.cpp:713-741: builds and publishes actuator_motors.
```

`mc_rate_control`, clean working tree:

```text
MulticopterRateControl.cpp:188-220: runs rate controller if flag_control_rates_enabled.
MulticopterRateControl.cpp:225-229: publishes rate_ctrl_status.
MulticopterRateControl.cpp:231-264: publishes vehicle_thrust_setpoint and vehicle_torque_setpoint.
```

Learned modules, working tree:

```text
mc_nn_control.cpp:377-397: publishes actuator_motors directly; no timestamp_sample source tag is assigned.
mc_raptor.cpp:872-901: publishes actuator_motors directly when status.active; timestamp_sample copied from vehicle_angular_velocity.
```

uORB same-topic semantics:

```text
uORBManager.hpp:224-239: single-instance advertise calls orb_advertise_multi; any number of advertisers may publish; publications are atomic, no coordination; multi creates independent instances.
Publication.cpp:47-63: Publication publishes through orb_advertise(get_topic(), nullptr), i.e. single instance.
uORBDeviceMaster.cpp:128-136: single-instance advertiser may use existing node.
uORBDeviceNode.cpp:188-193: publish atomically copies data into the topic queue.
uORBDeviceNode.cpp:302-308: current implementation can only have multiple publishers for instance 0; multiple instances have at most one publisher per instance.
```

Potential `actuator_motors` publishers during `nav_state==23`:

| Publisher | Gate | Expected rate source |
|---|---|---|
| `control_allocator` | `flag_control_allocation_enabled == 1` | torque/thrust input loop, observed 50 Hz setpoint path |
| `mc_nn_control` | `_use_neural` when nav_state equals mode id | angular velocity callback, observed ~228-242 Hz debug topic |
| `mc_raptor` | `status.active` | angular velocity/control loop, observed ~234-241 Hz status topic |

### T4.2 ULOG

40-log scan aggregate:

```text
mcnn:
  vehicle_torque_setpoint: 50.0 / 50.0 / 50.0 Hz
  vehicle_thrust_setpoint: 50.0 / 50.0 / 50.0 Hz
  actuator_motors: 232.65 / 234.04 / 246.23 Hz
  neural_control: 228.08 / 229.67 / 241.64 Hz
  rate_ctrl_status: 5.0 / 5.0 / 5.0 Hz

raptor:
  vehicle_torque_setpoint: 50.0 / 50.0 / 50.0 Hz
  vehicle_thrust_setpoint: 50.0 / 50.0 / 50.0 Hz
  actuator_motors: 233.1 / 239.32 / 240.2 Hz
  raptor_status: 233.8 / 240.07 / 240.95 Hz
  rate_ctrl_status: 5.0 / 5.0 / 5.0 Hz
```

The logs do not expose writer identity for each `actuator_motors` sample. `actuator_motors` has only the normal topic fields; the sampled logs did not show an independent `actuator_motors_1` instance in pyulog topic lists.

T4 verdict: `RACE`. The classical chain is still enabled and publishing torque/thrust setpoints; `control_allocator` is enabled by the same safe-default flags and code-publishes `actuator_motors`; the learned module publishes `actuator_motors` directly to the same single-instance topic. RAPTOR samples show the same race, so if RAPTOR’s 0-S3 result is accepted, race alone is not sufficient as the sole cause of mcnn S3. However, ULOG cannot attribute individual motor samples to a writer, so this must be a paper threat.

## 5. T5 — 未初始化字段

### T5.1 静态

Generated struct from `build/px4_sitl_mcnn_sih/uORB/topics/arming_check_reply.h:52-87`:

```text
struct arming_check_reply_s {
  uint64_t timestamp;
  uint8_t request_id;
  uint8_t registration_id;
  uint8_t health_component_index;
  bool health_component_is_present;
  bool health_component_warning;
  bool health_component_error;
  bool can_arm_and_run;
  uint8_t num_events;
  bool mode_req_angular_velocity;
  bool mode_req_attitude;
  bool mode_req_local_alt;
  bool mode_req_local_position;
  bool mode_req_local_position_relaxed;
  bool mode_req_global_position;
  bool mode_req_global_position_relaxed;
  bool mode_req_mission;
  bool mode_req_home_position;
  bool mode_req_prevent_arming;
  bool mode_req_manual_control;
  uint8_t _padding0[5];
  struct event_s events[5];
};
```

No default member initializers exist in that generated struct.

Uninitialized publisher code:

```text
mc_nn_control.cpp:198-217: arming_check_reply_s arming_check_reply; then assigns timestamp, request_id, registration_id, health_component_index, num_events, can_arm_and_run, angular/local_position/attitude/local_alt/home/mission/global/prevent/manual flags.
mc_raptor.cpp:416-438: same pattern.
```

Unassigned in both modules: `health_component_is_present`, `health_component_warning`, `health_component_error`, `mode_req_local_position_relaxed`, `mode_req_global_position_relaxed`, `_padding0`, and `events[]`.

Consumer code:

```text
externalChecks.cpp:176-181 consumes mode_req_local_position_relaxed and mode_req_global_position_relaxed.
externalChecks.cpp:196-199 consumes health_component_* if health_component_index > 0.
externalChecks.cpp:202-206 consumes events up to num_events; num_events is assigned 0 in these two modules.
```

Reference implementation check:

```bash
git clone --depth 1 https://github.com/Auterion/px4-ros2-interface-lib /tmp/px4-ros2-interface-lib-audit
git -C /tmp/px4-ros2-interface-lib-audit rev-parse HEAD
rg -n "ArmingCheckReply|arming_check_reply|fillArmingCheckReply|can_arm_and_run" /tmp/px4-ros2-interface-lib-audit/px4_ros2_cpp -S
```

Output summary:

```text
c3e410f035806e8c56246708432ded09c976434b
health_and_arming_checks.cpp:37: px4_msgs::msg::ArmingCheckReply reply{};
health_and_arming_checks.cpp:45: _mode_requirements.fillArmingCheckReply(reply);
requirement_flags.hpp:22: arming_check_reply.mode_req_local_position_relaxed = local_position_relaxed;
```

The online source is the Auterion/PX4 ROS 2 interface library: https://github.com/Auterion/px4-ros2-interface-lib/blob/main/px4_ros2_cpp/src/components/health_and_arming_checks.cpp and https://github.com/Auterion/px4-ros2-interface-lib/blob/main/px4_ros2_cpp/include/px4_ros2/common/requirement_flags.hpp. It uses brace initialization and explicitly fills the relaxed local-position requirement.

### T5.2 运行时观测

Precondition: T1-T4 were completed before this SITL attempt. I ran PX4 from temporary roots under `/tmp`, copying only runtime `etc` and RAPTOR policy into the temp root, not writing into the PX4 worktree.

mcnn attempt command summary:

```bash
env HEADLESS=1 PX4_SIMULATOR=sihsim PX4_SIM_MODEL=sihsim_x500_v2 PX4_SYS_AUTOSTART=10046 .../build/px4_sitl_mcnn_sih/bin/px4 <temp-root>
```

Output:

```text
px4_sitl_mcnn_sih/bin/px4: /lib/aarch64-linux-gnu/libc.so.6: version `GLIBC_2.38' not found
px4_sitl_mcnn_sih/bin/px4: /lib/aarch64-linux-gnu/libstdc++.so.6: version `GLIBCXX_3.4.32' not found
Host ldd: Ubuntu GLIBC 2.35-0ubuntu3.13
Docker check: permission denied connecting to /var/run/docker.sock
```

RAPTOR observation command summary:

```bash
cd /tmp/px4_audit_t5_raptor.../raptor
env HEADLESS=1 PX4_SIMULATOR=sihsim PX4_SIM_MODEL=sihsim_x500_v2 PX4_SYS_AUTOSTART=10046 timeout 35 .../build/px4_sitl_raptor_sih/bin/px4 .
pxh> sleep 5
pxh> param set MC_RAPTOR_ENABLE 1
pxh> param set MC_RAPTOR_OFFB 0
pxh> mc_raptor start
pxh> sleep 4
pxh> listener arming_check_reply 8
pxh> sleep 1
pxh> listener arming_check_reply 8
pxh> shutdown
```

Output summary:

```text
INFO [mc_raptor] Raptor mode registration successful, arming_check_id: 0, mode_id: 23
INFO [mc_raptor] Raptor mode configuration sent

First listener:
  request_id: 13
  registration_id: 0
  health_component_index: 0
  health_component_is_present: True
  health_component_warning: True
  health_component_error: True
  can_arm_and_run: True
  num_events: 0
  mode_req_local_position_relaxed: True
  mode_req_global_position_relaxed: False
  events[0..4]: nonzero garbage-looking ids/timestamps/arguments despite num_events=0

Second listener:
  request_id: 16
  same nonzero health_component_* and local_position_relaxed True
  events[3..4] differed from the first listener
```

T5 verdict: `GARBAGE` for RAPTOR. mcnn runtime is blocked by binary/host ABI mismatch, but static code has the same uninitialized local struct pattern.

Issue draft:

```text
PX4 internal external-mode modules can publish arming_check_reply with uninitialized fields. In PX4-Autopilot 3042f906, mc_raptor::updateArmingCheckReply() and MulticopterNeuralNetworkControl::ReplyToArmingCheck() declare arming_check_reply_s without value-initialization and do not assign mode_req_local_position_relaxed / mode_req_global_position_relaxed or the health_component_* booleans. Minimal reproduction: run px4_sitl_raptor_sih, set MC_RAPTOR_ENABLE=1, start mc_raptor, then run `listener arming_check_reply`; observed output includes mode_req_local_position_relaxed=True and nonzero health_component booleans even though the module never sets them. Commander consumes the relaxed-position fields in ExternalChecks::checkAndReport(), so these stack values can change mode requirements. The fix is to value-initialize the reply (`arming_check_reply_s reply{}`) and/or explicitly assign all consumed fields.
```

## 6. T6 — 时序上界

Pristine/clean constants:

```text
externalChecks.hpp:69 REQUEST_TIMEOUT = 50_ms
externalChecks.hpp:70 UPDATE_INTERVAL = 300_ms
externalChecks.hpp:72 NUM_NO_REPLY_UNTIL_UNRESPONSIVE = 3
```

Timeline evidence:

```text
ModeManagement.cpp:370-372 calls _external_checks.update().
externalChecks.cpp:231-255 receives arming_check_reply and caches current-request replies.
externalChecks.cpp:257-287 handles timeout after REQUEST_TIMEOUT.
externalChecks.cpp:290-309 starts a new arming_check_request every UPDATE_INTERVAL.
Commander.cpp:2039 calls modeManagementUpdate(); Commander.cpp:2043 handles mode/failsafe; Commander.cpp:2045-2051 runs health and arming checks at 10 Hz or on status/failsafe changes.
UserModeIntention.cpp:52-58 reads _health_and_arming_checks.canRun(user_intended_nav_state) during mode change.
externalChecks.cpp:115-130 and 162-206 merges the cached reply into failsafe flags during health checks.
```

Worst-case freshness:

- If the component keeps replying, `canRun()` can read a health-check result from just before the current commander loop. That result can be up to one 300 ms external-check period plus one 100 ms health-check period old, so about `400 ms`.
- If an established component stops replying after a last good reply, the code flags unresponsive when `++num_no_response > NUM_NO_REPLY_UNTIL_UNRESPONSIVE` (`externalChecks.cpp:266-269`), i.e. on the fourth missed timeout when max is 3. With 300 ms periods, 50 ms timeout, and up to 100 ms health-check delay, stale positive `can_run` can persist for about `4*300 + 50 + 100 = 1350 ms`.

Sync recompute path: `rg` found no mode-switch path that forces a synchronous arming-check request/reply/health recompute before `UserModeIntention::change()` reads `canRun()`. The regular async path is the only path found.

## 7. T7 — 内部状态表

MC attitude control:

```text
AttitudeControl.hpp:54-65 defines proportional gain API.
AttitudeControl.hpp:103-109 members are _proportional_gain, _rate_limit, _yaw_w, _attitude_setpoint_q, _yawspeed_setpoint.
AttitudeControl.cpp:55-113 update() computes quaternion attitude error, proportional rate setpoint, yaw feed-forward, and rate limits.
```

No attitude integral exists. Round 1’s “missing attitude I reset” is not a finding.

Persistent continuous internal states, EKF2 excluded:

| Module/state | Type | Reset/update condition |
|---|---|---|
| `PositionControl::_vel_int` | velocity PID integral | `PositionControl.hpp:164-165` reset APIs; `MulticopterPositionControl.cpp:521-522` reset before takeoff/ramp/not flying; `MulticopterPositionControl.cpp:565-569` reset XY when horizontal position/velocity not controlled; `MulticopterPositionControl.cpp:617-622` reset when position control disabled. |
| `RateControl::_rate_int` | rate PID integral | `rate_control.hpp:103-115` reset APIs; `MulticopterRateControl.cpp:188-194` resets when disarmed or not rotary-wing; `rate_control.cpp:80-83` updates only if not landed. |
| `TakeoffHandling::_takeoff_state`, `_takeoff_ramp_progress`, `_spoolup_time_hysteresis` | takeoff state/ramp, not an integrator | `Takeoff.hpp:91-100`; `Takeoff.cpp:48-110` transitions and resets to disarmed when not armed; `MulticopterPositionControl.cpp:617-622` updates takeoff state even when position control disabled. |
| `MulticopterAttitudeControl::_yaw_setpoint_stabilized`, `_stick_yaw`, `_last_attitude_setpoint`, `_attitude_control._attitude_setpoint_q` | setpoint/memory, not integrators | `mc_att_control.hpp:101-140`; `mc_att_control_main.cpp:145-155`, `300-309`, `313-342`, `370-374` reset/adapt on manual mode changes and heading reset. |

I did not find any other MC position/rate/attitude continuous integral state in `src/modules/mc_pos_control`, `src/modules/mc_rate_control`, `src/modules/mc_att_control`, or `src/lib/rate_control` via `rg -n "Vector3f _.*int|resetIntegral|_yaw_setpoint_stabilized|TakeoffHandling"`.

## 8. T8 — 小项

1. `mode_req_wind_and_flight_time_compliance`: not a field in `msg/versioned/ArmingCheckReply.msg:30-41`. It is present in `msg/FailsafeFlags.msg:19`. External modes cannot declare this requirement through `ArmingCheckReply`; this is an interface asymmetry.
2. `mode_req_offboard_signal`: not a field in `ArmingCheckReply.msg:30-41`. It is present in `FailsafeFlags.msg:17`. Same asymmetry.
3. `NAVIGATION_STATE_EXTERNAL1 = 23`: `VehicleStatus.msg:55-62` defines external states 23..30. `ModeManagement.cpp:95-178` first tries a matching mode-name hash in `COM_MODE%d_HASH`, otherwise first unused/free slot. If `mc_raptor` and `mc_nn_control` register simultaneously with no prior hashes, the first registration processed gets `23`, the second gets `24`; if a matching hash exists, hash reuse can override simple registration order.
4. `mc_nn_control` termination flag: `mc_nn_control.cpp:193` sets `flag_control_termination_enabled=true`; `VehicleControlMode.msg:19` says this flag means flight termination is enabled. In the observed stale safe-default path, commander zeroes the struct (`Commander.cpp:2760`), safe defaults set only selected control flags (`ModeManagement.hpp:90-100`), and ULOG shows `flag_control_termination_enabled [0]`. If a fresh config were accepted, this flag would become true.

## 9. 我不确定的地方

- mcnn T5 runtime is not observed because the existing `px4_sitl_mcnn_sih` binary requires GLIBC 2.38 / GLIBCXX 3.4.32 while the host has GLIBC 2.35, and Docker was inaccessible. Static code strongly indicates the same defect, but runtime classification for mcnn alone remains `INCONCLUSIVE`.
- `register_ext_component_request` / `_reply` are not available as decoded pyulog data in selected logs. Nav-23 ownership is inferred from module startup scripts and presence/absence of `neural_control` / `raptor_status`, not directly from a logged registration row.
- ULOG does not identify the writer of each `actuator_motors` sample. The `RACE` verdict is code-supported and flag-supported, but individual motor samples cannot be attributed to learned module vs allocator from the log fields.
- The internal-state table intentionally excludes EKF2 per task instruction and focuses on MC controller modules. I did not claim an exhaustive inventory of all commander/failsafe/navigation state machines.

## 10. 与项目笔记（v8 / EXPERIMENT_INDEX / Round 1）冲突之处

- If v8 states that mcnn and RAPTOR boards are isolated at compile time, that wording conflicts with T2. `mcnn_sih.px4board` compiles `MC_RAPTOR`. The correct statement is runtime isolation by startup scripts and ULOG identity topics.
- Round 1’s safe-default/source-id interpretation is supported, not contradicted: T1 proves the stale-guard is upstream/pristine and T3 extends the observation from first sample to entire nav-23 intervals.
- Round 1’s “rate_ctrl_status continues” observation is supported, but incomplete: T4 shows both torque/thrust setpoints and allocator-enabled `actuator_motors` publication remain active.
- Round 1’s attitude-integrator-reset language conflicts with T7 and should be removed or rewritten as “mc_att_control has no attitude integral state.”

## 11. Verification / worktree status

Before T5 SITL, `git -C external/PX4-Autopilot status --short` matched the T1.1 listing. SITL was run from `/tmp/px4_audit_t5...` temp roots, not from the PX4 worktree.

After the T5 run and after writing this report, `git -C external/PX4-Autopilot status --short` still returned the same tracked/untracked list as T1.1: ROMFS CMake, simulator/submodule pointers, EKF2/M2B shim files, `mc_raptor` local changes, sensor/DDS changes, and the same four untracked PX4 files (`10046_sihsim_x500_v2`, `mcnn_sih.px4board`, `raptor_sih.px4board`, `raptor_unclipped_sih.px4board`). No new PX4 worktree changes were introduced by the audit.
