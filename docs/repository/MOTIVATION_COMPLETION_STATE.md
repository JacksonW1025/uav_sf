# Motivation Completion State

Last updated: 2026-07-20

This file is the durable resume point for the bounded Motivation Completion
Study. It does not reopen, extend, or alter any frozen P5 v6, Issue #162, or
Freshness pilot denominator.

## Repository identity

- Starting HEAD: `955e7c98e3b29ddd21fa4d44fb562065700fa832`
- Starting `origin/main`: `955e7c98e3b29ddd21fa4d44fb562065700fa832`
- Starting ahead/behind: `0/0`
- Protected ancestor: `955e7c98e3b29ddd21fa4d44fb562065700fa832`
- Current phase: C1 concurrent authority-event preregistration
- Phase status: `C1_PREREGISTRATION_READY_FOR_FIRST_PUSH`

## Frozen evidence

- P5 v6: 35 matched pairs, 70 accepted sides, 70 Route PASS;
  `CONDITIONAL_PASS`.
- Issue #162: 3/3 fully instrumented historical reproductions and 1/1
  reduced-observation confirmation; `HISTORICAL_DEFECT_REPRODUCED`.
- Freshness pilot: 16 formal attempts, 10 accepted, 6 observability
  rejections, 10 Freshness `EXPOSURE`, 9 Route PASS, and 1 current natural
  Route `VIOLATION`.
- The frozen natural event is `freshness-f1-a02`, classified
  `NATURAL_POST_FALLBACK_STALE_TRAJECTORY_CONSUMPTION`: two controller
  consumptions after fallback carry the pre-fallback Trajectory subject
  timestamp; no post-revocation old-epoch consumption, external allocator
  input, or external writer output was observed.

## Current authorization

Execute the bounded phases N1, C1, R1, W1, B1, and M-FINAL in order. Each
phase must preserve exact revision identity, complete required windows, clock
validity, lineage, lifecycle evidence, preconditions, acceptance boundaries,
attempt limits, and safety stops. Raw evidence remains ignored under
`runs/motivation/`; only compact processed evidence and study records may be
tracked. No full Stateful Fuzzer campaign, Freshness denominator extension,
PX4 behavior fix, direct-actuator flight, HITL, real flight, or external-system
testing is authorized.

## Phase progress and counts

| Phase | Status | Accepted | Attempts | Rejected / excluded | Current disposition |
|---|---|---:|---:|---:|---|
| Initialization | `COMPLETE` | n/a | n/a | n/a | `f2aa93aa` pushed |
| N1 trajectory residue | `COMPLETE` | 8 / 9 | 14 / 18 | 6 | `CURRENT_EVENT_REOBSERVED_BUT_PHASE_DEPENDENT`; 2 matching violations |
| N1 reduced confirmation | `COMPLETE` | 1 / 1 | 1 / 3 | 0 | accepted Route PASS; no matching residue; stopped at target |
| C1 concurrency | `PREREGISTRATION_READY` | 0 / 15 | 0 / 30 | 0 | 15 slots frozen locally; no formal attempts |
| C1 minimal confirmations | `NOT_APPLICABLE_PENDING_TRIGGER` | 0 | 0 / 3 per finding | 0 | only if a violation is found |
| R1 session rollover | `NOT_STARTED` | 0 / 9 | 0 / 18 | 0 | pending |
| W1 workload spike | `NOT_STARTED` | 0 / 3 canonical | 0 | 0 | pending |
| B1 Family B | `NOT_STARTED` | 0 / 6 if executable | 0 | 0 | pending feasibility Gate |
| M-FINAL | `NOT_STARTED` | n/a | n/a | n/a | pending |

All future rejected attempts must be explicitly classified as
`OBSERVABILITY_REJECTED`, `MEASUREMENT_INSUFFICIENT`,
`ENVIRONMENT_FAILURE`, `CAMPAIGN_CONFIGURATION_FAILURE`,
`FORMAL_SAFETY_STOP`, or `NOT_APPLICABLE`; none enters a SUT denominator.

## Completed commits

- `f2aa93aa89e1764d0be6c806d79bfc8b683043f3` —
  `docs: initialize motivation completion workflow` (pushed).
- `54d0411bddbc62e28d05e006a844dedbf9ebe6b3` —
  `experiment: preregister n1 trajectory residue study` (pushed before every
  formal N1 attempt).
- `088ee9ab0d21b08b34ade7a9539e5c91ae70cc8c` —
  `experiment: freeze n1 execution matrix` (pushed; formal-attempt starting
  revision).
- `ed8486f03d07af70d738ce787a0ed77b1e110b3b` —
  `experiment: checkpoint n1 phase bucket a` (pushed; N1-B attempt starting
  revision).
- `b639b4bf072965cbe3e4b7a8b33c4a2c2f82a379` —
  `experiment: checkpoint n1 phase bucket b` (pushed; N1-C attempt starting
  revision).
- `3c4124d0afb513345475a738c32c68e75e92f890` —
  `experiment: trigger n1 reduced confirmation` (pushed; reduced-attempt
  starting revision).
- `fd9b93fb0d2f50554d6f52d19ac3cd573d7ae2f9` —
  `experiment: adjudicate current trajectory residue event` (pushed; final
  N1 disposition and evidence freeze).

## Next exact action

Run C1 preregistration focused tests and the full validator, commit and push
the oracle/schema/public-interface harness and frozen 15-slot matrix, record
that pushed commit in the matrix and ledger, push the freeze record, and only
then start `C1-A-A_FIRST` attempt 1 with seed `320101`.

## Current blockers

- N1-A reached its six-attempt cap with only 2/3 accepted runs. This is a
  bounded measurement-insufficient cell, not authorization to retry it.
- The accepted reduced-confirmation run did not reproduce the C-bucket event;
  this bounds the conclusion to phase-dependent re-observation rather than a
  stable reproduction claim.

## Protected hashes

### P5 v6

- Differential Gate:
  `9542eb7c98dfd4df1ab50026c149f21fb719fc6a2a09d040a9db4df647f132bc`
- Tracked campaign manifest:
  `02d857f555623c10dc44998cd202c2da6226ec5c40a94a75020d75df87f02518`
- Differential report:
  `39be58d185a39bc811d822998c2170741a812b0b75a9610029a7e82fa31153f9`

### Issue #162 successor study

- Primary preregistration:
  `11cc54e73dc03192374b4d877cf84cf3b864d9f084b8aa00549d1cdc3b52d060`
- Baseline ledger:
  `dcd71d33a4c297bc7e180ca6136ed04a62d4300990ce36da8a722962111ec22b`
- Current replay ledger:
  `326ab49cb72e5a668e65546b4652fb63997cd01e3188b1bbfc80e6e27c557663`
- Historical replay ledger:
  `906113c23860f582ed02b182e1e9ee64b401bb311f54ecb58ab8efffdc02a191`
- Reduced build provenance:
  `237d4f1ecea12f3f673fee1a4338d94bb926cdd34f88327c9a837ea278869d31`
- Final report:
  `41fcbb85cfcf5c82f58ad1e2c7b857c6864f7105ee65d0889ce7803709aad680`

### Freshness pilot

- Primary preregistration:
  `fbbac59f943f499b6cc16e2787976c4ea1814dba1ce89efe8d40c23c0603f05f`
- Final Gate:
  `71ad5ebb9ee305919381217092d4d80d6dcf6d0141cfe7a413ed219835e5d99c`
- Attempt ledger:
  `099a75a0166c0d3bbd08c28c6e9c8a9a78be98c04a0446669e192e5336b5d0dd`
- Pilot matrix:
  `d52dbdaaed9e73ac510de80db49531e5745444122c4e0d69822244be04cfa841`
- Final report:
  `21acf90a6f754fb7cfb2ecc068388320800404bcccb9c1f18dc25669f4e2ad6f`
