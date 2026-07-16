# Route-transition repository cleanup report

Cleanup date: 2026-07-16

## 1. Cleanup baseline

- Initial synchronized `main` HEAD: `36f9e6a7dd2afd56cb78e4ecf3d7a793ae902f19`.
- The pre-existing V4 addition / V5 deletion was checkpointed as `441308827893809cf7bd0b7fff10adf85f8b7938`.
- Pre-cleanup audit commit: `c0f12f1cc1ea1c1130b55d485775cd3968fb6e02`.
- Cleanup implementation HEAD: `db6bc999f392b1f063c15327dab6277787ea52e2`.

The final report/finalization commit follows the cleanup implementation commit; the handoff terminal checks below describe the pushed final `main` state.

## 2. Protection point

Annotated tag `pre-route-transition-cleanup-20260716` points to the pushed checkpoint. The tag was pushed before any research asset was moved, externalized, or deleted.

## 3. Deleted or externalized tracked files

Relative to the audited baseline, 1,662 tracked paths were removed from their old locations:

| Group | Count | Reason | Preserved form |
|---|---:|---|---|
| remaining `runs/**` runtime | 1,062 | per-eval/theta/checkpoint/JSONL/build-log runtime | external full manifest; 61 compact summaries archived in Git |
| remaining tier-0.5 runtime | 583 | per-evaluation and large campaign streams | external full manifest; 19 rules/verdict/provenance files archived in Git |
| legacy full manifests | 3 | per-file manifests, including 14.6 MiB and 56.7 MiB files | external originals with SHA; compact aggregate Git manifest |
| `artifacts/**` mapping layer | 5 | category-only duplicate | `data/README.md` and repository map |
| `configs/README.md`, `px4_overlay/README.md`, `data/raw/README.md` | 3 | mapping-only duplicates | consolidated active README files |
| old script/category mapping README files | 6 | superseded mapping-only layer | `scripts/README.md` and exact script inventory |

Generated ignored content was also removed: PX4 build trees and dirty ignored clone, Micro XRCE-DDS Agent build output, ROS 2 build/install output, Python/pytest caches, empty generated directories, and broken generated symlinks. ROS build logs were externalized rather than discarded. Exact groups and evidence are in `archive/pre_v4_baton/indexes/DELETION_INDEX.tsv`.

## 4. Archived research files

The final legacy tree contains 628 tracked files:

| Archive area | Files | Content |
|---|---:|---|
| `narratives/` | 2 | old V5 narrative and prior project context |
| `experiments/` | 116 | compact campaign summaries, tier-0.5 evidence, old workspace/tests |
| `reports/` | 386 | completed BATON/F1/F2/F2a/RAPTOR/wave/audit reports and attachments |
| `configs/` | 40 | old campaign config and unclipped-only overlays |
| `scripts/` | 54 | campaign runners, old probes, analyses, and plotting/utility code |
| `figures/` | 23 | old article/report figures |
| `indexes/` | 6 | old indexes plus path, deletion, and script inventories |
| archive root | 1 | archive scope, status, caveats, and mappings |

The group mapping is `archive/pre_v4_baton/indexes/PATH_MAP.tsv`. Legacy results remain available as Family B historical evidence but require V4-harness revalidation before use as a current cross-family claim.

## 5. External data archive

Location: `/mnt/nvme/uav_sf_external_archive/pre_v4_cleanup_20260716/`

| Item | Value |
|---|---|
| Externalized file rows | 1,665 |
| Externalized file bytes | 144,484,288 |
| Full manifest | `FULL_FILE_MANIFEST.tsv` |
| Full manifest SHA-256 | `108923dd981845f7c22a60fe364f1f0e508e4015d904f4978b092e0525251168` |
| Full SHA verification | 1,665 passed, 0 failed |
| Git aggregate manifest | `data/manifests/PRE_V4_EXTERNAL_ARCHIVE.tsv` (17 aggregate rows) |

The external archive also stores the pre-removal ignored PX4 diagnostics:

- `px4_dirty_source.diff`: 42,131 bytes, SHA-256 `b0db6d9ec038a7d0eb08e4ff407fac00d6eb1f129995432ab14f2b06942c54fa`;
- `px4_dirty_status.txt`: 1,480 bytes, SHA-256 `a0d0656f139eb718357b294f0c76aa7a6325bf15fc2bfcc68b48be7bcd6f416a`.

The source changes were checked against active `m2b_state_shim.patch`, board/airframe overlays, DDS installer, and the archived unclipped patch before the ignored dirty clone was removed.

## 6. Active directory structure

```text
.
├── README.md
├── AGENT.md
├── docker/
├── boards/
├── patches/
├── config/
├── data/{manifests,processed,traces}/
├── docs/{narrative,motivation,design,repository,evidence}/
├── experiments/{motivation,probes,templates}/
├── scripts/{setup,tracing,probes,analysis,validation}/
├── tests/
└── archive/pre_v4_baton/
```

`external/` and `ros2_ws/` remain ignored local dependency workspaces. Their build/log output is not canonical. `runs/` remains an ignored runtime path and has no tracked content.

## 7. Legacy directory structure

```text
archive/pre_v4_baton/
├── README.md
├── narratives/
├── experiments/
├── reports/
├── configs/
├── scripts/
├── figures/
└── indexes/
```

Archive material is excluded from the active Motivation Study by default. Historical commands are provenance, not active path guarantees.

## 8. Active scripts

There are 21 active code scripts:

- setup (9): PX4 clone, ROS 2 setup, Micro XRCE-DDS build, two Family B builds, and four overlay installers;
- tracing (3): DDS ground-truth overlay, ULog sanity, and parameterized actuator attribution;
- probes (2): reusable Offboard task and minimal Family B differential replay;
- analysis (5): metrics, comparison, retained property oracle/fitness, and validity gates;
- validation (2): Markdown link checker and canonical repository validator.

Only `scripts/setup/clone_px4.sh`, `scripts/setup/setup_ros2_ws.sh`, and `scripts/validation/validate_repo.sh` are canonical repository-level entry points. The Family B scripts are retained compatibility/reproduction surfaces, not the current research mainline. Full fields and per-file status are in `scripts/README.md` and `archive/pre_v4_baton/indexes/SCRIPT_INVENTORY.tsv`.

## 9. Archived scripts

There are 54 archived `.py`/`.sh` scripts. They cover old BATON campaign runners, RAPTOR/unclipped experiments, F1/F2/F2a, wave/multi-policy, wall-clock/tier-0.5 search, completed audits, plotting, and old artifact utilities. None is an active entry point. The exact list, category, supported family, replacement, and status are in `archive/pre_v4_baton/indexes/SCRIPT_INVENTORY.tsv`.

## 10. Tracked ignored files

- Before cleanup: 1,147 (`runs/campaigns`: 1,123; old `docs/**/evals`: 24).
- After cleanup: 0 using `git ls-files -ci --exclude-standard`.
- Tracked `runs/` files after cleanup: 0.
- No workflow relies on `git add -f` for current results.

This Git version rejects `git ls-files -i` without `-c` or `-o`; all tracked-ignore checks therefore use the equivalent explicit `-ci` form.

## 11. Current-tree large files

- Tracked files over 10 MiB: 0 (previously 2).
- Tracked files over 50 MiB: 0 (previously 1).
- Tracked `.log`: 0 (previously 8).
- Tracked `.ulg`: 0.
- The two oversized full manifests were externalized and replaced by a 17-row aggregate manifest.

## 12. Large objects remaining in Git history

History was intentionally not rewritten. The object scan reports:

- packed repository size: 2.62 GiB;
- historical blobs over 10 MiB: 243;
- historical blobs over 50 MiB: 5;
- largest historical blob: 56,700,424-byte `HISTORICAL_IGNORED_FILE_MANIFEST.tsv` (`8bc250363b29adc7e9f1989732fde25a6cf8603e`).

Historical ULogs around 52 MiB remain reachable from earlier commits. A later history-rewrite project would require separate coordination; no `filter-repo`, BFG, reset, force-push, or history rewrite was performed here.

## 13. Validation results

All cleanup-relevant validation passed:

| Validation | Result |
|---|---|
| `python3 -m compileall -q scripts tests` | pass |
| shell syntax for every `scripts/` and `docker/` `.sh` | pass |
| all tracked `.json` with `jq empty` | pass |
| all tracked `.yaml`/`.yml` with PyYAML | pass |
| Markdown local-link checker, including archive | 8 checked, 0 broken |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$PWD" python3 -m pytest -q tests` | 14 passed |
| `git diff --check` and cached diff check | pass |
| tracked ignored-file audit | 0 |
| unexpected untracked-file audit | 0 |
| tracked file over 10 MiB audit | 0 |
| `scripts/validation/validate_repo.sh` | pass |
| external per-file SHA-256 verification | 1,665 passed, 0 failed |

The validator removes its own Python/pytest caches on exit. Full PX4/SITL execution was not run: this task explicitly stops before new experiments, and the ignored dirty PX4 clone was removed after its reproducible modifications were captured/verified. Environment-dependent execution begins with the documented clone/setup commands.

## 14. Current narrative and Motivation Study entry points

- Sole current narrative: `docs/narrative/CURRENT_NARRATIVE.md`.
- Scope summary: `docs/narrative/SCOPE.md`.
- Sole Motivation Study entry: `docs/motivation/README.md`.
- Immediate work: P-1 Route Observability Feasibility, M2 External Mode and Registration Importance, M4 Official Test Coverage Gap, and P0 Official Handoff Flow.

The complete V4 was found in the repository as `docs/NEW_NARRATIVE_v4.md` and moved to the unique current entry. No substitute narrative was fabricated.

## 15. Unresolved research items

No cleanup blocker remains. Expected research unknowns are deliberately left unfilled:

- route-field availability, timestamp mapping, and writer attribution still require P-1 feasibility work;
- official external-mode lifecycle evidence and official test coverage have not yet been collected;
- Motivation inventory/matrix files contain schemas only;
- the V4 route-transition oracle/fuzzer has not been implemented;
- legacy Family B results have not been revalidated under the new harness.

These are the next research tasks, not cleanup failures.

## 16. Final repository state

Handoff terminal state after final commit/push:

- branch: `main`;
- `git status --porcelain`: empty;
- `git ls-files --others --exclude-standard`: empty;
- `git ls-files -ci --exclude-standard`: empty;
- upstream unpushed commit count: 0;
- current tracked files: 691;
- remote protection tag present.
