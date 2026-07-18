# Route Oracle v0

Version: `0.4` (result schema `1.3`).

Route Oracle v0 consumes a canonical route trace and the strengthened writer-attribution result. Every clause and overall result uses only `PASS`, `VIOLATION`, `UNKNOWN`, or `NOT_APPLICABLE`. Missing evidence is never converted into success.

Version 0.4 adds an explicit `observation_kind`. `TRANSITION` preserves the
0.3 source-to-target evaluation. `RETAINED_ROUTE` evaluates a preregistered,
clock-mapped stable window without inventing a target or fallback. In that mode
revocation, installation, and recovery are `NOT_APPLICABLE`; exclusivity and
continuity evaluate stable mode/epoch/authority/registration/writer identity
and complete writer sequence. The retained contract is
`RETAINED_ROUTE_OBSERVATION_CONTRACT.md`.

Tracked processed traces retain every final actuator-writer observation. To keep
each committed artifact below the repository's 10 MiB boundary, they retain one
in four allocator-input observations; the summary records this stride and hashes
the complete raw ULog. Allocator-input thinning is used only for installation
presence, never for writer sequence, exclusivity, gap, or continuity claims.

## Clauses

`revocation` reports route-exit time, last comparable producer publication, last old-route consumption, last route-attributed allocator/writer event, revocation latency, and post-revocation consumption/allocator/writer counts. A shared module such as `control_allocator` is not by itself an old-route identity; the event must carry the exited epoch. Post-exit influence checks require `route_epoch_id`; without it they are null and the clause is unknown. Consumption association also rejects a post-exit sample whose subject timestamp is no newer than the last consumed sample from the exited epoch.

`installation` requires target mode declaration, registration/activation when applicable, explicit setpoint configuration, fresh target consumption, enabled modules, allocator input, and a final writer event. For a declared complete source artifact, missing required evidence is a violation; for an incomplete artifact it remains unknown. Completion later than the selected profile's deadline is a violation.

`exclusivity` uses the target external-route transition window rather than the
worst window in the whole flight. COMPLETE single-writer evidence passes;
BOUNDED evidence remains `UNKNOWN` and reports `PASS_ABOVE_RESOLUTION` only as
an internal metric; competing stable writer IDs or simultaneous old/new route
epochs violate the clause.

`continuity` compares the last observed pre-transition valid output with the first target-side valid output and a period-derived allowance. A complete publication sequence may prove a gap even when a rate summary is only bounded; otherwise the clause remains unknown unless writer evidence is fully covered and exclusive. A continuing fallback writer may establish valid output only when its route epoch is known.

`recovery` checks fallback selection, fallback consumption/modules/allocator/writer installation, old producer/consumer/allocator/writer cessation, and automatic old-route re-entry. As with installation, absent required evidence in a declared complete source is a violation and absent evidence in an incomplete source is unknown. Unsupported design combinations are not applicable.

## Validation metadata and transition selection

Version 0.3 records `ground_truth_case_id`, `oracle_validation_profile`,
`threshold_profile_id`, and an explicit `evidence_completeness` map. These fields
describe validation provenance; they are never used to alter a clause decision.
Callers may select a transition by source and target mode. Selection is generic
and contains no case- or run-ID branches.

The default threshold profile is `route-oracle-v0.3-default`:

- installation deadline: 300 ms;
- recovery deadline: 300 ms;
- minimum continuity gap: 20 ms;
- continuity allowance: three observed publication periods.

Oracle validation uses the numerically identical frozen profile
`oracle-validation-preregistered-v1`. The profile was calibrated from the
248 ms maximum completion time in the pre-existing P0 normal reference, with a
52 ms guard margin, before the controlled live campaign. The 200/500/1000 ms
install-delay points are validation inputs and do not change the threshold.

## Time model

PX4 boot/uORB/ULog microseconds from one boot are directly comparable,
including multiple ULog segments caused by disarm/rearm. ROS-node timestamps
are mapped only through a VALID bridge carrying reference pair, affine rate,
offset, uncertainty, and a two-ended validity interval. Producer-to-PX4 latency
is unknown when that bridge is absent, degraded, invalid, or out of interval.

## Conservative examples

- One observed writer plus an uninstrumented candidate → `UNKNOWN` (`INSUFFICIENT_COVERAGE`).
- One observed writer with a missing sequence → `UNKNOWN` (`SEQUENCE_GAP`).
- Two stable writer IDs or overlapping old/new epochs in an exclusivity window → `VIOLATION`.
- Required target evidence absent from a complete artifact → `VIOLATION`.
- The same absence in an incomplete artifact → `UNKNOWN`.
- Continued `control_allocator` output after External→RTL, without a route epoch → revocation writer evidence `UNKNOWN`, not a violation.
- No declared transition → `NOT_APPLICABLE`.

The result schema is `data/schemas/route_oracle_result.schema.json`; the executable is `scripts/oracles/route_oracle_v0.py`.
