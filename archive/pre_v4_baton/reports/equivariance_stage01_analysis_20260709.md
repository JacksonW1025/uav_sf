# Equivariance Stage 0/1 Zero-Sim Analysis - 20260709

## Scope

Run command used for the analysis pass:

```bash
python scripts/equivariance_floor_analysis.py --output-json /tmp/equivariance_stage01_analysis.json
```

This pass only read existing artifacts:

- `runs/campaigns/equivariance_probe_20260708/equivariance_results.jsonl`
- `runs/campaigns/equivariance_probe_preflight_20260708/stage0_results.jsonl`
- `runs/campaigns/switch_severity_dense_sweep_20260630/sweep_results.jsonl`

No simulation was launched, no new ULOG was generated, and no new `runs/` campaign directory was created. The output JSON was written under `/tmp` and is not a retained run artifact.

## Stage 0 - mc_nn Input Tensor

Source: `external/PX4-Autopilot/src/modules/mc_nn_control/mc_nn_control.cpp:303-369`.

Key evidence, actual assignment order:

```cpp
_input_tensor->data.f[0] = trajectory_setpoint_local(0) - position_local(0);
_input_tensor->data.f[1] = trajectory_setpoint_local(1) - position_local(1);
_input_tensor->data.f[2] = trajectory_setpoint_local(2) - position_local(2);
_input_tensor->data.f[3] = _attitude_local_mat(0, 0);
_input_tensor->data.f[8] = _attitude_local_mat(1, 2);
_input_tensor->data.f[9] = linear_velocity_local(0);
_input_tensor->data.f[14] = angular_vel_local(2);
```

The code comment says `[pos_err(3), lin_vel(3), att(6), ang_vel(3)]` at line 305, but the actual tensor order is `pos_err(3), att(6), lin_vel(3), ang_vel(3)`.

| slots | value | frame / transform | yaw-equivariance implication |
|---:|---|---|---|
| 0-2 | `trajectory_setpoint_local - position_local` | both NED vectors premultiplied by fixed `frame_transf * frame_transf_2` at lines 338-346 | fixed local/world-like coordinates, not vehicle-yaw body-frame invariants |
| 3-8 | first two rows of `_attitude_local_mat` | `frame_transf * (frame_transf_2 * Dcm(attitude)) * frame_transf.transpose()` at lines 348-349 | contains attitude DCM entries derived from `vehicle_attitude`; absolute/world yaw is present |
| 9-11 | `linear_velocity_local` | NED velocity premultiplied by fixed `frame_transf * frame_transf_2` at lines 345-346 | fixed local/world-like velocity components |
| 12-14 | `angular_vel_local` | body angular velocity with `frame_transf` sign transform at lines 351-353 | angular rate is present |

Negative facts: no `previous_action` appears in the 15-D mc_nn tensor. The tensor does include angular velocity. Because it contains fixed-frame position/velocity and DCM attitude entries, mc_nn yaw equivariance is not structurally guaranteed; it can only be a learned property.

RAPTOR comparison source: `scripts/m2b_1_dump_raptor_input.py:59-85`. `label_vector()` constructs:

```python
values = position + quat_to_rotmat(orientation) + linear_velocity + angular_velocity + previous_action
```

That is `position(3) + rotation matrix(9) + linear velocity(3) + angular velocity(3) + previous_action(4) = 22`. RAPTOR also exposes world/frame attitude information, and additionally carries previous action. The mechanism-level claim is therefore limited to: both learned controllers have observation interfaces that can carry heading dependence, while the classical geometric controller is the symmetry baseline by construction.

## Stage 1 - Data And Method

The analysis script added in this pass is `scripts/equivariance_floor_analysis.py`; unit coverage is in `tests/test_equivariance_floor_analysis.py`.

Counts read:

| source | records |
|---|---:|
| probe total | 56 |
| classical floor | 24 |
| mc_nn probe | 32 |
| Stage 0 preflight | 4 |
| dense classical seed baseline | 9 |
| dense mc_nn seed baseline | 9 |

Theta consistency check passed. For `attitude_deg_42/45/48`, the probe `psi=0` theta files matched the dense-sweep base on `requested_rate_rad_s=1.15`, `switch_delay_s=0.09`, `wind_speed_m_s=0.0`, and `approach_phase_rad=0.0`. Therefore the dense attitude-axis `psi=0` records are legal to pool for the Fisher checks.

The plant envelope below reports yaw-invariant quaternion tilt in degrees under the existing `max_roll_pitch_deg` field name, matching the property-oracle physical tilt definition. Estimator yaw error is `vehicle_attitude` versus `vehicle_attitude_groundtruth`, with signed angle wrap before RMS/max.

## Classical Continuous Floor

Values are `psi 0 / 90 / 180 / 270`.

| theta | severity | yaw RMS deg | yaw range | max tilt deg | tilt range |
|---|---|---:|---:|---:|---:|
| `attitude_deg_42` | S0/S0/S0/S0 | 1.891 / 1.708 / 0.983 / 1.048 | 0.908 | 40.945 / 40.027 / 39.444 / 39.994 | 1.501 |
| `attitude_deg_45` | S0/S0/S1/S0 | 2.691 / 0.913 / 1.841 / 1.456 | 1.778 | 42.024 / 42.425 / 43.676 / 43.655 | 1.652 |
| `attitude_deg_48` | S0/S0/S0/S0 | 2.647 / 0.823 / 0.594 / 0.730 | 2.054 | 46.455 / 45.058 / 44.600 / 45.329 | 1.856 |
| `hard_attitude_deg_50` | S0/invalid/invalid/invalid | 0.817 / NA / NA / NA | 0.000 | 47.096 / 45.576 / 45.861 / 45.967 | 1.521 |
| `pair2` | S0/S0/S0/S0 | 2.468 / 0.896 / 1.382 / 0.922 | 1.572 | 61.722 / 61.060 / 59.901 / 59.559 | 2.164 |
| `pair5` | S0/S0/S0/S0 | 4.443 / 0.697 / 1.550 / 1.528 | 3.746 | 55.045 / 55.381 / 55.434 / 53.983 | 1.451 |

Dense seed-jitter baseline from the existing mc_nn dense sweep, classical side, `psi=0`:

| theta | yaw RMS range | max tilt range | max rate range |
|---|---:|---:|---:|
| `attitude_deg_42` | 1.810 | 1.601 | 0.085 |
| `attitude_deg_45` | 0.619 | 1.526 | 0.162 |
| `attitude_deg_48` | 1.135 | 1.685 | 0.253 |
| max | 1.810 | 1.685 | 0.253 |

Stage 0 preflight `pair2` same-seed/different-psi route anchor had yaw RMS range `0.792`, max tilt range `4.458`, and max rate range `0.852`; it is useful as a transformed-route sanity check, not a same-theta seed-jitter baseline.

Interpretation: achieved tilt ranges in the classical probe are near the dense attitude-axis seed-jitter scale (`max classical tilt range 2.164 deg`, dense max `1.685 deg`, ratio `1.28`). The yaw-estimator floor is not clean: `pair5` has yaw RMS range `3.746 deg`, which is `2.07x` the available dense attitude-axis yaw jitter baseline. This keeps Q3(b), magnetic/EKF heading anisotropy amplified by the knife edge, alive.

## Hard Cell And att45

`hard_attitude_deg_50`: the invalid cells are still clustered just below the trigger window. Invalid-only max tilt is `45.576 / 45.861 / 45.967 deg`, range `0.391 deg`; the valid `psi=0` cell triggers at `46.136 deg` and reaches max tilt `47.096 deg`. The invalid-cell spread is smaller than the available dense max-tilt jitter baseline (`1.685 deg`), so the hard cell is not decisive evidence of true plant anisotropy.

`attitude_deg_45`: `psi=180` is S1 while dense `attitude_deg_45` classical is S0 across all 3 seeds. The continuous values are still close to the dense jitter scale: yaw RMS range `1.778 deg` versus dense max yaw jitter `1.810 deg`, max tilt range `1.652 deg` versus dense max tilt jitter `1.685 deg`. This looks like a one-seed S0/S1 boundary case, not a collapsed classical floor.

## mc_nn Severity And Escape Cells

Focused mc_nn read for the two direction-reversal attitude cells:

| theta / psi | S3+ count | mean max tilt deg | mean max rate rad/s | mean yaw RMS deg |
|---|---:|---:|---:|---:|
| `attitude_deg_42` psi0 | 2/2 | 179.412 | 19.882 | 46.241 |
| `attitude_deg_42` psi90 | 0/2 | 65.103 | 5.324 | 1.710 |
| `attitude_deg_42` psi180 | 1/2 | 134.973 | 7.912 | 1.401 |
| `attitude_deg_42` psi270 | 2/2 | 179.572 | 23.023 | 132.601 |
| `attitude_deg_48` psi0 | 0/2 | 102.895 | 6.169 | 2.606 |
| `attitude_deg_48` psi90 | 2/2 | 141.622 | 18.878 | 28.096 |
| `attitude_deg_48` psi180 | 2/2 | 177.118 | 16.399 | 34.777 |
| `attitude_deg_48` psi270 | 2/2 | 179.280 | 22.087 | 118.292 |

Escape analysis:

| theta | escape psi | escape severity | escape mean tilt/rate | non-escape mean tilt/rate |
|---|---|---|---:|---:|
| `attitude_deg_42` | 90 | S0/S0 | 65.103 deg / 5.324 rad/s | 164.652 deg / 16.939 rad/s |
| `attitude_deg_48` | 0 | S0/S0 | 102.895 deg / 6.169 rad/s | 166.007 deg / 19.121 rad/s |

The escape cells also have much lower achieved plant excursion. Therefore Stage 1 does not yet prove that psi acts after conditioning on achieved tilt/rate. It remains a strong A-candidate signal, not a confirmed controller-level positive.

Dense-pooled Fisher checks are legal because theta consistency passed:

| contrast | counts | one-sided p |
|---|---:|---:|
| `attitude_deg_42`: psi0 > psi90 | 5/5 S3 vs 0/2 S3 | 0.047619 |
| `attitude_deg_48`: psi90/180/270 > psi0 | 6/6 S3 vs 1/5 S3 | 0.015152 |

Direction reversal remains important: `attitude_deg_42` is severe at psi0 and escapes at psi90, while `attitude_deg_48` escapes at psi0 and is severe at psi90/180/270. A single global "bad heading" explanation is too weak for that qualitative pattern, but the classical yaw-estimator floor prevents upgrading the result to confirmed positive.

## GO / NO-GO

Recommendation: **先 Stage 3**, not GO Stage 2 yet.

Reason: the classical continuous floor is clean enough on achieved tilt, and `hard_attitude_deg_50`/`attitude_deg_45` look like boundary/jitter issues, but the classical yaw-estimator proxy is not clean. The largest classical yaw RMS psi range is `3.746 deg`, `2.07x` the available dense seed-jitter baseline. That is concentrated in the estimator-yaw quantity that Q3 asked us to use as the magnetic/EKF proxy.

Stage 3 should explicitly rotate the magnetic field with psi or otherwise neutralize/verify the magnetic heading frame, and should explicitly add/verify `sensor_mag`, `vehicle_magnetometer`, and `estimator_innovations` in the logging setup before using magnetic innovation as direct evidence. Until then, the status remains: **strong A-candidate, not confirmed positive**.
