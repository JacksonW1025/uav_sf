# Tier 1 Parallel Profiling - 2026-06-26

Scope: Tier 1 step 1 only. This measured real `m2_map_elites.evaluate_theta()` evals, not the mock evaluator and not a campaign/resume run. Each eval ran classical plus `mc_nn_control` mode 23 SITL, then the property oracle on both ULOGs.

Raw one-shot run data is under ignored `docs/parallel_profile_20260626/evals/profile_runs/`.

## Setup

- Fixed theta: shim-free `physics_mismatch`, seed `20260628`, `mission_end_s=54`, target preset `behavior` (`P4/P6/P7`).
- Genome values: `mass_scale=1.0978`, `inertia_roll_scale=0.8140`, `inertia_pitch_scale=1.4403`, `inertia_yaw_scale=1.3517`, `twr_scale=0.9342`, no wind.
- Runner: `scripts/parallel_profile.py` worker calls `scripts/m2_map_elites.py::evaluate_theta()` directly.
- Isolation used for every worker: unique container name, `ROS_DOMAIN_ID`, `AGENT_PORT`, `PX4_UXRCE_DDS_PORT`, `TMPDIR`, and per-controller `PX4_RUN_ROOT_BASE`.
- Code audit before running found the old runner was unsafe for parallel evals by construction: shared `build/px4_sitl_mcnn_sih/log`, shared params, shared airframe copy, and fixed UDP `8888`. The profiling harness avoids those collisions.

## Step 1 - Crosstalk And Determinism

Serial baseline, same theta and seed, isolated one at a time:

| run | worker wall s | batch wall s | evals/h | classical P7 | mcnn P7 | classical roll/pitch max deg | mcnn roll/pitch max deg |
|---|---:|---:|---:|---:|---:|---:|---:|
| serial_r00 | 207.11 | 216.48 | 16.63 | 0.9511 | 1.2952 | 4.5357 | 5.7945 |
| serial_r01 | 207.67 | 216.47 | 16.63 | 0.9865 | 1.0972 | 4.8526 | 5.4200 |
| serial_r02 | 207.50 | 216.48 | 16.63 | 1.1753 | 1.2592 | 5.2617 | 6.3857 |

Parallel deviation versus serial median:

| metric | serial pairwise range | N=2 max deviation | N=4 max deviation | verdict |
|---|---:|---:|---:|---|
| `mcnn.metric.roll_pitch_max_deg` | 0.9657 | 4.5855 | 5.7260 | dirty |
| `mcnn.metric.tracking_error_max_m` | 0.0753 | 0.1959 | 0.1538 | elevated |
| `mcnn.rho.P7` | 0.1980 | 0.3335 | 0.5612 | elevated |
| `classical.rho.P7` | 0.2242 | 0.5869 | 0.6115 | elevated |
| `mcnn.rho.P1` | 0.0128 | 0.0070 | 0.0416 | dirty at N=4 |
| `mcnn.metric.min_altitude_agl_m` | 0.0227 | 0.0431 | 0.0734 | dirty at N=4 |

Crosstalk verdict: **not clean for N >= 2**.

All N=2 and N=4 workers used independent ports, domains, tmp dirs, ULOG output dirs, and PX4 roots, and all evals returned success. The failure mode is therefore not a file/port collision. The observed issue is resource or lockstep scheduling interference: parallel runs complete but change trajectory/property metrics beyond the isolated serial jitter band.

## Step 2 - Throughput

Because Step 1 is not clean at N=2, N=2 and N=4 are reported as measured but rejected. N=8 was not run.

| N | batch wall s | successes/failures | evals/h | max sampled CPU pct sum | max sampled memory | status |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 216.45 | 1/0 | 16.63 | 56.57 | 153.5 MiB | sustainable |
| 2 | 222.53 | 2/0 | 32.36 | 100.85 | not captured | rejected: crosstalk dirty |
| 4 | 222.62 | 4/0 | 64.69 | 194.28 | not captured | rejected: crosstalk dirty |
| 8 | not run | n/a | n/a | n/a | n/a | blocked by N=2/N=4 determinism |

CPU was not saturated before determinism failed. Host memory also was not near saturation (`free -h` showed about 51 GiB available before runs). The first N=1 memory sample after fixing stats parsing was 153.5 MiB for the running container.

## Speed Factor Probe

| speed factor | N | result | note |
|---:|---:|---|---|
| 1.0 | 1 | pass | baseline, 16.63 evals/h |
| 2.0 | 1 | fail | `RuntimeError: task node timed out for classical` |
| 3.0 | 1 | not run | stopped after 2.0 failed |

Stable speed-factor upper bound observed: **1.0**.

## Recommendation

Recommended campaign parallelism right now: **N=1**.

At the clean rate of about **16.6 evals/hour**:

- 1,000 evals: about 60.1 hours.
- 2,000 evals: about 120.3 hours.
- 3,000 evals: about 180.4 hours, about 7.5 days.
- 5,000 evals: about 300.7 hours, about 12.5 days.

Blocking issue before campaign-scale parallelism: resolve or bound the resource/lockstep interference seen at N=2 and N=4. File, port, tmp, and ULOG path collisions were isolated in the profiling harness; the remaining suspect is parallel CPU scheduling/lockstep timing rather than shared output state.
