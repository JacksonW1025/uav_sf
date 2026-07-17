# Oracle Validation Report

Oracle `0.3` was evaluated against 25 trace-level cases and 18 valid low-risk
live SITL runs. All 70 scored assertions (43 trace, 27 live) matched their
ground truth. This result validates the tested Oracle and evidence pipeline; it
does not identify a production PX4 defect because every violating live case is
an explicitly labeled test mutant.

## Frozen method

The trace manifest, live matrix, 300 ms installation/recovery deadline, 20 ms
minimum continuity gap, and three-period continuity allowance were frozen in
commit `6aa47c7` before the remaining controlled repeats. The 300 ms deadline
was selected from the retained P0 normal maximum of 248 ms plus a 52 ms guard
margin. It was not changed after observing the 200, 500, or 1000 ms live cases.

The trace layer copies retained real P0/P2/P3 traces and applies declared
mutations in ignored run storage. Base SHA-256 values are checked before and
after every mutation. These cases validate decision logic; they are not claimed
as real PX4 failures. The live layer runs the actual collector and Oracle
against a separately built, default-disabled mutant PX4.

## Trace mutation results

The 25 cases produced 43 clause assertions:

| Measure | Result |
|---|---:|
| Ground-truth violation detections | 14 |
| Ground-truth violation misses | 0 |
| Normal-case false-positive violations | 0 |
| Incomplete-evidence UNKNOWN assertions | 12 |
| Unexpected UNKNOWN assertions | 0 |
| Correct clause assertions | 43 / 43 |

Every clause has a PASS, VIOLATION, and UNKNOWN case. NOT_APPLICABLE is covered
by both a no-transition trace and a transition for which recovery does not
apply. Cross-clause violations occurred in 11 deliberately mutated cases:
recovery (7), continuity (3), revocation (2), installation (2), and exclusivity
(1). These are reported, not treated as errors: for example, deleting a final
writer can simultaneously violate installation, continuity, and recovery.

## Live results

All 18 planned runs were valid and all 27 target assertions were correct:

| Profile | Runs | Target assertions | Outcome |
|---|---:|---:|---|
| Canonical observation-only control | 3 | 9 | all PASS |
| Install delay 200 ms | 3 | 3 | all PASS (below deadline) |
| Install delay 500 ms | 3 | 3 | all VIOLATION |
| Install delay 1000 ms | 3 | 3 | all VIOLATION |
| Recovery incomplete 500 ms | 3 | 3 | all VIOLATION |
| Old-route late consumption 500 ms | 3 | 6 | revocation and recovery all VIOLATION |

Observed installation completion was 24–32 ms in controls, 232–236 ms for the
200 ms mutant, 528–536 ms for the 500 ms mutant, and 1016–1024 ms for the 1000
ms mutant. Recovery-incomplete also caused installation to violate on the exit
transition in all three repeats; this is the only live cross-clause side effect.

The competing-writer mutant remains
`NOT_IMPLEMENTED_WITH_JUSTIFICATION`: the current low-risk design cannot prove
that a second injected writer has real influence in the final actuator authority
domain. It is covered at trace level and no ineffectual writer was fabricated.

## Environment failures retained outside scoring

Before the valid campaign, the host exposed three independent compatibility
failures. The initial attempt lacked ROS Jazzy; the repository-pinned XRCE agent
required newer glibc/libstdc++; and a prebuilt PX4 required `libprotobuf.so.32`.
After switching to an ignored Humble workspace and host-built locked sources,
an inherited Gazebo resource path loaded an x500 model from another checkout,
causing missing compass data. The live harness now clears that inherited path.
Attempt JSON/logs remain under `runs/oracle_validation/live`; none entered the
valid-case denominator or was classified as an SUT violation.

## Oracle 0.3 changes supported by the evaluation

- missing required target/recovery evidence is VIOLATION only for a declared
  complete source artifact and UNKNOWN for incomplete evidence;
- post-exit old-epoch consumption, allocator, and writer influence are checked;
- stale subject timestamps provide explicit producer/session association for
  late old-route consumption;
- stable competing writers and old/new epoch overlap violate exclusivity;
- a complete final-writer sequence can prove a continuity gap;
- source/target mode selectors evaluate the intended transition in multi-stage
  flights;
- validation provenance and completeness are present in schema `1.2`, while
  route trace schema `1.2` remains sufficient.

Detailed evidence is in `data/processed/oracle_validation/case_results.json`,
`clause_confusion_matrix.tsv`, `live_case_results.json`, and
`live_clause_results.tsv`.
