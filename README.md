# Route-State-Guided Testing of PX4 Authority Handoffs

This repository studies stateful testing of flight-critical control-path
replacement in PX4. The required empirical route chain is:

```text
PX4 Internal Route
<-> Legacy Offboard
<-> Dynamic External Mode
<-> Mode Executor
<-> Internal Hold / RTL / Land / Recovery
```

The paper asks whether a route-state-guided generator can use cross-layer
semantic state to choose lifecycle action sequences and timing more effectively
than official scenarios, grammar-aware random generation, deterministic
enumeration, and feedback-free state-conditioned generation under a common
budget.

The Motivation and measurement foundation is complete with bounded claims.
The final method is not: the current implementation is a one-action timing-
selection prototype. Full semantic state, multi-action closed-loop generation,
the justified corpus, comparative baselines, repeated-campaign statistics, and
finding confirmation remain method obligations.

## Why mode state is not enough

A navigation-mode value reports declared state, not the control path that
produced the actuator effect. The same mode can be backed by different
producer sessions, registrations, command subjects, controllers, allocators,
writers, and lifecycle owners. Conversely, a mode can change before the new
path is complete or while output from the previous path is still effective.
Testing therefore follows the runtime route rather than treating the mode
label as proof of handoff.

## Runtime Route Instance

A Runtime Route Instance is the tuple of route epoch, producer/session
identity, registration and activation identity, controller/allocator/writer
lineage, and lifecycle/executor ownership. A new instance begins whenever
authority-relevant identity changes, even if the declared mode does not. Each
command-consumption and downstream effect event separately carries the dynamic
command subject timestamp used for freshness; it is not part of the stable
instance identity.

The implementation evaluates three route contracts and one rejection contract:

1. **Route conformance** checks timely revocation, complete installation,
   exclusivity, and continuity.
2. **Freshness and lineage** checks the age of the consumed command and the
   identity chain from producer through actuator writer.
3. **Successor progression** checks the expected route after completion and
   independently checks fault observation and complete safety-route
   installation when a fallback is expected.
4. **Registration and activation rejection** checks that preregistered
   negative cases are explicitly rejected and never treats non-activation as
   proof by itself.

The Evidence Admissibility Gate runs before those contracts. Missing critical
events, incomplete collection windows, sequence gaps, invalid clock mapping,
or incomplete route identity make the overall result `INCONCLUSIVE`; absence
of evidence is never converted into `PASS`.

## Repository layout

- `config/` contains immutable source identities and current method defaults.
- `docs/` defines scope, route semantics, method, experiment design, migration
  evidence, and current formal status.
- `scripts/` contains Family A adapters, collectors, oracles, evaluation,
  safety, cleanup, accounting, setup, and repository validation.
- `data/schemas/` defines the tracked input and output contracts.
- `patches/` contains observation-only changes against locked upstream
  sources.
- `tests/` contains non-flight unit and integration tests.
- `containers/family_a/` defines a digest-pinned validation and reference
  toolchain image.

Runtime artifacts belong under ignored `runs/` and must never be committed.

## Source of truth

- `codex-b` is the authoritative development branch.
- `main` and `origin/main` mirror reviewed `codex-b` milestones; older `main`
  history does not override the current branch.
- [NEW_NARRATIVE_v8.md](docs/NEW_NARRATIVE_v8.md) is the sole research
  narrative. Supporting documents separate current evidence, scope, model,
  method obligations, experiment gates, and environment provenance.
- Frozen experiment reports, ledgers, and attestations remain authoritative
  for their own study identities and are never rewritten by narrative changes.

## Execution-environment boundary

The registered Family A study environment is an ARM64 Ubuntu Noble container
running on AGX Thor L4T R38.2.1. The host supplies only the kernel, Docker, and
bounded compute and storage resources. The image supplies Python 3.12, ROS 2
Jazzy, Gazebo Harmonic, the exact PX4 and ROS sources, Micro XRCE-DDS Agent,
and every project runtime component. Host Conda, ROS, Gazebo paths, and Python
site packages are not inherited.

Each formal plan binds the execution and collector host, target kind,
architecture, operating system, PX4 binary digest, complete environment
manifest, container image ID, method digest, and safety-limits digest. The
collector records the same identity in an `environment_attested` event. A
missing or mismatched attestation makes the trace inadmissible.

## Build and validate

The repository validation uses only Python's standard library:

```bash
./scripts/validation/validate_repo.sh
```

Prepare detached source checkouts at the exact commits in
`config/dependencies.lock.json`:

```bash
./scripts/setup/prepare_sources.sh
```

Build the locked ARM64 validation and reference image:

```bash
docker buildx build --platform linux/arm64 \
  --file containers/family_a/Dockerfile \
  --tag uav-sf-family-a:locked .
```

## Run a preregistered Thor study

The completed studies are closed. Official-sequence, accepted-target campaigns
use the resumable general entry point, which refuses identity drift, open
attempts, duplicate attempt IDs, silent replacement, or execution beyond a
cell cap:

```bash
python3 -m scripts.runtime.run_campaign \
  --matrix experiments/motivation_thor_v1/matrix.json \
  --attestation experiments/motivation_thor_v1/environment-attestation.json \
  --study-root experiments/motivation_thor_v1 \
  --run-root runs \
  --image uav-sf-family-a-thor:formal-35971b4
```

Use the exact image reference recorded by the selected matrix and attestation.

Three-strategy fixed-budget studies use the round-by-round runner so that live
coverage from one state-aware attempt can affect only later decisions in the
same mechanism-strategy cell:

```bash
python3 -m scripts.runtime.run_fixed_budget_campaign \
  --matrix PATH/TO/FROZEN/matrix.json \
  --attestation PATH/TO/FROZEN/environment-attestation.json \
  --study-root PATH/TO/FROZEN \
  --run-root runs \
  --image EXACT_ATTESTED_IMAGE
```

Formal-run readiness does not authorize a launch. The v8 decision gates must
first establish the full semantic state, justified corpus, comparative methods,
campaign statistics, and finding-confirmation contract.

Each campaign batch completes all live PX4/Gazebo/ROS attempts before starting
offline ULog, clock, Evidence Gate, and Oracle processing. Formal concurrency
remains four; the five-way non-formal qualification did not replace it.

## Evaluate one closed trace

Create a new preregistered plan from `config/experiment.template.json`, fill in
the identity of the actual target environment, collect normalized events on
that environment with `scripts.collectors.trace_collector`, and evaluate the
closed trace:

```bash
python3 -m scripts.evaluator.evaluate_trace \
  --plan runs/example/experiment.json \
  --trace runs/example/route-events.jsonl \
  --output runs/example/evaluation.json
```

Official sequences, bounded random timing, and the state-aware strategy are
implemented in `scripts/evaluator/strategies.py`. The shared live runtime is
qualified for owned setpoint stall and owned process exit; other action
grammars fail closed. Safety supervision and cleanup completion are mandatory
for execution. Compact formal results are retained only after each launch has
closed through the Evidence Gate.

## Current status

- Formal experiment attempts retained across separate Thor studies: 295
- Retained historical results: 0
- Current empirical claims: bounded Thor SITL findings in the final reports
- Motivation Study: Stage A1 and Stage A2 complete with bounded claims
- Main Evaluation: one 18-launch setpoint-stall slice complete; the distinct
  process-exit action is qualified and preregistered with zero formal launches
- Target method: full semantic-state-guided action-sequence and timing
  generation; complete effectiveness claims remain pending

The 295 launches are a repository total across independent identities and
denominators, not a single pooled experiment.

Start with the [v8 research narrative](docs/NEW_NARRATIVE_v8.md). Supporting
documents define the [research scope](docs/RESEARCH_SCOPE.md),
[route model](docs/ROUTE_MODEL.md), [method](docs/METHOD.md),
[experiment plan](docs/EXPERIMENT_PLAN.md),
[current status](docs/CURRENT_STATUS.md), and
[Thor environment record](docs/THOR_MIGRATION_REPORT.md).
