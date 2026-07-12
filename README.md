# UAV Software Fuzzing: BATON

This repository studies the PX4 software subsystem that transfers actuator authority between the classical control stack and learned controllers. The research question is not merely whether a neural controller can fly: it is whether admission, handover, residual-state, and fallback behavior satisfy an explicit control-authority contract.

The canonical project narrative is [`docs/narrative/CURRENT_NARRATIVE.md`](docs/narrative/CURRENT_NARRATIVE.md). Historical narrative files remain available under [`docs/narrative/history/`](docs/narrative/history/) and at their legacy paths for traceability.

## Contract and scenarios

BATON organizes the subsystem around four clauses:

- **Admission**: a controller may acquire authority only when its prerequisites and replies are valid.
- **Handover**: the intended writer becomes active and conflicting actuator writers stop.
- **Residual**: persistent state is reset, preserved, or transferred deliberately.
- **Fallback**: commanded and failsafe exits return authority through a defined safety path.

The mode-transition space is:

- **S1 commanded switch-in**: Classical → Learned.
- **S2 active fallback**: Learned → Classical.
- **S3 failsafe-triggered transition**: Learned → Return / Land / Classical safety pipeline.
- **S4 repeated switching**: Classical → Learned → Classical → Learned …

## Current evidence

Confirmed or directly observed evidence is deliberately separated from planned work:

- PX4 external-mode allocation configuration is repeatedly rejected as stale because of freshness timestamp semantics.
- The classical `control_allocator` remains active after learned-mode activation, producing silent dual writes to `actuator_motors`.
- admission replies have incompletely initialized fields.
- deployed `mc_nn_control` has a catastrophic S1 differential at candidate states where the classical branch recovers.
- the hardened sim-time/lockstep harness reproduces preregistered anchors 100/100 and improves trigger-state convergence by approximately 85×.
- old wall-clock claims about a non-monotonic, holed boundary are `legacy_unverified` until repeated on the hardened harness.
- RAPTOR supports behavioral discrimination and a second-controller applicability check, but data-plane writer attribution is not yet closed.
- residual-state and fallback consequences are planned; allocation/single-writer repair is the immediate mechanism differential.

See [`docs/evidence/claim_audit.md`](docs/evidence/claim_audit.md) for the claim-by-claim boundary.

## Quick start

The environment uses the `uav_sf:phase1` container, PX4 commit `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`, and tracked overlays/patches in this repository.

```bash
./docker/build.sh
./scripts/clone_px4.sh
./scripts/setup_ros2_ws.sh
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=uav-sf ./docker/run.sh bash'
```

Build scripts under `scripts/` install the relevant tracked board, airframe, DDS, and PX4 patch assets before compiling. Do not treat an arbitrary dirty `external/PX4-Autopilot` tree as the source of truth.

## Repository navigation

- [`docs/indexes/EXPERIMENT_INDEX.md`](docs/indexes/EXPERIMENT_INDEX.md): canonical lookup from experiment ID/alias to scenario, code, data, and report.
- [`docs/indexes/REPOSITORY_MAP.md`](docs/indexes/REPOSITORY_MAP.md): directory roles and legacy-to-canonical mappings.
- [`docs/indexes/ARTIFACT_MANIFEST.tsv`](docs/indexes/ARTIFACT_MANIFEST.tsv): hashes and provenance for major artifacts.
- [`docs/study_design/`](docs/study_design/): research questions, contract, differential diagnosis, and scenario space.
- [`experiments/`](experiments/): BATON metadata and pointers; historical artifacts stay at stable legacy paths where moving would break reproducibility.
- `scripts/`: executable implementation, classified in [`scripts/README.md`](scripts/README.md) while legacy paths remain stable.
- `boards/` and `patches/px4/`: reproducible PX4 overlays and patches.
- `config/`: legacy stable configuration path; [`configs/README.md`](configs/README.md) is the canonical map.

## Reproduction entry points

```bash
python3 scripts/m1_diff_runner.py --help
python3 scripts/tier05_fork_campaign.py --help
python3 scripts/tier05_fork_finalize.py --help
python3 scripts/px4_race_r4_experiment.py --help
```

The Tier-0.5 report and structured 144-run ledger remain at `tier05_fork_20260712T090728Z/`. Raw ULogs and runtime roots are externally archived because this repository has no Git LFS support; their hashes and external locations are recorded in the artifact manifests.

## Evidence discipline

Use only these status terms: `confirmed`, `mechanism_observed`, `planned`, `legacy_unverified`, and `needs_review`. Missing metadata is `unknown`; old negative results and failed gates are retained. Do not promote a mechanism observation to a physical-causality claim, and do not use the legacy boundary shape as confirmed evidence.

## Current priorities

1. execute original-PX4 versus repaired allocation/single-writer mechanism differentials on hardened anchors;
2. close independent writer attribution for both `mc_nn_control` and RAPTOR;
3. test S2/S3 fallback and S4 repeated switching;
4. test preserved versus reset residual controller state;
5. rerun any retained legacy boundary/search claim before using it as confirmed evidence.

## Validation

```bash
python3 -m py_compile scripts/*.py
bash -n scripts/*.sh docker/*.sh
git ls-files '*.json' | xargs -r jq empty
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$PWD" python3 -m pytest -q tests
```
