# Post-reorganization Report

Generated: `2026-07-12`  
Repository: `/mnt/nvme/uav_sf`

## 1. Branch

`tier05-fork-20260712T090728Z`, tracking `origin/tier05-fork-20260712T090728Z`.

The branch was already a dedicated Tier-0.5 experiment branch, so it was retained rather than creating a new branch from `main`.

## 2. Pre-reorganization checkpoint

- Checkpoint commit: `c41b29347f21e38eedbc6e241e5c04af47b75f17`
- Message: `chore: checkpoint all current experimental work before BATON reorganization`
- Checkpoint was pushed before organization began.

## 3. Final commit

- Last completed content/archive commit before the final manifest: `eac8eab` (`chore: archive and index all historical ignored research artifacts`).
- The final repository commit is the pushed `HEAD` containing the final report/manifest hygiene update; resolve it with `git rev-parse HEAD`. A commit cannot embed its own SHA-1 without changing that SHA-1.

## 4. Remote branch

`origin/tier05-fork-20260712T090728Z` at `git@github.com:JacksonW1025/uav_sf.git`.

Important stages were pushed separately: checkpoint, BATON narrative/metadata, and canonical manifests.

## 5. Protection tag

- Annotated tag: `pre-baton-reorg-20260712-1217`
- Tag object: `fee5dd95a69fcc0c954a887bd0172771d01ec772`
- Peeled pre-reorganization commit: `4dff034bde781fd3b9e1b7c7e78a01337a92d795`
- Tag is present on `origin`.

## 6. New directory structure

- `docs/NEW_NARRATIVE_v5.md`: canonical narrative; `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md`: retained predecessor.
- `docs/study_design/`: research questions, contract, differential diagnosis, and scenario space.
- `docs/evidence/`: claim audit, contract anchors, and upstream issue ledger.
- `docs/indexes/`: experiment index, repository map, and artifact manifest.
- `docs/repository_audit/`: pre/post repository audits.
- `experiments/handover/`, `mechanism/`, `supporting_controls/`, `harness/`, `uncategorized/`: canonical metadata/pointer layer.
- `scripts/{runners,analysis,monitors,diagnostics,utilities}/`: category maps plus new repository utilities; legacy executable paths are retained.
- `configs/`, `px4_overlay/`, `data/`, `artifacts/`: canonical maps/policies without breaking stable legacy paths.

Historical reports, scripts, configs, processed results, and Tier-0.5 structured ledgers were not physically moved where a move would break commands, imports, or citations.

## 7. Classified experiments

- S1/mc_nn: F1 hardened anchor, F2 campaign, F2a archive reanalysis.
- S1/RAPTOR: old S1 campaign and old S2 unclipping ablation, with aliases preserved and disambiguated from BATON scenarios.
- Supporting controls: B1 wind/physics, B2 state contamination, B3 multi-policy, D1 amplitude, D2 fault injection.
- Harness: legacy wall-clock/GATE_FAIL and Tier-0.5 sim-time/lockstep β.
- Mechanism: admission, allocation freshness, single writer, residual state, fallback.
- Planned scenario coverage: BATON S2 active fallback, S3 failsafe transition, S4 repeated switching.

Each has an `experiment.yaml`; missing ownership/metadata is `unknown` or `needs_review`. D1/D2 remain indexed without invented conclusions.

## 8. Uncategorized experiments

- `experiments/uncategorized/equivariance_probe_20260708/`

Its README records original paths, observed files, probable purpose, checkpoint, uncertainty reason, and review need. No file was deleted or classified from its filename alone.

## 9. Path mapping

The complete mapping is in `docs/indexes/REPOSITORY_MAP.md`. Key mappings:

- `docs/NEW_NARRATIVE_v5.md` remains the canonical narrative at its stable path.
- `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md` is the only retained predecessor; older versions and duplicate copies were removed in the subsequent repository-hygiene pass.
- F1/F2/F2a, old RAPTOR S1/S2, B1/B2/B3/D1/D2 → matching experiment metadata directories.
- wall-clock/GATE_FAIL and β/100-of-100 → separate harness metadata directories.
- config-stale, writer attribution, and guard/reply issues → mechanism metadata directories.
- flat scripts and `config/` → category/canonical maps; executable paths retained.
- boards, patches, and installers → `px4_overlay/README.md` map; sources remain at stable paths.

## 10. Indexes added or updated

- `docs/indexes/EXPERIMENT_INDEX.md`: canonical experiment/negative/uncertain/planned index.
- `docs/indexes/REPOSITORY_MAP.md`: directory roles, lookup procedure, and legacy mapping.
- `docs/indexes/ARTIFACT_MANIFEST.tsv`: SHA-256, size, commit, status, and notes for major artifacts and aggregate external raw collections.
- `data/manifests/EXTERNAL_RAW_FILE_MANIFEST.tsv`: 28,500 new-work per-file original/external paths, sizes, SHA-256 values, and preservation statuses.
- `data/manifests/HISTORICAL_IGNORED_FILE_MANIFEST.tsv`: 95,297 historical files that had been hidden by the prior ignore policy.
- `data/manifests/HISTORICAL_IGNORED_NESTED_CACHE_MANIFEST.tsv`: 90 files from a nested-Git build-cache backup that Git represented as one ignored directory.
- `docs/evidence/claim_audit.md`: evidence-grade boundary for current claims.
- Legacy `docs/ARTIFACT_INDEX.md` is retained unchanged as historical lookup evidence.

## 11. Validation commands

Executed successfully:

```bash
python3 -m py_compile scripts/*.py scripts/utilities/*.py img/*.py
bash -n scripts/*.sh docker/*.sh
git ls-files '*.json' -z | xargs -0 -n100 jq empty
find experiments -name experiment.yaml ... yaml.safe_load(...)
python3 scripts/utilities/check_markdown_links.py
python3 scripts/m1_diff_runner.py --help
python3 scripts/tier05_fork_campaign.py --help
python3 scripts/tier05_fork_finalize.py --help
python3 scripts/px4_race_r4_experiment.py --help
python3 scripts/run_equivariance_probe.py --help
python3 scripts/utilities/archive_external_artifacts.py --help
python3 scripts/utilities/build_artifact_manifest.py --help
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=/mnt/nvme/uav_sf python3 -m pytest -q tests
git diff --check
```

Results:

- Python compilation: pass.
- Shell syntax: pass.
- Tracked JSON parsing: pass.
- 21 experiment YAML files: pass.
- Markdown checker: 10 local links checked, 0 broken.
- Unit tests: `75 passed, 4 subtests passed in 107.42s`.
- Required `--help` entry points: pass after adding argument parsing to `tier05_fork_finalize.py`.
- Stable legacy paths explicitly checked: present.

The first pre-fix `tier05_fork_finalize.py --help` probe exposed that the script previously executed analysis before handling help and rewrote two tracked derived files. Those verification-created changes were immediately reversed exactly; only the CLI parsing fix remains.

## 12. Tests not run

- Full PX4/SIH campaigns and mechanism-repair simulations were not rerun because they would consume substantial simulation resources and would constitute new experiments rather than repository validation.
- Bare repository-wide `pytest -q` was not used because ignored PX4/TFLM and ROS dependency trees are known to cause unrelated collection/ABI/import failures. The scoped repository test command passed.
- Original-versus-repaired PX4 single-writer, S2/S3 fallback, S4 repeated switching, and residual reset/preserve experiments remain planned.

## 13. Large files and LFS

- `git lfs` is not installed; the repository has no LFS rules or LFS objects.
- GitHub accepted the 54.07 MiB historical TSV manifest with a recommendation warning because it exceeds 50 MiB; it remains below GitHub's 100 MiB hard file limit.
- Tier-0.5 and Round-4 raw/runtime material selected: 28,500 files, `9,807,496,903` bytes, safely externalized to `/home/car/uav_sf_external_artifacts/pre_baton_reorg_20260712/`.
- A final all-history audit then found 95,297 ignored research files totaling `205,062,189,148` bytes; these were safely externalized to `/mnt/nvme/px4_work/uav_sf_baton_external_20260712/`.
- One nested-Git build-cache directory collapsed by Git's ignored listing contained another 90 files (`1,078,960` bytes); these were externalized to the same NVMe archive and separately manifested.
- Total externalized in this reorganization: 123,887 files, `214,870,765,011` bytes.
- Post-move verification recomputed size and SHA-256 for every file; all rows in all three manifests are `external_preserved`.
- Tracked JSON/CSV/reports were not moved. Raw `.ulg`/`.log` files are absent from the repository after archival.
- Empty ignored directory shells may remain on disk; they contain no files and do not appear in Git.

## 14. Sensitive files

- Candidate filename scan found no `.env`, credential, token, password, or private-key file in commit candidates.
- Candidate content scan found no common API key/token/private-key pattern in new research material.
- The only broad scan hit was the pre-existing `docker/Dockerfile` use of ordinary password terminology.
- Upstream test keys/certificates exist only in ignored third-party dependency/build trees and were not committed.
- No credential was printed or added.

## 15. Final Git status

After the final report/manifest commit, `git status --porcelain` is required and verified to be empty. The final command transcript is also reported in the task handoff.

## 16. Final unpushed commit count

After the final push, `git rev-list --count @{u}..HEAD` is required and verified as `0`.

`git ls-files --others --exclude-standard` is also required and verified empty. A separate `git ls-files --others --ignored --exclude-standard -- docs runs tier05_fork_20260712T090728Z` audit is verified empty after historical externalization.

## 17. Manual review still needed

- Close RAPTOR current-action writer/data-plane attribution.
- Implement and run original-versus-repaired allocation/single-writer mechanism differential.
- Run S2/S3 fallback, S4 repeated switching, and residual preserve/reset experiments.
- Rerun any legacy wall-clock boundary/search claim before promoting it from `legacy_unverified`.
- Determine exact historical artifact ownership for D1 and D2.
- Decide whether the equivariance probe becomes an optional BATON checker evaluation.
- Back up or relocate the two local external archives if `/home/car` and `/mnt/nvme/px4_work` are not the desired long-term institutional storage locations; their per-file hashes and paths are committed.

## Completion statement

All pre-existing trackable research work was checkpointed and pushed before organization. Uncertain and negative work was retained and indexed. Raw bytes were not rewritten; oversized raw/runtime evidence was externally preserved under the explicit no-LFS exception and fully hashed. Git history and tags were not rewritten, and no force push or destructive cleanup command was used.
