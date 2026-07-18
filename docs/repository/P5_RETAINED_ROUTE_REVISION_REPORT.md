# P5 retained-route revision readiness report

Date: 2026-07-18. Candidate contract: `p5-retained-route-observation-v1` / `1.0`.

## 1. v5 blocker summary

`campaign_seeded_v5` remains permanently `CLOSED_REVISION_CHANGE_REQUIRED` with
25/35 complete pairs and 50 accepted sides. Its T7 Dynamic attempt correctly
kept health on, stopped setpoints, retained the external route, and produced no
fallback target. The frozen selector nevertheless required an observed
external-to-fallback transition for every T4–T8 run. This was a measurement and
acceptance-contract mismatch, not a PX4 or Route Oracle violation; retrying v5
could not resolve it. The v5 manifest remains byte-for-byte unchanged at
SHA-256 `8c7727986...329c31f`.

## 2. Retained-route observation definition

`RETAINED_ROUTE` observes an already installed route over a preregistered stable
window when the action is not expected to revoke that route. It requires stable
mode, route epoch, authority, applicable registration/activation identity, and
final writer; no fallback target is invented or required. Setpoint cessation is
not treated as route revocation.

The canonical contract is `docs/design/RETAINED_ROUTE_OBSERVATION_CONTRACT.md`;
the preregistration is
`experiments/probes/p5/retained_route_revision_preregistration.yaml`.

## 3. Transition/retained-route boundary

The scenario matrix now declares observation kind explicitly: T1, T2, T4, T5,
T6, and T8 are `TRANSITION`; T7 is `RETAINED_ROUTE`. T7 is not modeled as
External-to-External because it has no source revocation, target installation,
or new route epoch. Equal transition endpoints would corrupt those clause
semantics and could hide an unexpected epoch change. T8 remains a transition
because health is removed while setpoints continue and fallback is expected.

## 4. Observation window

The existing P3 monitor confirms `heartbeat_or_health_enabled=true` and
`setpoint_enabled=false` with `channel_configuration_applied`. The immediately
following `experiment_window_started` is the anchor. Evaluation starts after a
fixed 500 ms settle interval and lasts 3000 ms. A raw
`OBSERVE`→`REQUEST_HOLD` event must bound the nominal end; cleanup Hold is
excluded. Both endpoints require a VALID affine clock bridge. Boundary events
inside clock uncertainty are conservative `UNKNOWN`; PX4-domain writer gaps use
PX4 time directly. The window was fixed before implementation and was not
adjusted from pilot outcomes.

## 5. Clause applicability

| clause | retained-route status requirement |
|---|---|
| revocation | `NOT_APPLICABLE` |
| installation | `NOT_APPLICABLE` |
| exclusivity | `PASS` |
| continuity | `PASS` |
| recovery | `NOT_APPLICABLE` |

Unexpected fallback/route change, a proved gap, or authority/writer conflict is
a `VIOLATION`. Missing clock, channel, route, epoch, window, or writer evidence
is `UNKNOWN`; missing fallback is not missing evidence.

## 6. Accepted-run contract

Acceptance requires runner return 0, monitor PASS, complete flight/trace/monitor
artifacts, exact candidate identity, VALID clock, confirmed health-on and
setpoint-off channels, external route active at start, a COMPLETE retained
window, retained Oracle result, both applicable clauses PASS, and all three
non-applicable clauses explicitly `NOT_APPLICABLE`. Transition-only metrics are
JSON `null`, never numeric zero.

## 7. Implementation changes

- structured `SelectedObservation` replaces the source/target tuple;
- matrix metadata drives `TRANSITION` versus `RETAINED_ROUTE` selection;
- Oracle CLI accepts `--observation-kind transition|retained-route`;
- the retained evaluator checks mapped window bounds, mode/epoch/authority,
  registration/activation, candidate writers, writer sequence, and gap;
- the classifier independently checks raw channel and monitor-bound evidence;
- retained metrics are emitted while transition-only metrics remain nullable;
- Legacy collection merges its already-preserved Offboard and monitor JSONL
  sidecars into one canonical trace.

PX4, adapters, observation patch, trace schema, monitor behavior, clock logic,
thresholds, fallback parameters, fault timing, and T7 semantics did not change.

## 8. Schema and version changes

- Route Oracle: `0.3` → `0.4`;
- Oracle result schema: `1.2` → `1.3`, adding `observation_kind`,
  `retained_route`, and violation categories;
- scenario matrix schema: `1.0` → `1.1`, adding explicit per-cell
  `observation_kind`;
- analysis/metrics configuration: `1.0` → `1.1` with explicit applicability;
- route trace remains `1.2`; threshold profile remains
  `route-oracle-v0.3-default`.

Historical Oracle 0.3/v5 outputs were not rewritten.

## 9. Focused tests

The focused selector/Oracle/classifier/metrics/schema and trace-composition
suite passed: `38 passed`. It covers conforming retention, unexpected fallback,
proved writer gap, writer overlap, missing route epoch, missing channel
evidence, missing fallback acceptance, invalid clock, transition regression,
T7/T8 selection, nullable metrics, and independent sidecar merge. The complete
repository validator passed with `125 passed` both before candidate revision-2
pilots and at final handoff.

## 10. v5 offline regression

The preserved Dynamic artifact
`p5_t7_turn_pair_r1_dynamic_external_mode/attempt_1` was evaluated outside the
v5 record. Oracle 0.4 selected `RETAINED_ROUTE`, mapped a COMPLETE 3000 ms
window, retained mode 23/epoch 4/activation 2, observed one
`control_allocator` writer with a 16 ms maximum gap, and returned PASS with the
required clause applicability. It required no `fallback_nav_state`. Its
historical v5 classification remains `MEASUREMENT_UNKNOWN` and it was not
backfilled.

## 11. Legacy Offboard T7 pilot

Candidate revision 2, seed 7001, attempt 1 was accepted at:
`runs/p5/p5_v6_candidate_t7_pilot/p5_v6_candidate_r2_t7_pilot_legacy_offboard/attempt_1`.

- runner and monitor: PASS; health on, setpoint off;
- clock: VALID, 33 samples, 37.233 ms maximum residual, 39.233 ms uncertainty;
- retained route: mode 14, epoch 3, authority `ros2_offboard`;
- window: COMPLETE, 3000 ms, 335 writer events;
- writer: only `control_allocator`; maximum unowned window 12 ms;
- unexpected route/fallback/authority/writer counts: all zero;
- clauses: exclusivity/continuity PASS; other three `NOT_APPLICABLE`;
- candidate identity: exact match.

The monitor's Hold at cleanup is after the retained window and is not an
unexpected fallback.

## 12. Dynamic External Mode T7 pilot

Candidate revision 2, seed 7001, attempt 1 was accepted at:
`runs/p5/p5_v6_candidate_t7_pilot/p5_v6_candidate_r2_t7_pilot_dynamic_external_mode/attempt_1`.

- runner and monitor: PASS; health on, setpoint off;
- clock: VALID, 35 samples, 65.374 ms maximum residual, 67.374 ms uncertainty;
- retained route: mode 23, epoch 4, activation 2, registration instance
  `3484295346109658`, authority `dynamic_external_mode`;
- window: COMPLETE, 3000 ms, 332 writer events;
- writer: only `control_allocator`; maximum unowned window 12 ms;
- unexpected route/fallback/authority/writer counts: all zero;
- clauses: exclusivity/continuity PASS; other three `NOT_APPLICABLE`;
- candidate identity: exact match.

## 13. Transition regression

The accepted v5 T5 Legacy trace `p5_t5_hover_pair_r1_legacy_offboard/attempt_1`
selected the identical mode 14/epoch 3 → mode 4 transition at 50,380,000 us
under Oracle 0.4. Overall PASS and all five clause statuses were identical to
Oracle 0.3. No transition threshold or decision rule changed.

## 14. Instrumentation sensitivity

Candidate revision 1 preserved three Legacy attempts. Attempts 1 and 3 had
DEGRADED clock bridges (108.350 and 101.561 ms residual maxima) and were
environment failures. Attempt 2 had a VALID clock and behaviorally complete
run, but the Legacy trace invocation merged only producer JSONL while Dynamic
already used monitor JSONL; its channel/window markers were therefore absent
from the canonical trace and it correctly remained `MEASUREMENT_UNKNOWN`.

Revision 2 changed only evidence composition by accepting repeated
`--producer-events` inputs and merging the already-preserved monitor JSONL. A
deterministic test covers this path. No event, patch, trace field, monitor
behavior, window, or Oracle standard was changed, and revision-1 sides were not
reused.

## 15. Remaining risks

The live validation contains one accepted matched pilot per mechanism, not a
formal repeated campaign. Clock uncertainty still limits cross-domain boundary
precision, although route epoch and writer gap evidence are PX4-domain. Only T7
health-on/setpoint-off is newly validated; T8 and more complex concurrent
authority events remain future campaign work. These are campaign-scale risks,
not blockers in the candidate measurement contract.

Candidate identity is frozen at implementation commit
`7f736c209b2818dc0d64024ffd6045c8549f0e13`, PX4
`4ae21a5e569d3d89c2f6366688cbacb3e93437c9`, scenario hash
`e0affa...b3db5`, contract hash `41be4c...90e4c`, and the unchanged patch,
build, adapters, thresholds, and fallback snapshot recorded in
`retained_route_candidate_identity.json`.

## 16. Authorization recommendation

**AUTHORIZED_FOR_V6_CREATION**

The contract is preregistered, the implementation and schemas are versioned,
focused and full validation pass, saved-v5 and transition regressions pass, and
both matched candidate pilots satisfy the same retained-route contract under an
exact identity. This authorizes a later explicit action to create a formal
`campaign_seeded_v6`; it does not create that manifest, start that campaign, or
reopen v5.
