# External RTL successor issue inventory

Date: 2026-07-19. Study namespace: `motivation/successor`.

## Scope and evidence standard

This inventory covers the two upstream cases named by the External RTL
Replacement and Expected-Successor Motivation Study. It separates a reported
runtime defect or unsupported lifecycle from application misuse, and it does
not treat a report as a local observation. Formal reproduction remains gated by
`experiments/motivation/successor/primary_reproduction_preregistration.yaml`.

The current locked versions are PX4
`4ae21a5e569d3d89c2f6366688cbacb3e93437c9` and
px4-ros2-interface-lib
`c3e410f035806e8c56246708432ded09c976434b` (`2.1.1-9-gc3e410f`). The
protected P5 v6 campaign is not an input to this study.

## Candidate summary

| candidate | upstream disposition | lifecycle category | mission consequence | reproduction priority |
|---|---|---|---|---|
| [Auterion/px4-ros2-interface-lib#162](https://github.com/Auterion/px4-ros2-interface-lib/issues/162) | Open; maintainer says the requested combination cannot currently be done | `EXECUTOR_NOT_IN_CHARGE`, then `EXPECTED_SUCCESSOR_NOT_REQUESTED` / `LIFECYCLE_DEAD_END` | Custom RTL completes above home, Land is not scheduled, aircraft remains armed and hovering | Primary |
| [Auterion/px4-ros2-interface-lib#167](https://github.com/Auterion/px4-ros2-interface-lib/issues/167) | Open; maintainer attributes the assertion to an unconditional schedule from the application's deactivation callback | `PROCESS_ASSERT_OR_CRASH`, but current evidence indicates invalid callback handling rather than a library defect | Executor process aborts during an interrupted custom takeoff | Secondary negative/control case |

## Issue 162 — replacement RTL does not activate its owner executor

### Provenance and reported workflow

- Source: [Mode Executor with RTL Internal Mode Replacement](https://github.com/Auterion/px4-ros2-interface-lib/issues/162), opened 2025-10-22.
- Closely matching PX4 source report:
  [PX4/PX4-Autopilot#25707](https://github.com/PX4/PX4-Autopilot/issues/25707), opened 2025-10-05 and closed 2025-10-17 after an explicit library-side prevention was added.
- Reported affected stack: PX4 release 1.16 (signed tag `v1.16.0`, commit
  [`6ea3539`](https://github.com/PX4/PX4-Autopilot/commit/6ea3539157ca358c70a515878b77077af7d4611d)),
  px4-ros2-interface-lib `release/1.16`, ROS 2 Jazzy, and Gazebo SITL. The
  audited current tip of that library release branch is tag `1.5.2`, commit
  [`a5b9f3c`](https://github.com/Auterion/px4-ros2-interface-lib/commit/a5b9f3cb7cb65d2be80183bad31e9a7ce9f02684), and it does not contain the
  later prevention.
- Public trigger: a manual/QGC RTL request or an RTL-producing failsafe selects
  an external custom mode registered as the internal RTL replacement.
- Preconditions: the custom RTL is also the owned mode of a Mode Executor; its
  final waypoint is above home; completing the custom mode is expected to let
  the executor schedule Land and then wait for disarm.

### Expected and observed lifecycle

Expected:

```text
RTL request
→ replacement Custom RTL selected
→ owning executor in charge
→ Custom RTL completion delivered to executor
→ Land requested and selected
→ Land route installed
→ Disarm
```

Reported:

```text
RTL request
→ replacement Custom RTL selected
→ executor remains Autopilot (ID 0)
→ Custom RTL reaches home and completes
→ no executor-owned Land request
→ aircraft remains armed and hovering
```

Issue #162 reports the final hover directly. The PX4 issue independently
identifies the same ownership split: the executor is selected from the internal
RTL *intention*, while replacement is applied to the selected navigation state.
The maintainer calls the manual-request behavior a bug, but states that
executors are explicitly unsupported for failsafe actions because failsafe
selection would override executor-scheduled modes.

### Source attribution and current status

The locked PX4 source still has the two decisions on separate paths:

- [`ModeManagement::onUserIntendedNavStateChange()`](https://github.com/PX4/PX4-Autopilot/blob/4ae21a5e569d3d89c2f6366688cbacb3e93437c9/src/modules/commander/ModeManagement.cpp#L419-L439)
  derives the executor from the user-intended nav state;
- [`getNavStateReplacementIfValid()`](https://github.com/PX4/PX4-Autopilot/blob/4ae21a5e569d3d89c2f6366688cbacb3e93437c9/src/modules/commander/ModeManagement.cpp#L441-L465)
  independently maps an internal nav state to its responsive external
  replacement;
- [`Commander::updateFailsafe()`](https://github.com/PX4/PX4-Autopilot/blob/4ae21a5e569d3d89c2f6366688cbacb3e93437c9/src/modules/commander/Commander.cpp#L2527-L2534)
  publishes the replaced `nav_state` beside `modeExecutorInCharge()`.

The immediate upstream mitigation is px4-ros2-interface-lib commit
[`dce6c1f`](https://github.com/Auterion/px4-ros2-interface-lib/commit/dce6c1f2e4a29e947fd32a84c4981773f1962c03),
`mode_executor: prevent mode replacing another mode`. It throws during
`ModeExecutorBase` construction when the owned mode replaces an internal mode.
Its parent
[`755f8ee`](https://github.com/Auterion/px4-ros2-interface-lib/commit/755f8eeacf19719a43ddef84f66640ff19702bc3)
is the last main-line revision before that guard. The guard is present in the
current locked library commit `c3e410f`; it is absent from `release/1.16`.

This mitigation prevents the unsupported combination; it does not implement
the requested successor lifecycle. The issue therefore cannot be replayed
unchanged on the current locked library: construction is expected to fail
before registration. A historical affected replay is required to observe the
runtime ownership/successor failure.

### Documentation gap

The locked official PX4 documentation separately says that a mode executor
activates through its owned mode and waits for completion, and that an external
mode may replace RTL for both user and failsafe selection:

- [Mode/Mode Executor definitions](https://github.com/PX4/PX4-Autopilot/blob/4ae21a5e569d3d89c2f6366688cbacb3e93437c9/docs/en/ros2/px4_ros2_control_interface.md#mode-executor)
- [Replacing an Internal Mode](https://github.com/PX4/PX4-Autopilot/blob/4ae21a5e569d3d89c2f6366688cbacb3e93437c9/docs/en/ros2/px4_ros2_control_interface.md#replacing-an-internal-mode)

The combination is not described there as unsupported. The library constructor
is the effective current constraint. This makes #162 both a historical runtime
ownership problem and a current documented lifecycle/composability gap.

### Oracle detectability

The existing Route Oracle 0.4 can establish that the replacement Custom RTL
route was selected and remained installed, but a route-only PASS would not
prove lifecycle progress. The Successor Progression Oracle must additionally
require:

1. `executor_in_charge == registered_owner_executor` while the owned Custom
   RTL is active;
2. a completion event for the active mode and delivery to that executor;
3. a Land request from the expected owner within the preregistered deadline;
4. Land selection and a distinct successor route epoch;
5. external producer release, Land completion, and terminal disarm.

The first failed obligation is expected to be `EXECUTOR_NOT_IN_CHARGE`; the
downstream observable consequence is `EXPECTED_SUCCESSOR_NOT_REQUESTED`, then
`UNEXPECTED_HOVER_AFTER_COMPLETION` / `DISARM_NOT_REACHED`.

## Issue 167 — assertion after interrupted schedule request

### Provenance and reported workflow

- Source: [Mode executor crashes when sending a mode schedule request](https://github.com/Auterion/px4-ros2-interface-lib/issues/167), opened 2025-11-22 and still open.
- Reported library revision:
  [`1624b2d`](https://github.com/Auterion/px4-ros2-interface-lib/commit/1624b2d3eedea2e5dc5081cd7a0d299fa9c72ee2), which is contained in tags
  `2.0.0`, `2.1.0`, and `2.1.1`.
- Public reproducer: [benchaso/flight-manager](https://github.com/benchaso/flight-manager).
- Trigger: schedule custom takeoff, then request Position before takeoff reaches
  its completion altitude.
- Reported consequence: `ScheduledMode::activate()` reaches `assert(!active())`
  and aborts the executor process.

### Maintainer analysis

The mode request cancels the active scheduled takeoff. Cancellation invokes the
application's completion callback with `Result::Deactivated`. The public
reproducer callback unconditionally advances to Position, and its `runState()`
does not reject a non-success result. At the same time, the explicit Position
request is scheduling Position, so the callback attempts a second activation
while the first request is active. The library assertion is intended to reject
that overlapping schedule.

The maintainer points to the official example's result check and recommends at
minimum ignoring `Result::Deactivated`. There is no upstream fix PR or commit;
the issue remains open pending confirmation from the reporter. Removing the
assertion suppresses the symptom but does not repair the overlapping lifecycle
request.

### Classification and Oracle relevance

On present evidence this is not a confirmed natural library defect. It is a
valuable legal-interruption testcase for ownership and completion handling,
but the correct expected lifecycle includes a deactivation result and forbids
the callback from unconditionally scheduling a successor. A future replay
would classify the upstream reproducer's abort as `PROCESS_ASSERT_OR_CRASH`
while attributing the initiating contract violation to the application. It is
secondary to #162 because it does not demonstrate a missing expected successor
under correct callback handling.

## Primary-target decision

Issue #162 is the primary reproduction target.

1. **Best repeatable problem:** #162 has the clearest safety chain and mission
   consequence: External RTL finishes above home but Land and Disarm do not
   follow because the intended executor never owns the lifecycle.
2. **Direct current-version replay:** no. Locked px4-ros2-interface-lib
   `c3e410f` contains the constructor guard and should reject the composition
   before registration. This expected rejection must be recorded, not called a
   successful successor chain.
3. **Historical checkout required:** yes. Start with the reported
   `release/1.16` commit `a5b9f3c`; retain `755f8ee` as the main-line pre-guard
   comparison if API compatibility makes it cheaper.
4. **Current status:** the runtime composition is prevented, not functionally
   fixed. PX4's underlying intention/replacement split remains in the locked
   source, and failsafe-owned executors remain explicitly unsupported.
5. **Oracle detectability:** Route Oracle 0.4 alone is insufficient; the new
   Successor Progression Oracle can detect the missing owner, request,
   installation, Land, and Disarm obligations without weakening route rules.
6. **Successor/ownership gap:** yes. #162 directly joins replacement-route
   selection to an executor-ownership gap and a missing Land successor.

The first formal attempt may run only after the primary preregistration fixes
the exact revisions, lifecycle profile, deadlines, acceptance criteria, and
environment-failure rules.
