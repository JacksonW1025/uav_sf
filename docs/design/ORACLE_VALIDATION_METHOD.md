# Oracle Validation Method

Status: frozen before the controlled live campaign. Oracle: `0.3`. Trace
schema: `1.2` (no new trace field was needed).

## Ground truth and two validation layers

The trace layer starts from retained real P0, P2, and P3 PX4 traces. Each case
records the base SHA-256 before and after mutation, the mutation operators, the
target clause, the expected status, evidence completeness, and the resulting
trace hash. The base must remain byte-identical. Mutated traces are generated in
ignored `runs/oracle_validation/trace_mutations`; only the manifest, reference
traces, case results, and clause matrix are committed.

The live layer uses low-risk x500 hover SITL. Mutants are compiled only in the
isolated `PX4-Autopilot-oracle-validation-mutant` worktree and are disabled
unless their explicit environment selector is present. Canonical controls use a
separate locked-commit worktree containing the observation-only patch but no
mutant patch. A live result is valid only when the normal P0 validity checks,
ULog collection, clock bridge, trace collection, and Oracle evaluation all
finish. Setup, PX4, ROS, agent, or Gazebo failures are environment failures and
are excluded from detection rates while their raw attempt evidence is retained.

## Frozen trace cases

`experiments/oracle_validation/trace_cases.yaml` preregisters PASS, VIOLATION,
UNKNOWN, and NOT_APPLICABLE cases. The violations cover late old-epoch
consumption/allocator/writer influence, missing or delayed installation stages,
stable competing writers, overlapping route epochs, a real writer gap, and
incomplete fallback recovery. Incomplete evidence cases independently remove
critical-window coverage, writer sequence, candidate-writer coverage, clock
mapping, route epochs, or source-artifact completeness.

## Frozen live cases and scoring

`experiments/oracle_validation/live_mutants.tsv` preregisters three repeats of
each control and mutant setting. Installation delay uses 200, 500, and 1000 ms;
recovery-incomplete and old-route-late-consumption use 500 ms. The 200 ms case
is below the frozen 300 ms deadline; 500 and 1000 ms are above it. All valid
target-clause repeats must match the preregistered status. All valid controls
must be free of VIOLATION. Competing-writer live injection is intentionally not
implemented because this design cannot prove two safe writers in the final
actuator authority domain; it remains trace-level validation.

## Host compatibility boundary

This host provides ROS 2 Humble while the canonical workspace was built under
Jazzy. Live validation therefore uses an ignored Humble workspace containing
the same locked `px4_msgs`, plus the host-built `/usr/local` XRCE agent. The
repository-pinned agent and prior PX4 binaries are retained as failed-attempt
evidence when their newer glibc/protobuf dependencies cannot load. The live
harness clears inherited Gazebo resource paths so another PX4 checkout cannot
silently supply the vehicle model. None of these compatibility choices changes
the canonical source lock or mutant semantics.

## Outputs

The trace confusion matrix is scored clause-by-clause, not as aggregate
accuracy. Reports include normal false positives, target detections, misses,
incomplete-evidence UNKNOWNs, unexpected UNKNOWNs, and cross-clause effects.
Mutants demonstrate test sensitivity only and are never classified as PX4
production defects.
