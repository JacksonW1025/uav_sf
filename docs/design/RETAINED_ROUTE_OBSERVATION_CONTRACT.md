# Retained-route observation contract

Contract version: `1.0`.

## Purpose and scope

P5 distinguishes an expected route replacement from an expected absence of
route replacement. `TRANSITION` observes a declared source-to-target handoff.
`RETAINED_ROUTE` observes whether an already installed route remains the sole,
continuous route after an input-channel change that is not expected to revoke
it. Both are observations of runtime route authority. A setpoint producer
stopping is not, by itself, route revocation.

The P5 mapping is explicit in `experiments/probes/p5/scenario_matrix.yaml`:

| transition class | observation kind | expected route behavior |
|---|---|---|
| T1 | `TRANSITION` | Internal to external |
| T2 | `TRANSITION` | External to internal Hold |
| T4 | `TRANSITION` | External to fallback |
| T5 | `TRANSITION` | External to fallback |
| T6 | `TRANSITION` | External to fallback |
| T7 | `RETAINED_ROUTE` | External remains external |
| T8 | `TRANSITION` | External to fallback |

The route-observability patch profile remains `TRANSITION`. That name describes
the high-rate instrumentation profile, not the P5 observation kind.

## Retained window

T7 uses the existing P3 monitor and these fixed boundaries:

- action confirmation: a raw `channel_configuration_applied` monitor event with
  `heartbeat_or_health_enabled: true` and `setpoint_enabled: false`;
- anchor: the immediately following canonical `experiment_window_started`
  event, with the same run ID and a ROS-node timestamp no earlier than the
  channel confirmation;
- settle interval: 500 ms after the anchor;
- nominal evaluation start: anchor plus 500 ms;
- nominal evaluation end: start plus 3000 ms;
- minimum nominal duration: 3000 ms;
- monitor bound: a raw `state_transition` from `OBSERVE` to `REQUEST_HOLD` must
  occur no earlier than the nominal end. The cleanup Hold request is outside the
  retained window.

The anchor is mapped from `ros_node_ns` into PX4 boot/ULog microseconds only by
a `VALID` affine clock bridge whose validity interval contains both endpoints.
Bridge uncertainty is reported with the window. An unexpected route event
strictly inside the uncertainty-trimmed interior is a violation; an event whose
membership is ambiguous at a window boundary makes the affected clause
`UNKNOWN`. Writer sequence and gap measurements use PX4/ULog time directly.

The window ends early only for reporting when an unexpected route change is
proved. Missing trace coverage, a non-valid bridge, an incomplete monitor
bound, or an unresolvable boundary is evidence failure and produces `UNKNOWN`,
not a shortened passing window. Pilot results cannot change these boundaries.

## Expected retained state and evidence

At the evaluation start, the expected external mode, route epoch, external
authority source, and—where applicable—registration and activation identities
must already be established. Throughout the window:

- the declared external mode and route epoch remain unchanged;
- the authority source remains the selected external mechanism;
- registration and activation identities do not conflict or disappear;
- no fallback or other route is selected;
- no internal route has concurrent authoritative influence;
- the instrumented final writer remains a single stable writer attributed to
  the retained epoch; and
- the complete writer sequence has no unowned interval above the existing
  continuity allowance: `max(20 ms, 3 × observed publication period)`.

Required evidence is the complete raw flight artifact, canonical route trace,
VALID clock bridge, raw monitor channel and bound events, route-epoch events,
declared-mode/authority evidence, registration evidence for Dynamic External
Mode, and complete candidate-writer coverage. Missing required evidence remains
`UNKNOWN`. The absence of a fallback target is expected and is not missing
evidence.

## Clause applicability and verdict

For `RETAINED_ROUTE`:

| clause | applicability | meaning |
|---|---|---|
| revocation | `NOT_APPLICABLE` | no source-route revocation is expected |
| installation | `NOT_APPLICABLE` | no new target route is expected |
| exclusivity | applicable | retained authority and writer remain unique |
| continuity | applicable | retained route and writer remain continuously owned |
| recovery | `NOT_APPLICABLE` | no fallback/recovery is expected |

Overall status is `VIOLATION` if any applicable clause violates, `PASS` only
when every applicable clause passes and every other clause is explicitly
`NOT_APPLICABLE`, and otherwise `UNKNOWN`. Categories are:

- `UNEXPECTED_FALLBACK`: a proved change to an internal fallback route;
- `UNEXPECTED_ROUTE_CHANGE`: another proved mode or epoch change;
- `ROUTE_RETENTION_GAP`: a proved unowned interval above the allowance;
- `AUTHORITY_CONFLICT`: conflicting declared authority or route epochs;
- `WRITER_CONFLICT`: multiple authoritative final writers;
- `STALE_OR_INSUFFICIENT_EVIDENCE`: evidence cannot prove the contract.

## Accepted-run contract and metrics

A T7 attempt is accepted only when the runner returns success; monitor status is
`PASS`; required flight, trace, monitor, and identity artifacts exist; candidate
identity matches; the bridge is `VALID`; channel confirmation is health on and
setpoint off; the external route is active at the window start; the retained
window is `COMPLETE`; the retained-route Oracle result exists; exclusivity and
continuity are `PASS`; and revocation, installation, and recovery are
`NOT_APPLICABLE`.

An unexpected fallback, route change, gap, or conflict is a valid SUT-side
Oracle `VIOLATION`. Missing channel, route, epoch, clock, window, artifact, or
writer evidence is `MEASUREMENT_UNKNOWN`. Runner or infrastructure failures
remain environment/excluded attempts under the existing P5 rules.

Transition-only metrics are `null` for T7, never zero. Reliable retained metrics
are the nominal/evaluated window duration, unexpected route/fallback counts,
maximum unowned interval, authority/writer conflict counts, and Oracle clause
statuses. Physical metrics retain their existing independent applicability.

## Design consistency review

1. **Is T7 in scope?** Yes. It probes whether the declared external authority
   remains reflected by the runtime producer/controller/writer route after a
   partial channel failure. It does not claim a handoff occurred.
2. **Relation to transitions?** Both compare a preregistered expected route
   evolution with observed runtime authority. One expects replacement; the
   other expects stable retention.
3. **Why not External to External?** No authority boundary, target installation,
   source revocation, or new route epoch is expected. Encoding equal endpoints
   would make transition clauses semantically false and hide an epoch change.
4. **Reusable clauses?** Exclusivity and continuity reuse existing writer,
   epoch, coverage, and gap concepts.
5. **Non-applicable clauses?** Revocation, installation, and recovery are
   explicitly `NOT_APPLICABLE`.
6. **Oracle version?** Yes. The new observation mode and result envelope require
   Route Oracle `0.4`; transition evaluation remains backward-compatible.
7. **Trace schema revision?** No. Version `1.2` already carries window markers,
   modes, epochs, authority, registration, writers, sequences, and timestamps.
   Exact channel flags remain authoritative in the preserved raw monitor log.
8. **Patch revision?** No. Existing route-epoch and full writer-sequence
   instrumentation supplies the required PX4 evidence.
9. **Scenario matrix schema?** Yes, `1.1`, solely to make `observation_kind`
   explicit per cell rather than infer all semantics from T numbers.
10. **Accepted metrics schema?** The runner output gains observation kind and
    retained metrics; transition-only values are nullable. No historical result
    is rewritten.
11. **Why is T8 different?** T8 removes health while setpoints continue and
    preregisters a fallback. T7 retains health while setpoints stop and
    preregisters continued external selection.
12. **Effect on T1–T6?** Their selected source/target modes, Oracle clauses,
    thresholds, and classification remain transition semantics. T8 does too.

## Version and compatibility decision

This revision changes only P5 observation metadata, the structured selector,
the P5 classifier/metrics envelope, Route Oracle mode/result schema, tests, and
documentation. It does not change the PX4 build, adapters, observation patch,
trace schema, clock bridge, monitor, thresholds, fallback configuration, fault
timing, or T7 channel semantics. Existing Oracle `0.3` result files remain
historical schema `1.2` artifacts and are never rewritten.
