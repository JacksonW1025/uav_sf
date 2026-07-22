# W1 Real-Workload Runtime/Trace Spike Report

Date: 2026-07-22

Disposition: `MEASUREMENT_INSUFFICIENT`

## Executive conclusion

W1 closed when W1-B reached its frozen three-attempt cap with zero accepted
source traces. All three formal attempts are excluded `FORMAL_SAFETY_STOP`
results. Attempt 1 crossed the speed boundary after entering go-to and also
lost the observation-only sidecar at startup. Attempt 2 crossed the altitude
boundary during internal takeoff. Attempt 3 crossed the speed boundary after
internal-to-Offboard installation; its normal Land/Disarm cleanup did not
complete, PX4 aborted, and its direct-timesync clock bridge was `DEGRADED`.

No accepted source trace exists. The mandatory ordering therefore made W1-C
trace-only replay and W1-D Canonical Adapter command replay not applicable;
both have zero attempts. The source audit found no Native Adapter semantic gap,
so W1-E was not authorized and also has zero runtime attempts. W1 establishes
neither new route/lifecycle semantics nor accepted timing/physical-context
value. These are unavailable measurements, not negative claims about the
workload or SUT behavior.

## Scope and research question

This was a bounded PX4/Gazebo SITL flight-safety validation of Aerostack2
software reliability, runtime consistency, lifecycle transition, route
conformance, trace acquisition, and deterministic replay. It used public ROS 2
and PX4 interfaces, observation-only instrumentation, and controlled local
process stop. It did not use random exploration, direct-actuator flight, HITL,
real flight, an external aircraft, or a third-party system.

The frozen question asked whether one real ROS 2 UAV workload adds route,
producer/session, lifecycle, recovery, setpoint, or publication-timing
information beyond synthetic behavior and official examples, while keeping
task transitions distinct from route replacements.

## Repository and source identity

- W1 starting repository HEAD:
  `6f5abd682cca47b9e8febdbdcfb8ea0a9714e236`.
- Preregistration commit, pushed before formal runtime:
  `1f41229d17e42af6945bd040ccb1579128b1229e`.
- Source/build audit amendment:
  `a599cffffd29bf64072dc84cf338d43575d48c97`.
- Runtime tooling checkpoint:
  `b1b0b32671c8fb02dd63b719c9fe7718e5deaa4f`.
- Runtime amendments used by attempts 2 and 3:
  `a394d0f92c0ff8339ccb272e0b4d66d0bdb736b6` and
  `b29949654070c45ceb7fb2135eaa12c9951ab87b`.
- Final repository identity is the pushed closure commit containing this
  report and Gate; its exact hash is verified in the post-push handoff.

The primary workload was Aerostack2 commit
`a8e7318b8d1d7c5adc580e8a16374357773bc11a`. Its exact PX4 platform plugin was
`as2_platform_pixhawk` commit
`482563ba979baea965df918995c141a362e26637`, and the simulation project was
`project_px4_vision` commit
`22d945c956ae234839b3c48555ab2c1ba40eaee3`. The flight stack used PX4 commit
`4ae21a5e569d3d89c2f6366688cbacb3e93437c9`, `px4_msgs` commit
`18ecff03041c6f8d8a0012fbc63af0b23dd60af1`, and
`px4-ros2-interface-lib` commit
`c3e410f035806e8c56246708432ded09c976434b`.

The complete simulator model/world hashes, ROS and package snapshot, DDS,
compiler/build, container digest, mission configuration, local executable, and
collector/adapter hashes are in the [source lock](../../experiments/motivation/w1_workload/source_lock.yaml).

## Source/build/interface audit

The [W1-A audit](W1_AEROSTACK2_SOURCE_BUILD_AUDIT.md) recorded four non-formal
build diagnostics. A minimal compatibility patch adapted observation fields to
the locked `px4_msgs`; it did not change mission, route, setpoint, mode,
fallback, controller, writer, or lifecycle behavior. After the missing exact
`mocap4r2_msgs` dependency was locked, the required Aerostack2 task stack built
successfully. No fallback workload was needed.

The audit found public arm and Offboard services, internal takeoff and aircraft
Land commands, go-to and follow-path action goal/feedback/result/cancel
interfaces, motion-reference topics, alerts, platform status, ROS clock, and
PX4 observation paths. Go-to and follow-path use different upstream behavior
publishers but the same position-reference interface, PID speed controller,
`as2_platform_pixhawk` PX4 producer, `TrajectorySetpoint` path, controller
chain, allocator input, and final `control_allocator` writer. Follow-path
cancel produces hover at the task layer; the source audit did not classify it
as route replacement.

## Native Adapter Gate

The source audit set:

- `native_adapter_adds_new_semantics: false`;
- `estimated_integration_cost: MEDIUM`;
- `native_spike_authorized: false`; and
- `decision: NOT_APPLICABLE_NO_NEW_ROUTE_OR_LIFECYCLE_SEMANTICS`.

No workload-specific PX4 route owner, final producer/session, controller,
writer, cancel fallback, completion, or recovery semantic absent from the
Canonical Adapter was found. W1-E therefore has zero runtime attempts and is
`NOT_APPLICABLE`. This source decision is narrower than a runtime claim that
Aerostack2 has no value.

## Mission and trace acquisition method

The frozen mission was internal ground, arm, internal takeoff to 1.5 m,
Aerostack2 Offboard, go-to, follow-path, cancel to hover, explicit aircraft
Land, and disarm. The horizontal task extent was at most 5 m; maximum altitude
was 3 m; commanded horizontal/vertical speed limits were 1.0/0.6 m/s;
acceleration, attitude, angular-rate, and yaw-rate limits were also frozen.

A sidecar subscribed to services/actions, motion references, platform and
controller status, PX4 nav state, setpoints, physical state, and direct
TimesyncStatus without publishing commands. Rosbag and ULog ran in parallel.
The repository route collector recovered nav state, route epochs, controller
consumption, allocator input, and final-writer lineage. Raw artifacts remained
under the ignored `runs/motivation/w1_workload/` tree; only compact summaries
and hashes are tracked.

## Formal attempt accounting

| Attempt | Seed | Completed mission phases | Classification | Terminal evidence |
|---|---:|---|---|---|
| `w1b_seed510101_a1` | 510101 | through go-to | `FORMAL_SAFETY_STOP` | speed 3.200 m/s; sidecar startup failure; clock invalid; Land/Disarm not observed; controlled process stop clean |
| `w1b_seed510102_a2` | 510102 | through internal takeoff | `FORMAL_SAFETY_STOP` | altitude 3.008 m; Land/Disarm complete; direct-timesync diagnostic `VALID`; controlled process stop clean |
| `w1b_seed510103_a3` | 510103 | through go-to | `FORMAL_SAFETY_STOP` | speed 3.182 m/s; clock `DEGRADED`; Land/Disarm incomplete; PX4 abort; controlled process stop clean |

The accepted/rejected accounting is 0 accepted from 3 W1-B attempts and 3
excluded formal safety stops. W1-C, W1-D, and W1-E each have 0 runtime
attempts. No failed attempt was deleted or overwritten. None entered a SUT
violation denominator.

Attempt 1's sidecar assigned a reserved ROS node attribute; the pushed
amendment corrected that observation-only defect and made normal cleanup
continue after a latched safety stop. Attempt 2 showed that repeated public
takeoff requests reset a relative takeoff target; the next pushed amendment
issued one request and selected direct TimesyncStatus samples. The direct
33-sample diagnostic for attempt 2 was `VALID` with a 45,149,660 ns maximum
residual. These corrections did not change the mission geometry, speed,
altitude, route selection, acceptance rule, or cap.

## Source trace content and route classification

There is no accepted source trace ID. The required [trace manifest](../../experiments/motivation/w1_workload/trace_manifest.json)
therefore has status `UNAVAILABLE_NO_ACCEPTED_SOURCE_TRACE`, null bag/ULog
identity, no valid accepted clock interval, and no canonical replay IDs.

Excluded attempts 1 and 3 contain partial high-confidence route evidence for
the expected internal-to-Offboard replacement: the authority source changed
from PX4 internal control to ROS 2 Offboard while the downstream controller
chain and `control_allocator` writer remained observable. This partial evidence
is not promoted into an accepted semantic result. No accepted
Offboard-to-aircraft-Land edge exists. No attempt reached the complete
go-to-to-follow-path or cancel-to-hover edge, so W1 observed zero admissible
task-only transitions and cannot test their runtime stability.

Topic or behavior names were not used alone to classify a route replacement.
The missing complete lifecycle, valid clock, Land/Disarm, and route windows
make the relevant semantic result `UNKNOWN` under the frozen acceptance rule.

## Trace-only and Canonical Adapter replay

W1-C required an accepted W1-B trace. Because none existed, trace-only replay
was not executed: 0 accepted from 0 attempts. Consequently, there was no input
on which to establish deterministic event-sequence equality or an accepted
zero-command-publication replay result.

W1-D required an accepted W1-C result. Canonical Adapter command replay was
therefore not executed: 0 accepted from 0 attempts against a target of 3 and a
cap of 6. There are no source/replay lifecycle, publication-rate, cancel
timing, phase-duration, route-timing, physical-motion, or variance comparisons.
The absent cells are measurement-insufficient, not zero-difference results.

## Evidence admissibility and claim boundary

Each attempt produced compact workload/route summaries, ULog and rosbag hashes,
lineage counts, cleanup results, and a raw artifact-set hash. Attempts 2 and 3
had complete observation-only sidecars; attempt 3 also recorded motion
references and PX4 setpoints. They remain excluded because flight-safety,
clock, lifecycle, and terminal-cleanup requirements are conjunctive.

The tracked [compact closure summary](../../data/processed/motivation/w1_workload/w1_summary.json)
hash-locks all three per-attempt summaries and records 134,425,141 bytes of
ignored raw evidence across the three attempts.

The final disposition is `MEASUREMENT_INSUFFICIENT`, selected exactly because
the relevant formal cap was reached without evidence sufficient for a semantic
or timing disposition and without a persistent source/build/simulator
environment blocker. It is not `ENVIRONMENT_BLOCKED`: the stack built and ran,
and the campaign repeatedly reached internal takeoff or Offboard. It is not a
negative scope decision: the runtime evidence was not admissible enough to
establish that result.

This bounded study does not show that one real stack represents all UAV
workloads; that all task transitions are authority transitions; that a Native
Adapter is safer; that three replays estimate population frequency; or that a
later search method is effective. The three safety stops are not SUT
violations. Failure to establish new route semantics does not imply absence of
research value.

## Validation and integrity

The W1 focused suite passed 12 tests. The final repository validator passed all
15 stages with 244 tests and 60 checked local links. JSON/YAML parsing, W1 Gate
and unavailable-manifest schemas, source-lock hashes, shell/Python syntax,
tracked raw-run exclusion, ignored-file audit, large-file limits, and
whitespace checks passed. Recalculation of every file recorded by the three raw
artifact manifests matched its stored size and SHA-256.

After the last attempt, no PX4, Gazebo, ROS mission/recorder, Micro XRCE-DDS
Agent, or Aerostack2 process remained, and port 8888 was unoccupied. No raw
bag, ULog, build directory, external source tree, credential, or machine-local
absolute path is tracked. The protected P5 v6, Issue #162 successor,
Freshness, N1, C1, and R1 evidence was not modified.

## Final Gate and next registered phase

The [W1 Gate](../../experiments/motivation/w1_workload/w1_gate.json) records
`evidence_complete: false`, no accepted source or replay, zero Native attempts,
and the same `MEASUREMENT_INSUFFICIENT` disposition. It authorizes only
progression of the bounded registration workflow to
`B1_REGISTERED_CONTROLLER_INVENTORY_AND_FAMILY_B_GATE`. B1 has not started.
W1 does not authorize a large integration, random campaign, or full Stateful
Testing, and it creates no M-FINAL conclusion or new narrative version.
