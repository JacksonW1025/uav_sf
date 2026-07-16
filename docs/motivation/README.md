# Motivation Study workspace

This directory is the active entry point for the completed Phase A Motivation
Study. It contains the P-1 feasibility result, M2 source audit, M4 official-test
coverage audit, and the gated P0 normal-flow baselines.

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

## Files

- `HANDOFF_INVENTORY.tsv`: candidate handoffs and whether each is a true route change.
- `EXTERNAL_MODE_REGISTRATION_EVIDENCE.md`: source-backed registration/lifecycle evidence template.
- `LIFECYCLE_ISSUE_MATRIX.tsv`: issue/PR symptoms by lifecycle stage.
- `OFFICIAL_TEST_COVERAGE.tsv`: official-test coverage against route obligations.
- `WORKLOAD_CANDIDATES.tsv`: candidate supported workloads and replay cost.
- `../design/OBSERVABILITY_MATRIX.tsv`: field-level signal feasibility.
- `P0_OFFICIAL_HANDOFF_BASELINE_REPORT.md`: P0-A/B/C results and limitations.

## Evidence rules

- Use primary/official sources where possible and record a stable link or commit/path.
- Keep unknown cells empty or mark `TBD`/`not_collected`; do not infer an observation from the schema.
- Separate a mode request, registration, activation, runtime producer/writer change, fallback selection, and fallback installation.
- Do not import legacy Family B results into a Family A evidence row without a new, explicit validation link.
- Put raw captures under ignored `runs/` or the external archive, never in this directory.

Phase A stops here. Do not treat P0 as authorization to start a fault campaign,
random search, full fuzzer, or later-phase probes.
