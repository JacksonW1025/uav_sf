# BATON Claim Audit

| Claim | Grade | Evidence | Boundary |
|---|---|---|---|
| external-mode allocation config is rejected as stale | `mechanism_observed` | PX4 source/history audit and Round-4 report | physical repair consequence not yet measured |
| classical allocator remains active in learned mode | `mechanism_observed` | source/trace audit | writer dose alone is not a causal physical result |
| `actuator_motors` has classical and learned writes | `mechanism_observed` | mc_nn value/fingerprint attribution | RAPTOR attribution remains incomplete |
| admission reply contains incompletely initialized fields | `mechanism_observed` | code and minimal listener reproduction | end-to-end flight consequence not tested |
| deployed mc_nn S1 candidate states have catastrophic differential | `confirmed` | classical recovery plus hardened mc_nn anchor campaign | applies to tested S1 anchors/SUT only |
| hardened anchors reproduce 100/100 | `confirmed` | Tier-0.5 frozen rule, 100 valid Stage-3 runs | not a claim of universal bit-exact determinism |
| trigger-state convergence improves about 85× | `confirmed` | Tier-0.5 Gate A reports 84.8× trigger-span reduction | preregistered pair-1 comparison |
| old boundary is non-monotonic and holed | `legacy_unverified` | wall-clock dense/search archive | rerun required on hardened harness |
| RAPTOR distinguishes controller behavior | `confirmed` | retained RAPTOR campaign and unclipped ablation summaries | actual writer/data-plane equivalence not closed |
| residual state causes later physical risk | `planned` | lifecycle/code differences only | no completed physical differential |
| fallback path satisfies the contract | `planned` | scenario/oracle design only | S2/S3 experiments incomplete |
| single-writer repair removes the physical differential | `planned` | repair experiment is designed | must compare original versus repaired PX4 |

Negative and gate-failure evidence is retained. Round-4 `GATE_FAIL` is not evidence that the actuator race is harmless.
