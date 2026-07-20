# N1 Trajectory Residue Source and Observation Audit

Date: 2026-07-20

This pre-execution audit preserves the frozen `freshness-f1-a02` finding and
defines the distinction that N1 must adjudicate. It does not change the
Freshness pilot, PX4 control behavior, or Route Oracle 0.4.

## Frozen same-domain order

The raw ULog (`5b795892…e33c8`) establishes this PX4-clock sequence:

| PX4 time (us) | Observation |
|---:|---|
| `29,068,000` | last external Trajectory subject timestamp later retained by the controller |
| `30,164,000` | final pre-transition controller consumption carrying that subject timestamp |
| `30,168,000` | Commander publishes the External `23` → RTL `5` route epoch `3` → `4` change |
| `30,168,000` | `vehicle_control_mode` is published with auto control enabled, Offboard disabled, and the position cascade enabled |
| `30,172,000` | position-controller observation carries the old `29,068,000` subject timestamp |
| `30,180,000` | position-controller observation again carries the old subject timestamp |
| `30,188,000` | first RTL-side Trajectory setpoint arrives |

The two retained observations occur 4 ms and 12 ms after the route epoch
change and before the first RTL Trajectory publication. No post-revocation
old-epoch observation, external-attributed allocator input, or external writer
output is recorded.

## Source ordering

On locked PX4 revision `4ae21a5e…`, Commander handles the failsafe selection
and publishes the route-epoch observation before it publishes the updated
`vehicle_control_mode` and `vehicle_status` in the same work cycle. The logged
control mode at the transition already has `flag_control_auto_enabled=true`,
`flag_control_offboard_enabled=false`, and multicopter position control still
enabled.

`MulticopterPositionControl::Run()` then updates its local
`trajectory_setpoint`, emits the observation-only consumption record, applies
EKF-reset adjustment, and—when the position controller remains enabled and the
setpoint is not older than the controller-enable time—passes that same local
setpoint to `PositionControl::setInputSetpoint()`. External→RTL does not disable
the position cascade, so the ordinary disable branch does not clear the local
setpoint. Navigator's first RTL setpoint replaces it at `30,188,000 us` in the
frozen run.

This source order makes genuine short-lived retained-input use a plausible
candidate explanation. It does not by itself establish repeatability,
frequency, downstream physical influence, or a source-level root cause.

## Artifact alternative

An observation/lineage artifact remains possible if the observation event is
associated with the newly declared route solely because the collector has
already seen the Commander route-epoch record while the controller event still
describes a pre-transition computation, or if the observed local setpoint does
not reach the controller's applied-input branch. N1 therefore requires the
complete same-domain order of route epoch, `vehicle_control_mode`, controller
observation, first RTL setpoint, allocator input, and writer output on every
accepted run. Missing critical order is an observability rejection, never a
PASS or VIOLATION.

## Health phase dimension

PX4 external checks publish a request every `300 ms`. The N1 harness waits for
the first public `freshness_health_reply` appended after the stable-window
marker and performs locally owned process termination after 30 ms (A), 150 ms
(B), or 260 ms (C). These are legal harness waits; no PX4 health state is read
or mutated directly. The fault record preserves the anchor reply, requested
offset, observed monotonic offset, and phase bucket for acceptance review.

## Interpretation boundary

- A matching accepted event requires Route Oracle 0.4 `VIOLATION`, the old
  Trajectory subject after the declared fallback, complete same-domain order,
  and complete route/controller/allocator/writer evidence.
- Repeated controller residue without old-epoch allocator or writer evidence
  remains a narrow Route input-use finding; it is not automatically a claim of
  actuator-level external authority.
- No matching event in the bounded 3×3 accepted matrix preserves the original
  evidence-complete found event and supports only bounded non-reproduction.
- N1 will not estimate a population occurrence rate or change PX4 behavior.
