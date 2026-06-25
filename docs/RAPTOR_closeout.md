# RAPTOR closeout

Date: 2026-06-25

Scope: lightweight closeout only. No M3, no `mc_nn_control`, no large campaign.

## Artifact index

- P0/C NaN/Inf delivery and module input handling:
  `docs/raptor_closeout_p0_nonfinite_active2_20260625`
- A Gazebo plant asymmetry:
  `docs/raptor_closeout_gz_asym_20260625`
- B adversarial activation transient:
  `docs/raptor_closeout_activation_20260625`,
  `docs/raptor_closeout_activation_extreme_20260625`,
  `docs/raptor_closeout_activation_extreme2_20260625`
- C finite-sensor reachability spot check:
  `docs/raptor_closeout_reachable_finite_sensor_20260625`

## P0: NaN/Inf shim fix

D2's silent failure had two concrete causes in the current one-EKF SIH path:

- `vehicle_local_position` and `vehicle_attitude` are published directly from
  `EKF2.cpp`; the old velocity/attitude shim only patched `EKF2Selector.cpp`, so
  profile 4/5 never reached the logged shared state in this configuration.
- `M2B_START/M2B_END` are PX4 boot-time seconds. The old 24.0-24.5 s default was
  not guaranteed to overlap the RAPTOR active window. The closeout run used
  80.0-80.5 s and records that timebase in theta metadata.

Fixes made:

- `patches/px4/m2b_state_shim.patch` now injects NaN/Inf in the direct
  `EKF2.cpp` publish path for velocity and attitude, while retaining the existing
  selector and gyro paths.
- `scripts/m2_5_estimator_fairness.py` now has fail-loud state-shim delivery
  checks for profile 4/5. Missing shared-topic pollution or missing active-window
  `raptor_input` touch marks the eval invalid instead of silently recording null.
- `scripts/m2b_state_profiles.py` and `scripts/m2b_nan_probe.py` propagate that
  fail-loud result and use the corrected default active window.

## C: NaN/Inf input handling

Run: `docs/raptor_closeout_p0_nonfinite_active2_20260625`

All six paired evals delivered NaN/Inf into the target shared topic and into
`raptor_input`, then RAPTOR produced no NaN motor outputs.

| channel/profile | shared topic nonfinite C/R | `raptor_input` nonfinite | active motor NaN | quadrant |
|---|---:|---:|---:|---|
| velocity/nan | 189/189 | 333 | 0 | boring_both_safe |
| velocity/inf | 189/189 | 351 | 0 | boring_both_safe |
| angular_velocity/nan | 348/354 | 72 | 0 | boring_both_safe |
| angular_velocity/inf | 357/354 | 33 | 0 | boring_both_safe |
| attitude/nan | 504/504 | 76 | 0 | boring_both_safe |
| attitude/inf | 504/504 | 20 | 0 | boring_both_safe |

Judgment: no RAPTOR input-sanitize defect was reproduced. This is now a valid
null for the synthetic module-level NaN/Inf probe, not a shim miss.

Reachability spot check: `config/m2_5_estimator_harsh_300ms_sine8hz.json` was run
as one finite GPS/EKF delay/noise/gate/tau pair in
`docs/raptor_closeout_reachable_finite_sensor_20260625`. Both controllers were
safe, and nonfinite counts were zero in `vehicle_local_position`,
`vehicle_attitude`, `vehicle_angular_velocity`, and `raptor_input`. This does not
prove no finite sensor path can ever reach NaN/Inf; it says this realistic harsh
finite estimator path did not.

## A: Gazebo plant asymmetry

Run: `docs/raptor_closeout_gz_asym_20260625`

Method: modified the actual Gazebo `x500` SDF, then flew classical and RAPTOR on
the same modified plant. The runner restores the model after each case and stores
model evidence under each eval directory.

| case | quadrant | primary bug | tracking max C/R m | roll max C/R deg | rate max C/R rad/s |
|---|---|---:|---:|---:|---:|
| motor0_080 | boring_both_safe | false | 1.39/1.63 | 9.22/9.21 | 0.372/0.361 |
| motor0_065 | boring_both_safe | false | 1.62/1.79 | 12.2/12.8 | 0.579/0.646 |
| motor0_050 | too_hard_not_bug | false | 4.60/4.65 | 79.7/59.4 | 30.4/16.1 |
| com_x_002 | boring_both_safe | false | 1.62/1.55 | 12.0/11.7 | 0.673/0.579 |
| com_x_004 | boring_both_safe | false | 1.59/1.65 | 12.1/11.2 | 0.651/2.09 |
| com_x_006 | boring_both_safe | false | 1.70/1.60 | 13.3/11.3 | 0.532/0.568 |

Judgment: no clean plant-asymmetry primary bug. RAPTOR tolerated single-motor
20% and 35% thrust loss and 2/4/6 cm x-COM offset on this hover plus gentle sine
task. At 50% single-motor loss both controllers failed, so that point is a
control-authority/too-hard boundary, not RAPTOR-specific.

## B: Activation transient

Runs:

- Main sweep: `docs/raptor_closeout_activation_20260625`
- Strong finite setpoint: `docs/raptor_closeout_activation_extreme_20260625`
- Strongest finite setpoint: `docs/raptor_closeout_activation_extreme2_20260625`

Method: `scripts/m1_offboard_task.py` now supports an optional two-stage task.
For RAPTOR cases, PX4 first enters classical Offboard at `approach_start_s`, flies
the finite aggressive approach, then switches to RAPTOR at `controller_switch_s`.
Classical baseline flies the same approach and continues in Offboard. The ULOG
analysis measures actual roll/pitch and angular-rate in the 0.5 s before switch.

The original M1 compare still flags aggressive cases as `too_hard_not_bug`
because tracking RMS/max exceed the normal envelope. For this specific activation
question, the closeout also records `activation_flight_quadrant`, which ignores
pure tracking lag and treats ground contact, failsafe, disarm, attitude/rate
divergence, motor NaN, and motor saturation as flight-unsafe.

| case | pre-switch roll C/R deg | pre-switch rate C/R rad/s | flight quadrant | activation bug |
|---|---:|---:|---|---:|
| hover_activation | 1.76/2.33 | 0.309/0.202 | boring_both_flight_safe | false |
| circle_30deg | 15.7/18.1 | 0.619/0.608 | boring_both_flight_safe | false |
| circle_45deg | 26.3/25.2 | 1.13/1.05 | boring_both_flight_safe | false |
| circle_45deg_wind | 29.7/19.3 | 1.03/1.18 | boring_both_flight_safe | false |
| circle_60deg | 37.6/34.9 | 1.70/1.71 | boring_both_flight_safe | false |
| circle_75deg | 43.0/42.8 | 2.24/2.36 | boring_both_flight_safe | false |

Judgment: no RAPTOR-specific activation-window bug was reproduced. The strongest
finite setpoint produced an actual switch near 43 deg and 2.3 rad/s, with both
controllers remaining flight-safe. The default position/offboard chain did not
produce a clean 60 deg switch without changing controller limits, so this result
is a strong but not arbitrary-attitude activation probe.

## Overall picture

This closeout found no confirmed `primary_bug`.

The remaining picture is:

- Shared-state NaN/Inf handling: after fixing delivery, RAPTOR consumed delivered
  NaN/Inf in velocity, angular velocity, and attitude inputs without producing
  NaN RPM. The prior D2 null is replaced by valid evidence.
- Plant asymmetry: Gazebo physical x500 tests did not expose a RAPTOR-only
  failure for moderate single-motor degradation or COM offset. A 50% single-motor
  loss is beyond the tested task's control authority for both controllers.
- Activation transient: RAPTOR did not show a unique hidden-state reset/adaptation
  failure up to an actual ~43 deg, ~2.3 rad/s switch condition. Tracking lag exists
  in aggressive approach cases for both controllers, but not a RAPTOR-only loss.
- Prior D1/D2/D3 diagnostics still stand: the evaluated artifact is the 22-D
  RAPTOR path, the D3 continuous-degradation statistic is not supported, and the
  old Inf timeouts are best treated as harness/task timeouts plus the now-fixed
  delivery problem.

Remaining explicit gaps are narrow and scoped: this was not a large campaign, did
not test M3, did not introduce `mc_nn_control`, did not alter controller limits to
force arbitrary 60 deg activation, and did not prove that every finite real sensor
fault path is incapable of producing EKF NaN/Inf.
