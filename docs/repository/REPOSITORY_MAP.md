# Repository map

| Path | Role | Policy |
|---|---|---|
| `docs/narrative/` | current pointer, complete Narrative V7, and scope | exactly three files |
| `config/dependencies.lock.yaml` | exact dependency/environment identity | no floating refs |
| `docs/design/` | route, timestamp, writer, and trace contracts | source-backed |
| `docs/motivation/` | frozen stage reports and M-FINAL report | preserve historical conclusions |
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
| `experiments/motivation/` | preregistrations, ledgers, and machine Gates | append-only phase evidence |
| `experiments/fuzzer_v0/family_a/` | frozen Family A Fuzzer v0 preregistration and artifact index | `PREREGISTERED_NOT_ACTIVATED`; zero attempts |
| `experiments/fuzzer_v0/family_a/activation_review/` | independent V0-P static readiness review, decision, ledger, and future runbook | `DECLINE_IMPLEMENTATION_NOT_READY`; no runtime authorization |
| `experiments/probes/p0/` | reproducible P0 procedure | gate passed; normal flow only |
| `external/`, `ros2_ws/`, `runs/` | ignored dependencies/build/raw runtime | never tracked |

The former in-tree legacy archive is intentionally absent. Use
`docs/repository/LEGACY_RECOVERY.md` for the protected Git recovery point.

The pre-M-FINAL Fuzzer v0 design and utilities remain prototype material. The
only current preregistration authority is the Family A bundle above together
with its source lock, Oracle lock, Evidence Admissibility Gate, activation
Gate, and zero attempt ledger.
