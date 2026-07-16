# Pre-cleanup repository audit

Audit date: 2026-07-16  
Branch: `main`  
Audited HEAD: `4413088a9c1165af2ef6f38e08dfb87720804f63`  
Protection tag: `pre-route-transition-cleanup-20260716`

This report records the repository state before route-transition cleanup. It is an audit and disposition plan, not a claim that legacy evidence is invalid. Uncertain research material is assigned to `ARCHIVE_LEGACY` or `NEEDS_REVIEW`, never deleted by filename alone.

## Safety and scope

- `git fetch origin`, `git checkout main`, and `git pull --ff-only origin main` completed; the branch was and remains `main`.
- The pre-existing replacement of `docs/NEW_NARRATIVE_v5.md` by the complete `docs/NEW_NARRATIVE_v4.md` was checkpointed and pushed as `4413088` before this audit.
- The V4 title contains **Testing Route-Replacing Authority Transitions in PX4**.
- No password, access token, private key, or `.env` was found in the checkpointed research changes. Pattern hits were confined to ignored upstream PX4/Fast DDS test fixtures under `external/`.
- No history rewrite, force push, reset, clean, or other destructive Git operation is planned.

## Required command summary

The full outputs of the required inventory commands were captured during the audit; the compact findings are below.

| Check | Result |
|---|---:|
| `git status --porcelain=v1` | clean after checkpoint |
| `git ls-files` | 2,324 tracked paths |
| `git ls-files -ci --exclude-standard` | 1,147 tracked-and-ignored paths |
| `git ls-files --others --exclude-standard` | 0 untracked, non-ignored paths |
| `git count-objects -vH` | 171 loose objects / 9.07 MiB; 5,935 packed objects / 2.62 GiB |
| tracked `runs/` paths | 1,123 |
| tracked `docs/` paths | 391 |
| tracked `scripts/` paths | 80 |
| tracked `.log` / `.ulg` | 8 / 0 |
| tracked files over 10 MiB | 2 |
| tracked files over 50 MiB | 1 |

This Git version requires `-c` or `-o` with `git ls-files -i`; therefore the semantically equivalent tracked-file audit uses `git ls-files -ci --exclude-standard`.

## Size and shape

| Top-level path | Working-tree size | Tracked paths | Tracked bytes | Disposition |
|---|---:|---:|---:|---|
| `.git/` | 2.7 GiB | n/a | n/a | `NEEDS_REVIEW` (history only; do not rewrite) |
| `external/` | 5.3 GiB | 0 | 0 | `DELETE_GENERATED` for builds; `NEEDS_REVIEW` for dirty clone until patch capture |
| `ros2_ws/` | 250 MiB | 0 | 0 | `DELETE_GENERATED` build/install/log; setup remains reproducible |
| `data/` | 69 MiB | 6 | 71,359,348 | `EXTERNALIZE_RAW` large manifests; keep compact policy/manifests |
| `runs/` | 59 MiB | 1,123 | 38,102,884 | `EXTERNALIZE_RAW`; retain compact legacy summaries in archive |
| `tier05_fork_20260712T090728Z/` | 37 MiB | 602 | 29,260,898 | `EXTERNALIZE_RAW`; retain compact legacy summaries in archive |
| `docs/` | 21 MiB | 391 | 15,956,570 | V4 `KEEP_ACTIVE`; prior reports `ARCHIVE_LEGACY` |
| `scripts/` | 3.2 MiB | 80 | 1,279,948 | classify individually; generic code active, campaign code legacy |
| `img/` | 1.2 MiB | 23 | 1,124,431 | `ARCHIVE_LEGACY` old article figures |
| `tests/` | 324 KiB | 13 | 85,778 | generic tests active; campaign-specific tests legacy |
| `config/` | 264 KiB | 41 | 139,636 | PX4 overlay active; old campaign configs legacy |
| `experiments/` | 228 KiB | 25 | 18,820 | `ARCHIVE_LEGACY` pre-V4 experiments |
| `artifacts/` | 40 KiB | 5 | 671 | `DELETE_GENERATED` mapping-only layer after merge into repository/data docs |
| `boards/`, `patches/` | 76 KiB | 5 | 49,456 | `KEEP_ACTIVE` reproducible Family B overlay assets |
| `configs/`, `px4_overlay/` | 16 KiB | 2 | 635 | `DELETE_GENERATED` mapping-only layers after merge |
| `docker/` | 20 KiB | 3 | 7,436 | `KEEP_ACTIVE` |

The largest current-tree files are:

| Bytes | Path | Disposition |
|---:|---|---|
| 56,700,424 | `data/manifests/HISTORICAL_IGNORED_FILE_MANIFEST.tsv` | `EXTERNALIZE_RAW` (full manifest exceeds 10 MiB) |
| 14,594,634 | `data/manifests/EXTERNAL_RAW_FILE_MANIFEST.tsv` | `EXTERNALIZE_RAW` (full manifest exceeds 10 MiB) |
| 2,806,447 | `docs/round5_delivered_state_20260709/raptor_v8_delivered_state.csv` | `ARCHIVE_LEGACY` |
| 2.25–2.48 MiB each | seven `runs/**/checkpoint.json` files | `EXTERNALIZE_RAW` |
| 1.08–1.22 MiB each | six `runs/**/evals.jsonl` files | `EXTERNALIZE_RAW` |

There are no tracked zero-byte files and no tracked symlinks. Broken symlinks found by the filesystem scan are confined to ignored/generated PX4 build trees and are `DELETE_GENERATED`.

## Tracked ignored files and runtime trees

All 1,147 tracked-and-ignored paths are accidental policy exceptions:

- 1,123 paths under `runs/campaigns/`;
- 24 paths under `docs/px4_race_r4_gate_20260709/evals/`.

They include eight identical tracked build logs, checkpoints, JSONL evaluation streams, per-evaluation records, and theta files. `runs/` must return to an untracked runtime-only location. Raw/runtime data will be moved to the external archive with SHA-256 inventory; compact research summaries will be copied or moved to `archive/pre_v4_baton/experiments/` before the tracked originals are removed.

## History-only large blobs

The 2.62 GiB pack still contains historical ULogs and old manifests. The largest 100-object scan shows numerous ULogs around 52.3–52.8 MiB, including old M2b, estimator, RAPTOR nonfinite, and state-map evaluations. The largest reported blob is the 56,700,424-byte historical ignored-file manifest. These are `NEEDS_REVIEW` history debt only: this cleanup will report them but will not use `filter-repo`, BFG, force-push, or otherwise rewrite history.

## Duplication, layout, and references

- Content-hash analysis found 11 duplicate blob groups covering 204 paths. Major groups are repeated build logs, repeated route-theta JSON, repeated model SDFs, and repeated campaign records. Runtime duplicates are `EXTERNALIZE_RAW`; historical report copies are retained only inside the legacy archive when they add provenance.
- `artifacts/`, `configs/`, `px4_overlay/`, and the category-only `scripts/*/README.md` directories are mapping layers rather than independent assets. Their useful descriptions will be merged into active documentation.
- `docs/` has 364 date-named files, including 68 Markdown reports. These primarily document completed BATON/F1/F2/F2a, RAPTOR, wave, multi-policy, wall-clock, audit, and article work and are `ARCHIVE_LEGACY`.
- The current Markdown checker reports one broken local link: the root README still points to deleted `docs/NEW_NARRATIVE_v5.md`.
- A path/reference scan found 606 old-path or legacy command references. Those references occur chiefly inside historical reports and should remain as provenance after archival; active README, AGENT, setup, validation, and repository maps must be updated.
- Absolute machine-local strings are widespread (23,668 text hits), overwhelmingly inside retained runtime JSON records. Active code will be parameterized; archived reports keep historical commands as provenance. Runtime records with local paths move outside Git.
- No tracked symlink is broken. Empty directories are generated, ignored runtime/build paths and will disappear when generated trees are removed.

## Ignored PX4 tree

`external/PX4-Autopilot` is dirty. Source changes include airframe registration, EKF2 and sensor timing/state instrumentation, `mc_raptor`, DDS topic configuration, and local board/airframe files; many nested submodules also report modified/uninitialized state. This is `NEEDS_REVIEW` until the source diff is compared with tracked patches/boards/installers. Required research changes must be captured as tracked patches or overlays; generated builds and the unreproducible dirty working tree must not be the final repository state.

## Disposition matrix

| Class | Material | Rationale / action |
|---|---|---|
| `KEEP_ACTIVE` | Docker; PX4/ROS setup; board/patch assets; general SITL, logging, timing, replay, oracle, freshness/latency/writer tracing; V4; route/Motivation templates | Direct support for route observability and Family A, or minimal Family B reproduction |
| `MOVE_REUSABLE` | General setup, trace, probe, analysis, validation scripts currently at flat legacy paths | Move to the new script taxonomy and update active imports/commands |
| `ARCHIVE_LEGACY` | old narrative/context; BATON S1–S4; F1/F2/F2a; mc_nn/RAPTOR campaigns; unclipped ablation; wave1/wave2/multi-policy; wall-clock search; completed audits/reports; old configs/runners/plots/tests/figures | Preserve evidence and paper evolution without presenting it as current Family A evidence |
| `EXTERNALIZE_RAW` | `runs/`; tier-0.5 runtime tree; per-eval data; checkpoints; build/runtime logs; ULogs; large trace/manifests | Raw/runtime material does not belong in Git; record stable path, bytes, hash, experiment, status |
| `DELETE_GENERATED` | caches; ROS/PX4 build/install/log output; broken generated symlinks; duplicate build logs; mapping-only layers after merge | Deterministic/generated or structurally redundant; deletion is justified by reproducibility and retained canonical docs |
| `NEEDS_REVIEW` | dirty ignored PX4 source until diff capture; history-only large blobs; any ambiguous legacy research item | Preserve/capture first; do not infer disposability from name |

## Cleanup execution plan backed by this audit

1. Capture dirty PX4 research modifications into tracked patch/overlay form, then remove generated builds and do not retain an unreproducible dirty ignored source tree.
2. Create `archive/pre_v4_baton/` with narratives, reports, experiments, configs, scripts, figures, and exact path indexes. Use `git mv` for tracked research assets.
3. Move raw/runtime content and the two oversized manifests to `../uav_sf_external_archive/pre_v4_cleanup_20260716/`; create a compact Git manifest with hashes and aggregate rows.
4. Establish the V4 narrative, design, Motivation Study, repository, data, experiment-template, and active-script entry points.
5. Remove only the generated/redundant items identified above, recording exact old paths and reasons in cleanup indexes and the final report.
6. Run compilation, shell syntax, JSON/YAML parsing, Markdown links, unit tests, diff checks, tracked-ignore audit, untracked audit, and large-file audit through one canonical validation command.

