# PX4 Actuator Writer Attribution (Round 3)

PX4 HEAD: `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`  
PX4 worktree clean?: `no` before and after this report; status baseline is listed in §8.  
Date: `2026-07-09`

Scope note: source paths below are relative to `external/PX4-Autopilot/`. This round used read-only PX4 source/log inspection and wrote only this new report. No instrumentation patch and no simulation rerun were performed.

## 0. 最终判定

- 归因结论： `CONTAMINATED`
- 一句话依据： all four inspected mcnn S3 anchors have allocator-tagged `actuator_motors` samples that align to downstream `actuator_outputs`; in the critical `nav_state==23` switch-to-first-loss window, allocator-tagged effective output frames are `9.4%` to `16.2%`.
- 对 v8 F1/F2 因果归因的影响： `受威胁`

The race is not merely nominal. The allocator samples reached the output path consumed by SIH. Existing v8 text must not claim a clean single-writer neural actuator stream for the mcnn S3 flips.

## 0.1 ⚠️ 如果 CONTAMINATED 或 INCONCLUSIVE

`CONTAMINATED`: v8 F1/F2 claims that phrase S3 as caused solely by the neural policy need to be rewritten. The defensible wording from these logs is weaker: S3 occurred during neural external mode while a classical allocator writer was also intermittently driving effective motor frames.

To recover the stronger causal claim, the missing experiment is a direct mcnn rerun of the same F1 anchors with `flag_control_allocation_enabled=false` actually accepted/effective, or with a writer tag in the output path, showing the same S3 timing without allocator-tagged effective frames. RAPTOR logs are a useful mechanism control, but they cannot rescue the mcnn v8 attribution by themselves.

## 1. T0 — mcnn 仿真环境结论

Commands:

```bash
ldd --version
cat /etc/os-release
file external/PX4-Autopilot/build/px4_sitl_mcnn_sih/bin/px4
ldd external/PX4-Autopilot/build/px4_sitl_mcnn_sih/bin/px4 || true
strings external/PX4-Autopilot/build/px4_sitl_mcnn_sih/bin/px4 | rg 'GLIBC_2\.[0-9]+' | sort -Vu | tail -20
rg -n 'PX4_DIR=|PX4 SITL .deb version|/workspace|noble' docs/mcnn_gate1_build.log docs/validity_automation_real_20260627/px4_mcnn_sih_build.log
cmake --build external/PX4-Autopilot/build/px4_sitl_mcnn_sih --target bin/px4 -- -n
docker info
```

Output summary:

- Host: Ubuntu `22.04.5 LTS`, GLIBC `2.35`.
- Existing mcnn binary: `ELF 64-bit LSB pie executable, ARM aarch64`; `ldd` fails with required `GLIBC_2.38` and `GLIBCXX_3.4.32`.
- Existing RAPTOR SIH binary on the same host only requires GLIBC up to `2.34`.
- Build logs show mcnn was built under `/workspace/external/PX4-Autopilot`, with `PX4 SITL .deb version: 1.18.0~alpha1-noble`; `docker/Dockerfile` defaults to Ubuntu `24.04`.
- `docker info` fails on this host with Docker socket permission denied.
- A dry-run build did not compile; it stopped because the existing mcnn CMake cache was created under `/workspace`, not `/mnt/nvme/uav_sf`.

Conclusion: the existing mcnn SITL binary cannot run on this host. A local host rebuild is technically plausible with the present toolchain (`g++ 11.4`, CMake `3.22.1`, Ninja `1.10.1`), but it requires regenerating/rebuilding the mcnn build tree or using the Ubuntu 24.04 container. I did not compile. mcnn instrumentation rerun status for this round: `需先解决环境`. RAPTOR rerun remains feasible, but was not needed after T1-T3 became conclusive.

## 2. T1 — 时间戳指纹分析（含 Δt 分布图/数字）

Parser command used for the table below:

```bash
python3 scripts/px4_actuator_attribution_audit.py
```

Parser semantics: first contiguous `vehicle_status.nav_state == 23` interval; `Δt = diff(actuator_motors.timestamp)`; `first_loss = first |vehicle_angular_velocity| > 8 rad/s or first vehicle_attitude tilt > 90 deg`; mcnn neural tag is `timestamp_sample > 1e12`, mcnn allocator tag is valid `timestamp_sample` close to actuator timestamp; RAPTOR tag is exact timestamp alignment to active `raptor_input` / `raptor_status`; downstream source is each `actuator_outputs` sample aligned to the preceding `actuator_motors` sample within 20 ms.

Output summary:

| log | nav23 dur s | first loss | loss dt s | actuator_motors Hz | Δt us min/p50/p95/p99/max | duplicate timestamp extras | 20 ms Δt count | actuator source | downstream actuator_outputs source |
|---|---:|---|---:|---:|---|---:|---:|---|---|
| mcnn S3 pair1 `s20262001` | 61.844 | tilt>90 | 0.604 | 233.28 | 0/4000/8000/8000/12000 | 39 | 0 | allocator `1617/14427=0.112`, neural `12810/14427=0.888` | allocator `1515/14251=0.106`, neural `12736/14251=0.894` |
| mcnn S3 pair2 `s20261901` | 62.448 | tilt>90 | 0.616 | 244.88 | 0/4000/4000/8000/8000 | 13 | 0 | allocator `2441/15292=0.160`, neural `12851/15292=0.840` | allocator `2305/14919=0.155`, neural `12614/14919=0.845` |
| mcnn S3 pair4 `s20261902` | 64.408 | tilt>90 | 0.500 | 233.56 | 0/4000/8000/8000/12000 | 32 | 0 | allocator `1791/15043=0.119`, neural `13252/15043=0.881` | allocator `1679/14886=0.113`, neural `13207/14886=0.887` |
| mcnn S3 pair5 `s20261903` | 64.380 | tilt>90 | 0.648 | 233.63 | 0/4000/8000/8000/8000 | 19 | 0 | allocator `1751/15041=0.116`, neural `13290/15041=0.884` | allocator `1670/14884=0.112`, neural `13214/14884=0.888` |
| mcnn safe validity e0000 | 46.448 | none | 46.448 | 234.71 | 0/4000/8000/8000/8000 | 14 | 0 | allocator `1258/10902=0.115`, neural `9644/10902=0.885` | allocator `1194/10761=0.111`, neural `9567/10761=0.889` |
| mcnn safe validity e0001 | 47.968 | none | 47.968 | 235.12 | 0/4000/8000/8000/8000 | 22 | 0 | allocator `1229/11278=0.109`, neural `10049/11278=0.891` | allocator `1172/11143=0.105`, neural `9971/11143=0.895` |
| mcnn safe baseline `s20261302` | 62.136 | none | 62.136 | 235.61 | 0/4000/8000/8000/8000 | 24 | 0 | allocator `1285/14640=0.088`, neural `13355/14640=0.912` | allocator `1213/14527=0.083`, neural `13314/14527=0.917` |
| RAPTOR pair4 `s20262302` | 85.176 | none | 85.176 | 239.55 | 0/4000/4000/8000/12000 | 5 | 0 | non-RAPTOR `3/20404`, RAPTOR `20401/20404` | non-RAPTOR `4/19765`, RAPTOR `19761/19765` |
| RAPTOR pair5 `s20262003` | 84.168 | none | 84.168 | 239.01 | 0/4000/4000/8000/12000 | 8 | 0 | non-RAPTOR `5/20117`, RAPTOR `20112/20117` | non-RAPTOR `5/19532`, RAPTOR `19527/19532` |

Critical windows, `t_switch` to first loss, downstream `actuator_outputs` only:

| log | critical output frames | allocator effective frames |
|---|---:|---:|
| mcnn S3 pair1 | 138 | `13/138 = 9.4%` |
| mcnn S3 pair2 | 148 | `24/148 = 16.2%` |
| mcnn S3 pair4 | 117 | `15/117 = 12.8%` |
| mcnn S3 pair5 | 147 | `21/147 = 14.3%` |

Interpretation:

- Pure Δt alone would be misleading. The stream is single-peaked around 4 ms and has no 20 ms interval component because allocator writes usually occur on the same 4 ms simulation clock grid as neural writes, not as a separate visible 20 ms gap.
- The logger is fast enough for this attribution: in the same windows, `actuator_motors` is `233-245 Hz`, `actuator_outputs` is `230-239 Hz`, `neural_control` is `226-239 Hz`, `vehicle_angular_velocity` is `234-246 Hz`, and `vehicle_torque_setpoint` is exactly `50.0 Hz`.
- The key evidence is the source tag plus downstream alignment, not the Δt histogram.

Selected ULOGs:

```text
runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/route_a_addendum3_diag_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_s20262001/mcnn_gate3_route_a_addendum3_diag_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_s20262001_mcnn.ulg
runs/route_a_anchor_regression/route_a_anchor_regression_20260629/evals/route_a_anchor_regression_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901/mcnn_gate3_route_a_anchor_regression_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901_mcnn.ulg
runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/route_a_addendum3_diag_20260629_rp36_44_rate1p55_2p15_w3_r4_f038_s20261902/mcnn_gate3_route_a_addendum3_diag_20260629_rp36_44_rate1p55_2p15_w3_r4_f038_s20261902_mcnn.ulg
runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/route_a_addendum3_diag_20260629_rp32_40_rate1p30_1p95_w0_r4_f038_s20261903/mcnn_gate3_route_a_addendum3_diag_20260629_rp32_40_rate1p30_1p95_w0_r4_f038_s20261903_mcnn.ulg
```

## 3. T2 — 来源判别字段

`msg/versioned/ActuatorMotors.msg` fields:

```text
uint64 timestamp
uint64 timestamp_sample
uint16 reversible_flags
float32[12] control
```

Source inspection commands:

```bash
rg -n 'timestamp_sample|PublishOutput|publish_actuator_controls|Publication<actuator_motors_s>|ORB_ID\\(actuator_motors\\)' \
  external/PX4-Autopilot/src/modules/mc_nn_control \
  external/PX4-Autopilot/src/modules/mc_raptor \
  external/PX4-Autopilot/src/modules/control_allocator
```

Findings:

- `mc_nn_control.cpp:377-397` publishes `actuator_motors` but never assigns `timestamp_sample`. In the inspected mcnn logs, its effective neural samples carry an impossible constant stack value such as `187650765556352`, which separates them from allocator samples.
- `control_allocator.cpp:386` copies `vehicle_torque_setpoint.timestamp_sample` to `_timestamp_sample`; `control_allocator.cpp:713-715` writes that into `actuator_motors.timestamp_sample`. In inspected mcnn logs, allocator-tagged samples have valid `timestamp_sample` close to/equal to the actuator timestamp.
- `mc_raptor.cpp:872-874` assigns `actuator_motors.timestamp_sample = _vehicle_angular_velocity.timestamp_sample`; RAPTOR attribution was therefore done by exact timestamp alignment to active `raptor_input` / `raptor_status`, not by a garbage timestamp.
- mcnn value cross-check: in the pair4 S3 log, `13040` actuator samples exactly match same-timestamp `neural_control.network_output[0..3]`; `1537` same-timestamp samples do not and carry allocator-style valid `timestamp_sample` and clipped `[0,1]` motor values.

Conclusion: `timestamp_sample` is not a deliberate source tag for mcnn, but the current uninitialized field makes the two writers distinguishable in existing logs. This is supported by exact neural-output matching and by downstream output alignment.

## 4. T3 — 下游 consume 链

Source commands:

```bash
rg -n 'ORB_ID\\(actuator_motors\\)|actuator_outputs_sim|_actuator_out_sub|FunctionMotors|publish\\(actuator_outputs\\)' \
  external/PX4-Autopilot/src/lib/mixer_module/functions/FunctionMotors.hpp \
  external/PX4-Autopilot/src/modules/simulation/pwm_out_sim \
  external/PX4-Autopilot/src/modules/simulation/simulator_sih
```

Complete effective chain:

1. `mc_nn_control` publishes `actuator_motors` through `uORB::Publication<actuator_motors_s> _actuator_motors_pub{ORB_ID(actuator_motors)}`. No instance argument is given, so this is instance 0.
2. `control_allocator` publishes the same `ORB_ID(actuator_motors)` instance 0.
3. `mc_raptor` also publishes the same `ORB_ID(actuator_motors)` instance 0 in RAPTOR runs.
4. `pwm_out_sim` uses `MixingOutput`; `FunctionMotors` constructs `_topic(&context.work_item, ORB_ID(actuator_motors))` and registers a callback. This consumes the merged instance-0 `actuator_motors` stream.
5. `PWMSim::updateOutputs()` publishes `actuator_outputs_sim` (`PWMSim.cpp:93-94`; pyulog exposes the logged output topic as `actuator_outputs` in these logs).
6. `Sih` subscribes to `ORB_ID(actuator_outputs_sim)` (`sih.hpp:144`) and `Sih::read_motors()` copies those outputs into the motor state `_u[i]` (`sih.cpp:329-347`), which then drives SIH force/torque integration.

There is no later control allocation layer after `actuator_motors` in this SIH path. The effective downstream question is whether allocator-tagged `actuator_motors` frames are followed by `actuator_outputs`; the T1 alignment shows they are.

## 5. T4 — instrumentation 重跑结果（若做）

Not done. T1-T3 were conclusive: allocator-tagged mcnn samples entered the downstream effective output stream in all four inspected S3 anchors and in safe mcnn controls. Adding instrumentation would refine counts, but it is not required to choose between `CLEAN`, `CONTAMINATED`, and `INCONCLUSIVE`.

## 6. T5 — 关分配器对照（若做）

Not done. The direct mcnn control-allocator-off comparison remains the most useful rescue experiment, but the existing binary/environment prevents an immediate mcnn rerun. Existing logs already prove contamination, so the round classification does not depend on this rerun.

## 7. 我不确定的地方

- I did not run the allocator-off mcnn counterfactual, so I cannot say whether S3 would still occur with identical timing under a clean neural-only actuator path.
- The mcnn source tag relies on an uninitialized `timestamp_sample` artifact, not a designed writer ID. It is strong in these logs because it is consistent, value-checked against `neural_control`, and aligned to downstream outputs, but it is still an artifact.
- `first_loss` here uses explicit thresholds (`|omega| > 8 rad/s` or tilt > 90 deg). That is enough for the requested early flip window, but it is not a full replacement for the paper's complete S3 oracle.
- pyulog names the downstream logged output topic as `actuator_outputs`, while the SIH source subscribes to `actuator_outputs_sim`; I relied on the source chain plus cadence/alignment to connect these.

## 8. 复现与还原说明（instrumentation 如何加、如何撤）

No instrumentation was added. Revert for this round is deleting this report and the read-only helper script `scripts/px4_actuator_attribution_audit.py` if desired.

PX4 tracked source/path audit:

```bash
git -C external/PX4-Autopilot rev-parse HEAD
git -C external/PX4-Autopilot diff -- src/modules/mc_nn_control src/modules/control_allocator src/lib/mixer_module src/modules/simulation/simulator_sih src/modules/simulation/pwm_out_sim msg/versioned/ActuatorMotors.msg | wc -l
git -C external/PX4-Autopilot status --short
```

Output summary:

```text
3042f906abaab7ab59ae838ad5a530a9ef3df9a6
0
```

The PX4 `status --short` before and after this report remained the same pre-existing dirty baseline:

```text
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
 M src/drivers/ins/sbgecom/sbgECom
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
