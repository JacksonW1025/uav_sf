# Current-Version External Mode Setpoint Freshness Source Audit

Status: source audit complete; no flight result is claimed here

Audit date: 2026-07-20

Scope: Family A Dynamic External Mode; Trajectory, Attitude, and Rate setpoints

## 1. Locked source identity

This audit is revision-specific. Every statement below was checked against the
locked local sources, not inferred from an API name or a message comment.

| Component | Locked revision |
|---|---|
| PX4-Autopilot | `4ae21a5e569d3d89c2f6366688cbacb3e93437c9` |
| px4_msgs | `18ecff03041c6f8d8a0012fbc63af0b23dd60af1` |
| px4-ros2-interface-lib | `c3e410f035806e8c56246708432ded09c976434b` |
| Micro-XRCE-DDS-Agent | `73622810d984349b80bbac0ef55fc0b694d62222` |

The PX4 and library paths cited below are relative to
`external/PX4-Autopilot` and
`ros2_ws/src/px4_ros2_interface_lib`, respectively. Generated uCDR code was
also inspected in the locked observation build, but its source-of-truth
template is cited so the finding does not depend on an untracked build file.

## 2. Executive source conclusion

At these revisions there is **no enforced per-setpoint freshness timeout** for
Dynamic External Mode Trajectory, Attitude, or Rate inputs. The message API has
a `SetpointConfig.timeout_ms` field, but neither the locked library nor PX4
applies it:

- PX4 declares the field and says that zero disables it
  (`msg/versioned/SetpointConfig.msg:27-33`), but
  `ModeManagement::checkConfigControlSetpointUpdates()` reads `source_id`,
  `type`, and `should_apply` without reading or storing `timeout_ms`
  (`src/modules/commander/ModeManagement.cpp:609-659`).
- The stored mode state has only `current_setpoint_type`, not a timeout or last
  receive time (`src/modules/commander/ModeManagement.hpp:87-103`).
- The library value-initializes `SetpointConfig` and assigns no timeout during
  either compatibility probing or activation
  (`px4_ros2_cpp/src/components/mode.cpp:207-218,398-408`), so it sends zero.

Producer process death is eventually detected through the independent
External Mode arming-check request/reply mechanism. A setpoint-only stall while
that reply path stays alive has no corresponding detector in this source
snapshot. Until the declared mode changes, each controller retains the last
input and keeps generating downstream commands from it.

This is a source-level **policy gap/design exposure hypothesis**, not by itself
a runtime defect verdict. The pilot must measure the exposure and apply the
separately preregistered Freshness Oracle.

## 3. Transport and timestamp semantics

### 3.1 Producer publish time is not carried in the setpoint message

The three library setpoint implementations explicitly publish `timestamp = 0`:

- Trajectory: `px4_ros2_cpp/src/control/setpoint_types/experimental/trajectory.cpp:30-51,54-73`;
- Attitude: `px4_ros2_cpp/src/control/setpoint_types/experimental/attitude.cpp:22-38,41-64`;
- Rate: `px4_ros2_cpp/src/control/setpoint_types/experimental/rates.cpp:21-34`.

The uXRCE-DDS receive callback deserializes and immediately publishes the
message into uORB (`src/modules/uxrce_dds_client/dds_topics.h.em:226-283`). The
generated-message template replaces a zero `timestamp` (and zero
`timestamp_sample`) with `hrt_absolute_time()` during deserialization
(`Tools/msg/templates/ucdr/msg.h.em:156-175`). Therefore, for these library
messages:

```text
setpoint.timestamp == PX4-side deserialize/receive time (approximately),
not the ROS producer callback time.
```

The producer publish time must be recorded separately by the harness in the
ROS clock domain and mapped with the existing clock bridge. PX4 receive time can
be recovered from each setpoint's uORB timestamp/ULog sample. The difference is
transport and scheduling latency, not setpoint age at the producer.

### 3.2 Consumption and downstream timestamps lose origin age

Controller consumption time is the controller-loop time at which the stored
input is actually used. It is not represented by the input message timestamp.
Moreover, each downstream stage gives its newly produced message a fresh PX4
timestamp:

- position control publishes a fresh attitude setpoint
  (`MulticopterPositionControl.cpp:603-615`);
- attitude control publishes a fresh rate setpoint
  (`mc_att_control_main.cpp:353-376`);
- rate control publishes fresh thrust and torque setpoints
  (`MulticopterRateControl.cpp:218-264`);
- control allocation publishes fresh `actuator_motors.timestamp`
  (`ControlAllocator.cpp:710-744`).

Consequently, a fresh allocator or actuator timestamp does **not** prove a
fresh external command. Reliable attribution needs the original external
setpoint timestamp carried as observation lineage alongside controller,
allocator, and writer events.

## 4. Exact External Mode health-loss state machine

The health path is independent of the setpoint timer. The library subscribes
to each `ArmingCheckRequest` and publishes a reply whenever the registration is
valid (`health_and_arming_checks.cpp:24-65`). Its four-second wall timer only
shuts the library down if PX4 stops sending requests; it does not detect a
stalled setpoint producer (`health_and_arming_checks.cpp:67,86-100`).

PX4 defines:

```text
REQUEST_TIMEOUT = 50 ms
UPDATE_INTERVAL = 300 ms
NUM_NO_REPLY_UNTIL_UNRESPONSIVE = 3
NUM_NO_REPLY_UNTIL_UNRESPONSIVE_INIT = 10
```

at `externalChecks.hpp:69-75`. The runtime state is
`waiting_for_first_response`, `num_no_response`, `unresponsive`, and
`total_num_unresponsive` (`externalChecks.hpp:81-91`). Its transitions are:

1. Registration initializes first-response waiting, count zero, and responsive
   state (`externalChecks.cpp:56-81`).
2. A reply is accepted only for an active registration, the current request
   id, and a timestamp no older than 300 ms. It resets `num_no_response` and
   clears first-response waiting (`externalChecks.cpp:229-254`).
3. Fifty milliseconds after an unanswered request, the code pre-increments the
   miss counter and flags only when
   `++num_no_response > max_num_no_reply`
   (`externalChecks.cpp:257-287`). Thus, after at least one valid reply, this
   exact revision flags on the **fourth** consecutive timed-out request, not
   the third. The source comment `3 * UPDATE_INTERVAL` is inconsistent with
   the comparison operator.
4. New request cycles begin every 300 ms (`externalChecks.cpp:290-310`). Once a
   slot is unresponsive, its bit is removed from subsequent request masks
   (`externalChecks.cpp:302-306`).
5. `checkAndReport()` maps an unresponsive mode to `mode_req_other` and emits a
   critical health failure (`externalChecks.cpp:123-139,211-219`). Health
   reporting is normally evaluated at 10 Hz or immediately after relevant
   state changes (`Commander.cpp:2042-2054`).
6. `modeCheck` clears the mode's can-run bit
   (`HealthAndArmingChecks/checks/modeCheck.cpp:181-184`),
   `modeCanRun()` rejects it
   (`failsafe/framework.cpp:707-724`), and the generic final fallback is RTL
   (`failsafe/failsafe.cpp:729-769`). Commander then installs the selected
   failsafe nav state (`Commander.cpp:2499-2554`).

The expected process-death detection latency is therefore phase-dependent:
approximately three to four 300 ms request intervals plus the 50 ms request
timeout and Commander evaluation/scheduling. It must be measured rather than
hard-coded as 900 ms. Before the first valid reply, the analogous condition is
the eleventh miss because the same strict `>` test is applied to the initial
limit of ten.

## 5. Setpoint-type semantics after producer cessation

### 5.1 Trajectory

`mc_pos_control` runs on local-position updates. A uORB update overwrites the
member `_setpoint`; without an update the previous value remains
(`MulticopterPositionControl.cpp:395-441`). The only activation guard rejects a
setpoint older than the time position control was enabled
(`:445-456`); it does not compare age on later cycles. While position control
stays enabled, the retained setpoint is passed to the controller each loop
(`:545-577`) and a fresh attitude output is published (`:603-615`). The one
second test at `:467-489` changes only takeoff intent. The 200 ms path at
`:579-600` handles a numerically invalid control update using a last-valid
setpoint; it is not a producer freshness timeout. The stored external setpoint
is cleared only when position control is disabled (`:403-414`).

Expected stale behavior: the controller continues tracking the last position,
velocity, and/or acceleration target. Physical consequence depends strongly on
which components are finite: a last absolute position tends toward hold at the
target; a finite horizontal velocity continues motion until fallback.

### 5.2 Attitude

`mc_att_control` runs on every attitude update. A newer
`vehicle_attitude_setpoint` updates the internal desired quaternion and stored
body thrust (`mc_att_control_main.cpp:248-331`). If no new message arrives,
there is no age branch: `_attitude_control.update(q)` uses the stored desired
state and publishes a new rate setpoint on every loop (`:333-376`).

Expected stale behavior: the last attitude and thrust are held by the attitude
loop. The closed attitude loop normally limits attitude error, so its physical
effect differs from an unbounded rate command, but non-hover thrust and the
pre-fault attitude still matter.

### 5.3 Rate

`mc_rate_control` runs on angular-velocity updates. Only a new
`vehicle_rates_setpoint` changes `_rates_setpoint` and `_thrust_setpoint`
(`MulticopterRateControl.cpp:125-186`). With no new message, the retained values
are used on every enabled rates-control cycle (`:188-220`), and fresh thrust
and torque outputs are published (`:231-264`). There is no input-age test.

Expected stale behavior: the last body rates and thrust remain closed-loop
targets. A nonzero roll rate can continue accumulating roll until health-driven
fallback or another route changes the control configuration; therefore this
level can produce a larger excursion than attitude or trajectory for the same
pre-revocation duration.

### 5.4 Allocator and writer

Torque updates drive `ControlAllocator::Run()`; the allocator stores the latest
torque and thrust, allocates on a torque update, then publishes actuator output
(`ControlAllocator.cpp:295-453`). The subscriptions and stored vectors contain
no freshness or route identity (`ControlAllocator.hpp:189-218`). The writer
publishes its current allocation result whenever it runs and stamps it with the
current HRT time (`ControlAllocator.cpp:710-744`). Because all three upstream
controller chains continue producing fresh torque while their input route is
active, allocator input and actuator output can continue after the producer's
last publish even though their own timestamps look fresh.

Direct actuator is intentionally excluded from flight testing in this Goal.
Source inspection nevertheless shows it is a recognized type
(`SetpointConfig.msg:9-15`) and its library publisher also uses a zero timestamp
(`px4_ros2_cpp/src/control/setpoint_types/direct_actuators.cpp:24-47`). A future
design must audit output-module retention and terminal gating separately; no
direct-actuator runtime conclusion is made here.

## 6. What is currently observable

| Required instant/evidence | Current status | Required treatment |
|---|---|---|
| `fault_injection_time` | Observable in harness clock | Emit an immutable fault marker and clock sample. |
| `producer_last_publish_time` | Not carried in PX4 setpoint | Harness marker in ROS clock domain. |
| `PX4_last_setpoint_receive_time` | Recoverable | Since producer sends timestamp zero, uCDR assigns HRT receive time; preserve all three input topics in ULog. |
| `last_fresh_setpoint_time` | Derivable | Last accepted receive time before producer cessation; policy deadline is separate. |
| `last_setpoint_consumption_time` | Trajectory update-only marker is insufficient; Attitude/Rate absent | Add periodic controller-use events with original input timestamp. |
| external allocator attribution | Existing marker proves rate-controller output, but not originating setpoint | Add source setpoint type/timestamp lineage to controller observation events and correlate within bounded scheduling windows. |
| external writer attribution | Existing writer event has writer identity only | Preserve controller lineage through allocator correlation and route epoch; do not infer from output timestamp alone. |
| health reply/health loss | Replies can be marked by harness; health loss only indirectly visible today | Add/derive last reply, first `mode_req_other`, and Commander fallback declaration. |
| fallback installation | Observable | Route epoch plus nav/control-mode change. |
| physical state/recovery | ULog supplies attitude, angular velocity, local position/velocity and land state | Extract at native ULog timestamps; no DDS topic expansion is required if coverage validates. |

The locked DDS topic list has inbound Trajectory, Attitude, and Rate setpoints
(`src/modules/uxrce_dds_client/dds_topics.yaml:173-183`).
`vehicle_angular_velocity` is not enabled as an outbound DDS topic in this
configuration (the entry is commented near line 58), so native ULog extraction
is preferred for angular-rate evidence. This avoids altering transport load.

## 7. Required observation extension

The existing route-observability patch already records route epoch, Trajectory
update, rate-controller allocator input, and final writer output, but its
Trajectory event is emitted only when the subscription updates. That proves
receipt/first use, not continued consumption of a retained command.

The freshness harness therefore needs these observation-only additions:

1. producer markers: channel state, setpoint type, values, publish sequence,
   ROS timestamp, and explicit last-publish/fault markers;
2. health markers: request id/reply sequence and last reply publish time;
3. PX4 receive events for all three input topics, using their PX4-assigned
   timestamps;
4. controller-use events for Trajectory, Attitude, and Rate on a bounded
   observation cadence, with `origin_setpoint_timestamp`,
   `origin_setpoint_type`, and current route epoch;
5. allocator-input and actuator-output events correlated to that lineage, plus
   writer id and route epoch;
6. health-loss, fallback-declared, fallback-installed, and control-mode-change
   instants;
7. ULog physical series: quaternion/Euler attitude, angular velocity, local
   position/velocity/altitude, land state, and actuator output.

Fields derivable without duplicating raw samples are:

```text
setpoint_age = consumption_time - origin_setpoint_timestamp
fault-to-* = event_time - mapped_fault_time
maximum stale age = max(setpoint_age in pre-revocation window)
route retention = fallback_installation_time - fault_time
physical excursions = extrema relative to the frozen pre-fault baseline
recovery_duration = physical_recovery_time - fallback_installation_time
```

Any PX4 changes must publish observations only. They must not be read by
Commander, controllers, allocator, or output code and must not modify control
branching, timing configuration, timeout policy, accepted messages, or
setpoints.

## 8. Why the existing Route Oracle can PASS or not trigger

Route Oracle 0.4 adjudicates declared route replacement: after PX4 declares a
source route revoked, it checks whether the old producer/controller/writer
persists and whether the target route installs. The window studied here starts
earlier:

```text
producer stops
→ external route is still declared and installed
→ retained command continues through the declared route
→ health detector eventually declares fallback
```

During that interval, route attribution can be internally consistent with the
still-declared external route. Route Oracle may therefore PASS clauses about
current-route writer identity, have no revocation clause to evaluate, or return
`NOT_APPLICABLE` when no route transition occurs (especially setpoint-only
stall with health alive). If clock, consumption, or target-window evidence is
missing it can also remain UNKNOWN. This is not a contradiction: the new
Freshness Oracle evaluates command age and pre-revocation exposure; Route
Oracle evaluates route declaration/installation/revocation after a route event.

Holding a final setpoint is not automatically a Route Oracle violation and
must not automatically be labeled a Freshness violation. In the locked source,
the only explicit configured setpoint timeout is zero/unimplemented, so bounded
retention is initially an `EXPOSURE` unless it violates a preregistered contract
or route attribution becomes inconsistent.

## 9. Relationship to upstream Issue #27514

[PX4-Autopilot Issue #27514](https://github.com/PX4/PX4-Autopilot/issues/27514),
opened 2026-05-29, describes the same broad concern: controllers lack external
setpoint freshness checks, retain the last command after process death, and
depend on the arming-check heartbeat for eventual fallback. It also calls out
the setpoint-level severity gradient and the setpoint-stalled/health-alive case.

The issue and the locked revision are **not completely identical**:

- the issue text states three missed 300 ms replies and approximately 900 ms;
  this revision's strict `++count > 3` flags on the fourth miss;
- the current message schema already contains `SetpointConfig.timeout_ms`,
  whereas the issue discusses adding a declared timeout surface;
- the field is nevertheless behaviorally inert here: PX4 does not consume it
  and the library sends zero.

Thus the source audit independently confirms the issue's qualitative mechanism
but does not yet reproduce its reported runtime duration or physical example.
The bounded pilot must independently measure those claims on the exact locked
stack. A conforming result, exposure, or natural violation remains possible;
none is predeclared by this audit.

## 10. Source-derived contract for preregistration

The formal pilot should preregister two different expectations:

- `TOTAL_PROCESS_STOP`: no freshness policy is enforced; retained-command use
  before the health-driven fallback is expected design exposure. After PX4
  declares and installs fallback, the old route must stop within the unchanged
  Route Oracle deadlines.
- `SETPOINT_ONLY_STALL`: health replies continue, so the source predicts no
  health-driven fallback and no setpoint-driven fallback. A complete bounded
  target window with retained-command influence is `EXPOSURE`, not automatic
  `VIOLATION`; use beyond a separately explicit policy deadline, incorrect
  route attribution, or continued influence after fallback can be a
  `VIOLATION`.

Missing receive timestamps, missing consumption lineage, an incomplete target
window, or an invalid clock bridge must produce `UNKNOWN` or rejection, never a
fabricated PASS/EXPOSURE/VIOLATION.
