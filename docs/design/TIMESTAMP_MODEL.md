# Timestamp model

Basis: PX4 `4ae21a5e569d3d89c2f6366688cbacb3e93437c9` and
px4-ros2-interface-lib `c3e410f035806e8c56246708432ded09c976434b`.

## Domains

| Domain | Meaning | Directly comparable with |
|---|---|---|
| PX4 boot time | `hrt_absolute_time()` microseconds since PX4 boot | PX4 uORB and normal ULog timestamps from the same boot |
| PX4 uORB timestamp | message `timestamp`, normally PX4 boot microseconds | other PX4 uORB timestamps in the same run |
| ROS 2 node clock | `node.get_clock()->now()`; system or simulated according to `use_sim_time` | only records from the same ROS clock configuration |
| DDS receive time | local subscriber callback clock at delivery | ROS node records on the same clock; not PX4 until offset is estimated |
| simulator time | Gazebo simulation time, which can pause or advance faster than wall time | ROS time only when `/clock` and `use_sim_time` are active |
| wall clock | host UTC/system time | other synchronized host wall clocks; never raw PX4 boot time |
| producer timestamp | adapter monotonic timestamp and publish sequence | producer events in the same process; requires a bridge to PX4 |
| consumer timestamp | patched `hrt_absolute_time()` at controller consumption | PX4/uORB/ULog timestamps in the same boot |
| ULog timestamp | logged uORB timestamp in microseconds | PX4 boot/uORB values from that ULog |

The interface library deliberately writes zero into most command/setpoint
message timestamps and lets PX4 stamp ingress. In the locked PX4,
`uxrce_dds_client.cpp:on_request` applies the session time offset, and
`UXRCE_DDS_SYNCT` defaults enabled. `timesync_status` and convergence must be
captured; a configured default is not evidence of a converged clock.

## Ordering and offsets

Within one PX4 boot, order control-plane, consumption, allocator, writer, and
output events by PX4 boot microseconds. ULog preserves that order subject to
logger rate limits. Equal timestamps are broken by this precedence only when
the corresponding sequence counters are continuous:

```text
setpoint received → setpoint consumed → allocator input published
→ actuator output published → actuator output observed
```

`RouteObservability` records `timestamp`, `subject_timestamp`, publisher-local
`sequence`, profile, and expected period. BASELINE is expected every 100 ms
(about 10 Hz). TRANSITION is configured every 8 ms and measured at 121.71 Hz
for the final writer. Logger interval `0` means every uORB update in the PX4
logger API and is not a frequency in hertz. A sequence discontinuity proves
that an event was produced but is absent from ULog; the missing interval must
remain unknown even if the average rate exceeds 100 Hz.

ROS/DDS and PX4 timestamps are not subtracted directly. At run start and after
every time-sync reset, record pairs `(ros_receive_ns, px4_message_timestamp_us)`
from a PX4 outbound message. Recover PX4 boot time using the reported DDS
offset, fit an affine rate and reference pair, and retain residual range.
Declare a bridge valid only after DDS time-sync convergence and a bounded,
non-jumping residual. Each bridge segment has its own ID and uncertainty. The
implementation and thresholds are in `CLOCK_BRIDGE_IMPLEMENTATION.md`.

## Freshness, overlap, and gap

- PX4 consumption freshness is `(consume_px4_us - subject_px4_us) / 1e6`.
- Producer-to-PX4 latency uses the clock bridge and includes its uncertainty.
- A route is live only on a consumption/writer event, not merely a producer
  publication.
- Overlap is the intersection between the old route's last permitted influence
  interval and the new route's first influence interval.
- Gap is the interval from old-route revocation to the first valid target-route
  consumption/writer event when no valid safe output exists.
- Negative ages beyond bridge uncertainty invalidate the sample.
- With q4, target critical windows have 12–16 ms maximum gaps and no sequence
  loss in all three controlled repeats. q1 remains the bounded negative control
  and cannot exclude overlap inside its missing sequences.
- Logger stop/start at disarm creates multiple ULog files in the same PX4 boot.
  P0-D merges all segments on the common PX4 timestamp axis; selecting only the
  last file would erase the pre-disarm transition.

## Replay and accelerated simulation

Replay keeps recorded PX4/ULog time as the authoritative event axis. Wall time
and playback time are annotations only. With accelerated Gazebo, deadlines are
expressed in simulator/PX4 time; CPU scheduling diagnostics remain wall-clock
measurements and cannot be mixed into flight-time gaps. Pauses, `/clock`
resets, PX4 restarts, or non-monotonic timestamps start a new clock segment.
No overlap/gap claim may span segments without a new validated bridge.
