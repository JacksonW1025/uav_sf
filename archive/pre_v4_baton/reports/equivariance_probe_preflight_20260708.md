# Yaw-Equivariance Probe Preflight - 20260708

## Scope

Preparation only. The Phase 1 classical floor gate and mc_nn equivariance probe were not run.

The metamorphic relation is world-z yaw rotation: commanded heading, route-A circle bearing, and wind bearing rotate together while amplitudes stay fixed. The primary Phase 1 readout remains property-oracle severity invariance across yaw.

## Implementation

- Transform module: `scripts/equivariance_transform.py`
- Driver: `scripts/run_equivariance_probe.py`
- Optional Stage 0 task probe: `scripts/m1_offboard_task.py`
- Tests:
  - `tests/test_equivariance_transform.py`
  - `tests/test_equivariance_probe.py`

Code-level sign note: `m1_offboard_task.py` encodes the route-A circle as `N=sin(phase), E=cos(phase)`. Therefore the semantic NED circle bearing is `pi/2 - phase`. To make the actual trajectory bearing add `psi`, the raw `setpoint.circle.phase_rad` and `theta_genome.genome.approach_phase_rad` subtract `psi`. Commanded yaw and wind bearing add `psi`.

Stage 0 adds an opt-in `setpoint.diagnostic_probe.relative_times_s` block to the theta. Only Stage 0 theta files set it. The task node records four exact command samples as `setpoint_probe` events; normal campaigns are unchanged.

## Stage 0 Evidence

Command run:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=equivariance_stage0_probe2_20260708 ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && python scripts/run_equivariance_probe.py --run-id equivariance_probe_preflight_20260708 --stage0-preflight --no-resume --sim-speed-factor 1.25 --run-timeout 230"'
```

Result artifact: `runs/campaigns/equivariance_probe_preflight_20260708/stage0_summary.json`

- Evals: 4 classical runs on `pair2`, seed `2026070800`
- Severity read: `false`
- Valid evals: `4/4`
- Heading deltas: `[0.0, 90.0, 180.0, 270.0]` deg
- Expected deltas: `[0, 90, 180, 270]` deg
- Commanded body maneuver identical: `true`
- Task-probed body maneuver identical: `true`
- Stage 0 passed: `true`

Per-yaw bearings and body-frame probe source:

| psi deg | yaw deg | circle bearing deg | wind bearing deg | wind speed m/s | probe source |
|---:|---:|---:|---:|---:|---|
| 0 | 0 | 90 | 0 | 6.0 | `m1_offboard_task.setpoint_probe` |
| 90 | 90 | 180 | 90 | 6.0 | `m1_offboard_task.setpoint_probe` |
| 180 | 180 | 270 | 180 | 6.0 | `m1_offboard_task.setpoint_probe` |
| 270 | 270 | 0 | 270 | 6.0 | `m1_offboard_task.setpoint_probe` |

Body-frame samples were identical across all four yaw cases. The task-probed samples were:

```json
[
  {"t_s": 0.0, "pos_body_ne_m": [0.0, 6.0], "vel_body_ne_m_s": [16.964600329, 0.0], "acc_body_ne_m_s2": [0.0, -47.966277389]},
  {"t_s": 0.25, "pos_body_ne_m": [3.89668829, 4.562435794], "vel_body_ne_m_s": [12.899983294, -11.017626575], "acc_body_ne_m_s2": [-31.151605236, -36.473843474]},
  {"t_s": 0.5, "pos_body_ne_m": [5.926130044, 0.93860679], "vel_body_ne_m_s": [2.653848177, -16.755737948], "acc_body_ne_m_s2": [-47.375732919, -7.503578943]},
  {"t_s": 1.0, "pos_body_ne_m": [1.854101966, -5.706339098], "vel_body_ne_m_s": [-16.13429369, -5.242349805], "acc_body_ne_m_s2": [-14.82239487, 45.618640674]}
]
```

## Locked Phase 1 Plan

List command checked:

```bash
python3 scripts/run_equivariance_probe.py --run-id equivariance_probe_20260708 --wind-zero --list-only
```

Plan summary:

- Theta count: 6
- Theta IDs: `attitude_deg_42`, `attitude_deg_45`, `attitude_deg_48`, `pair2`, `pair5`, `hard_attitude_deg_50`
- Yaw angles: `0, 90, 180, 270` deg
- Classical floor gate: `24` evals (`6 theta x 4 yaw x 1 seed`)
- mc_nn probe: `48` evals (`6 theta x 4 yaw x 2 seeds`)
- Stage 0: `4` evals already completed
- Wind-zero first round: `true`
- Total Phase 1 evals after GO: `72`; total including Stage 0: `76`

## GO Command

Run only after explicit GO:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=equivariance_probe_20260708 ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && python scripts/run_equivariance_probe.py --run-id equivariance_probe_20260708 --wind-zero --sim-speed-factor 1.25 --run-timeout 230"'
```

Expected wall time: about 3.5 h serial at N=1.

## Stop State

Stopped at preparation-complete state and waiting for explicit GO. No Phase 1 floor gate or mc_nn severity probe was launched.
