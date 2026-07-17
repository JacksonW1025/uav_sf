# Phase A.1 repository report

Study: **Testing Route-Replacing Authority Transitions in PX4**

Run date: 2026-07-16

Starting repository commit: `98dc60237d96250923b3d8cf146d51001f9d2c76`

Final repository commit: the `main` commit containing this report; its exact SHA is recorded by the final push audit because a commit cannot contain its own object ID.

## 1. Patch repair and clean reconstruction

The starting observability patch referenced `RouteObservability.msg` from `msg/CMakeLists.txt` but did not contain the new-file diff. That defect was confirmed. The message was recovered from the ignored observability worktree and cross-checked against its generated header, collectors, source references, and recorded P0 ULog field values. The tracked patch now contains the complete `/dev/null` new-file section, fields, event/source/topic IDs, stable writer IDs, CMake registration, instrumentation, and logger configuration.

The checker, setup helper, and rebuild helper all read PX4 commit `4ae21a5e569d3d89c2f6366688cbacb3e93437c9` from `config/dependencies.lock.yaml`; there is no separate hard-coded checker lock. A detached worktree created at that commit had no message file before patching. The tracked patch alone created it, passed `git diff --check`, and built `px4_sitl_default` in the locked container environment. Both `build/px4_sitl_default/uORB/topics/route_observability.h` and `build/px4_sitl_default/bin/px4` were verified. Ignored logs and hashed provenance are under `runs/phase_a1/`.

The integration procedure is [rebuild_observability_patch.sh](../../scripts/validation/rebuild_observability_patch.sh); textual and semantic assertions are in `tests/test_px4_observability_patches.py`.

## 2. Observation profiles and measured scale

The patch defines publisher-local, monotonically increasing sequences and two compile-time profiles without changing arbitration, controller algorithms, or outputs:

| Profile | Expected period | Intended use |
|---|---:|---|
| BASELINE | 100 ms | approximately 10 Hz, long low-overhead state observation |
| TRANSITION | 8 ms | transition-window writer, overlap, and gap observation |

PX4 logger interval was audited in milliseconds; interval zero logs every topic update. No high-rate console printing was added.

| Measurement | BASELINE | TRANSITION |
|---|---:|---:|
| final-writer events recorded / expected | 386 / 386 | 4,495 / 4,514 |
| average final-writer rate | 10.00 Hz | 121.709 Hz |
| maximum recorded final-writer gap | 100 ms | 20 ms |
| final-writer coverage | 100% | 99.579% |
| final-writer logger losses | 0 | 19 |
| all instrumentation events recorded / expected | 1,159 / 2,466 | 10,646 / 10,684 |
| mean / maximum logged CPU load | 0.3630 / 0.4200 | 0.2671 / 0.3000 |
| ULog size | 9,114,735 bytes | 9,022,240 bytes |

The runs are not a controlled CPU benchmark, so the lower TRANSITION CPU sample is not attributed to the profile. TRANSITION passes the explicit frequency alternative (`>=100 Hz`) but fails per-publication completeness. The minimum directly recorded final-writer gap scale is 20 ms; overlap or gap shorter than a missing-sample interval cannot be excluded. Consequently exclusivity and continuity are not promoted to PASS.

Design details and measurement boundaries are in [TIMESTAMP_MODEL.md](../design/TIMESTAMP_MODEL.md), [WRITER_ATTRIBUTION_MODEL.md](../design/WRITER_ATTRIBUTION_MODEL.md), and [P1_OBSERVABILITY_FEASIBILITY_REPORT.md](../motivation/P1_OBSERVABILITY_FEASIBILITY_REPORT.md).

## 3. Actuator writer inventory and coverage

[ACTUATOR_WRITER_INVENTORY.tsv](../design/ACTUATOR_WRITER_INVENTORY.tsv) contains all nine locked-source `actuator_motors` publishers found by source search. Four are compiled into `px4_sitl_default` and all four are instrumented with stable IDs: `control_allocator` (2), `rover_ackermann` (3), `rover_differential` (4), and `rover_mecanum` (5). The x500 P0 runtime candidate is `control_allocator`.

Five non-default candidates have stable IDs but are not instrumented in this configuration: `mc_raptor`, `mc_nn_control`, `uavcannode_esc_raw`, `spacecraft`, and `mixer_test`. Selecting any uncovered route family makes the collector return `INSUFFICIENT_COVERAGE`; a uORB instance is never treated as writer identity.

The strengthened collector reports candidates, uninstrumented candidates, publisher sequence gaps, expected/actual rate, maximum gap, transition windows, holes, competing windows, and coverage ratio. It cannot return `EXCLUSIVE` for missing candidates, gaps, low rate, holes, or an unlocatable transition. Unit tests cover single-writer continuity, competing writers, gaps, missing candidates, observation holes, and no evidence. Current P0 coverage status is `SEQUENCE_GAP`.

## 4. Canonical trace 1.1 and migration

Schema 1.1 separates behavioral intent from command level. `behavior_phase` holds values such as `hover`, `straight_line`, and `mission_complete`; `setpoint_level` is restricted to the documented control-level enumeration. External Mode velocity trajectories emit `setpoint_level="velocity"`; Offboard derives the level from `OffboardControlMode` and finite setpoint fields.

The three earlier 1.0 P0 traces were migrated with `migrate_route_trace_v1_0_to_v1_1.py`. Phase-like old values moved to `behavior_phase`; indeterminate levels became `unknown`; source hashes were preserved in migration reports. Their summaries are marked `superseded_measurement_v1`.

Committed high-rate processed traces retain every final-writer event and one in four allocator-input events to remain below 10 MiB. The stride is explicit in each summary; complete ULogs remain hashed, ignored source artifacts. This thinning is never used for final-writer sequence, exclusivity, gap, or continuity decisions.

## 5. Route Oracle v0

[Route Oracle v0](../design/ROUTE_ORACLE_V0.md), version `0.1`, emits only `PASS`, `VIOLATION`, `UNKNOWN`, or `NOT_APPLICABLE` for revocation, installation, exclusivity, continuity, and recovery. Missing evidence becomes `UNKNOWN`. Shared writer identity is not treated as a route epoch. Cross ROS/PX4 latency is unknown unless a clock bridge supplies ID, offset, uncertainty, and a valid interval; same-boot ULog time is preferred.

The result schema is `data/schemas/route_oracle_result.schema.json`. Oracle and collector tests passed.

## 6. P0-A, P0-B, and P0-C reruns

| Scenario | Run | execution_status | route_verdict | Writer rate/status |
|---|---|---|---|---|
| P0-A Offboard | `p0a_offboard_phase_a1_20260716T0710` | PASS | UNKNOWN | 121.709 Hz / `SEQUENCE_GAP` |
| P0-B External Mode | `p0b_external_mode_phase_a1_20260716T0720` | PASS | UNKNOWN | 121.943 Hz / `SEQUENCE_GAP` |
| P0-C Executor | `p0c_executor_phase_a1_20260716T0730` | PASS | UNKNOWN | 121.606 Hz / `SEQUENCE_GAP` |

All three intended normal flows completed, and all three 1.1 traces validate. Oracle installation passes for the selected target edge. Revocation, exclusivity, continuity, or recovery remain unknown where route epochs, clock bridging, continuous writer observations, or post-disarm evidence are missing. Full bounded interpretation is in [P0_OFFICIAL_HANDOFF_BASELINE_REPORT.md](../motivation/P0_OFFICIAL_HANDOFF_BASELINE_REPORT.md).

## 7. P0-D post-disarm result

Official attempt: `p0d_post_disarm_phase_a1_20260716T0755`.

The first route completed Takeoff → External Mode 23 → Complete → RTL → disarm. Nav state 23 was observed at disarm; disarmed observations included 23 and 5. There was one activation, one deactivation, and one graceful unregister request, but no direct slot-removal proof. The subsequent rearm was repeatedly denied by PX4 system-health checks, so the second armed Hold/Position window did not execute.

The bounded conclusion is **post-disarm nav-state retention** and **insufficient evidence** for clean re-entry. No qualifying evidence established data-plane residue. Execution is FAIL and route verdict UNKNOWN. See [P0D_POST_DISARM_REENTRY_REPORT.md](../motivation/P0D_POST_DISARM_REENTRY_REPORT.md).

## 8. Motivation studies

M1 contains 26 pinned inventory rows: 19 source-audited true route handoffs and seven trajectory/task/shared-authority/terminal non-handoffs. These purposive examples do not estimate industry-wide frequency. Prioritized seeds are external-to-internal completion/failure, internal-to-external admission, external-to-external replacement, replacement RTL fallback, and real-workload emergency/cancel/takeover edges. See [M1_HANDOFF_INVENTORY_REPORT.md](../motivation/M1_HANDOFF_INVENTORY_REPORT.md).

M3 contains 12 pinned issues, PRs, or commits. It separates locked-version fixes, still-applicable or unresolved reports, unconfirmed relevance, design semantics, and historical problems. High-value themes are disarm restoration, replacement/executor ownership, unregister ordering, registration freshness, and setpoint configuration. See [M3_LIFECYCLE_PROBLEMS_REPORT.md](../motivation/M3_LIFECYCLE_PROBLEMS_REPORT.md).

M5 evaluates three public systems. Aerostack2 at `a8e7318b8d1d7c5adc580e8a16374357773bc11a` is primary; MRS UAV System ROS2 at `99e59bf355bcb80bb69165e1d466f0d17f76bd17` is backup. This phase performs source selection, interface audit, and acquisition planning only—no large-stack integration. See [M5_WORKLOAD_SELECTION_REPORT.md](../motivation/M5_WORKLOAD_SELECTION_REPORT.md) and [REAL_WORKLOAD_TRACE_PLAN.md](../motivation/REAL_WORKLOAD_TRACE_PLAN.md).

## 9. Gate and deterministic follow-ons

[phase_a1_gate_result.json](../../experiments/motivation/phase_a1_gate_result.json) is `FAIL`. Criterion 10 failed because P0-D did not complete rearm and the required clean-re-entry evidence chain. In addition, P0 writer sequence gaps keep whole-window exclusivity and continuity unknown.

P2 was not run. P3 was not run. This follows the requested gate ordering; no P5, random search, coverage-guided fuzzing, full fuzzer development, or dangerous maneuver was performed.

## 10. CI, tests, and final repository state

`.github/workflows/repository-validation.yml` runs Python syntax, dependency-lock validation, pytest, JSON/YAML/TSV and route-schema checks, patch textual completeness, Markdown links, forbidden-legacy scans, ignored/raw-run audits, and the tracked-file size audit. It deliberately does not build PX4 or execute SITL and uses no secrets.

Local results before push:

- project pytest: 39 passed;
- clean locked PX4 transition build: PASS;
- repository validator: PASS (all 15 steps);
- tracked files above 10 MiB: expected zero after staging;
- tracked raw `runs/` files: zero.

The final push audit records clean status, no unexpected untracked files, no tracked ignored files, no tracked runs, no unpushed/unpulled commits, and exact local/origin commit equality.
