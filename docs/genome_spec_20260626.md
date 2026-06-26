# Tier 0.5 Step 2.1 Genome Spec

Date: 2026-06-26

Scope: first Tier 0.5 subtask only: theta genome, legal genetic operators, MAP-Elites bins, P5 non-vacuous step validation, and shim decision. Fitness wiring and search-loop smoke tests remain out of scope.

## Parameter-Surface Inventory

`scripts/m1_offboard_task.py` is already the right task surface. It supports a finite `TrajectorySetpoint` stream, fixed hover, `step`, `ramp`, `sine`, `circle`, feedforward, two-stage classical approach, controller switch by sim time, Method-A groundtruth activation triggers, and post-switch hover. This step added two small extensions on that surface:

- `setpoint.step.start_s`: explicit delayed step time while keeping the existing `step.delta_ned` mechanism.
- `setpoint.activation_trigger.switch_delay_s`: optional delay between Method-A groundtruth trigger and controller mode command.

Genome variables are therefore mapped onto the existing theta JSON rather than a separate scenario format:

- sustained wind: `SIH_WIND_N/E` through `boot_px4_params` and `px4_params`
- physical mismatch: `SIH_MASS`, `SIH_IXX/IYY/IZZ`, `SIH_T_MAX`, `SIH_Q_MAX`, and compensated `MPC_THR_HOVER`
- B-tier switching: existing circle approach plus groundtruth `activation_trigger` and post-switch hover
- P5 step stimulus: existing `step.delta_ned`, now with `step.start_s`

Missing or deferred surfaces:

- state-estimator contamination needs the M2b publish-point shim and is blocked by patch drift
- motor/sensor faults remain excluded from this genome and need a Gazebo route plus a verified SIH boundary
- CoG/payload offset is approximated by inertia/mass scaling until SIH exposes a direct CoG parameter

## Existing Search Scaffold

Existing search code was found in `scripts/m2_map_elites.py`, `scripts/m2b_state_map_elites.py`, and `scripts/m2b_state_profiles.py`. This step reuses their theta-shape conventions, SIH parameter names, MAP-Elites family/bucket idea, and M2b shim metadata, but does not reuse M2 fitness: M2 optimized divergence/RAPTOR-era metrics, while the property fitness wire is reserved for Tier 0.5 step 2.2.

## Shim Drift Decision

`external/PX4-Autopilot` is at PX4 `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`, but the external tree has local overlay changes. `patches/px4/m2b_state_shim.patch` fails both reverse and forward `git apply --check` against that tree, including drift in:

- `src/modules/sensors/vehicle_angular_velocity/VehicleAngularVelocity.hpp`
- `src/modules/sensors/vehicle_angular_velocity/VehicleAngularVelocity.cpp`
- `src/modules/ekf2/EKF2Selector.hpp`
- `src/modules/ekf2/EKF2Selector.cpp`
- `src/modules/ekf2/EKF2.hpp`
- `src/modules/ekf2/EKF2.cpp`

Decision for this step: state-contamination variables remain in the spec but are marked `DEFERRED - pending m2b_state_shim.patch drift`. The delivered runnable genome is the shim-free subset: wind, physics mismatch, switching, and moderate step.

## Genome Variables

MAP-Elites feature dimensions are `disturbance_type` x `amplitude_bucket`, where `disturbance_type` is `wind`, `physics_mismatch`, `state_contam`, `switching`, or `step`, and `amplitude_bucket` is `low`, `mid`, or `high` from normalized per-family severity.

| variable | type / bounds | simulator + injection | route status |
|---|---|---|---|
| `disturbance_type` | categorical: `wind`, `physics_mismatch`, `state_contam`, `switching`, `step` | scenario selector | `state_contam` deferred |
| `wind_speed_m_s` | continuous `[0.0, 8.0]` | SIH `SIH_WIND_N/E` | shim-free |
| `wind_direction_rad` | continuous `[0, 2*pi]` | SIH `SIH_WIND_N/E` | shim-free |
| `mass_scale` | continuous `[0.85, 1.25]` | SIH `SIH_MASS` plus inertia coupling | shim-free |
| `inertia_roll_scale` | continuous `[0.70, 1.60]` | SIH `SIH_IXX` | shim-free |
| `inertia_pitch_scale` | continuous `[0.70, 1.60]` | SIH `SIH_IYY` | shim-free |
| `inertia_yaw_scale` | continuous `[0.70, 1.80]` | SIH `SIH_IZZ` | shim-free |
| `twr_scale` | continuous `[0.90, 1.15]` | SIH `SIH_T_MAX/SIH_Q_MAX`, `MPC_THR_HOVER` compensation | shim-free; high-TWR claims require multi-seed confirmation |
| `fake_velocity_bias_m_s` | continuous `[-0.50, 0.50]` | M2b shared-state shim | `DEFERRED` |
| `fake_angular_rate_bias_rad_s` | continuous `[-0.25, 0.25]` | M2b shared-state shim | `DEFERRED` |
| `position_estimate_jump_m` | continuous `[-0.50, 0.50]` | M2b shared-state shim | `DEFERRED` |
| `approach_radius_m` | continuous `[1.8, 6.0]` | offboard circle setpoint | shim-free |
| `approach_frequency_hz` | continuous `[0.25, 0.50]` | offboard circle setpoint | shim-free |
| `approach_phase_rad` | continuous `[0, 2*pi]` | offboard circle setpoint | shim-free |
| `switch_roll_pitch_deg` | continuous `[12.0, 55.0]` | groundtruth activation trigger | shim-free; cross-constrained to reachable circle tilt |
| `switch_rate_rad_s` | continuous `[0.30, 3.00]` | groundtruth activation trigger | shim-free |
| `switch_delay_s` | continuous `[0.0, 1.0]` | `activation_trigger.switch_delay_s` | shim-free |
| `step_magnitude_m` | continuous `[0.50, 1.50]` | offboard `step.delta_ned` | shim-free; moderate P5 step, not C-tier amplitude attack |
| `step_axis` | categorical: `x`, `y`, `z` | offboard `step.delta_ned` | shim-free |
| `step_sign` | discrete: `-1`, `1` | offboard `step.delta_ned` | shim-free |
| `step_time_s` | continuous `[28.0, 40.0]` | `timing.trajectory_start_s` + `step.start_s` | shim-free; must leave settling window |
| `mission_end_s` | continuous `[46.0, 70.0]` | `timing.mission_end_s` | shim-free |
| `setpoint_rate_hz` | categorical: `50`, `80`, `100` | offboard publication rate | shim-free |

Explicit exclusions:

- C-tier setpoint amplitude attack is not in the genome. The step axis is a moderate settling stimulus only.
- Motor/sensor faults are not in the genome. Future route: Gazebo plus prior SIH boundary check.

## Legal Operators

Implemented in `scripts/theta_genome.py`:

- `random_genome`
- `mutate_genome`
- `crossover_genome`
- `normalize_genome`
- `validate_genome`
- `theta_from_genome`
- `feature_bin`

Legality checks cover variable type and bounds, deferred state contamination, P5 step settling-window slack, moderate step range, switching reachability against the selected circle profile, and physical hover-throttle sanity.

Offline checks:

- `python3 scripts/theta_genome.py --self-test 1000 --seed 20260626`
- result: 1000 random + 1000 mutated + 1000 crossed genomes, 3000 total validated
- feature bins populated across wind, physics mismatch, switching, and step
- `python3 -m unittest tests.test_theta_genome`: 3 tests, OK

## P5 Revival

Probe script: `scripts/tier05_p5_step_probe.py`

Run:

- run-id: `tier05_p5_step_20260626`
- seeds: `20262601`, `20262602`, `20262603`
- controllers: `classical`, `mcnn`
- theta: pure 0.75 m x-axis step at 32 s, no wind, no physics mismatch, no shim
- artifacts: ULOGs and per-run outputs under ignored `docs/tier05_p5_step_20260626/evals/`
- structured summaries: `docs/tier05_p5_step_20260626/p5_calibration_candidate.json` and `docs/tier05_p5_step_20260626/p5_step_calibrated_summary.json`

P5 is no longer vacuous:

- all 6 controller runs detected exactly one step
- all 6 had `details.P5.vacuous=false`
- calibrated P5 margins were positive
- classical min P5 rho: `0.3611290926`
- mc_nn min P5 rho: `0.2998305995`

P5 calibration:

- `epsilon_set = 1.05 m`
- `T_set = 5.0 s`
- `W_hold = 2.0 s`
- basis: max best-`W_hold` max error was `0.3393834506 m`; multiplied by 3 and rounded to 0.05 m. Worst measured settling time at that epsilon was `3.88 s`; plus 1.0 s slack rounded to 0.5 s.

Nominal outcome:

- all 6 pure-step runs remained `S0_clean_recovery`
- no calibrated property differential primary bug was reported

mode-23 identity:

- mc_nn confirmed in all 3 mc_nn runs
- `neural_control_rate_hz`: `229.2148` to `230.7305`
- `raptor_input_present=false`
- `network_output` matched `actuator_motors` at exact timestamps with exact-equal counts `6101` to `6170`

## Completion

Step 1 completion: green. The genome spec is explicit, MAP-Elites bins are defined, and random/mutation/crossover operators generate legal shim-free scenarios offline.

Step 2 completion: green with a deferred shim caveat. P5 has non-empty truth on pure-step data, P5 thresholds are calibrated and recorded in `docs/oracle_calibration.md`, the pure-step runs remain S0 for both controllers, and mc_nn mode-23 identity is positively confirmed. State-contamination variables are honestly deferred pending M2b shim patch-drift cleanup.
