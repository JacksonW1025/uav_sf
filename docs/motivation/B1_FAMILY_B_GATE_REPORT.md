# B1 Registered Controller Inventory and Family B Gate

Date: 2026-07-22
Disposition: `ENVIRONMENT_BLOCKED`

## 1. Scope and research questions

B1 is a revision-locked flight-safety validation and software-reliability
study of PX4 registered controller-graph replacement. It asks which concrete
registered controllers exist, what portions of the classic multicopter graph
they replace, whether controller/allocator/writer lineage and restoration are
observable, whether a deterministic reference is bounded, and whether later
Family B campaign work is justified. It does not rank controller performance,
models, policies, planners, airframes, or real-flight capability.

## 2. Starting and final repository identity

- B1 starting HEAD: `e7b28518bdd3afc58696878bf1c0f2b39fd8e218`.
- Preregistration: `792a36d6ff9a26202e9fde31e4b085eff90b65c8`.
- Preregistration identity activation: `4c48621e08027c4a8eeff206d7fd63bfe55257c4`.
- Reference implementation amendment: `091f48ddd1776af0d54d22b51d466377547b6374`.
- Reference identity lock: `0cb95ef61781fa87e69f50ccb18bc41acbdefe5e`.
- Formal attempts used repository commit `0cb95ef61781fa87e69f50ccb18bc41acbdefe5e`.
- The final scoped B1 commit is the commit containing this report; no history
  was rewritten.

## 3. Exact dependency identity

| Dependency | Exact identity |
|---|---|
| PX4-Autopilot | `4ae21a5e569d3d89c2f6366688cbacb3e93437c9` |
| PX4 Gazebo source | `bb0b9cf974acf4f1bcb5f5fcf80b88841562dea9` |
| px4_msgs | `18ecff03041c6f8d8a0012fbc63af0b23dd60af1` |
| px4-ros2-interface-lib | `c3e410f035806e8c56246708432ded09c976434b` |
| Host/toolchain | Ubuntu 22.04.5 arm64; GCC/G++ 11.4.0; CMake 3.22.1; Python 3.10.12 |
| ROS/DDS | ROS Humble; `rmw_fastrtps_cpp` 6.2.10 |
| Container identity | `ros:humble-ros-base-jammy`, arm64 digest `sha256:9bdda47f584f33aae18456225a8a95fe7bcde821727757f02a3252cbc46e8188`; defined but not executed |
| SITL | `px4_sitl_default`, `gz_x500`, default world, airframe 4001 |

World/model, parameter, source, collector, Oracle, schema, controller, and
tooling hashes are frozen in `source_lock.yaml` and `build_manifest.json`.

## 4. Inventory method

The audit searched the locked PX4 and interface-library trees for
`RegisterExtComponentRequest`, `register_ext_component_request`,
`SetpointConfig`, registration lifecycle handling, `mc_nn`, `mc_raptor`,
Control Allocator inputs, direct actuator outputs, VehicleControlMode flags,
controller setpoint layers, module stop/unregister paths, and classic
restoration. Every concrete subject was traced from registration through
activation, configured setpoint type, input, output, allocator participation,
final writer, release, and fallback. Retained `family_b/` assets were checked
only as historical leads against the current dependency identity.

## 5. Complete subject inventory

The inventory contains 8 subjects: 2 concrete true registered controller
routes, 1 candidate/implemented partial-subgraph reference, 1 classic
baseline, and 4 exclusions. There are no unresolved rows.

| Subject | Classification | Decision |
|---|---|---|
| PX4 classic cascade | `ORDINARY_INTERNAL_MODULE` | baseline |
| Commander registration infrastructure | `ORDINARY_INTERNAL_MODULE` | exclude as subject |
| `mc_nn_control` | `TRUE_REGISTERED_CONTROLLER_ROUTE` | real subject, static only |
| `mc_raptor` | `TRUE_REGISTERED_CONTROLLER_ROUTE` | real subject, static only |
| locked interface examples | `SETPOINT_PRODUCER_ONLY` | exclude |
| DirectActuators API | `EXCLUDED` | no concrete subject |
| retained `family_b/` overlays | `EXCLUDED` | historical identity only |
| B1 deterministic reference | `PARTIAL_CONTROLLER_SUBGRAPH_REPLACEMENT` | selected reference |

The field-complete source evidence is in `inventory.tsv`.

## 6. Inclusion and exclusion rationale

A subject is included only when its configured setpoint type changes classic
controller participation, allocator participation, or authoritative writer
lineage and it has a concrete controller implementation. Commander is the
mechanism rather than a subject. The generic DirectActuators API is capability,
not an implementation. Existing attitude/rate/trajectory examples register
modes and publish setpoints but do not provide an independent replacement
controller law. Retained Family B overlays target an older setup, reference a
missing setup script, and delegate to `mc_nn`/RAPTOR rather than define a new
controller.

## 7. mc_nn analysis

1. It publishes an in-process `RegisterExtComponentRequest` for a mode and
   arming check, using request ID 231.
2. It becomes active when `vehicle_status.nav_state` equals the assigned mode
   ID, then publishes `SetpointConfig::TYPE_DIRECT_ACTUATORS`.
3. That configuration disables `mc_pos_control`, `mc_att_control`,
   `mc_rate_control`, and `control_allocator`.
4. It consumes trajectory/manual target, local position, attitude, and angular
   velocity and publishes `ActuatorMotors`.
5. Control Allocator does not participate.
6. `mc_nn_control` is the authoritative direct actuator writer.
7. A normal mode exit stops neural output; module stop unregisters the mode;
   Commander selects Hold when active unregister is processed and resets the
   setpoint configuration for the next internal mode.
8. The locked tree has a `px4_sitl_neural`/gz_x500 source path.
9. It embeds a TensorFlow Lite model and model-specific parameters, but no
   special hardware is required for the documented SITL path.
10. It is a controller-specific real subject, not a neutral infrastructure
    subject. Its learned control law and direct actuator output confound the
    route-only question.

## 8. RAPTOR analysis

1. It publishes an in-process registration request for a mode and arming
   check, using request ID 1337; it may replace Offboard.
2. It becomes active when nav state equals its assigned mode ID and applies
   `TYPE_DIRECT_ACTUATORS`.
3. It bypasses the complete classic cascade and Control Allocator.
4. It consumes trajectory/internal reference, local position, attitude, and
   angular velocity and publishes `ActuatorMotors` plus status/input telemetry.
5. Control Allocator does not participate.
6. `mc_raptor` is the authoritative direct actuator writer.
7. Normal exit stops output; stop unregisters; Commander applies its existing
   active-unregister fallback and next-mode graph restoration.
8. The source documents `px4_sitl_raptor` with gz_x500.
9. The locked local checkout lacks initialized policy/rl_tools submodules and
   the runtime requires a policy archive or embedded checkpoint.
10. It is a controller-specific subject, not an infrastructure reference.

## 9. Other candidate analysis

The locked interface library proves the generic registration and setpoint
configuration mechanism, including an actuator-direct API, but supplies no
additional concrete closed-loop registered controller suitable for this Gate.
The current `family_b/` directory is retained provenance only. The selected B1
reference is an isolated ROS 2 `ModeBase` controller with a deterministic
altitude PD law, latched yaw, level attitude, finite checks, and thrust clamped
to `[0.35, 0.65]`.

## 10. Controller-graph model

`ModeUtil::getControlMode()` maps setpoint type to graph participation:

| Route profile | Active graph |
|---|---|
| Classic trajectory | position → attitude → rate → allocator |
| B1 reference attitude | B1 altitude/attitude controller → attitude → rate → allocator |
| Rates | external rates → rate → allocator |
| Thrust and torque | external wrench → allocator |
| Direct actuators | external writer; classic cascade and allocator bypassed |

This source-backed mapping is stronger than a module name or active-process
claim, but static mapping alone does not prove a runtime installation.

## 11. Allocator and writer model

`mc_nn` and RAPTOR bypass the allocator and directly write ActuatorMotors.
Their direct writer hooks are not present in the current observation patch, so
runtime writer attribution for those subjects is incomplete. The reference
retains Control Allocator. Its intended lineage is reference process/session
→ VehicleAttitudeSetpoint → attitude consumption → rate controller torque and
thrust → Control Allocator → ActuatorMotors. The final writer string remains
`control_allocator` before, during, and after the reference route; route epoch
and upstream consumption, not the writer name, must distinguish ownership.

## 12. Observability audit

The 24-row audit establishes a complete observation contract for the selected
reference profile. Registration request/reply, nav-state route epoch,
VehicleControlMode, setpoint topics, controller consumption, allocator input,
final writer sequence, actuator output, release, and restored classic
consumption are directly observable or derivable with complete lineage.
Registration/session rollover remains derivable with limitation outside one
boot. The reference adds only process-side structured identity/output markers;
existing PX4 hooks are observation-only and do not feed control decisions.

The audit does not claim runtime completeness because no accepted combined
build authorized runtime. Accordingly final writer, graph, and restoration
observability are `NOT_RUNTIME_CONFIRMED` even though their static contracts are
complete.

## 13. Missing evidence

- No B1 reference binary was produced within the accepted build cap.
- No controller loadability, registration, activation, installation,
  reference window, normal release, controlled stop, or restoration window was
  executed.
- `mc_nn` and RAPTOR direct actuator writers remain uninstrumented.
- No runtime clock bridge or route trace exists for B1.
- Re-entry within one boot was not tested.

## 14. Reference subject feasibility decision

B1-C satisfied all 12 preregistered authorization clauses and authorized
`b1_deterministic_attitude_reference`, conditional on a separately pushed
amendment and one accepted B1-D combined build. The amendment was pushed before
formal attempts. The implementation is bounded and does not change Commander,
Control Allocator, classic controller semantics, fallback, Oracle thresholds,
attempt caps, or safety bounds. The later build-cap failure revoked runtime
authorization; it does not retroactively change the B1-C feasibility decision.

## 15. Implementation summary

The implemented reference consumes `VehicleLocalPosition` z, vertical
velocity, and heading. On activation it latches z/yaw, publishes level
`VehicleAttitudeSetpoint`, and applies a finite saturated altitude PD term to a
fixed hover thrust. It does not copy or forward classic output, use a model,
write motors, modify route selection, or provide random behavior. An isolated
B1-only colcon package avoids modifying files protected by prior-stage hashes.
A bounded monitor, controlled process-stop marker, per-run summarizer, logger
profile, and focused tests were added.

## 16. Build and static probe result

Target: 1 accepted combined PX4-observability plus reference build; maximum 3
formal attempts. Result: `0 accepted / 3 attempts`.

| Attempt | Classification | Result |
|---|---|---|
| `b1d_build_a1` | `CAMPAIGN_CONFIGURATION_FAILURE` | generated gz pytest cache tripped clean-source guard before build |
| `b1d_build_a2` | `CAMPAIGN_CONFIGURATION_FAILURE` | PX4 built 1214 targets; colcon rejected misplaced global `--log-base` before reference configure |
| `b1d_build_a3` | `CAMPAIGN_CONFIGURATION_FAILURE` | shared patch idempotency check rejected the correctly base+incrementally patched worktree before build |

The attempt-2 PX4 component binary has SHA-256
`84c4ca62868f02a0434bcce503d6baf5ff4f538678ccb4eeb2a5bd1fa91323ce`.
It is component evidence only. The reference binary is absent; combined build
success and loadability are false. The third attempt reached the frozen cap,
so no further build was performed.

## 17. Normal baseline attempts and results

B1-E was not authorized because B1-D had no accepted combined build. It is
`NOT_APPLICABLE`, with `0 accepted / 0 attempts` against a target of 3 and cap
of 6. No runtime result is reported.

## 18. Recovery attempts and results

B1-F was not authorized because B1-E was not executed. It is
`NOT_APPLICABLE`, with `0 accepted / 0 attempts` against a target of 3 and cap
of 6. No controlled stop was executed.

## 19. Evidence admissibility

Admissible evidence comprises locked-source inventory, source paths and
mechanisms, complete feasibility/observability matrices, pushed source and
tool hashes, focused tests, three append-only formal build records, raw build
logs, and the attempt-2 PX4 binary manifest. No old Family B runtime asset, no
diagnostic outcome, and no partial component build enters a runtime or accepted
build denominator.

## 20. Attribution boundaries

Static source establishes possible graph configuration, not a realized route.
A successful PX4 component build does not establish the reference build,
loadability, registration, installation, or restoration. A shared
`control_allocator` name is not route identity. Controller performance would
not by itself establish a route violation. No absent natural violation or
unexecuted runtime is interpreted as conformance.

## 21. Family A abstraction reuse

Family A's route instance, command lineage, route epoch, clock bridge,
revocation, installation, exclusivity, continuity, and recovery abstractions
were reused at the static design and per-attempt adjudication level. The
reference profile shows how they descend through controller consumption and
allocator input to the final writer. Runtime reuse was not validated because
B1-E/F were not authorized.

## 22. Family B representativeness

The locked tree contains two concrete full direct-actuator registered routes
and one bounded partial-subgraph reference design. This is enough to show that
Family B is a real, heterogeneous mechanism class, but not enough to represent
all PX4 controller replacement. The two real subjects share learned-policy and
direct-writer confounds; the reference was not built or flown.

## 23. Recommended paper role

Family B should remain `future work`. It should not enter the main evaluation
or supplementary runtime validation on B1 evidence. The source inventory and
Gate may be mentioned as scope justification, with the environment block and
missing direct-writer/runtime evidence explicit.

## 24. Final disposition

`ENVIRONMENT_BLOCKED`. B1 is compliantly closed because the formal build cap
was reached and all non-accepted attempts are preserved. It does not authorize
a full Family B campaign. This is not a negative claim that PX4 lacks
registered controllers; two true routes were found and a bounded reference was
authorized and implemented at source level.

## 25. Claim boundaries

B1 may claim the inventory counts and classifications, the source-backed graph
model, the selected reference's bounded design, the static observation
contract, and the exact build-cap outcome. It may not claim runtime handoff,
writer exclusivity, route continuity, classic restoration, controller safety
ranking, general Family B safety, state-aware search effectiveness, random
campaign authorization, or completion of M-FINAL.

## 26. Next registered phase

B1 authorizes only progression to the registered `M-FINAL` bookkeeping and
unified Gate. M-FINAL has not started. B1 authorizes neither a random campaign
nor complete Stateful Testing.
