# Yaw-Equivariance Probe Results - 20260708

## Scope

Run ID: `equivariance_probe_20260708`

Command:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=equivariance_probe_20260708 ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && python scripts/run_equivariance_probe.py --run-id equivariance_probe_20260708 --wind-zero --sim-speed-factor 1.25 --run-timeout 230"'
```

Artifacts:

- Results JSONL: `runs/campaigns/equivariance_probe_20260708/equivariance_results.jsonl`
- Summary JSON: `runs/campaigns/equivariance_probe_20260708/summary.json`

The driver ran 56 records: 24 classical floor-gate records and 32 mc_nn records. The mc_nn stage was skipped for two unclean floor theta points, so the planned 72 Phase 1 records were intentionally reduced.

## Classical Floor Gate

| theta | psi 0 | psi 90 | psi 180 | psi 270 | floor |
|---|---:|---:|---:|---:|---|
| `attitude_deg_42` | S0 | S0 | S0 | S0 | clean |
| `attitude_deg_45` | S0 | S0 | S1 | S0 | dirty, Outcome C |
| `attitude_deg_48` | S0 | S0 | S0 | S0 | clean |
| `pair2` | S0 | S0 | S0 | S0 | clean |
| `pair5` | S0 | S0 | S0 | S0 | clean |
| `hard_attitude_deg_50` | S0 | invalid | invalid | invalid | invalid floor, Outcome C |

The hard cell invalids were task-node rc=3 state-trigger timeouts. At psi 90/180/270, max observed roll-pitch was about 45.58/45.86/45.97 deg, below the trigger window min of 46 deg; mc_nn was not read for that theta.

## mc_nn Severity

Each cell is seed `2026070801 / 2026070802`.

| theta | psi 0 | psi 90 | psi 180 | psi 270 | outcome |
|---|---:|---:|---:|---:|---|
| `attitude_deg_42` | S3/S3 | S0/S0 | S0/S3 | S3/S3 | A, confirmed |
| `attitude_deg_45` | skipped | skipped | skipped | skipped | C |
| `attitude_deg_48` | S0/S0 | S3/S3 | S3/S3 | S3/S3 | A, confirmed |
| `pair2` | S3/S3 | S3/S0 | S3/S3 | S3/S3 | A candidate, single controlled seed |
| `pair5` | S3/S3 | S0/S0 | S0/S3 | S3/S0 | A, confirmed |
| `hard_attitude_deg_50` | skipped | skipped | skipped | skipped | C |

## Interpretation

Outcome counts from the driver: `A=4`, `C=2`.

Applying the stricter two-seed confirmation discipline:

- Confirmed Outcome A: `attitude_deg_42`, `attitude_deg_48`, `pair5`
- Outcome A candidate only: `pair2`
- Outcome C: `attitude_deg_45`, `hard_attitude_deg_50`
- Outcome B: none in this first wind-zero set

All positive reads are on theta points with classical severity invariant across psi. The dominant mc_nn violation reason was P2 angular-rate envelope; some S3 cases also violated P1 attitude envelope.
