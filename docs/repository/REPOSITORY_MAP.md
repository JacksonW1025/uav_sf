# Repository map

| Path | Role | Policy |
|---|---|---|
| `docs/narrative/` | unique current narrative and scope | exactly two files |
| `config/dependencies.lock.yaml` | exact dependency/environment identity | no floating refs |
| `docs/design/` | route, timestamp, writer, and trace contracts | source-backed |
| `docs/motivation/` | P-1, M2, M4, and gated P0 evidence | no fabricated results |
| `scripts/setup/` | Family A/B profile bootstrap | Family A has no B dependency |
| `scripts/behavior/` | interface-neutral behavior core | no ROS/PX4 imports |
| `scripts/adapters/` | Family A control adapters | no Family B imports |
| `scripts/tracing/` | route trace collection | explicit timestamp/evidence domains |
| `scripts/probes/` | small gated probes | no random campaigns |
| `scripts/analysis/` | compact trace summaries | schema validated |
| `patches/px4/route_observability/` | observation-only PX4 patches | exact-commit, tested |
| `family_b/` | future cross-family build assets | optional, revalidate first |
| `data/schemas/` | machine-readable contracts | tested |
| `data/processed/` | compact reproducible outputs | source provenance required |
| `experiments/motivation/` | gate result | machine readable |
| `experiments/probes/p0/` | P0 procedure | run only after gate pass |
| `external/`, `ros2_ws/`, `runs/` | ignored dependencies/build/raw runtime | never tracked |

The former in-tree legacy archive is intentionally absent. Use
`docs/repository/LEGACY_RECOVERY.md` for the protected Git recovery point.
