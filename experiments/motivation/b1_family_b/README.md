# B1 registered-controller inventory and Family B Gate

This directory freezes and records B1, a revision-locked study of registered
PX4 controller-graph replacement, controller lifecycle, route conformance,
allocator/writer observability, and conditional bounded SITL feasibility.

The preregistration must be committed and pushed to `origin/main` before the
formal B1-A inventory begins. `family_b/` is historical input only: no retained
overlay, prototype, build result, or conclusion is accepted until it is
revalidated against the source lock in this directory.

The ordered phases are B1-A source inventory, B1-B observability audit, B1-C
reference Gate, conditional B1-D build/static integration, conditional B1-E
normal Classic→Reference→Classic SITL, conditional B1-F controlled recovery,
and B1-G adjudication. A failed B1-C Gate makes B1-D/E/F `NOT_APPLICABLE`; it
does not make them PASS and does not authorize substituting mc_nn or RAPTOR
runtime attempts.

Raw builds, ULogs, full traces, and runtime logs belong under the ignored
`runs/motivation/b1_family_b/` tree. Git retains only the lock, inventory,
compact evidence, manifest, append-only ledger, Gate, report, and any small
pre-runtime implementation or observation-only instrumentation amendment.

B1 may close positively, conditionally, negatively, measurement-insufficient,
or environment-blocked. Every compliant closure advances only to the registered
M-FINAL phase; B1 never authorizes a random campaign, complete Stateful
Testing, or M-FINAL execution.

B1-A found eight inventory subjects: two concrete true registered controller
routes (`mc_nn` and `mc_raptor`), one selected partial-subgraph reference, one
classic baseline, and four exclusions. B1-C authorized the bounded reference
in `reference_decision.yaml`; the authorization remains conditional on the
separately pushed amendment and an accepted B1-D build/static attempt.
