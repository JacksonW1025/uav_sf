# P5 v5 revision-blocking issue

## Disposition

`campaign_seeded_v5` is `CLOSED_REVISION_CHANGE_REQUIRED`. No further formal
v5 runs are authorized, and no v6 campaign has been created.

The blocker was exposed by `p5_t7_turn_pair_r1`. It is a mismatch between the
preregistered T7 behavior and the frozen P5 transition-selection/acceptance
path, not a Route Oracle or SUT violation.

## Preserved evidence

- Legacy Offboard attempt 1 returned 13 after PX4 exited. Required flight,
  trace, and clock artifacts are absent, so it is preserved as an
  `ENVIRONMENT_FAILURE`.
- Dynamic External Mode attempt 1 completed with runner return 0, monitor
  status `PASS`, a `VALID` 35-sample clock bridge with 55.0 ms maximum
  residual, and a complete raw trace. It is preserved as
  `MEASUREMENT_UNKNOWN` because the selected P5 Oracle could not be produced.
- No missing evidence is promoted to PASS, and neither attempt is used in a
  paired differential result.

The artifacts remain under the ignored campaign root:

```text
runs/p5/campaign_seeded_v5/p5_t7_turn_pair_r1_legacy_offboard/attempt_1
runs/p5/campaign_seeded_v5/p5_t7_turn_pair_r1_dynamic_external_mode/attempt_1
```

## Root cause

T7 is preregistered as `liveness_on_setpoint_off`. The established P3 contract
is that proof-of-life or health remaining ON retains the external route even
when setpoints stop. The Dynamic attempt behaved accordingly: its monitor
completed the bounded observation with no `fallback_nav_state`.

The frozen P5 runner's `selected_modes()` function handles every T4 through T8
case as an external-to-fallback transition and requires an independently
observed integer fallback route. With no fallback in a conforming T7 run, it
raises `independently observed fallback route is unavailable`. The classifier
therefore returns `MEASUREMENT_UNKNOWN` before it can establish the required
selected critical window and Oracle result.

Retrying cannot resolve this mismatch: a T7 run that produces the required
fallback would contradict the preregistered liveness-on behavior, while a
conforming run cannot satisfy the current selected-transition requirement.

## Frozen-revision impact

Resolving the blocker requires changing at least one frozen campaign element:

- transition selection for retained-route T7 observations;
- the P5 accepted-run classification rule;
- the required critical-window/Oracle evidence definition for a no-fallback
  observation; or
- the scenario semantics, which is not recommended because it would erase the
  channel-decoupling behavior under study.

These changes are forbidden within v5. The campaign is therefore closed with
25 complete pairs, 50 accepted sides, one partial T7 pair, and nine untouched
pairs. The P5 Differential Gate is `INCONCLUSIVE` because the preregistered
matrix is incomplete for a measurement-design reason.

## Required next decision

Before authorizing any successor campaign, preregister a minimal retained-route
T7 observation contract that specifies:

1. which transition or stable-route window is selected when no fallback is
   expected;
2. how revocation, installation, exclusivity, continuity, and recovery clauses
   apply or become `NOT_APPLICABLE` without converting missing evidence to PASS;
3. the accepted-run requirements for that window; and
4. focused tests proving T7 accepts a conforming retained-route run and rejects
   a true missing-evidence run.

Only after that revision is reviewed, committed, and piloted may a v6 campaign
be explicitly created. T1–T6 v5 evidence must not be mixed into the successor
campaign as accepted paired sides.
