# Repository Map

## Canonical entry points

- Current narrative: `docs/narrative/CURRENT_NARRATIVE.md`.
- Experiment lookup: `docs/indexes/EXPERIMENT_INDEX.md`.
- Evidence boundaries: `docs/evidence/claim_audit.md`.
- Artifact hashes/provenance: `docs/indexes/ARTIFACT_MANIFEST.tsv`.
- Per-experiment metadata: `experiments/**/experiment.yaml`.

## Top-level roles

| Path | Role |
|---|---|
| `docs/` | narrative, study design, evidence ledgers, indexes, audits, and stable historical reports |
| `experiments/` | canonical BATON classification and metadata; pointers to stable artifact paths |
| `scripts/` | runners, analysis, monitors, diagnostics, installers, and utilities; see `scripts/README.md` |
| `config/` | stable legacy configuration path used by runners |
| `configs/` | canonical explanation/mapping for `config/` |
| `boards/`, `patches/px4/` | PX4 board overlays and source patches |
| `px4_overlay/` | canonical overlay map; does not duplicate source assets |
| `data/` | raw/processed policy and external provenance manifests |
| `artifacts/` | canonical report/table/figure/log category map |
| `img/` | stable figure sources and rendered figures |
| `runs/` | selected tracked campaign review artifacts; legacy raw paths may be ignored/external |
| `tests/` | unit/static tests |
| `tier05_fork_20260712T090728Z/` | tracked Tier-0.5 structured ledger/report at its provenance-preserving path |
| `external/`, `ros2_ws/` | ignored local dependencies/workspaces; not canonical research sources |

## Finding an experiment

1. Search ID or alias in `EXPERIMENT_INDEX.md`.
2. Open the linked `experiments/**/experiment.yaml` for SUT, scenario, clause, harness, runner, config, data, report, and limitation fields.
3. Use `ARTIFACT_MANIFEST.tsv` to verify size/SHA-256 and the commit containing a tracked artifact.
4. For externally archived raw files, use `data/manifests/EXTERNAL_RAW_FILE_MANIFEST.tsv`; paths record both the original repository location and external location.

## Data and execution

- Original ULogs are never overwritten. Large raw Tier-0.5 and Round-4 files are externally archived because Git LFS is unavailable.
- Derived JSON/CSV stays separate from ULogs and is tracked at its historical path where feasible.
- Runners remain under `scripts/`; `scripts/runners/README.md` maps the category.
- Analyses remain under `scripts/` and `img/`; `scripts/analysis/README.md` maps them.
- Contract checks are mapped by `scripts/monitors/README.md`.
- Writer/root-cause work is mapped by `scripts/diagnostics/README.md`.
- PX4 patches/overlays are under `patches/px4/` and `boards/px4/sitl/`, installed by tracked scripts.

## Legacy-to-canonical mapping

| Legacy path or name | Canonical BATON location |
|---|---|
| `docs/NEW_NARRATIVE_v5.md` | `docs/narrative/CURRENT_NARRATIVE.md`; version copy in `docs/narrative/history/` |
| `docs/PROJECT_NARRATIVE_CONTEXT_v*.md` | copies in `docs/narrative/history/`; legacy paths retained for citations |
| `docs/ARTIFACT_INDEX.md` | legacy map retained; canonical lookup is `docs/indexes/EXPERIMENT_INDEX.md` and `ARTIFACT_MANIFEST.tsv` |
| F1 | `experiments/handover/S1_commanded_switch_in/mcnn/F1_anchor/` |
| F2 | `experiments/handover/S1_commanded_switch_in/mcnn/F2_campaign/` |
| F2a | `experiments/handover/S1_commanded_switch_in/mcnn/F2_archive_reanalysis/` |
| old RAPTOR S1 | `experiments/handover/S1_commanded_switch_in/raptor/S1_campaign/` |
| old RAPTOR S2 | `experiments/handover/S1_commanded_switch_in/raptor/S2_unclip/` |
| B1/B2/B3/D1/D2 | matching `experiments/supporting_controls/` directory |
| wall-clock/GATE_FAIL | `experiments/harness/legacy_wall_clock/` |
| Tier-0.5/β/100-of-100 | `experiments/harness/sim_time_lockstep_beta/tier05_fork_20260712/` |
| config stale | `experiments/mechanism/allocation_freshness/` |
| actuator attribution/single-writer repair | `experiments/mechanism/single_writer/` |
| guard/reply initialization | `experiments/mechanism/admission/` |
| equivariance probe | `experiments/uncategorized/equivariance_probe_20260708/` |
| flat `scripts/*.py` and `scripts/*.sh` | category maps under `scripts/{runners,analysis,monitors,diagnostics,utilities}/` |
| `config/` | retained stable path, documented by `configs/README.md` |
| `boards/` + `patches/` + installers | documented by `px4_overlay/README.md` |

Physical moves were deliberately avoided where scripts, reports, imports, or historical commands depend on stable paths. Canonical mappings provide the BATON organization without changing experiment semantics.
