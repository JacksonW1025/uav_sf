# Fuzzer v0 Design

> **Pre-M-FINAL prototype:** this file and the associated 200-evaluation plan,
> Route Oracle 0.3 identity, prototype seed manifest, and validation-only
> mutant seeds are not the current formal protocol. The authoritative frozen
> Family A protocol is the
> [Family A Fuzzer v0 preregistration](FAMILY_A_FUZZER_V0_PREREGISTRATION.md),
> which is `PREREGISTERED_NOT_ACTIVATED` with zero formal attempts.

## Purpose and authorization

Fuzzer v0 searches bounded SITL route-transition schedules for evidence that Route
Oracle 0.3 classifies as a route-contract violation. It is authorized only after
the committed Oracle Validation Gate is `PASS`. It is not a general PX4 command
fuzzer, a shell mutator, a hardware test, or a large campaign.

The canonical campaign always uses the locked canonical PX4 build. Test-only live
mutants are accepted only by the readiness-validation profile and can never enter
the discovery corpus or the confirmed-discovery count.

## Pipeline

```text
versioned seed
  -> schema and semantic validation
  -> deterministic mutation from (case, RNG seed)
  -> duplicate fingerprint
  -> bounded SITL execution
  -> validity classification
  -> Route Oracle 0.3
  -> fitness and novelty
  -> corpus admission
  -> three-run replay for a candidate VIOLATION
  -> clause-preserving minimization
  -> canonical-build attribution boundary
```

Every stage writes a structured record. Raw ULog, process output, and monitor logs
remain under ignored `runs/fuzzer_v0/`; compact results and indices are the only
tracked campaign products.

## Components

The implementation is split into modules with narrow responsibilities:

- `case_model.py`: schema loading, semantic checks, canonical JSON, IDs, and
  fingerprints.
- `seed_loader.py`: allowlisted corpus loading and validation-profile filtering.
- `mutators.py`: bounded temporal, state-conditioned, sequence, channel, and
  context transformations.
- `scheduler.py`: deterministic random baseline and state-aware guided selection.
- `executor.py`: an allowlisted case-to-probe compiler and watchdog-protected
  execution. Case data is never evaluated as code or interpolated into a shell.
- `validity.py`: evidence-first outcome classification.
- `fitness.py`: contract-distance, novelty, physical-severity, and penalty terms.
- `corpus.py`: content-addressed deduplication and atomic index updates.
- `replay.py`: three-repeat reproduction with the original case and environment.
- `minimize.py`: deterministic delta debugging that preserves the same target
  clause and a reproducible violation.
- `cli.py`: `validate-seeds`, `run`, `replay`, and `minimize` entry points.

## Case identity and reproducibility

A case is canonicalized by sorting object keys and retaining array order. Its
`case_id` is stable metadata; its `case_digest` is SHA-256 over the canonical case
excluding `case_id` and non-semantic provenance. A duplicate fingerprint uses:

```text
route family
source, target, and fallback routes
behavior context
ordered transition-event kinds
channel state sequence
fault kind and target
quantized timing bins
```

An evaluation records the case digest, seed digest, scheduler strategy, scheduler
RNG seed, mutation operator and parameters, canonical PX4 revision, dependency-lock
digest, simulator seed, observation profile, and artifact root. Given the same
inputs, mutation and scheduling are deterministic.

## Seed boundaries

The initial corpus contains declarative representations of P0 normal transitions,
P2 process faults, P3 channel decoupling, and P5 matched cells. Oracle live-mutant
seeds carry `environment.profile = oracle_validation_mutant` and are usable only by
readiness tests. Aerostack2-derived seeds are admitted only if the Real Workload
Gate is `PASS`; otherwise the source is recorded as unavailable rather than
synthetically claimed.

## Search strategies

`random_baseline` samples a seed and one applicable mutation using a recorded RNG
seed. `state_aware_guided` prioritizes valid, nonduplicate parents that add a route
state, transition sequence, or behavior-context bin, then uses fitness only within
the same validity tier. Neither strategy can reward a process crash, missing ULog,
invalid clock bridge, or incomplete critical window.

The v0 smoke configuration is capped at 200 total evaluations. The planned split
is 50 random, 100 guided, and at most 50 replay/minimization evaluations. Lower
limits are permitted; higher limits require a new committed gate.

## Executor trust boundary

The executor accepts only schema-valid enum values and numeric parameters within
the transition grammar's envelope. It maps these values to a fixed Python argument
vector for repository probes. It does not accept shell text, executable paths,
environment-variable names, raw MAVLink/uORB messages, arbitrary PX4 parameters,
or source patches from a fuzz case.

Each run uses a unique artifact directory and simulator partition, canonical
dependency locks, a maximum wall-clock duration, and watchdogs for PX4, Gazebo,
the DDS agent, and expected ULog production. Hardware discovery is rejected.

## Result and corpus rules

Validity and SUT outcome are orthogonal in evidence but serialized as one of the
enumerated result classifications. Only `SUT_PASS` and `SUT_VIOLATION` are valid
scenario outcomes. `MEASUREMENT_UNKNOWN` is retained for audit but cannot enter the
violation corpus. Input/setup errors and environment failures receive no positive
fitness.

A raw `SUT_VIOLATION` is a candidate, not a PX4 defect. It is replayed three times.
All three valid replays must preserve the same target clause for `REPRODUCIBLE`;
mixed valid outcomes are `FLAKY`; zero matching valid outcomes are
`NOT_REPRODUCED`; infrastructure failures are reported separately. A minimized
case must pass the same three-run condition.

Confirmed discoveries are deduplicated by target clause, source/target route,
route-epoch pattern, root-cause signature, and minimal event sequence. Mutant
validation cases are never included.

## Safety envelope and stop conditions

The smoke campaign is SITL-only with x500, the default world, low speed, bounded
turn and descent rates, low wind, minimum altitude constraints, and a fixed run
timeout. Kill-switch actions, hardware, HIL, high-speed/aggressive flight, Family B,
and arbitrary code mutation are outside the grammar.

Execution stops at the evaluation cap, five independent reproducible violations,
the configured consecutive-environment-failure threshold, or an unavailable
PX4/Gazebo watchdog. Stopping does not convert incomplete work into a passing gate.

## Frozen v0 limitations

Fuzzer v0 is intentionally single-vehicle and Family A only. It has no ML/RL
policy, no coverage instrumentation inside PX4 beyond the route trace, no network
packet mutation, no real-flight execution, and no automatic upstream issue filing.
The search result is a bounded experiment, not a failure-rate estimate.
