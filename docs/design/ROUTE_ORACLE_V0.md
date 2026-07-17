# Route Oracle v0

Version: `0.2`.

Route Oracle v0 consumes a canonical route trace and the strengthened writer-attribution result. Every clause and overall result uses only `PASS`, `VIOLATION`, `UNKNOWN`, or `NOT_APPLICABLE`. Missing evidence is never converted into success.

Tracked processed traces retain every final actuator-writer observation. To keep
each committed artifact below the repository's 10 MiB boundary, they retain one
in four allocator-input observations; the summary records this stride and hashes
the complete raw ULog. Allocator-input thinning is used only for installation
presence, never for writer sequence, exclusivity, gap, or continuity claims.

## Clauses

`revocation` reports route-exit time, last comparable producer publication, last old-route consumption, last route-attributed writer event, revocation latency, and post-revocation consumption/writer counts. A shared module such as `control_allocator` is not an old-route identity. Post-exit writer and consumption counts require `route_epoch_id`; without it they are null and the clause is unknown.

`installation` requires target mode declaration, registration/activation when applicable, explicit setpoint configuration, fresh target consumption, enabled modules, allocator input, and a final writer event. Any missing check makes installation unknown.

`exclusivity` uses the target external-route transition window rather than the
worst window in the whole flight. COMPLETE single-writer evidence passes;
BOUNDED evidence remains `UNKNOWN` and reports `PASS_ABOVE_RESOLUTION` only as
an internal metric; competing stable writer IDs violate the clause.

`continuity` compares the last observed pre-transition valid output with the first target-side valid output and a period-derived allowance, but returns unknown unless writer evidence is fully covered and exclusive. A continuing fallback writer may establish valid output only when its route epoch is known.

`recovery` checks fallback selection, fallback modules, fallback writer activity, old producer/consumer/writer cessation, and automatic old-route re-entry. Unsupported design combinations are not applicable; missing causal evidence is unknown.

## Time model

PX4 boot/uORB/ULog microseconds from one boot are directly comparable,
including multiple ULog segments caused by disarm/rearm. ROS-node timestamps
are mapped only through a VALID bridge carrying reference pair, affine rate,
offset, uncertainty, and a two-ended validity interval. Producer-to-PX4 latency
is unknown when that bridge is absent, degraded, invalid, or out of interval.

## Conservative examples

- One observed writer plus an uninstrumented candidate → `UNKNOWN` (`INSUFFICIENT_COVERAGE`).
- One observed writer with a missing sequence → `UNKNOWN` (`SEQUENCE_GAP`).
- Two writer IDs in an exclusivity window → `VIOLATION`.
- Continued `control_allocator` output after External→RTL, without a route epoch → revocation writer evidence `UNKNOWN`, not a violation.
- No declared transition → `NOT_APPLICABLE`.

The result schema is `data/schemas/route_oracle_result.schema.json`; the executable is `scripts/oracles/route_oracle_v0.py`.
