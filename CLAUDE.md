# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A research testbed, not an application. It tests whether a *route-replacing
authority transition* in PX4 (`px4_internal` <-> `legacy_offboard` <->
`dynamic_external_mode` <-> `mode_executor` <-> internal hold/RTL/land/recovery)
actually revokes the old control path and completely installs the new one. A
navigation-mode label is never accepted as evidence; the code follows the
Runtime Route Instance identity instead.

Host-side tooling is Python 3 **standard library only** (no `requirements.txt`,
no pytest; `jsonschema` is used opportunistically if importable). The live
PX4/Gazebo/ROS 2 workload only ever runs inside digest-pinned ARM64 containers.

## Commands

Everything runs from the repository root as a module (`python3 -m ...`); there
is no installed package.

```bash
# Full gate: static validation + compileall + all unittests + shell syntax + git diff --check
./scripts/validation/validate_repo.sh

# Static repository validation only (fast)
python3 -m scripts.validation.validate_repo

# All tests / one module / one case
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_evaluation -v
python3 -m unittest tests.test_evaluation.EvaluationTests.test_passing_trace -v

# Evaluate one closed trace (exit 0 PASS / 1 VIOLATION / 2 INCONCLUSIVE / 3 REFUSED)
python3 -m scripts.evaluator.evaluate_trace \
  --plan runs/example/experiment.json \
  --trace runs/example/route-events.jsonl \
  --output runs/example/evaluation.json

# Run or resume a frozen study matrix (resumable; refuses identity drift)
python3 -m scripts.runtime.run_campaign \
  --matrix experiments/<study>/matrix.json \
  --attestation experiments/<study>/environment-attestation.json \
  --study-root experiments/<study> --run-root runs --image <exact attested image>
# add --dry-run to print per-cell next attempt IDs without launching anything

# Read-only post-hoc analyses over the retained corpus
python3 -m scripts.analysis.oracle_ablation     --root . --output-root <fresh dir>
python3 -m scripts.analysis.sensitivity         --root . --output-root <fresh dir>
python3 -m scripts.analysis.matched_differential --root . --output-root <fresh dir> --motivation-smoke

# Detached source checkouts at the locked commits, then images
./scripts/setup/prepare_sources.sh
docker buildx build --platform linux/arm64 --file containers/family_a/Dockerfile --tag uav-sf-family-a:locked .
docker buildx build --platform linux/arm64 --file containers/family_a_runtime/Dockerfile \
  --build-arg REPOSITORY_COMMIT="$(git rev-parse HEAD)" --tag uav-sf-family-a-thor:candidate --load .
```

## Architecture

### Execution pipeline

`run_campaign` → `formal_attempt` → `run_container` → (in container) `run_sitl`
→ raw evidence under `runs/` → (in container) `process_attempt` → compact
evidence + ledger closure under `experiments/<study>/`.

`process_attempt` is the whole offline chain in one place
([process_attempt.py:73](scripts/runtime/process_attempt.py#L73)):
`inspect_ulog` → `close_trace` (ULog + sidecars + clock bridge → hash-chained
`closed.trace.jsonl`) → `evaluate` → outcome classification
(`ACCEPTED` / `OBSERVABILITY_REJECTED` / `INCONCLUSIVE` / `TIMEOUT` /
`FORMAL_SAFETY_STOP` / `ENVIRONMENT_FAILURE`). An Oracle `VIOLATION` is
deliberately `ACCEPTED` evidence, not a failed attempt.

`run_campaign` runs a **two-phase barrier** per batch: every `--phase live`
container must exit before any `--phase finalize` ULog/clock/Gate/Oracle work
starts, so analysis load cannot perturb a still-running attempt's timing.

### Evidence layers

1. **Route model** — [scripts/model/runtime_route.py](scripts/model/runtime_route.py)
   owns `ROUTES`, `EVENT_KINDS`, the ten-field `RuntimeRouteInstance`, and the
   SHA-256 event chain. `validate_repo` asserts these Python constants equal the
   enums in [data/schemas/route_event.schema.json](data/schemas/route_event.schema.json)
   and the plan schema, so a route or event kind must be added in both places.
2. **Plan** — [scripts/evaluator/plan.py](scripts/evaluator/plan.py) (schema
   `1.2`) validates with exact field-set equality at every level. Adding one
   plan field means touching `plan.py`, `data/schemas/experiment_plan.schema.json`,
   `config/experiment.template.json`, `scripts/runtime/make_plan.py`, and
   `tests/helpers.py` together.
3. **Collection** — `scripts/collectors/`: `trace_collector` (live append with
   contiguous sequence + hash chain), `ulog_route`, `clock_bridge` (cross-domain
   time fit), `closed_trace` (offline assembly of the final trace).
4. **Gate then contracts** — [evaluate_trace.py](scripts/evaluator/evaluate_trace.py)
   runs `evidence_gate` first; if inadmissible the overall status is
   `INCONCLUSIVE` regardless of clause outcomes. Then four Oracles run: route
   conformance, freshness/lineage, successor progression, registration contract.
   Clause statuses are `PASS` / `VIOLATION` / `UNKNOWN` / `NOT_APPLICABLE`;
   shared clause helpers and the "complete installation" search live in
   [oracles/common.py](scripts/oracles/common.py).
5. **Result model** — [result_model.py](scripts/evaluator/result_model.py)
   enriches the compact result into the semantic form and validates it.
6. **Accounting** — two distinct hash-chained ledgers:
   [accounting/study.py](scripts/accounting/study.py) (per study, `fcntl`-locked,
   append-only, `REGISTERED`→`LAUNCHED`→`CLOSED`, tracked at
   `experiments/<study>/attempt-ledger.jsonl`) and
   [accounting/attempts.py](scripts/accounting/attempts.py) (per-attempt state
   machine). Both refuse mutation, replacement, and out-of-order transitions.
7. **Analysis corpus** — [analysis/corpus.py](scripts/analysis/corpus.py) pins
   the frozen corpus to exact per-study accepted counts (131 + 20 = 151). It
   fails loudly if `runs/` no longer holds those plans and traces, so the
   post-hoc analyses are not runnable from a clean clone.
8. **In-container runtime** — [runtime/ros2/](runtime/ros2/) holds the actual
   ROS 2 nodes (`external_mode.cpp`, `mode_executor.cpp`,
   `gazebo_clock_sidecar.cpp`, plus Python requester/telemetry/safety nodes).
   Observation-only upstream changes live in [patches/](patches/) and are digest-locked
   in `config/patches.lock.json`.

### Invariants the code already enforces — do not weaken them

- **Fail closed.** Entry points never overwrite an output (`_write_new`), print
  `{"status": "REFUSED", ...}` to stderr, and exit nonzero. Missing evidence
  yields `INCONCLUSIVE`/`UNKNOWN`, never `PASS`.
- **Frozen identity.** `formal_attempt` compares the matrix against
  `config/method.defaults.json` and `config/safety_limits.formal.json` by digest,
  and the local image against the attested image ID. Editing either config file
  invalidates every existing matrix — do it only with a new preregistered study.
- **Formal concurrency is exactly 4** with four disjoint CPU sets
  ([run_campaign.py:70](scripts/runtime/run_campaign.py#L70)); five-way exists
  only as a non-formal qualification result.
- **Only `official_sequence` is executable live.** The other two strategies in
  `scripts/evaluator/strategies.py` are implemented and validated but rejected by
  the formal runtime until a live action backend records the applied schedule.
- **`runs/` is ignored and must never be committed**; `experiments/` keeps only
  compact evidence and ledgers. The checkout host is never the experiment
  environment — each plan registers its target environment and the trace must
  carry the matching `environment_attested` event.

## Repository validation gotchas

[scripts/validation/validate_repo.py](scripts/validation/validate_repo.py) is
stricter than a lint pass and will block otherwise-reasonable edits:

- **Top-level allowlist** (`ALLOWED_TOP`): any new root-level file or directory
  must be added there or validation fails.
- **Term scan** (`FORBIDDEN`, [line 57](scripts/validation/validate_repo.py#L57)):
  a set of regexes rejects out-of-scope research-family names, retired
  identifiers, and vocabulary implying superseded or set-aside artifacts.
  A separate line-scoped rule rejects the bare route word unless the same line
  writes it as `legacy_offboard` or "legacy offboard".
  Read the list before writing prose or comments; it applies to every tracked
  file except `docs/NEW_NARRATIVE_v7.md`.
- **Every `scripts/**/*.py` is imported** — an import-time error in any module
  fails the whole gate.
- **Local Markdown links must resolve**, `README.md` must keep its four
  documented commands, no tracked file may exceed 10 MiB, and `data/processed/`
  must not exist.

## Working agreements

From [AGENT.md](AGENT.md), which stays authoritative:

- `origin/main` is the authoritative state; fetch with pruning and confirm a
  clean worktree before investigating or changing code.
- Scope is Family A route-replacing authority transitions only — no controller
  replacement, no actuator-level authority transfer, no other research family.
- Keep every dependency, source commit, image, and package pinned to an
  immutable identity.
- Run `./scripts/validation/validate_repo.sh` before handoff.

`docs/` is normative: [RESEARCH_SCOPE.md](docs/RESEARCH_SCOPE.md),
[ROUTE_MODEL.md](docs/ROUTE_MODEL.md), [METHOD.md](docs/METHOD.md),
[EXPERIMENT_PLAN.md](docs/EXPERIMENT_PLAN.md), and
[CURRENT_STATUS.md](docs/CURRENT_STATUS.md). A behavior change that contradicts
those documents is a documentation change too.
