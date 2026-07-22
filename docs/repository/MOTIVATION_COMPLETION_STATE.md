# Motivation Completion State

Last updated: 2026-07-22

This file is the durable resume point for the bounded Motivation Completion
Study. It does not reopen, extend, or alter any frozen P5 v6, Issue #162, or
Freshness pilot denominator.

## Repository identity

- Starting HEAD: `955e7c98e3b29ddd21fa4d44fb562065700fa832`
- Starting `origin/main`: `955e7c98e3b29ddd21fa4d44fb562065700fa832`
- Starting ahead/behind: `0/0`
- Protected ancestor: `955e7c98e3b29ddd21fa4d44fb562065700fa832`
- Current phase: B1 registered-controller inventory and Family B Gate complete;
  M-FINAL is next but has not started
- Phase status: `B1_COMPLETE_ENVIRONMENT_BLOCKED_AT_BUILD_CAP`

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
| C1 concurrency | `COMPLETE` | 14 / 15 | 17 / 30 | 1 configuration failure, 2 observability rejections | `CONDITIONAL_PASS_BOUNDED_LINEARIZATION_CONFORMANCE`; 0 violations |
| C1 minimal confirmations | `NOT_TRIGGERED` | 0 | 0 / 3 | 0 | no accepted violation |
| R1 session rollover | `COMPLETE` | 0 / 9 | 6 / 18 | 6 formal safety stops | `MEASUREMENT_INSUFFICIENT_AT_R1_A_ATTEMPT_LIMIT` |
| W1 workload spike | `COMPLETE` | 0 source; 0 / 3 canonical | 3 source; 0 replay | 3 formal safety stops | `MEASUREMENT_INSUFFICIENT` |
| B1 Family B | `COMPLETE` | 0 build; 0 / 3 normal; 0 / 3 recovery | 3 build; 0 runtime | 3 configuration failures; B1-E/F not applicable | `ENVIRONMENT_BLOCKED`; future work |
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
- `2cb2e021f1604868387f94b5eef6b6457f719416` —
  `oracle: preregister authority event linearization probe` (pushed before
  every formal C1 attempt).
- `6fa55e5256c6b99e20867f7ebca01ef8d06ab1` —
  `experiment: freeze c1 execution matrix` (pushed; C1 attempt 1 starting
  revision).
- `4f90d132bb856384438dc81a038b6c26f8be96b6` —
  `oracle: exclude c1 cleanup from linearization window` (pushed observation-
  only correction after the excluded configuration-failure attempt).
- `89dc2bacdafcf33113d7c8ce75459cbb5c128988` —
  `experiment: activate c1 oracle amendment` (pushed; first Oracle 0.2 formal
  attempt starting revision).
- `0f6f50968510704067cebc48949a29f2ec6d5a0d` —
  `experiment: record c1 a-first result` (pushed).
- `ffc0cb3522dbbab97a7df30378ff7dbe73205ee8` —
  `experiment: record c1 near observability rejection` (pushed; second A/near
  attempt starting revision).
- `489204770d5ac095cde6274148f2ce3e5dd175ea` —
  `experiment: add c1 preflight observation warmup` (pushed future-only
  harness amendment after A/near closed at cap).
- `b24cfb4fb18c175856f2d01991c8d498f1d2710f` —
  `experiment: complete concurrent authority event probe` (pushed final C1
  report, conditional Gate, compact summary, and frozen 17-attempt ledger).
- `d78a206080a033f20fbd66fdb940c2ff8b1040d2` —
  `docs: record c1 phase closure` (pushed durable C1 closure and R1-next
  state).
- `9faad09d0e9e7631497034e7ee27f8ab2ce9d896` —
  `oracle: preregister r1 session isolation study` (pushed before every
  formal R1 attempt).
- `e132665d7f38ee7fa4e2c66120ceb4d6f0617fbc` —
  `test: handle local-only provenance binaries` (pushed clean-checkout
  validation-contract correction; no frozen R1 artifact changed).
- `ca875a19290cfb25008e34f7eafab369a71aac06` —
  `docs: activate r1 execution checkpoint` (pushed post-freeze bookkeeping;
  formal R1 attempt starting revision).
- `f1be7d2aa138a003bb311e04f2e5d4fb4396c6e9` —
  `experiment: checkpoint r1 scenario a cap` (pushed six-attempt R1-A ledger
  and registered stop-rule checkpoint).
- `1f41229d17e42af6945bd040ccb1579128b1229e` —
  `experiment: preregister w1 real workload spike` (pushed before every formal
  W1 runtime attempt).
- `a599cffffd29bf64072dc84cf338d43575d48c97` —
  `experiment: amend w1 runtime compatibility` (pushed source/build/interface
  audit and compatibility lock).
- `b1b0b32671c8fb02dd63b719c9fe7718e5deaa4f` —
  `experiment: lock w1 runtime trace tooling` (pushed before W1-B attempt 1).
- `a394d0f92c0ff8339ccb272e0b4d66d0bdb736b6` —
  `experiment: amend w1 flight-safety runtime tooling` (pushed before W1-B
  attempt 2).
- `b29949654070c45ceb7fb2135eaa12c9951ab87b` —
  `experiment: amend w1 bounded SITL trace acquisition` (pushed before W1-B
  attempt 3).
- `792a36d6ff9a26202e9fde31e4b085eff90b65c8` —
  `experiment: preregister b1 family b gate` (pushed before formal B1 source,
  build, or runtime evidence).
- `4c48621e08027c4a8eeff206d7fd63bfe55257c4` —
  `experiment: activate b1 preregistration` (pushed identity checkpoint).
- `091f48ddd1776af0d54d22b51d466377547b6374` —
  `experiment: prepare b1 reference controller probe` (pushed before B1-D).
- `0cb95ef61781fa87e69f50ccb18bc41acbdefe5e` —
  `experiment: lock b1 reference probe identity` (formal-attempt identity).

## Next exact action

The exact next registered phase is M-FINAL, the unified Motivation Completion
Gate. M-FINAL has not started. B1 authorizes only this registered progression;
it does not authorize a Family B campaign, random campaign, or full Stateful
Testing, and it does not predeclare an M-FINAL result.

## Current blockers

- N1-A reached its six-attempt cap with only 2/3 accepted runs. This is a
  bounded measurement-insufficient cell, not authorization to retry it.
- The accepted reduced-confirmation run did not reproduce the C-bucket event;
  this bounds the conclusion to phase-dependent re-observation rather than a
  stable reproduction claim.
- C1 attempt `c1-a-a-first-a01` is excluded as a campaign configuration
  failure: Oracle 0.1 admitted post-window cleanup RTL. Its raw evidence and
  original result remain preserved; diagnostic 0.2 reanalysis PASS is not
  promoted into the accepted denominator.
- C1-A/near reached its two-attempt cap with two clock-bridge sample-count
  rejections (16 valid samples versus the frozen minimum 20). The cell is
  closed measurement-insufficient and will not be retried.
- R1-A reached its six-attempt cap with zero accepted runs. Attempt 1 ended in
  a PX4 abort after new registration; attempts 2–6 crossed the frozen
  pre-cleanup ground-contact boundary before new activation. All six are
  `FORMAL_SAFETY_STOP`, no Oracle outcome was produced, and R1-B/R1-C were not
  started under the registered stop rule.
- W1-B reached its three-attempt cap with zero accepted source traces. Attempts
  1 and 3 crossed the frozen speed boundary after entering go-to; attempt 2
  crossed the altitude boundary during internal takeoff. All three are
  `FORMAL_SAFETY_STOP`. W1-C and W1-D were not executed because no accepted
  source trace existed, and W1-E was not authorized by the Native Adapter Gate.
  No route, lifecycle, timing, or replay conclusion entered an accepted
  denominator.
- B1-D reached its three-attempt cap with zero accepted combined builds. All
  three are `CAMPAIGN_CONFIGURATION_FAILURE`: a generated submodule cache
  tripped the clean guard, a colcon global option was ordered incorrectly after
  a successful PX4 component build, and the shared patch preparation script
  rejected a correctly base-plus-incrementally-patched worktree as partial.
  The reference binary/loadability was not established; B1-E and B1-F are
  `NOT_APPLICABLE`. No runtime controller, writer, or restoration result exists.

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
