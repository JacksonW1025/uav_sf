# Phase A completion report

Date: 2026-07-16

## 1. Git boundary

- Starting HEAD: `2b439e393d782332eec1e4724e90d675b4276cd7`.
- Protected recovery tag: `pre-route-transition-cleanup-20260716`.
- Final HEAD reference: the pushed `main` commit containing this report; its
  exact SHA is verified with `git rev-parse HEAD` and `origin/main` in the
  terminal completion record. (A commit cannot contain its own SHA.)
- Only `main` was changed; history was not rewritten and no force push was
  used.

## 2. Repository convergence

The complete 628-file `archive/pre_v4_baton/` was removed. Across the two
convergence commits, 646 obsolete files were deleted from `main`, including
old narrative copies, campaign reports/results, plots, compatibility wrappers,
duplicated tests, archive indexes, old experiment YAML, and obsolete active
analysis/probe code. The only narrative files now tracked are
`docs/narrative/CURRENT_NARRATIVE.md` and `docs/narrative/SCOPE.md`.

Reusable tracing and attribution concepts were reduced to active,
campaign-independent components:

- `scripts/tracing/route_trace_collector.py`;
- `scripts/tracing/actuator_writer_collector.py`;
- `scripts/analysis/summarize_route_trace.py`;
- the lock/patch checking and repository validation helpers.

They have no old campaign theta, property/severity, RAPTOR status, or mc_nn
message dependency. Legacy recovery is represented only by
`docs/repository/LEGACY_RECOVERY.md` and the protected tag.

The minimal future Family B surface is 12 files: one README, two board
overlays, one SIH airframe, one reproduction configuration, one observation
shim patch, and six setup/build scripts. It is optional, excluded from the
Family A profile, contains no retained campaign conclusions, and must be
revalidated before use.

## 3. Locked dependencies and environment

| Dependency | Exact identity |
|---|---|
| PX4-Autopilot | `4ae21a5e569d3d89c2f6366688cbacb3e93437c9` |
| px4_msgs | `18ecff03041c6f8d8a0012fbc63af0b23dd60af1` |
| px4-ros2-interface-lib | `c3e410f035806e8c56246708432ded09c976434b` |
| Micro-XRCE-DDS-Agent | `73622810d984349b80bbac0ef55fc0b694d62222` |
| Ubuntu base image | `public.ecr.aws/docker/library/ubuntu@sha256:786a8b558f7be160c6c8c4a54f9a57274f3b4fb1491cf65146521ae77ff1dc54` |

The captured environment is aarch64, Ubuntu 24.04, ROS 2 Jazzy, Gazebo
Harmonic, GCC 13.3.0, CMake 3.28.3, and Python 3.12.3. Apt, Python, and
toolchain snapshots are tracked under `data/processed/environment/`. Normal
setup reads the lock, checks exact HEAD/remote/clean state, and cannot advance a
revision implicitly; `--update-lock` is explicit.

## 4. Family A build

`./scripts/setup/bootstrap_family_a.sh` completed with
`FAMILY_A_BOOTSTRAP=PASS`. Micro XRCE-DDS Agent, locked PX4, px4_msgs,
px4_ros2-interface-lib, the official examples, and the local External
Mode/Executor package built. Colcon reported 18 packages complete. The official
multicopter go-to External Mode, mode-with-executor, multiple-modes, RTL
replacement, setpoint/navigation, rover, VTOL, and Python examples all have
source-audited inventory rows and build status PASS. Official example binaries
were not mislabeled as directly run; P0 used the local locked-source adapter
and executor derived from the documented API.

The observation patch also applied to the exact PX4 commit and the patched
`px4_sitl_default` binary linked successfully.

## 5. P-1 observability

All 14 route fields are classified: 4 DIRECT, 7 DERIVED,
3 INSTRUMENTATION_REQUIRED, and 0 UNOBSERVABLE. Every DIRECT/DERIVED row names
its locked source symbol, signal, collector, timestamp source, confidence, and
limitation.

PX4 boot/uORB/ULog timestamps can be ordered within a boot. ROS node, DDS
receive, simulation, and wall clocks remain distinct until an offset segment
or clock bridge is measured. The P0 summary therefore reports each domain
separately and does not compute cross-domain overlap/gap.

Native uORB/ULog does not retain publisher identity and an XRCE-delivered ROS
identity is not preserved after the uORB boundary. The minimal observation-only
PX4 patch adds a rate-limited structured `route_observability` topic at:

1. multicopter trajectory-setpoint consumption;
2. `mc_rate_control` allocator-input publication;
3. `control_allocator` actuator-output publication.

It changes no setpoint, control decision, scheduling policy, or algorithm and
uses no high-rate printf. The collector can now distinguish producer
publication from PX4 consumption and explicitly attribute the final writer in
the covered multicopter route.

P-1 gate result: **PASS, 10/10**, with no blocking items.

## 6. M2 registration study

Thirteen locked-source evidence entries cover request/reply registration,
admission/setpoint configuration, activation/deactivation, completion,
executor scheduling, replacement mapping, health/unresponsive detection,
unregistration, fallback selection, official integration assertions, and the
supplemental Family B facility association.

Registration allocates capability/IDs but does not activate the route.
Activation follows nav/arming state and starts the declared setpoint data
plane. Completion and fallback selection are also distinct from proof that the
successor route is completely installed. Node loss combines explicit graceful
unregistration with PX4 health timeout for crashes; neither mechanism alone
proves final writer/module recovery. This explicit lifecycle and its gaps make
the facility an independent test target. Family B reuses registration and
arming-check facilities, but its data plane is not part of the Family A result.

## 7. M4 official-test audit

Fifteen source/assertion-backed rows cover PX4 units, SITL integration,
px4-ros2-interface-lib units/integration, official examples, executor and mode
replacement, Offboard loss/failsafe, registration, and supplemental Family B
tests. Official coverage establishes substantial nav-state/mode state,
fallback-selection, and basic-execution behavior.

The audited tests do not establish concrete producer/writer identity, timely
old-route revocation, complete target-route installation, overlap/gap,
re-entry residue, or complete recovery. Those remain later-oracle obligations.

## 8. P0 baseline

Because P-1 passed, three low-risk normal runs were executed:

- P0-A Offboard: PASS, 2,231 canonical events, 183 producer and 387 PX4
  consumption events, maximum observed age 6.597 ms.
- P0-B Dynamic External Mode: PASS, 2,188 events, successful registration as
  mode 23, single completion/deactivation, and RTL/disarm.
- P0-C Mode Executor: PASS, 2,005 events; ready, arm, takeoff, external mode,
  RTL, and wait-disarmed results were all Success.

All three attributed allocator input to `mc_rate_control` and actuator output
to `control_allocator`. Compact traces validate against the canonical schema
and summaries contain raw-artifact SHA-256 digests. Raw ULogs/logs remain
ignored under `runs/`.

P0-B/C ended disarmed but with selected `nav_state` returning to the still
registered external ID 23. This is recorded as residue/limitation and is not
promoted to a bug claim or complete-recovery evidence. No fault injection,
process-kill experiment, RC contention, high-speed/high-attitude command,
random search, P2/P3/P5 work, or full fuzzer was started.

## 9. Validation and final state

The repository validator covers lock/floating-ref checks, narrative uniqueness
and forbidden legacy headlines, Family A import boundaries, JSON/YAML/TSV and
JSON-schema contracts, Markdown links, shell/Python syntax, pytest, whitespace,
tracked-ignored/untracked/raw-run audits, and the 10 MiB tracked-file ceiling.
The final run passed all tests. Final push verification requires a clean status,
zero unpushed commits, zero unexpected untracked files, zero tracked ignored or
tracked `runs/` files, and zero tracked files over 10 MiB.
