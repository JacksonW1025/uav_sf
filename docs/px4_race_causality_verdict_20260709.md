# Actuator Race Causality Verdict (Round 4)

PX4 HEAD: `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`  
Date: `2026-07-09`  
Worktree: root and `external/PX4-Autopilot` were already dirty; no tracked PX4 source was edited in this round.  
Docker: docker daemon accessible via `sg docker`; docker 权限已获得（不写口令）.

Evidence scripts/artifacts:

- `scripts/px4_race_causality_round4.py`
- `scripts/px4_race_r4_experiment.py`
- `docs/px4_race_causality_round4_analysis_20260709.json`
- `docs/px4_race_r4_gate_20260709/gate_results.json`

## 0. 最终判定

- P2 上游回归: **UPSTREAM_REGRESSION**.
- P1 RAPTOR 是否也有 race: **无法判定**. R3 的 RAPTOR 时间戳归因数字作废；当前 RAPTOR 动作没有单独记录，不能用 mcnn 的值匹配法完成归因。
- P1.3 分配器帧率异常: allocator nominal 由 50 Hz `vehicle_torque_setpoint` callback 驱动，但 `actuator_motors` queue depth 为 1，mcnn 约 234 Hz 直接写同一 topic，logger/下游只能看到存活帧；26-39 Hz 是观测到的 allocator 存活/生效帧率，不是 allocator 运行频率。
- P5 可比窗口: fixed 0.5 s 和 0.6 s 窗口均未显示翻/不翻组 allocator 占比显著差异；Mann-Whitney exact two-sided p=`0.1142857143`。限制: 无差异不等于 race 无关，仍可能与交接状态交互。
- P0 mcnn 环境: **已恢复**，r4 binary 已构建并 smoke 注册 `mc_nn_control mode_id=23`。
- P3-gate: **GATE_FAIL**. 重建环境不能稳定复现原 ULOG 的 S3 timing；pair4 三次中一次为 S0。
- **P3 最终裁决: 未运行**。按任务规则，GATE_FAIL 后停止，不能给出 `RACE_HARMLESS` / `RACE_CAUSAL` / `RACE_PROTECTIVE`。

这不是 race harmless 的证据。它只说明：当前重建 SUT/harness 不能支持有效反事实实验；v8 不能据此保留“race 无害、归因干净”的强因果措辞。

## 0.1 对 v8 的影响

| 项 | 影响 |
|---|---|
| F1 | 需改措辞。历史 ULOG 的 mcnn S3 仍存在，但本轮不能证明 rebuilt SUT deterministic reproduce，也不能证明 race harmless。建议措辞: “历史 ULOG 中 mcnn 在 S3 窗口内翻机；重建环境的 P3 gate 未通过，因此 allocator race 的反事实因果地位未能验证。” |
| F2 | 需改措辞。若 F2 使用“神经策略单独致因”叙述，必须降级为“与神经策略输出相关，但 allocator race 未被反事实排除”。 |
| F2a | 需改措辞/后续需重跑。RAPTOR race 归因未解，不能使用 R3 RAPTOR 时间戳数字作为对称性证据。 |
| RQ3 | 需改措辞。可以说 upstream stale-config regression 真实存在；不能说 RAPTOR 已证明同样 race 且无害。 |
| B1 | 历史 classical baseline ULOG 不受本轮代码改动影响；但任何 rebuilt counterfactual baseline 都需先过 determinism gate。 |
| B2 | 同 B1。不要把未运行的 `R4_ALLOC_ABL=1` safe arm 当作证据。 |
| B3 | 同 B1。 |
| S1 | 需改措辞。mcnn safe 历史日志仍 safe，但“关掉 allocator 后仍 safe”未测试；race protective 可能性未排除。 |
| S2 | 需改措辞。所有 safe-arm-B 语义必须标为未测。 |
| D1 | 需重写因果段。当前可写的是“发现真实 upstream regression + mcnn 下游污染 + gate fail 阻止反事实判定”，不是“race 已排除”。 |

## 0.2 非 HARMLESS 后果

本轮没有得到 `RACE_CAUSAL` 或 `RACE_PROTECTIVE`，但也没有得到 `RACE_HARMLESS`。直接后果:

- 不允许跑/引用 P3 arm B 结论。
- 需要先恢复可复现 SUT。至少要定位 pair4 rebuilt rerun 为什么一次 S0、两次 S3，并解释 pre-switch state drift。
- 若后续 gate pass 后再发现 `RACE_CAUSAL` / `RACE_PROTECTIVE`，需重跑 P3 矩阵；若全量 926 eval 串行，按原估计约 40 h。

## 1. P2

Commands:

```bash
cd external/PX4-Autopilot
git show 0eb14d64d5f90b50ae752ef6101faa69d7a8e1b2 --stat
git show 0eb14d64d5f90b50ae752ef6101faa69d7a8e1b2 -- src/modules/commander/ModeManagement.cpp
git show 0eb14d64^:src/modules/commander/ModeManagement.cpp | sed -n '534,570p'
git show 0eb14d64^:src/modules/commander/ModeManagement.hpp | grep -n "_last_served\|config_control_setpoint"
git log --oneline 0eb14d64^..HEAD -- src/modules/commander/ModeManagement.cpp
git log -1 --format='%H%n%an <%ae>%n%ad%n%B' 0eb14d64
git log --all --oneline --grep='config_control_setpoints' -i -- src/modules/commander/ModeManagement.cpp src/modules/commander/ModeManagement.hpp
git log --all --oneline -G'_last_served_change_us|config_control_setpoint\.timestamp|stale config_control_setpoints|setControlModeDefaults\(control_mode\)' -- src/modules/commander/ModeManagement.cpp src/modules/commander/ModeManagement.hpp
```

Before `0eb14d64`, external-mode cached config was accepted unconditionally:

```cpp
if (_modes.valid(nav_state)) {
	control_mode = _modes.mode(nav_state).config_control_setpoint;
	ret = true;
} else {
	Modes::Mode::setControlModeDefaults(control_mode);
}
```

The commit message says it fixes stale cached `config_control_setpoints` from earlier activations by rejecting cache entries older than activation and using safe defaults until fresh config arrives. It does not include a test in the touched files, and it does not discuss the “external mode publishes config once at registration” case.

Conclusion: before this commit, `mc_nn_control`'s `allocation=false` would be copied into `vehicle_control_mode` for nav_state 23. After this commit, the once-published registration-time config is stale at activation, so Commander falls back to safe defaults and leaves allocation enabled. Later `main` history did not contain a fix for `_last_served_change_us`; only branch `origin/external_modes_setpoint_types` has a related off-main change.

判定: **UPSTREAM_REGRESSION**.

## 2. P1

Commands:

```bash
rg -n "timestamp_sample.*vehicle_angular_velocity|vehicle_torque_setpoint.timestamp_sample|actuator_motors.timestamp_sample" external/PX4-Autopilot/src/modules
python3 scripts/px4_race_causality_round4.py
```

R3 RAPTOR 批评成立:

- `mc_raptor.cpp` publishes `actuator_motors.timestamp_sample = _vehicle_angular_velocity.timestamp_sample`.
- `MulticopterRateControl.cpp` sets `vehicle_torque_setpoint.timestamp_sample = _vehicle_angular_velocity.timestamp_sample`.
- `ControlAllocator.cpp` copies `_timestamp_sample = vehicle_torque_setpoint.timestamp_sample`.

So RAPTOR and allocator frames share the same timestamp lineage. **R3 的 RAPTOR 归因数字作废**.

RAPTOR value matching could not be completed because current action is not logged. `raptor_input.previous_action` is previous normalized action, not the current actuator command. The shifted previous-action proxy matched only:

| log | actuator proxy matches | downstream proxy matches |
|---|---:|---:|
| RAPTOR pair4 | `199/20404` | `7/19765` |
| RAPTOR pair5 | `173/20117` | `3/19532` |

This proves the proxy is incomplete; it does not prove absence of race.

mcnn self-check using the same script reproduced R3's value split. For pair4:

- actuator samples `15043`
- exact neural value matches `13040`
- simultaneous neural timestamp nonmatches with allocator signature `1537`
- all allocator residuals `1791`

Setpoint fingerprint cross-check: least-squares motor mix from `[torque xyz, thrust xyz, intercept]`, trained on alternating allocator-tagged frames, has much lower residual on allocator-tagged frames than neural-tagged frames:

| log | allocator test median RMSE | neural median RMSE |
|---|---:|---:|
| mcnn pair1 | `0.0314` | `0.5185` |
| mcnn pair4 | `0.1629` | `0.5355` |
| safe e0000 | `0.0329` | `0.4601` |

P1.3 frame-rate anomaly:

- `ControlAllocator::init()` registers update callback on `vehicle_torque_setpoint`; `Run()` publishes after the torque-driven update path.
- Generated `actuator_motors` ORB queue length is `1`.
- mcnn writes `actuator_motors` at about 234 Hz into the same topic.
- Therefore logger/downstream does not observe every allocator publish; observed allocator frames are queue-surviving/effective frames.
- Duplicate timestamp extras are same-timestamp collisions: one allocator-like valid `timestamp_sample` row and one neural-like row at the same `timestamp`.

## 3. P5

Command:

```bash
python3 scripts/px4_race_causality_round4.py
```

Downstream allocator fractions:

| window | flip fractions | safe fractions | U | exact two-sided p |
|---|---|---|---:|---:|
| fixed 0.5 s | `[0.0885, 0.1653, 0.1282, 0.1565]` | `[0.1148, 0.0603, 0.0690]` | `11.0` | `0.1142857143` |
| fixed 0.6 s | `[0.0949, 0.1667, 0.1357, 0.1481]` | `[0.1096, 0.0507, 0.0647]` | `11.0` | `0.1142857143` |
| full nav23 | `[0.1063, 0.1545, 0.1128, 0.1122]` | `[0.1110, 0.1052, 0.0835]` | `11.0` | `0.1142857143` |

Interpretation: allocator dose is not significantly higher in flip logs under these comparable windows. This is evidence against race being a simple sufficient cause, but it does not exclude interaction with handoff state.

## 4. P0

Commands/output summary:

```bash
sg docker -c 'docker info --format "ServerVersion={{.ServerVersion}} Driver={{.Driver}}"'
# ServerVersion=29.3.0 Driver=overlayfs
docker images
# uav_sf:phase1 4e590ec80407 ... 4.76GB
```

Build provenance:

- Original build logs: `docs/mcnn_gate1_build.log`, `docs/validity_automation_real_20260627/px4_mcnn_sih_build.log`.
- Original image/tag: `uav_sf:phase1`.
- Original command: `HEADLESS=1 make px4_sitl_mcnn_sih` under `/workspace/external/PX4-Autopilot`.
- PX4 SHA: `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`.
- Compiler in container: `gcc/g++ 13.3.0`.
- r4 build command:

```bash
cmake -S . -B build/px4_sitl_mcnn_sih_r4 -GNinja -DCONFIG=px4_sitl_mcnn_sih -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build/px4_sitl_mcnn_sih_r4 --target bin/px4 -- -j$(nproc)
```

r4 binary:

- md5: `4502483282e5d04e7af418c6dd2c26a0`
- Build ID: `aeb02187cf5e1d9896e1c68f0101e40dcde14997`

Model source hashes:

- `control_net.cpp`: `70f48109434addab550252b5a75965745f6161e09a60ac7c54a86a322885a47c`
- `control_net.hpp`: `43919e86c65c320a2c58d5d140ae552fc4bffcd0ed6bf7185b634e1f70ff4bc3`

Smoke: r4 binary started SIH, `mc_nn_control` registered successfully with `mode_id=23`.

Important caveat: an initial `make` attempt ignored the intended build suffix and rebuilt `external/PX4-Autopilot/build/px4_sitl_mcnn_sih/bin/px4`. Original campaign binary md5 observed before that was `8b00b8bea8ab8d1d3dc5e6cfc4d4de8a`; after rebuild it was `4d034c8171687be49537caee3a8522f0`. The isolated r4 build was used for gate runs, but the original campaign binary is no longer present in that default build tree.

## 5. P3-gate

Command:

```bash
sg docker -c './docker/run.sh bash -lc '"'"'source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && PX4_SIM_SPEED_FACTOR=1.25 python3 scripts/px4_race_r4_experiment.py --phase gate --build-dir external/PX4-Autopilot/build/px4_sitl_mcnn_sih_r4 --docs-dir docs/px4_race_r4_gate_20260709 --repetitions 3 --run-timeout 190'"'"''
```

Gate summary:

| case | original loss dt | rep1 | rep2 | rep3 | run-to-run span | result |
|---|---:|---:|---:|---:|---:|---|
| pair1 | `0.604 s` | `0.568 s` S3 | `0.772 s` S3 | `0.744 s` S3 | `204 ms` | fail timing |
| pair4 | `0.500 s` | `1.732 s` S3 | `0.236 s` S3 | `64.600 s` S0 | `64364 ms` | fail timing/outcome |

Allocator fractions stayed broadly close, so the gate failure is not “patch worked/failed”; this was arm A with no patch:

| case | original full downstream allocator | reruns |
|---|---:|---|
| pair1 | `10.63%` | `10.62%`, `11.46%`, `10.73%` |
| pair4 | `11.28%` | `9.76%`, `11.05%`, `10.55%` |

Pre-switch state drift was already visible at handoff. Example pair4 original switch state was roll/pitch/rate `35.35 deg / -38.69 deg / 1.998 rad/s`; reruns were `38.67/-35.72/2.020`, `36.00/-37.05/1.997`, and `37.25/-31.11/1.976`. The rebuilt environment did not reproduce the original pre-switch trajectory exactly, and one pair4 rerun did not flip.

判定: **GATE_FAIL**. Per task rule, stop here and do not run P3.

## 6. P3

Not run. No `R4_ALLOC_ABL` patch was created or applied because P3-gate failed.

## 7. 我不确定的地方

- The exact source of gate nondeterminism is not isolated. Candidates include rebuilt binary differences, DDS/offboard timing, isolated run-root/dataman differences, and SIH/PX4 scheduling phase.
- RAPTOR race remains unmeasured from existing ULOGs because the current RAPTOR action is not logged.
- The setpoint fingerprint is a strong cross-check for mcnn allocator-tagged frames, but it is a fitted linear proxy, not a full `ActuatorEffectiveness` replay.
- Because the original campaign binary was overwritten in the default build tree during P0 recovery, exact binary replay is no longer possible from local build artifacts.

## 8. 还原说明

No PX4 source patch was applied. No `R4_ALLOC_ABL` parameter exists in the current source. No `patches/px4/r4_alloc_race_ablation.patch` was created because the gate failed before P3.

To remove Round 4 generated artifacts:

```bash
rm -f docs/px4_race_causality_verdict_20260709.md
rm -f docs/px4_race_causality_round4_analysis_20260709.json
rm -rf docs/px4_race_r4_gate_20260709
rm -f scripts/px4_race_causality_round4.py scripts/px4_race_r4_experiment.py
rm -rf external/PX4-Autopilot/build/px4_sitl_mcnn_sih_r4
```

Do not remove or reset unrelated dirty files without separate review; both the repo root and PX4 subtree had pre-existing modifications.
