# Motivation Study workspace

This directory is the only active entry point for Motivation Study M1–M5. It contains schemas and evidence-collection guidance only; cleanup did not populate empirical results.

## Immediate priorities

1. **P-1 Route Observability Feasibility:** determine which route fields can be observed without modifying PX4 and which require tracked instrumentation.
2. **M2 External Mode and Registration Importance:** collect official design, lifecycle, issue, and registration evidence.
3. **M4 Official Test Coverage Gap:** map official tests to revocation, installation, writer identity, overlap/gap, residue, and full recovery obligations.
4. **P0 Official Handoff Flow:** capture one documented handoff path before designing probes.

## Files

- `HANDOFF_INVENTORY.tsv`: candidate handoffs and whether each is a true route change.
- `EXTERNAL_MODE_REGISTRATION_EVIDENCE.md`: source-backed registration/lifecycle evidence template.
- `LIFECYCLE_ISSUE_MATRIX.tsv`: issue/PR symptoms by lifecycle stage.
- `OFFICIAL_TEST_COVERAGE.tsv`: official-test coverage against route obligations.
- `WORKLOAD_CANDIDATES.tsv`: candidate supported workloads and replay cost.
- `../design/OBSERVABILITY_MATRIX.tsv`: field-level signal feasibility.

## Evidence rules

- Use primary/official sources where possible and record a stable link or commit/path.
- Keep unknown cells empty or mark `TBD`/`not_collected`; do not infer an observation from the schema.
- Separate a mode request, registration, activation, runtime producer/writer change, fallback selection, and fallback installation.
- Do not import legacy Family B results into a Family A evidence row without a new, explicit validation link.
- Put raw captures under ignored `runs/` or the external archive, never in this directory.

No Motivation experiment has been run as part of repository cleanup.
