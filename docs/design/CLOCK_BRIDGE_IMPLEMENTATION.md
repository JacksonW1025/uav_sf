# ROS–PX4 clock bridge implementation

The bridge collector captures the PX4 outbound timestamp, the latest converged
DDS offset, ROS node receive time, and monotonic receive time. It records the
`TimesyncStatus` callback directly and, when available, prefers continuous
`VehicleStatus` outbound samples carrying the same current time-sync evidence.
PX4 boot time is recovered as:

```text
px4_boot_us = outbound_timestamp_us + timesync_estimated_offset_us
```

This matters because the DDS-visible outbound timestamp is synchronized toward
ROS epoch time; treating it as boot time produces false resets.

The continuous status pairs cover the complete lifecycle window and avoid
mistaking a bursty `TimesyncStatus` delivery pattern for clock drift. They do
not weaken the convergence requirement: every selected sample retains source
protocol, estimated offset, round-trip time, and convergence fields from the
latest observed `TimesyncStatus`.

Gazebo/PX4 simulated time and host wall time do not advance at exactly the same
rate. A segment therefore uses the affine map:

```text
ros_ns = reference_ros_ns
       + rate_ratio * 1000 * (px4_us - reference_px4_us)
```

`offset_ns` is still reported at the reference sample for compatibility. The
inverse affine map is used by Route Oracle 0.2. Residual median, maximum,
sample count, validity interval, rate, reference pair, ID, and uncertainty are
stored in `clock_bridge.json`.

## Segments and preregistered validity

A new segment begins on PX4 time reversal, ROS or monotonic time reversal, a
ROS-versus-monotonic jump over 50 ms, or a DDS source/convergence-state change.
Duplicate PX4 samples are ignored by the fit. Latency is never computed across
segments.

Thresholds were fixed after the q16 baseline smoke (67.1 ms maximum affine
residual) and before the controlled queue matrix, P0-D, P2, or P3 experiments:

| threshold | value |
|---|---:|
| minimum unique samples | 20 |
| VALID maximum residual | 100 ms |
| DEGRADED maximum residual | 250 ms |
| maximum DDS round trip | 20 ms |
| reset/jump boundary | 50 ms |

The 100 ms bound is deliberately wider than the 67.1 ms baseline and remains
well below the 500 ms-scale failure deadlines studied later. `VALID` permits a
point estimate plus `uncertainty_ns`; `DEGRADED` permits only an interval;
`INVALID` makes cross-domain results `UNKNOWN`.

The schema is `data/schemas/clock_bridge.schema.json`; collection and tests are
in `scripts/tracing/clock_bridge_collector.py` and `tests/test_clock_bridge.py`.
