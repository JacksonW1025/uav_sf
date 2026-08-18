# Route-State-Guided Testing of PX4 Authority Handoffs

This repository is the V8 research checkout for evidence-gated,
route-state-guided testing of PX4 authority handoffs. The target method uses a
cross-layer semantic state to select lifecycle action sequences and timing in a
closed loop, then compares four generation methods under one fairness contract.
Official or handwritten scenarios are reported separately as a practice
reference.

## Current state

Repository consolidation (Stage 0) is complete. The retained Stage A1/A2
studies establish a bounded Motivation and measurement foundation, and one
18-launch timing slice establishes only that bounded live feedback plumbing was
executable in its recorded environment.

The V8 method is not implemented. The current checkout has no active plan
schema, semantic-state extractor, combined admissibility Gate, finding state
machine, observation patch, flight-runtime image, campaign runner, or formal
matrix. **No flight or formal experiment entry point is active.** The next gate
is the observation and evidence-provenance contract in the
[Chinese executable plan](docs/EXPERIMENT_PLAN.zh-CN.md).

This absence is intentional: earlier three-strategy timing machinery and the
coupled observation-patch bundle were removed instead of being presented as a
V8 implementation. Git history remains the recovery mechanism for deleted
material.

## Research boundary

The connected PX4 system in scope is:

```text
PX4 internal routes
<-> Legacy Offboard
<-> Dynamic External Mode
<-> Mode Executor
<-> internal Hold / RTL / Land / Recovery
```

The upper mission, planner, behavior, and companion stack supplies realistic
seeds, reachability evidence, and representative full-stack replay. It is not
the defect target. Additional autopilots, airframes, HITL, and real flight are
optional external validation rather than hidden completion dependencies.

## Authority and evidence

- [NEW_NARRATIVE_v8.md](docs/NEW_NARRATIVE_v8.md) is the sole research
  narrative.
- [CURRENT_STATUS.md](docs/CURRENT_STATUS.md) records completed evidence and
  the current implementation boundary.
- [V8_REPOSITORY_AUDIT.md](docs/V8_REPOSITORY_AUDIT.md) defines why every
  retained tracked component belongs in the V8 checkout.
- [EXPERIMENT_PLAN.zh-CN.md](docs/EXPERIMENT_PLAN.zh-CN.md) is the detailed,
  editable execution blueprint; [EXPERIMENT_PLAN.md](docs/EXPERIMENT_PLAN.md)
  is its synchronized English counterpart.
- Retained experiment ledgers, attestations, compact evidence, and final
  reports remain authoritative for their recorded identities. Their old
  terminology is historical evidence metadata, not the current method schema.

The Runtime Route Instance target is:

```text
(route, route_epoch, producer_session, registration_id, activation_id,
 controller_id, allocator_id, writer_id, lifecycle_owner, executor_owner)
```

The current event/model code is only a partial skeleton. It does not yet prove
that those fields are independently observed, and it must not be used to claim
V8 admissibility or finding confirmation.

## Repository layout

- `docs/` contains the V8 narrative, scope, model, method, status, audit, and
  synchronized plans.
- `experiments/` contains only allowlisted V8 evidence packages: Stage A1/A2,
  their direct post-hoc/qualification support, and the bounded timing slice.
- `scripts/` contains partial low-level collection, clock, model, Oracle,
  accounting, safety, isolation, workload, and boundary-validation primitives.
- `runtime/ros2/` contains in-scope PX4/ROS workload components that require a
  new V8 patch, image, and qualification before reuse.
- `config/` contains locked source identity and evidence-support configuration;
  it contains no active V8 experiment template.
- `data/schemas/` contains only the partial event and accounting schemas.
- `containers/family_a/` is a repository-validation image, not a flight image.

Ignored `runs/`, `external/`, and `ros2_ws/` state is outside the Stage 0
tracked-tree audit and is not modified by repository validation.

## Validate the current boundary

The host-side validation uses Python's standard library and does not execute a
flight workload:

```bash
./scripts/validation/validate_repo.sh
```

It checks the retained experiment allowlist, absence of removed active paths,
JSON/schema consistency, immutable source identities, Markdown links, Python
imports, unit tests, shell syntax, and Git whitespace. A pass means only that
the tracked checkout satisfies the V8 Stage 0 boundary.

The optional ARM64 validation image runs the same command:

```bash
docker buildx build --platform linux/arm64 \
  --file containers/family_a/Dockerfile \
  --tag uav-sf-v8-validation:local .
```

## Retained evidence summary

- Stage A1: 200 closed launches across independent primary/remediation
  identities; 151 accepted/admissible evidence sets, 94 PASS and 57 VIOLATION.
- Stage A2: 51-launch primary study retained as `MEASUREMENT_INSUFFICIENT`, plus
  an independent 26/26 accepted/admissible remediation.
- Timing/feedback feasibility slice: 18/18 accepted, admissible, physically
  valid deliberate freshness violations; random and the prototype tied.
- Repository total: 295 closed formal launches across separate studies and
  denominators. It is not one pooled sample or a defect count.

See [CURRENT_STATUS.md](docs/CURRENT_STATUS.md) for evidence links and bounded
claims. Follow the experiment plan in order; no later gate authorizes itself.
