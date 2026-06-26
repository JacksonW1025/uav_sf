# Tier 1 Step 1b Parallel Recovery Report - 2026-06-26

Starting point: `3d999af` reported N>=2 crosstalk dirty and
`--sim-speed-factor 2.0` failing, with the safe fallback at N=1,
speed-factor 1.0, about 16.6 evals/hour.

## Verdict

Parallel execution was not recovered. Two CPU-pinning variants completed
all N=2 evals without resource failures, but both still failed the strict
crosstalk gate. N=2 is therefore still not campaign-safe.

The usable throughput improvement is single-eval speedup: N=1 with
`PX4_SIM_SPEED_FACTOR=1.25` passed three real evals. The observed
conservative throughput is about 23.3 evals/hour. `1.5` failed with the
same classical task-node timeout signature as the previous `2.0` probe, so
the observed stable speed-factor upper bound is 1.25.

Recommended campaign setting from this recovery attempt:

| Setting | Crosstalk verdict | Failure verdict | Throughput |
|---|---:|---:|---:|
| N=1, speed 1.25 | not applicable | clean in 3/3 real evals | 23.3 evals/hour |
| N=2 pinned, speed 1.0 | dirty | 0/2 run failures | 32.35 evals/hour, rejected |
| N=1, speed 1.0 | clean fallback from prior profile | clean | 16.6 evals/hour |

At 23.3 evals/hour, 3000 evals take about 129 hours (5.4 days). 5000 evals
take about 215 hours (9.0 days). If speed-factor 1.25 is rejected for
maximum conservatism, use the previous N=1 speed 1.0 fallback: 3000 evals
take about 181 hours (7.5 days).

## Step A - Root-Cause Diagnosis

The offboard setpoint publisher is wall-clock scheduled:

- `scripts/m1_offboard_task.py` creates a ROS wall timer with
  `create_timer(1.0 / self.wall_timer_hz, self.tick)`.
- `wall_timer_hz = setpoint_rate_hz * PX4_SIM_SPEED_FACTOR`, capped by
  `max_wall_timer_hz`.
- Outgoing setpoint/control messages are timestamped from the latest PX4
  message timestamp (`self.now_us`), so the message clock is sim-time, but
  the publication cadence is wall-clock/event-loop time.

This matches the suspected failure mode: the eval uses lockstep SIH, but the
setpoint stream is not itself driven by lockstep sim time.

Setpoint arrival intervals were measured from ULOG
`trajectory_setpoint.timestamp` within the controller-active to mission-end
window. The p50/p99 cadence stays near 12/24 ms, so this is not a simple
global rate drop. The long sim-time gaps and duplicate timestamp ratio grow
under parallel load, which is consistent with wall-clock scheduling
interference.

| Condition | Controller | Runs | p50 ms | p99 ms | Median max gap ms | Duplicate ratio |
|---|---:|---:|---:|---:|---:|---:|
| serial isolated | classical | 3 | 12.0 | 24.0 | 1006.6 | 0.051 |
| serial isolated | mcnn | 3 | 12.0 | 24.0 | 987.8 | 0.046 |
| original N=2 | classical | 2 | 12.0 | 24.0 | 1257.2 | 0.066 |
| original N=2 | mcnn | 2 | 12.0 | 24.0 | 1197.4 | 0.059 |
| original N=4 | classical | 4 | 12.0 | 24.0 | 1573.9 | 0.087 |
| original N=4 | mcnn | 4 | 12.0 | 24.0 | 1724.0 | 0.095 |

No evidence was found for shared path/port collision in the profiling
scaffold: container name, ROS domain, agent port, tmpdir, and PX4 run root
are unique per worker.

## Step B - CPU Pinning

Added minimal pinning support:

- `docker/run.sh` now accepts `DOCKER_CPUSET_CPUS` and passes it to Docker as
  `--cpuset-cpus`.
- `scripts/parallel_profile.py` now accepts `--cpuset-groups`, assigns one
  cpuset group per worker slot, exports the selected group in worker
  metadata, and records it in batch summaries.

### Variant 1: N=2, 6+6 cores

Command cpusets: `0-5;6-11`.

| Batch | N | Cpusets | Wall s | Success | Failure |
|---|---:|---|---:|---:|---:|
| serial r00 | 1 | `0-5` | 216.48 | 1 | 0 |
| serial r01 | 1 | `0-5` | 216.46 | 1 | 0 |
| serial r02 | 1 | `0-5` | 216.50 | 1 | 0 |
| crosstalk N=2 | 2 | `0-5;6-11` | 222.54 | 2 | 0 |

Crosstalk verdict: dirty.

| Suspicious metric | Serial range | Parallel delta | Tolerance | Ratio |
|---|---:|---:|---:|---:|
| classical angular_rate_max_rad_s | 0.0264 | 0.0911 | 0.0791 | 3.45 |
| classical final_error_m | 0.0371 | 0.1170 | 0.1114 | 3.15 |

This was much smaller than the original unpinned N=2/N=4 dirty case, but it
still exceeded the strict gate.

### Variant 2: N=2, 4+4 cores with spare cores

Command cpusets: `0-3;4-7`, leaving `8-11` unused by containers.

| Batch | N | Cpusets | Wall s | Success | Failure |
|---|---:|---|---:|---:|---:|
| serial r00 | 1 | `0-3` | 216.46 | 1 | 0 |
| serial r01 | 1 | `0-3` | 216.46 | 1 | 0 |
| serial r02 | 1 | `0-3` | 216.44 | 1 | 0 |
| crosstalk N=2 | 2 | `0-3;4-7` | 222.53 | 2 | 0 |

Crosstalk verdict: dirty.

| Suspicious metric | Serial range | Parallel delta | Tolerance | Ratio |
|---|---:|---:|---:|---:|
| classical rho.P5 | 0.0384 | 0.1672 | 0.1151 | 4.35 |

Because N=2 remained dirty, N=4 pinned was not run. Scaling past a failed
N=2 crosstalk gate would not be defensible.

## Speed-Factor Probe

N=1 speed-factor probing used real evals and the same cpuset `0-3`.

| Speed factor | Result | Host wall s | Eval wall s | Notes |
|---:|---:|---:|---:|---|
| 1.25 | pass | 149.50 | 147.86 | first probe |
| 1.25 | pass | 157.91 | 155.92 | repeat 1 |
| 1.25 | pass | 157.60 | 156.03 | repeat 2 |
| 1.5 | fail | 119.87 | 118.44 | `RuntimeError: task node timed out for classical` |

Using host wall time, speed 1.25 averages 154.67 s/eval, or 23.3
evals/hour. Speed 1.5 is not stable, and speed 2.0 remains rejected from the
previous profiling run.

The 1.5 task log reached `controller_active` and `trajectory_start`, then no
mission result was produced before the parent timed out waiting for the task
node. This is the same class of failure as the earlier speed 2.0 probe and
supports the wall-clock/sim-time desynchronization hypothesis.

## Step C Status

No setpoint sim-time lock was implemented in this time box. That change
would alter the eval timing semantics for every run and must be followed by
the route-A strict-anchor regression and the Part-2 P7-gradient regression.
Since coarse CPU pinning did not recover N=2 and speed 1.25 gives a safe
single-eval throughput improvement, the deeper setpoint rewrite should be a
separate task.

Recorded implementation direction for Step C:

- Drive setpoint publication from sim-time progress, or make lockstep wait
  for the setpoint stream.
- Revisit task/PX4 wall-clock waits under speed-factor after the setpoint
  stream is sim-time driven.
- Then rerun N=2/N=4 crosstalk and speed 2.0/3.0 plus the required anchors.

## Final Recommendation

Use N=1 for campaign orchestration. Parallel N=2 is still not clean under the
strict serial-vs-parallel jitter gate, even with CPU pinning.

Use `PX4_SIM_SPEED_FACTOR=1.25` as the observed stable throughput setting if
the campaign and baseline both run under the same setting. Otherwise fall
back to the prior N=1 speed 1.0 number.

Final observed throughput for planning: N=1, speed 1.25, about 23.3
evals/hour.
