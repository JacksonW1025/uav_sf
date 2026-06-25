# M2b-1 diagnostics

本轮只做 D1/D2/D3 三项诊断；没有跑 120-eval campaign，没有做 M2b-2/M3，也没有引入
`mc_nn_control`。

## Evidence index

- D1 source/policy evidence:
  `docs/m2b_1_diag_d1/source_policy_evidence.txt`
- D1 actual `raptor_input` dump:
  `docs/m2b_1_diag_d1/raptor_input_sample_vdelay000.json`
- D1 paper/docs cross-check notes:
  `docs/m2b_1_diag_d1/paper_docs_evidence.txt`
- D2 fresh rerun logs/ULOG/nonfinite scan:
  `docs/m2b_1_diag_d2_inf_20260624/`
- D2 old timeout recheck:
  `docs/m2b_1_diag_d2_inf_20260624/old_probe_recheck.md`
- D3 low-noise ratio run:
  `docs/m2b_1_diag_d3_ratio_20260624/`

## D1 - What model is being tested

做法:

- Read `external/PX4-Autopilot/src/modules/mc_raptor/mc_raptor.hpp` and
  `mc_raptor.cpp`.
- Read RLtools L2F observation flattening code under
  `external/PX4-Autopilot/src/modules/mc_raptor/rl_tools/inference/applications/l2f/`.
- Inspected `src/modules/mc_raptor/blob/policy.tar` and generated policy header metadata.
- Dumped one real `raptor_input` sample from an existing RAPTOR ULOG and expanded the
  logged quaternion to the actual 22-D policy vector.
- Cross-checked against PX4 RAPTOR docs, RLtools RAPTOR README, and the RAPTOR paper /
  supplementary notes.

Observed implementation:

- Subscribed shared-state inputs are `vehicle_local_position`, `vehicle_attitude`,
  `vehicle_angular_velocity`, and `trajectory_setpoint`. There is no
  `vehicle_acceleration` or `sensor_accel` subscription in this PX4 module.
- Logged `raptor_input` carries 17 fields: position[3], orientation quaternion[4],
  linear_velocity[3], angular_velocity[3], previous_action[4]. The network input is not
  17-D: RLtools expands the quaternion to a row-major 3x3 rotation matrix, so the policy
  sees 22 dimensions.
- Effective 22-D policy vector:
  1. position error in target-yaw frame, 3 dims, clipped to +/-0.5 m
  2. orientation as flattened 3x3 rotation matrix, 9 dims
  3. linear velocity error in target-yaw frame, 3 dims, clipped to +/-1.0 m/s
  4. angular velocity in body/FLU sign convention, 3 dims, no explicit clipping
  5. previous action history, 4 dims, one-step history
- Coordinate handling: PX4 NED/FRD values are sign-converted into the policy convention;
  position and velocity error are rotated into target yaw frame.
- Action output is 4-D. Raw policy action is kept as `previous_action` in the policy
  scale, then mapped by `(action + 1) / 2` into `actuator_motors.control[0..3]`. The PX4
  module applies the Crazyflie motor remap and sets unused actuator slots to `NAN`.
- Policy execution is stateful: the actor is `Dense(22->16, ReLU) -> GRU(hidden=16) ->
  Dense(16->4)`. The inference executor recurrent state is reset on mode activation.
- Compile/runtime dimensions match this: `ACTION_HISTORY_LENGTH=1`, `OUTPUT_DIM=4`,
  native control interval 10 ms, intermediate interval 2.5 ms, and runtime
  `force_sync_native = IMU_GYRO_RATEMAX / 100 = 4` for the observed 400 Hz gyro rate.
- `policy.tar` contains input shape `500 x 2 x 22`, output shape `500 x 2 x 4`,
  checkpoint name `logs/2025-04-19_16-16-17`, and 2084 parameters.

Actual ULOG alignment:

- Sample ULOG:
  `docs/m2b_velocity_delay_verify_4x_20260624/evals/m2b_velocity_delay_verify_4x_20260624_vdelay_000ms/m1_m2b_velocity_delay_verify_4x_20260624_vdelay_000ms_raptor.ulg`
- Dump:
  `docs/m2b_1_diag_d1/raptor_input_sample_vdelay000.json`
- One active sample at elapsed 60.04 s was finite and expanded to the expected 22-D
  vector. Example values: position all zero, linear velocity
  `[0.1563, 0.0352, 0.0011]`, angular velocity `[0.1497, 0.0052, -0.0004]`, and
  previous action `[0.2715, -0.0245, -0.0668, 0.1567]`.

Paper/docs comparison:

- PX4 docs describe RAPTOR as taking position, orientation, linear velocity, and angular
  velocity and outputting motor commands; they also list the policy as 2084 parameters.
- RLtools RAPTOR README describes the observation as position, flattened row-major
  rotation matrix, linear velocity, angular velocity, and previous action, with
  normalized motor actions.
- The paper/supplementary notes include an accelerometer/IIR discussion for linear
  velocity delay mitigation on non-EKF platforms. That path is not present in this PX4
  `mc_raptor` artifact.

判定:

- We are testing the PX4/RLtools RAPTOR policy artifact, not an unrelated or obviously
  simplified local controller. The policy identity, 22-D observation shape, 4-D action
  shape, GRU structure, checkpoint name, and 2084 parameter count line up with the
  public RAPTOR/PX4 descriptions.
- The absence of acceleration input is not itself a mismatch with the main published
  observation. However, the supplementary accelerometer/IIR velocity-delay mitigation
  path is absent here, so the exact paper-side velocity-delay failure/mitigation story
  should not be assumed to transfer one-to-one to this PX4/SIH artifact.
- Attack selection should continue to be based on the actual 22-D observation and 4-D
  motor action path above, not on an assumed accel-observation/S2 path.

## D2 - Root-cause velocity/attitude Inf timeouts

做法:

- Fresh rerun with one controller per run for `velocity/inf` and `attitude/inf`, both
  `classical` and `raptor`, under `docs/m2b_1_diag_d2_inf_20260624/`.
- Captured PX4 console, task log, topics log, agent log, ULOG, params, task/PX4 return
  codes, and nonfinite field scans.
- Rechecked the prior timeout logs under
  `docs/m2b_inf_probe_4x_20260624/evals/` and summarized the recheck in
  `docs/m2b_1_diag_d2_inf_20260624/old_probe_recheck.md`.

Fresh rerun evidence:

- All four fresh runs completed: `task_returncode=0`, `px4_returncode=0`,
  `timeout_observed=false`.
- Params were active in ULOGs: `M2B_EN=1`, with `M2B_V_PROF=5` for velocity Inf and
  `M2B_A_PROF=5` for attitude Inf.
- But `nonfinite_summary.json` shows no `Inf`/`NaN` reached the intended logged/shared
  fields:
  - velocity runs: `vehicle_local_position.vx/vy/vz` all finite, and
    `raptor_input.linear_velocity[0..2]` all finite.
  - attitude runs: `vehicle_attitude.q[0..3]` all finite, and
    `raptor_input.orientation[0..3]` all finite.

Prior timeout recheck:

- Prior `velocity_inf` and `attitude_inf` failed in `m1_diff_runner.py` as
  `task node timed out for classical` after `m1_offboard_task.py` waited 160 s.
- The task logs reached `trajectory_start` but not `mission_end`.
- The PX4 console logs do not show a crash or lockstep stall. In both prior timeout
  cases, PX4 later executed:
  `listener vehicle_status 1`, `listener vehicle_local_position 1`,
  `listener vehicle_angular_velocity 1`, `logger status`, and `shutdown`.
- The listener samples were fresh around PX4 timestamp 139-140 s. `vehicle_status`
  still published, `vehicle_local_position` and `vehicle_angular_velocity` still
  published, logger reported no dropouts, and PX4 printed `Exiting NOW.`

判定:

- The two original `velocity_inf` / `attitude_inf` timeouts should be classified as
  harness/task timeout, not PX4 process crash, EKF crash, or lockstep stall.
- The fresh rerun does not prove RAPTOR handles velocity/attitude Inf, because Inf did
  not reach `vehicle_local_position`, `vehicle_attitude`, or `raptor_input`.
- The actionable bug here is upstream of the intended Inf robustness probe: the
  velocity/attitude Inf shim evidence is not valid yet. Until the shim can prove
  nonfinite delivery to the shared topics, these two cases should not be counted as
  confirmed RAPTOR/PX4 Inf defects.

## D3 - Low-noise ratio degradation

做法:

- Added ratio-based D3 script:
  `scripts/m2b_1_ratio_diagnostics.py`
- Ran fixed low-noise diagnostics only; no campaign:
  4 scenarios x 5 seeds = 20 `m1_diff_runner.py` paired evals.
- Regime:
  nominal TWR `1.743`, sim speed `1x`, hover/steady window from 28 s to 52 s,
  sine amplitude `0.0`, seeds `20261201..20261205`.
- Scenarios:
  `baseline`, `velocity_noise_y0308`, `gyro_bias_x0153`, `velocity_delay_030ms`.
- Ratio metric:
  for each controller and metric, `perturbed metric / that controller's own multi-seed
  baseline mean`.

Baseline noise floor:

- `tracking_error_rms_m` baseline:
  - classical mean `0.4853`, stdev `0.1609`, range `0.4242`
  - RAPTOR mean `0.4238`, stdev `0.1155`, range `0.2495`
- Baseline ratio spread is still large:
  - classical RMS ratio stdev `0.3316`
  - RAPTOR RMS ratio stdev `0.2725`

Primary `tracking_error_rms_m` results:

| scenario | fairness | classical median ratio | RAPTOR median ratio | RAPTOR - classical |
| --- | --- | ---: | ---: | ---: |
| `velocity_noise_y0308` | true | 0.778 | 1.114 | 0.336 |
| `gyro_bias_x0153` | true | 1.102 | 1.187 | 0.085 |
| `velocity_delay_030ms` | true | 0.965 | 1.236 | 0.272 |

Metric scan notes:

- `tracking_error_max_m` follows the same weak pattern: RAPTOR median ratio is about
  `1.18-1.22` for velocity noise/delay, not a large multiplier.
- `final_error_m` shows larger deltas for some velocity cases, but final error is a
  single terminal sample with high baseline variance; it is not stable enough to carry
  the continuous-degradation claim by itself.
- `motor_saturation_ratio` is not useful for ratio judgment here because baseline values
  are near zero / sparse.
- All perturbation scenarios passed shared-state fairness checks in the D3 run.

判定:

- No tested point satisfies the desired pattern of `classical ratio ~= 1` while
  `RAPTOR ratio >> 1` with a stable distribution above the baseline floor.
- The best-looking primary point is `velocity_delay_030ms`, where RAPTOR RMS median is
  `1.236x` and classical RMS median is `0.965x`. That is a weak, small effect, not a
  robust differential degradation result.
- `velocity_noise_y0308` has a larger median delta, but it is mostly because classical
  improves below baseline while RAPTOR stays near/slightly above baseline. RAPTOR's
  distribution is still inside the baseline-scale spread.
- Current "continuous degradation" evidence should be treated as noise / weak trend, not
  as an FSE result.

## Recommendation

倾向: do not spend the next large search budget on RAPTOR in the current M2b search
space. Promote `mc_nn_control` to the next primary target, and keep RAPTOR as a
robustness/control comparison unless a narrower RAPTOR follow-up is explicitly chosen.

Reasons:

- D1 says this is the real PX4/RLtools RAPTOR artifact, so the negative result is not
  explained by accidentally testing a wrong tiny placeholder model.
- D1 also says the exact supplementary accel/IIR velocity-delay story is not the path
  implemented here, so paper-specific failure expectations need to be re-derived for
  this artifact.
- D2 did not produce a true velocity/attitude Inf crash; the old timeouts are harness
  timeouts, and the fresh Inf rerun did not deliver Inf into the target topics.
- D3 does not support a statistically robust RAPTOR-specific continuous degradation
  line under the low-noise ratio metric.

This is not a robustness claim for RAPTOR. It only says the current M2b RAPTOR evidence
does not justify a larger RAPTOR campaign before switching attention.

## External references checked

- RAPTOR paper / supplementary HTML: https://arxiv.org/html/2509.11481v2
- RLtools RAPTOR README: https://github.com/rl-tools/raptor
- Local PX4 RAPTOR docs:
  `external/PX4-Autopilot/docs/en/neural_networks/raptor.md`
