# Repository map

The active surface is intentionally small and route-transition oriented. Historical paths are not active entry points even when preserved under the legacy archive.

| Path | Role | Data policy |
|---|---|---|
| `README.md`, `AGENT.md` | project and agent entry points | active |
| `docs/narrative/` | unique current V4 narrative and scope | active |
| `docs/motivation/` | Motivation Study M1–M5 templates/evidence | active; no fabricated observations |
| `docs/design/` | route model, observability matrix, profile schema | active |
| `docs/repository/` | audit, map, cleanup report | active |
| `docs/evidence/` | current evidence pointers | active; legacy clearly labelled |
| `experiments/motivation/` | Motivation Study plans/adapters | code/plans only; runtime to `runs/` |
| `experiments/probes/` | focused post-feasibility probes | code/plans only |
| `experiments/templates/` | route-aware testcase templates | no runtime data |
| `scripts/setup/` | one PX4 clone, one ROS setup, Family B overlays/builds | logs/builds ignored |
| `scripts/tracing/` | signal installation and trace attribution | raw captures external |
| `scripts/probes/` | Offboard task and minimal Family B replay | runtime ignored |
| `scripts/analysis/` | retained compact Family B analysis | derived summaries only |
| `scripts/validation/` | canonical repository validation | no retained output |
| `boards/`, `patches/`, `config/` | reproducible PX4 overlays and minimal Family B config | tracked source/config only |
| `data/manifests/` | compact aggregate external-data inventory | no large per-file manifests |
| `data/traces/` | schemas/small curated examples | no raw traces |
| `data/processed/` | compact derived summaries | source/provenance required |
| `runs/` | local runtime output | ignored; nothing tracked |
| `external/`, `ros2_ws/` | local dependency/source/build workspaces | ignored; reproducible setup required |
| `archive/pre_v4_baton/` | prior BATON evidence and implementation | legacy; not current Motivation Study |

## Consolidated mapping layers

- The former `configs/` map is merged into `config/README.md`.
- The former `px4_overlay/` map is merged into `boards/README.md`, `patches/README.md`, and `config/README.md`.
- The former `artifacts/` category map is replaced by `data/README.md`, this map, and the legacy archive layout.
- Old `docs/indexes/` content is retained under `archive/pre_v4_baton/indexes/`.

## Canonical entry points

| Purpose | Command/path |
|---|---|
| Current narrative | `docs/narrative/CURRENT_NARRATIVE.md` |
| Motivation Study | `docs/motivation/README.md` |
| PX4 clone | `scripts/setup/clone_px4.sh` |
| ROS 2 setup | `scripts/setup/setup_ros2_ws.sh` |
| Minimal mc_nn build | `scripts/setup/build_px4_mcnn_sih.sh` |
| Minimal RAPTOR build | `scripts/setup/build_px4_raptor_sih.sh` |
| Repository validation | `scripts/validation/validate_repo.sh` |
| Legacy archive | `archive/pre_v4_baton/README.md` |
| External raw inventory | `data/manifests/PRE_V4_EXTERNAL_ARCHIVE.tsv` |
