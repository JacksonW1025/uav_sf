# V8 experiment plan and execution checklist

This is the synchronized English counterpart of the detailed
[Chinese runbook](EXPERIMENT_PLAN.zh-CN.md). Both files must retain identical
step numbers, status, deliverables, exit criteria, and stop conditions. The
[V8 narrative](NEW_NARRATIVE_v8.md) remains the sole research narrative.

## Status rules

- `[x] COMPLETE`: artifacts exist, acceptance passed, and evidence is linked.
- `[>] NEXT`: the only step that may begin implementation.
- `[ ] PENDING`: a prerequisite is open.
- `[!] BLOCKED`: a recorded blocker prevents continuation.

Commands labelled **planned interface** do not exist yet. They are required
deliverables, not evidence of readiness. On every gate change, update both
plans, [CURRENT_STATUS.md](CURRENT_STATUS.md),
[V8_REPOSITORY_AUDIT.md](V8_REPOSITORY_AUDIT.md), and the boundary validator.

## Progress

| Step | Status | Gate | Formal launch |
| ---: | --- | --- | --- |
| 0 | `[x] COMPLETE` | V8 tracked-tree consolidation | prohibited |
| 1 | `[>] NEXT` | Observation/evidence provenance contract | prohibited |
| 2 | `[ ] PENDING` | Independent identity/effect observation | prohibited |
| 3 | `[ ] PENDING` | Combined admissibility Gate | prohibited |
| 4 | `[ ] PENDING` | V8 result/finding state machine | prohibited |
| 5 | `[ ] PENDING` | Minimal patches, image, environment identity | prohibited |
| 6 | `[ ] PENDING` | Early full-stack seeds and reachability | prohibited |
| 7 | `[ ] PENDING` | Lifecycle × mechanism corpus freeze | prohibited |
| 8 | `[ ] PENDING` | Semantic state and execution schemas | prohibited |
| 9 | `[ ] PENDING` | Closed-loop generator and four methods | prohibited |
| 10 | `[ ] PENDING` | Frozen benchmark and leakage control | prohibited |
| 11 | `[ ] PENDING` | Component/replay qualification | prohibited |
| 12 | `[ ] PENDING` | Runtime, safety, interference qualification | prohibited |
| 13 | `[ ] PENDING` | Non-formal pilot and budget estimation | prohibited |
| 14 | `[ ] PENDING` | Formal preregistration freeze | dry-run only |
| 15 | `[ ] PENDING` | Repeated formal campaigns | conditionally allowed |
| 16 | `[ ] PENDING` | Candidate confirmation and attribution | separate identity |
| 17 | `[ ] PENDING` | Representative full-stack replay | separate identity |
| 18 | `[ ] PENDING` | Accounting closure and reporting | no new launch |

## Global stop rules

Stop on identity drift; incomplete hashes/sequences/clocks; circular identity
provenance; shared allocator/writer evidence; physical, safety, cleanup, or
environment failure; live/offline host overlap; out-of-scope content; or any
open prerequisite. Record the outcome as qualification/measurement/environment
failure, `INCONCLUSIVE`, or a blocked gate—never as SUT PASS/VIOLATION.

## Step 0 — Consolidate the V8 tracked tree

**Status: `[x] COMPLETE`**

**Work completed:** retained-evidence allowlist; removal of unrelated/zero-formal
studies, old three-policy entry points, patch bundle, patch lock, source build,
and flight image; retention of low-level V8 primitives; synchronized plans,
audit, and boundary validator.

**Available commands:**

```bash
git status --short --branch
./scripts/validation/validate_repo.sh
```

**Deliverables:** both plans, repository audit, boundary validator.

**Exit:** only allowlisted V8 evidence and partial components remain; validation
passes; no flight/formal entry point exists.

**Stop:** a deletion would mutate retained ledger/result content.

## Step 1 — Freeze the observation/evidence provenance contract

**Status: `[>] NEXT`**

Inventory every authority/lifecycle/effect field; record source boundary, clock,
cardinality, and `OBSERVED/DERIVED/INFERRED/CONSTANT`; define complete identity
requirements and independent allocator versus writer/effect boundaries.

**Planned interface:**

```bash
python3 -m scripts.validation.validate_evidence_contract \
  --contract docs/EVIDENCE_CONTRACT.md \
  --schema data/schemas/observation_provenance.schema.json
```

**Deliverables:** evidence contract, provenance schema, field/source matrix,
positive/negative fixtures, validator tests.

**Exit:** every correctness field has non-circular provenance and every
authority event has a complete identity obligation.

**Stop:** a correctness field is available only from plan expectations, route
labels, or constants.

## Step 2 — Implement independent identity/effect observation and closure

**Status: `[ ] PENDING`**

Design minimal multirotor-only observations, provenance-preserving adapters and
clock closure, separate allocator and writer/effect events, and deterministic
fixtures for re-entry, restart, registration, completion, and fallback.

**Planned interface:**

```bash
python3 -m scripts.validation.validate_observation_contract --fixtures tests/fixtures/v8
python3 -m unittest tests.test_v8_trace_closure -v
```

**Deliverables:** V8 event schema, adapters, closure, fixtures, provenance tests.

**Exit:** equivalent evidence produces byte-stable traces; no event fabricates
two evidence layers.

**Stop:** provenance is lost, instances merge, clocks cannot close, or expected
results are required to construct evidence.

## Step 3 — Build the combined admissibility Gate

**Status: `[ ] PENDING`**

Compose trace integrity, required events, identity provenance, clocks,
environment identity, and physical validity into one overall decision while
retaining layer diagnostics.

**Planned interface:**

```bash
python3 -m scripts.validation.validate_admissibility --fixtures tests/fixtures/v8
```

**Deliverables:** combined Gate schema/implementation, truth table, physical
fixtures, standalone-evaluator protection tests.

**Exit:** any failed sub-gate makes the result `INCONCLUSIVE`; standalone use
cannot bypass physical validity.

**Stop:** runner and standalone admission disagree or missing evidence passes.

## Step 4 — Build the V8 result/finding state machine

**Status: `[ ] PENDING`**

Separate execution results, exposures, candidates, and confirmed findings;
record origin; implement reproduction, minimization, measurement check,
clustering, attribution, source grounding, and consequence states; define a
stable cluster signature.

**Planned interface:**

```bash
python3 -m scripts.validation.validate_finding_schema --fixtures tests/fixtures/findings
```

**Deliverables:** result/finding schemas, state machine, compatibility note,
tests.

**Exit:** all four finding levels and transitions are machine-distinct; repeated
traces do not inflate finding counts.

**Stop:** violations auto-promote to defects/safety findings or formal
candidates leak into the same benchmark.

## Step 5 — Create minimal V8 patches, image, and environment identity

**Status: `[ ] PENDING`**

Separate instrumentation from controlled stimuli; touch only required Family A
multirotor paths; lock purposes/paths/hashes; build the ARM64 image; attest
source, binary, package, patch, repository, and environment identities.

**Planned interface:**

```bash
./scripts/setup/prepare_v8_sources.sh
docker buildx build --platform linux/arm64 \
  --file containers/family_a_v8_runtime/Dockerfile \
  --tag uav-sf-family-a-v8:candidate --load .
python3 -m scripts.runtime.attest_v8_environment --image uav-sf-family-a-v8:candidate
```

**Deliverables:** minimal patch sets/lock, image, candidate manifest,
attestation.

**Exit:** no rover/extra-family path; clean sources reproduce apply/build; all
digests agree.

**Stop:** patch categories mix, unregistered source changes exist, or host state
leaks into the image.

## Step 6 — Integrate the full upper stack early

**Status: `[ ] PENDING`**

Freeze the mission/behavior stack and tasks; run non-formal normal missions;
collect traces, trajectories, parameter distributions, reachable transitions,
reality distance, and responsibility boundaries before corpus freeze.

**Planned interface:**

```bash
python3 -m scripts.runtime.collect_full_stack_seeds \
  --plan qualification/full_stack_seed_plan.json --non-formal
python3 -m scripts.validation.validate_seed_corpus qualification/full_stack_seeds
```

**Deliverables:** seed corpus, ranges, reachability report, frozen task/outcome
measures, attribution map.

**Exit:** core candidates have public/source/trace provenance; the upper stack
is not only a final demonstration.

**Stop:** stack drift, unbound seeds, unclear responsibility, or invalid tasks.

## Step 7 — Freeze the lifecycle × mechanism corpus

**Status: `[ ] PENDING`**

Inventory lifecycle phases against failure/authority mechanisms. Record action
provenance, preconditions, effect markers, cleanup, safety, parameter bounds,
reality distance, role, and include/exclude rationale.

**Planned interface:**

```bash
python3 -m scripts.corpus.validate_action_inventory config/v8_action_inventory.json
python3 -m scripts.corpus.freeze_core_corpus \
  --inventory config/v8_action_inventory.json --output config/v8_core_corpus.json
```

**Deliverables:** inventory, core corpus, grammar schema, provenance manifest.

**Exit:** research/provenance—not backend convenience—determines the corpus;
every action is reachable, observable, and cleanable.

**Stop:** missing provenance/cleanup, post-result bounds, or unequal grammars.

## Step 8 — Implement semantic state and execution schemas

**Status: `[ ] PENDING`**

Implement semantic extraction and campaign/episode/action-sequence/reset/
coverage schemas. Re-observe after every action; begin campaigns with empty
memory; reset all external authority and reach a safe route.

**Planned interface:**

```bash
python3 -m scripts.validation.validate_v8_schemas
python3 -m scripts.state.replay --fixtures tests/fixtures/v8 --determinism-check
```

**Deliverables:** schemas, deterministic extractor, plan builder, reset
contract, semantic coverage store.

**Exit:** epoch, owner, lifecycle, freshness, successor, mission context, and
bounded history are deterministic and distinguishable.

**Stop:** sequences are precomputed without re-observation, reset leaks state,
or raw telemetry coverage substitutes for semantic feedback.

## Step 9 — Implement the closed loop and four fair methods

**Status: `[ ] PENDING`**

Under a common grammar, bounds, seeds, reset, outcomes, and budget, implement
grammar-aware random, systematic enumeration, feedback-free
state-conditioned, and full state/feedback-guided generation. Report official
or handwritten scenarios through a separate reference runner.

**Planned interface:**

```bash
python3 -m scripts.generator.qualify_policies --config config/v8_methods.json
```

**Deliverables:** four policies, shared executor, decision log, seed replay,
feedback tests, separate practice-reference adapter.

**Exit:** seeds replay; conditions differ only at policy decisions; only
overall-admissible executions update coverage.

**Stop:** unequal capabilities/budgets/visibility, future-result feedback, or
inadmissible coverage updates.

## Step 10 — Freeze benchmark and leakage controls

**Status: `[ ] PENDING`**

Build separate historical-known, confirmed-current-natural, and seeded-fault
sets before formal work; retain held-out splits; route newly discovered natural
candidates only to an independent confirmation queue.

**Planned interface:**

```bash
python3 -m scripts.benchmark.validate --manifest config/v8_benchmark.json
```

**Deliverables:** manifest, origins, replay contract, held-out/leakage rules,
separate metrics.

**Exit:** every item replays and has a ground-truth level/digest; pilot/formal/
held-out boundaries are explicit.

**Stop:** unreproducible issues become ground truth, origins pool, or formal
results alter the primary benchmark.

## Step 11 — Qualify components, replay, and reduced observation

**Status: `[ ] PENDING`**

Test schema, closure, Gate, Oracles, state, generator, reset, and accounting;
replay retained/synthetic evidence; compare full and reduced observation; keep
frozen results unchanged.

**Planned interface:**

```bash
./scripts/validation/validate_repo.sh
python3 -m scripts.qualification.replay_suite --non-formal
python3 -m scripts.analysis.reduced_observation --non-formal
```

**Deliverables:** qualification report, compatibility boundary,
reduced-observation dependence report, limitations.

**Exit:** determinism/fail-closed checks pass and instrumentation dependence is
quantified.

**Stop:** replay instability, missing evidence passes, or unexplained primary
classification changes.

## Step 12 — Qualify runtime, safety, cleanup, and interference

**Status: `[ ] PENDING`**

Run single smoke, repeated serial, matched serial-versus-parallel, host
live/offline exclusion, safety stop, cleanup, and crash recovery. Start at
concurrency one; do not inherit the old four-way result.

**Planned interface:**

```bash
python3 -m scripts.qualification.runtime --plan qualification/v8_runtime.json
python3 -m scripts.qualification.interference --plan qualification/v8_interference.json
```

**Deliverables:** runtime/interference reports, qualified concurrency,
resources, barrier proof, safety/cleanup/recovery evidence.

**Exit:** matched timing/clock/outcome is unperturbed; all live work ends before
offline work; cleanup fails closed.

**Stop:** concurrency changes clock, real-time, outcome, or safety behavior;
reduce concurrency or freeze serial.

## Step 13 — Run non-formal pilot and estimate budgets

**Status: `[ ] PENDING`**

With isolated pilot identities, estimate campaign variance, admissible yield,
actions/episode, sequence length, reset/wall/analysis cost, safety interruption,
and candidate rate. Use results only to freeze design.

**Planned interface:**

```bash
python3 -m scripts.runtime.run_v8_pilot --matrix pilot/v8_matrix.json --non-formal
python3 -m scripts.analysis.pilot_design --root pilot/v8
```

**Deliverables:** pilot ledger/report, variance/cost estimates, proposed
budgets/repetitions/effect sizes/uncertainty/stopping rule.

**Exit:** campaign variance is estimable and pilots are excluded from formal
denominators.

**Stop:** pilots tune primary thresholds or stopping depends on desired results.

## Step 14 — Freeze formal preregistration

**Status: `[ ] PENDING`**

Freeze thesis/RQs, corpus, benchmark, methods/ablations, metrics, campaign unit,
reset, paired seeds, budgets, maximum sequence, cost reporting, repetitions,
effect sizes, uncertainty, stopping, confirmation, and full-stack selection.

**Planned interface:**

```bash
python3 -m scripts.validation.validate_preregistration \
  --plan experiments/v8_main/preregistration.json
python3 -m scripts.runtime.run_v8_campaign \
  --matrix experiments/v8_main/matrix.json --dry-run
```

**Deliverables:** immutable preregistration/matrix/attestation/digests and
empty-ledger readiness proof.

**Exit:** dry-run lists exact attempts without launch/ledger; identities agree;
campaign is the independent unit.

**Stop:** any design choice awaits results or built artifacts differ.

## Step 15 — Execute repeated formal campaigns

**Status: `[ ] PENDING`**

Only after Step 14: preflight/accounting → attestation → live execution →
safety/cleanup → complete live barrier → offline closure/Gate/Oracle → compact
retention → ledger close. No offline work may overlap live work on that host.

**Planned interface:**

```bash
python3 -m scripts.runtime.run_v8_campaign \
  --matrix experiments/v8_main/matrix.json \
  --attestation experiments/v8_main/environment-attestation.json
```

**Deliverables:** campaign/episode/attempt ledgers, manifests, compact evidence,
coverage, candidate queue, accounting.

**Exit:** preregistered stopping is reached; every launch has one closure;
denominators recompute from ledgers.

**Stop:** drift, open attempt, barrier/safety/cleanup failure, or a preregistered
pause rule.

## Step 16 — Confirm, minimize, cluster, and attribute candidates

**Status: `[ ] PENDING`**

Under new identities: independent reproduction → sequence/timing minimization →
measurement/instrumentation checks → clustering → source/spec attribution.

**Planned interface:**

```bash
python3 -m scripts.findings.confirm --queue experiments/v8_main/candidates.jsonl
```

**Deliverables:** confirmation ledgers, minimal reproducers, cluster manifest,
attribution dossiers, labels.

**Exit:** distinct-finding metrics use only clusters reaching the preregistered
confirmation level.

**Stop:** instrumentation/environment/upper-stack cause remains plausible or
source grounding is insufficient.

## Step 17 — Replay representative full-stack consequences

**Status: `[ ] PENDING`**

Use Step 6 task/measures, Step 14 selection rules, and Step 16 confirmed
clusters. Run matched full-stack closed-loop SITL and measure mission failure,
progress, trajectory, recovery, and physical consequences with attribution.

**Planned interface:**

```bash
python3 -m scripts.runtime.replay_full_stack \
  --selection experiments/v8_full_stack/selection.json
```

**Deliverables:** separate identity/ledger, matched outcomes, consequence
report, attribution boundary.

**Exit:** selected findings are reachable and consequences reproduce; tasks,
measures, thresholds, and selection were frozen first.

**Stop:** upper-stack differential is open, configuration drifts, or selection
cherry-picks results.

## Step 18 — Close accounting, analyze, and report

**Status: `[ ] PENDING`**

Recompute denominators; analyze campaigns; report effects/uncertainty, coverage,
time/cost, admissible yield, and interruptions; separate origins; build
RQ/claim/evidence traceability; validate the repository.

**Planned interface:**

```bash
python3 -m scripts.analysis.v8_final --root experiments/v8_main
./scripts/validation/validate_repo.sh
```

**Deliverables:** final report/summary, claim-evidence matrix, limitations,
artifact manifest, closed ledgers.

**Exit:** all numbers recompute; no launch-level pseudoreplication; claims match
evidence; repository validation passes.

**Stop:** open/missing accounting, post-hoc primary metrics, pooled origins, or
SITL consequences generalized to real-flight risk.

## Maintenance checklist

- [ ] Chinese and English step numbers/status match.
- [ ] Exactly one step is `NEXT`.
- [ ] Every new file maps to a V8 obligation.
- [ ] Commands are labelled available or planned.
- [ ] Completed gates link evidence.
- [ ] Qualification/pilot never enters a formal denominator.
- [ ] `./scripts/validation/validate_repo.sh` passes.
