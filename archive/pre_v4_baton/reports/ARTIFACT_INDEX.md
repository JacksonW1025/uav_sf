# Artifact Index

This index lists the retained artifacts after the Route-A cleanup. Raw logs, ULOGs, and per-eval run directories are intentionally ignored or local-only.

## Authoritative Context

- `NEW_NARRATIVE_v5.md`: current narrative and next-step context.
- `PROJECT_NARRATIVE_CONTEXT_v8 (1).md`: retained immediately preceding project context.

## Route A Evidence

- `fuzz1_activation_20260625.md`: first mc_nn violent-activation kill. Historical lead only; differential claim is superseded by FUZZ-1b/FUZZ-1c.
- `fuzz1b_locked_20260625.md`: groundtruth-aligned downgrade of FUZZ-1. Superseded by FUZZ-1c severity and decontamination.
- `fuzz1c_severity_20260625.md`: graded severity scan that found S2-vs-S3 wide differentials.
- `fuzz1c_decontam_20260625.md`: current hard result. Symmetric infrastructure decontamination confirms 4 strict classical-S0 versus mc_nn-S3 differentials.

Structured data retained:

- `fuzz1_activation_20260625/results.json`
- `fuzz1_activation_20260625/results.jsonl`
- `fuzz1b_locked_20260625/results.json`
- `fuzz1b_locked_20260625/results.jsonl`
- `fuzz1c_severity_20260625/results.json`
- `fuzz1c_severity_20260625/results.jsonl`
- `fuzz1c_severity_20260625/severity_thresholds.json`
- `fuzz1c_decontam_20260625/results.json`
- `fuzz1c_decontam_20260625/results.jsonl`
- `fuzz1c_decontam_20260625/criteria.json`

## Controller Bring-up And Closeout

- `mcnn_gonogo.md`: mc_nn_control GATE-1/ID/GATE-2 status rollup.
- `mcnn_gonogo_gate2_20260625.md`: mc_nn source review, including no RAPTOR-like observation clipping.
- `mcnn_gonogo_gate3_20260625.md`: position-error amplitude probe, NO-GO.
- `RAPTOR_closeout.md`: RAPTOR closeout summary and scoped null results.

Retained compact directories:

- `mcnn_gonogo_gate1_20260625/`
- `mcnn_gonogo_idcheck_20260625/`
- `mcnn_gonogo_gate3_20260625/`
- `raptor_closeout_p0_nonfinite_active2_20260625/`
- `raptor_closeout_gz_asym_20260625/`
- `raptor_closeout_activation_20260625/`
- `raptor_closeout_activation_extreme_20260625/`
- `raptor_closeout_activation_extreme2_20260625/`
- `raptor_closeout_reachable_finite_sensor_20260625/`

## Cleanup Policy

Removed from the tracked tree:

- Old M0/M1/M2/M2.5/M2.6/M2b reports and intermediate run directories.
- Old handoff and RAPTOR-only narrative documents superseded by v2.
- Tracked `*.log` files.
- Tracked raw run directories under `docs/**/evals/`.

Ignored going forward:

- `*.ulg`
- `*.log`
- `docs/**/evals/`
