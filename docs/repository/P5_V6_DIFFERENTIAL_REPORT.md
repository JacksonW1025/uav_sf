# P5 v6 paired differential report

Date: 2026-07-18. Campaign: `campaign_seeded_v6`.

## 1. Disposition

The formal P5 v6 matrix is complete: 35/35 matched pairs and 70/70 accepted
formal sides. The P5 Differential Gate is **`CONDITIONAL_PASS`**.

Under the frozen PX4, adapter, Oracle, scenario, retained-route contract,
threshold, and fallback revision, this campaign observed no route violation.
The condition is inferential, not a frozen-revision blocker: cross-domain
timing differences were not resolved above clock uncertainty, and one
state-dependent physical signal requires confirmation under the preregistered
adaptive rule.

The machine-readable decision is
[p5_v6_differential_gate.json](../../experiments/probes/p5/p5_v6_differential_gate.json).

## 2. Frozen campaign and provenance

- Implementation commit: `7f736c209b2818dc0d64024ffd6045c8549f0e13`
- PX4 commit: `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`
- PX4 binary SHA-256: `931320a0...8993`
- Observation patch SHA-256: `73555576...e8b7c`
- Dynamic adapter binary SHA-256: `af5a02a2...ef79b`
- Legacy adapter source SHA-256: `1448d8be...1314`
- Route Oracle/result/trace: `0.4` / `1.3` / `1.2`
- Scenario schema/hash: `1.1` / `e0affa...b3db5`
- Retained-route contract: `p5-retained-route-observation-v1` / `1.0`,
  SHA-256 `41be4c...90e4c`
- Threshold profile: `route-oracle-v0.3-default`
- Fallback: Hold, expected nav state `4`

Every accepted side matched this identity. Both sides of every pair used the
same simulation seed and context. No v3/v4/v5 or candidate-pilot side was
reused. The v5 manifest remains byte-for-byte unchanged at SHA-256
`8c7727986...329c31f`.

The frozen accepted input is
`runs/p5/campaign_seeded_v6/accepted_runs.tsv`, SHA-256
`b19449ce...c5a8685`. The preregistered analysis produced 71 cell/metric
comparisons in `paired_results.tsv` and `paired_summary.json`, SHA-256
`1711238e...14f0bb` and `a4f4aa43...e728e8` respectively.

## 3. Completeness and acceptance audit

| audit item | result |
|---|---:|
| complete / partial / pending pairs | 35 / 0 / 0 |
| accepted Legacy / Dynamic sides | 35 / 35 |
| transition / retained-route sides | 60 / 10 |
| return-0 and runner-valid sides | 70 |
| scenario monitor PASS | 70 |
| clock bridge VALID | 70 |
| observation window COMPLETE | 70 |
| Route Oracle PASS / UNKNOWN / VIOLATION | 70 / 0 / 0 |
| frozen-identity mismatches | 0 |
| matched-seed mismatches | 0 |
| campaign-configuration failures | 0 |

Continuity and exclusivity passed on all 70 accepted sides. Revocation and
installation passed on all 60 transition sides and were explicitly
`NOT_APPLICABLE` on all ten T7 sides. Recovery passed on the 50 transition
sides where it applies, was `NOT_APPLICABLE` on the ten T1 admission sides,
and was also explicitly `NOT_APPLICABLE` on the ten T7 sides.

## 4. Route correctness findings

Across all accepted transition sides:

- post-revocation allocator input, setpoint consumption, stale-subject
  consumption, and writer-output maxima were all zero;
- no old/new route-epoch overlap was observed;
- no competing critical-window writer was observed;
- every critical window was `COMPLETE`;
- the maximum observed unowned window was 16 ms, within the 24 ms policy;
- no applicable Oracle clause returned UNKNOWN or VIOLATION.

Thus the campaign found no illegal overlap, proved route gap, post-revocation
old-route influence, or incomplete target installation.

## 5. Timing analysis

All differences below are paired medians in the direction Dynamic minus
Legacy. Cross-domain differences are interpreted against the maximum combined
per-run clock uncertainty for that cell.

| question / cell | median difference | 95% paired-bootstrap CI | combined uncertainty | conclusion |
|---|---:|---:|---:|---|
| T1 admission/activation | -12 ms | [-32, 64] ms | 108.99 ms | unresolved |
| T2 release | +4 ms | [-4, 8] ms | 119.16 ms | unresolved |
| T4 graceful-shutdown detection/fallback | -5.91 ms | [-131.76, 45.91] ms | 103.20 ms | unresolved |
| T4 release | +12 ms | [-4, 12] ms | 103.20 ms | unresolved |
| T5 crash detection/fallback | +41.84 ms | [-38.93, 81.82] ms | 141.95 ms | unresolved |
| T6 pause detection/fallback | +122.99 ms | [-121.02, 329.99] ms | 116.10 ms | unresolved |
| T8 target consumption | -8 ms | [-12, 8] ms | 109.70 ms | unresolved |

Target-installation medians ranged from -12 to +12 ms across the transition
cells, but every confidence interval crossed zero and every difference was
below combined clock uncertainty. Recovery-duration differences were also
unresolved. There is no stable admission, release, failure-detection,
fallback-selection, installation, or recovery timing advantage for either
mechanism in this dataset.

PX4-domain route epoch, writer ordering, overlap, and gap evidence does not
inherit cross-domain clock uncertainty. Those same-domain findings were
uniformly conforming as described above.

## 6. Physical response and state dependence

One of 71 preregistered comparisons was resolved above its physical resolution
bound: in T4 turn/graceful-shutdown pairs, Dynamic peak tilt was higher by a
median `0.007939 rad`, with 95% CI `[0.004781, 0.008803] rad` and combined
resolution `0.001414 rad`. All five paired differences were positive.

This is a state-dependent physical-response signal, not a route violation or
mechanism-wide safety ranking. Its coefficient of variation was `0.2115`, just
above the preregistered `0.20` adaptive threshold, so confirmation is required
before calling it stable. Altitude loss, peak tilt in all other cells, and
recovery duration were not resolved above their uncertainty/resolution and
bootstrap criteria.

Hover, straight, and descent therefore showed no resolved physical mechanism
difference. Turn showed the single T4 peak-tilt signal; T7 turn retention did
not reproduce a resolved tilt difference.

## 7. T7 retained-route result

All ten T7 accepted sides independently confirmed health/proof-of-life ON and
setpoint OFF. Each side retained its expected external route over a `COMPLETE`
3000 ms window after the fixed 500 ms settle interval.

- continuity and exclusivity: 10/10 PASS;
- revocation, installation, recovery: 30/30 explicit `NOT_APPLICABLE` clause
  results;
- unexpected fallback and route-change counts: all zero;
- authority and writer conflict counts: all zero;
- maximum unowned window: at most 20 ms, below the 24 ms policy;
- transition object and transition-only metrics: null / not applicable.

Legacy remained on mode 14/epoch 3 with `ros2_offboard` authority; Dynamic
remained on mode 23/epoch 4 with its registration/activation identity. No
route, epoch, authority, registration, activation, or writer instability was
observed. The v5 T7 measurement-design gap is therefore closed for this frozen
revision.

## 8. T8 continued-setpoint fallback result

All ten T8 accepted sides independently confirmed health OFF and setpoint ON.
Despite continued setpoints, all ten observed the expected Hold fallback
(`fallback_nav_state=4`), complete transition windows, and PASS for all five
transition clauses. Continued setpoint publication did not prevent fallback in
either mechanism under the frozen parameters.

## 9. UNKNOWN, violation, and environment patterns

There was no accepted UNKNOWN pattern and no Route Oracle violation. The 25
preserved environment attempts consist of 14 abort/timeout/runner failures
without a complete artifact set and 11 run-environment `DEGRADED` clock
bridges. Seven of the latter were recorded by the frozen runner as
`MEASUREMENT_UNKNOWN` but are formally classified as `ENVIRONMENT_FAILURE` by
the campaign rule because the degradation was environmental. Formal counts are
therefore 25 environment failures and zero excluded attempts.

Environment attempts were asymmetric (16 Dynamic, 9 Legacy), but they include
PX4 crashes, monitor timeouts, missing artifacts, and clock degradation under
elevated host scheduling load. They were excluded from accepted-pair analysis
and do not establish a SUT mechanism difference. No acceptance standard was
lowered, and all invalid sides were replaced only by new same-seed attempt IDs.

## 10. Preregistered adaptive decision

The analysis emitted `INCREASE_TRIGGERED_CELLS_TO_MAXIMUM`: all seven cells
triggered at least one adaptation reason, chiefly coefficient of variation or
a difference below combined uncertainty. The maximum is ten paired repeats.

The explicitly authorized v6 formal matrix is fixed at five repeats per cell,
and the Goal requires stopping new cases after 35 complete pairs. Therefore no
additional v6 side was run. The adaptive result is carried into the Gate as a
condition and follow-up recommendation; it is not authority to expand or
rewrite this completed campaign.

## 11. Differential Gate

The Gate is `CONDITIONAL_PASS` because:

1. the formal matrix, identity, clock, window, transition, retained-route, and
   matched-pair requirements are complete;
2. no route violation, systematic UNKNOWN, overlap, post-revocation influence,
   or policy-exceeding gap was observed;
3. T7 retention and T8 fallback are independently demonstrated for both
   mechanisms;
4. no timing superiority is resolved above clock uncertainty;
5. the T4 peak-tilt signal is measurable but requires adaptive confirmation;
6. the preregistered adaptation rule triggered all cells, so global safety or
   stable timing-ranking claims are not permitted.

The evidence supports entering a scoped next research-design phase, provided
that it preserves these inferential limits. There is no v6 revision blocker.

## 12. Confirmed mechanism facts

- Legacy and Dynamic use different authority/mode/epoch identities by design,
  yet both revoked, installed, and handed off routes without observed illegal
  overlap or old-epoch influence.
- Health retention, not setpoint continuity alone, governs T7 retention in the
  tested channel-decoupling case.
- Removing health while setpoints continue still produced Hold in every T8
  side.
- The frozen Oracle can adjudicate both transition and stable retained-route
  observations without inventing a fallback for T7.
- This campaign does not resolve mechanism-level timing superiority.
- T4 graceful shutdown has one repeat-confirmation candidate: higher Dynamic
  peak tilt in turns.

## 13. Ranked next-stage candidates

No next-stage work is started by this report. Recommended order:

1. External RTL replacement and expected successor, extending the now-verified
   replacement/fallback model to a safety-mode successor chain.
2. RC/GCS/failsafe concurrent authority events, directly exercising the
   lifecycle/event interleavings not covered by one-event v6 cells.
3. Mode Executor ownership and lifecycle progression, adding multi-stage
   completion, cancellation, and recovery ownership.
4. Stateful Fuzzer v0 design and smoke campaign, after deterministic
   interleaving invariants are preregistered.
5. Family B reference registered controller, testing whether the route
   contracts generalize to an internal registered controller.
6. Aerostack2 runtime spike or trace extraction, kept exploratory until its
   authority and writer evidence can map to the existing schemas.

Large-scale fuzzing, full Aerostack2 integration, a formal Family B campaign,
real-aircraft flight, a new PX4 version matrix, and v7 creation remain out of
scope.
