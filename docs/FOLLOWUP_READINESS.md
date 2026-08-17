# Follow-up experiment readiness

## Verified entry

The complete Thor container and formal campaign entry can directly run a newly
preregistered Family A official-sequence matrix that uses the existing live
fixture semantics. Verification after both Stage A1 motivation studies
covered:

- exact local image identity and ARM64 container preflight;
- repository, dependency, binary, environment, method, and safety digests;
- empty/pending dry-run scheduling and completed-ledger no-op resume checks;
- 200 closed formal launches with no open attempt;
- four-slot isolation and two-active-attempt supplemental execution;
- a live-runtime/processing barrier that keeps ULog and Oracle work out of the
  timing-sensitive SITL phase;
- compact-result digest verification and reproducible study summaries;
- host validation of all tracked files and unit tests.

The invocation remains:

```bash
python3 -m scripts.runtime.run_campaign \
  --matrix PATH/TO/NEW/matrix.json \
  --attestation PATH/TO/NEW/environment-attestation.json \
  --study-root PATH/TO/NEW \
  --run-root runs \
  --image EXACT_ATTESTED_IMAGE
```

The formal default remains concurrency four. Five-way is retained only as a
non-formal qualification result; it must not be selected by a formal matrix.
See `experiments/concurrency_barrier_qualification/` for the frozen specs and
decision record.

## Completed Stage A2 boundary

The V7 moving-workload realism bridge is implemented and complete. Its shared
position-only straight-line workload, motion-phase observations, physical
validity contract, observer and safety qualification, frozen identities, and
separate formal matrices are retained with the Stage A2 studies. The primary
ledger remains insufficient; the independent remediation reached all four
targets with 26/26 accepted and admissible launches. This closes Motivation
Study execution but does not authorize a strategy comparison under the Stage
A2 identity.

## Explicit limitation

`bounded_random_timing` and `state_aware` have deterministic policy functions,
plan-schema checks, and unit tests, but no live action backend currently applies
their selected schedule to PX4. The formal matrix validator therefore refuses
either label. Those experiments are ready for preregistration and backend
implementation, not direct formal execution. This prevents an official
sequence from being mislabeled as a search strategy.
