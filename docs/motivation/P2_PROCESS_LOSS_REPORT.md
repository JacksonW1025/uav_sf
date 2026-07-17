# P2 Process Loss and Last-Command Lifetime

P2 completed 18 accepted deterministic cases: two route objects, three fault
classes, and three repeats per object/fault pair. The complete accepted matrix
is [experiment_matrix.tsv](../../experiments/probes/p2/experiment_matrix.tsv),
and each row links by `run_id` to the corresponding directory under
`data/processed/p2/`.

## Method

Each case used the locked q4 TRANSITION observation build, `gz_x500`, no wind,
no RC/GCS mode switching, stable hover, and an explicitly configured Hold
fallback (`COM_OF_LOSS_T=1.0`, `COM_OBL_RC_ACT=5`). Offboard and Dynamic
External Mode ran as processes separate from the flight monitor. The injector
delivered exactly one of:

- SIGTERM, with the producer's normal graceful shutdown path;
- SIGKILL, with no producer cleanup handler; or
- SIGSTOP followed by SIGCONT after a fixed 2.0 s pause.

The monitor—not the process under test—maintained the clock bridge and flight
state observation. This prevents a killed producer from also deleting its
fault-time measurement. Every accepted bridge is `VALID` under the thresholds
preregistered before P2. Fault ROS time is converted to a PX4 interval using
the affine bridge and its uncertainty.

## Results

| object | fault | accepted | fallback | detection latency min / median / max | maximum altitude loss |
|---|---|---:|---:|---:|---:|
| Offboard | SIGTERM | 3 | 3/3 | 144 / 158 / 237 ms | 0.015 m |
| Offboard | SIGKILL | 3 | 3/3 | 1,048 / 1,121 / 1,185 ms | 0.060 m |
| Offboard | SIGSTOP/SIGCONT | 3 | 3/3 | 1,063 / 1,221 / 1,260 ms | 0.060 m |
| Dynamic External | SIGTERM | 3 | 3/3 | 47 / 88 / 252 ms | 0.042 m |
| Dynamic External | SIGKILL | 3 | 3/3 | 1,184 / 1,337 / 1,354 ms | 0.143 m |
| Dynamic External | SIGSTOP/SIGCONT | 3 | 3/3 | 1,298 / 1,360 / 1,396 ms | 0.153 m |

All 18 experiment verdicts are PASS. Clock uncertainty ranges from 27.8 to
96.0 ms. All 18 Route Oracle 0.2 results are PASS, all 90 clauses are PASS,
and the accepted set contains zero post-revocation old-epoch consumption or
writer events. Maximum observed tilt during a fault window was 1.09 degrees.

The accepted data records fault interval, last producer setpoint, last old
epoch consumption/allocator/writer, failure detection, fallback epoch, first
fallback consumption/allocator/writer, and physical metrics. Offboard
proof-of-life publication time is available directly from the producer log.
The locked External interface did not log individual arming-check reply times,
so its exact last health-reply time is explicitly `UNKNOWN` rather than copied
from the setpoint timestamp. The locked DDS configuration comments out
`/fmu/out/vehicle_angular_velocity`; rate peak is therefore also `UNKNOWN`.
Attitude and altitude metrics remain available.

## Exclusions and claim boundary

Ignored raw evidence retains startup/cleanup SITL aborts and runs whose clock
bridge was `DEGRADED` or sample-deficient. They were not counted or silently
rerun under the same ID. No threshold was changed. The accepted processed set
contains exactly 18 cases and no non-PASS or non-VALID row.

These repeats establish deterministic behavior for these six configurations;
they are not a failure probability estimate and are not a fuzzer campaign.
