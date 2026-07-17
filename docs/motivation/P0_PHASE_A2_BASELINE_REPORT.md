# P0 Phase A.2 Baseline Report

Phase A.2 accepted three valid runs for each baseline family after the queue,
epoch, clock, schema, and Oracle changes. The accepted set is exactly the nine
directories under `data/processed/p0_phase_a2/` whose names begin with `p0a`,
`p0b`, or `p0c`.

| Family | Accepted runs | Execution | Route Oracle 0.2 clauses | Clock |
|---|---:|---|---|---|
| P0-A Offboard | 3 | PASS | 5/5 PASS | VALID |
| P0-B Dynamic External | 3 | PASS | 5/5 PASS | VALID |
| P0-C Mode Executor | 3 | PASS | 5/5 PASS | VALID |

P0-A uses `queue_q4_r1_20260717`, `queue_q4_r3_20260717`, and
`p0a_offboard_r4_20260717`. P0-B uses `p0b_external_r1` through `r3`; P0-C
uses `p0c_executor_r1` through `r3` (all dated 20260717).

Every selected target transition has zero sequence gaps, all current final
writer candidates are instrumented, and every target critical window is
`COMPLETE`. Some bookkeeping/startup windows are `BOUNDED` because the vehicle
does not continuously publish actuator evidence while inactive; the Oracle
selects the actual source epoch with PX4 consumption and does not treat those
unrelated windows as the tested handoff. Global capture is `COMPLETE` for the
accepted runs.

All clock bridges are `VALID` under the preregistered 20-sample, 100 ms maximum
residual, 20 ms round-trip, and 50 ms segment-jump thresholds. Observed maximum
residuals stay below the validity threshold. Cross-domain metrics are only
reported for those valid segments.

All legacy Phase A.1 traces were migrated to schema 1.2 without inventing
identities and their summaries carry `superseded_by_phase_a2_measurement=true`.
