# Motivation Study workspace

This directory is the entry point for the bounded Motivation studies. It
contains the Phase A foundations and the later frozen N1, C1, and R1 closure
records. Raw runtime evidence remains outside this directory under ignored
`runs/` namespaces.

## Completed work

1. **P-1 Route Observability Feasibility:** 14/14 fields classified; 4 DIRECT,
   7 DERIVED, 3 INSTRUMENTATION_REQUIRED, 0 UNOBSERVABLE.
2. **M2 External Mode and Registration Importance:** 13 locked-source evidence
   entries distinguish registration, activation, completion, loss, fallback,
   and replacement.
3. **M4 Official Test Coverage Gap:** 15 official test/example rows show that
   state/lifecycle coverage does not establish writer identity, revocation,
   installation, overlap/gap, residue, or full recovery.
4. **P0 Official Handoff Flow:** three legal normal-flow baselines ran after the
   P-1 gate passed.
5. **Current-Version Setpoint Freshness Pilot:** 10 accepted runs from 16
   attempts confirm bounded design exposure; one accepted Trajectory run has a
   natural post-fallback Route violation, while the Attitude cell is
   measurement-insufficient at its frozen attempt cap.
6. **N1 Trajectory Residue:** closed with 8 accepted runs from 14 attempts and
   a phase-dependent re-observation disposition.
7. **C1 Concurrent Authority Events:** closed conditionally with 14 accepted
   runs from 17 attempts and no accepted linearization violation.
8. **R1 Session Rollover:** closed measurement-insufficient when R1-A reached
   its six-attempt cap with zero accepted runs; R1-B/R1-C were not started.

## Files

- `HANDOFF_INVENTORY.tsv`: candidate handoffs and whether each is a true route change.
- `EXTERNAL_MODE_REGISTRATION_EVIDENCE.md`: source-backed registration/lifecycle evidence template.
- `LIFECYCLE_ISSUE_MATRIX.tsv`: issue/PR symptoms by lifecycle stage.
- `OFFICIAL_TEST_COVERAGE.tsv`: official-test coverage against route obligations.
- `WORKLOAD_CANDIDATES.tsv`: candidate supported workloads and replay cost.
- `../design/OBSERVABILITY_MATRIX.tsv`: field-level signal feasibility.
- `P0_OFFICIAL_HANDOFF_BASELINE_REPORT.md`: P0-A/B/C results and limitations.
- `SETPOINT_FRESHNESS_SOURCE_AUDIT.md`: revision-locked freshness and health-path source audit.
- `SETPOINT_FRESHNESS_PILOT_REPORT.md`: final four-cell bounded pilot analysis and Gate disposition.
- `N1_TRAJECTORY_RESIDUE_REPORT.md`: bounded natural-event adjudication.
- `C1_CONCURRENT_AUTHORITY_EVENTS_REPORT.md`: deterministic authority-event probe closure.
- `R1_SESSION_ROLLOVER_REPORT.md`: rapid re-entry/session-rollover closure and claim boundary.

## Evidence rules

- Use primary/official sources where possible and record a stable link or commit/path.
- Keep unknown cells empty or mark `TBD`/`not_collected`; do not infer an observation from the schema.
- Separate a mode request, registration, activation, runtime producer/writer change, fallback selection, and fallback installation.
- Do not import legacy Family B results into a Family A evidence row without a new, explicit validation link.
- Put raw captures under ignored `runs/` or the external archive, never in this directory.

The Motivation completion workflow has advanced through R1. W1 is the exact
next registered phase, but it has not started. No existing result authorizes a
random campaign or full fuzzer execution.
