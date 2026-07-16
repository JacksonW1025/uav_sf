# Wave-2 State-Contamination Campaign

Date: 2026-07-03
PX4: `3042f906`
Board/mode: `px4_sitl_mcnn_sih`, mode id 23 (`mc_nn`)
Execution: serial N=1, `PX4_SIM_SPEED_FACTOR=1.25`, no Step C timing rewrite

## Scope

Wave-2 tested the non-switching estimated-state contamination axis. The strict differential oracle was unchanged: after decontamination, classical must remain clean and `mc_nn` must fail under the established property/severity gates. Continuous rho gaps are diagnostic unless they satisfy the existing property gates and pass multi-seed confirmation.

The selected descriptor was `velocity_bias_bucket x angular_rate_bias_bucket` over the `state_contam` subspace. Position-estimate jump remains a generated contamination variable, but it is not a descriptor axis in this run.

## Gate A Prime

Gate A was redefined from a single-sample four-anchor gate to a hard deterministic gate plus boundary-rate tracking:

| anchor group | result |
|---|---:|
| pair1 hard anchor | 1/1 strict S0/S3 |
| pair2 hard anchor | 1/1 strict S0/S3 |
| pair4 boundary anchor | 7/8 strict S0/S3 |
| pair5 boundary anchor | 8/8 strict S0/S3 |

Decision: pass. The only boundary non-strict seed was pair4 seed `20262202`, reported as the expected boundary flip rather than a shim failure. Artifact: `runs/route_a_anchor_regression/wave2_gateA_prime_20260703/summary.md`.

## Genome And Plumbing

`state_contam` is now a routable genome subspace. The enabled variables are:

| genome variable | shim route |
|---|---|
| `position_estimate_jump_m` | `M2B_P_PROF=2`, X-axis position bias |
| `fake_velocity_bias_m_s` | `M2B_V_PROF=2`, X-axis velocity bias |
| `fake_angular_rate_bias_rad_s` | `M2B_G_PROF=2`, Z-axis angular-rate bias |

Generated theta sets `M2B_EN=1` when contamination is nonzero and records `environment.uses_state_shim=true`. The build wrapper installs the rebuilt shim before PX4 build. Focused tests cover theta generation, campaign routing, fairness/delivery, and the rebuilt patch.

## Probe

Probe: `wave2_statecontam_probe_20260703_rerun`, 24 random evals.

| metric | value |
|---|---:|
| evals | 24 |
| valid | 23 |
| invalid | 1 classical task rc=2 |
| archive bins | 14 |
| state-shim delivery/fairness | 23/23 |
| identity | 23/23 |
| decontamination | 23/23 |
| strict differential | 0 |
| relative-degradation evals | 23/23 |

Gate C decision: pass. The space was not all invalid/too-hard, and the shim delivery check verified symmetric contaminated shared topics plus `mc_nn` observation touch.

## Main Campaign

Budget logged before run: guided 200 + random 200, confirmation repeats 3, max confirmation candidates 3, serial N=1.

| arm | evals | valid | invalid | archive bins | strict differentials | primary candidates | relative-degradation evals | best diagnostic gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| guided | 200 | 200 | 0 | 24 | 0 | 0 | 200 | P2 gap 2.396 |
| random | 200 | 199 | 1 mcnn task rc=2 | 25 | 0 | 0 | 199 | P2 gap 2.254 |

Validity gates over valid evals:

| arm | state-shim delivery/fairness | identity | decontamination |
|---|---:|---:|---:|
| guided | 200/200 | 200/200 | 200/200 |
| random | 199/199 | 199/199 | 199/199 |

Relative-degradation property counts over valid evals:

| arm | P1 | P2 | P4 | P6 | P7 |
|---|---:|---:|---:|---:|---:|
| guided | 24 | 200 | 200 | 114 | 3 |
| random | 22 | 199 | 199 | 125 | 4 |

No eval in either arm reached the strict S0/S3 differential oracle. Classical and `mc_nn` remained decontaminated S0 in the confirmed relative-degradation records.

## Confirmation

Built-in top-candidate confirmation found no primary bugs:

| arm | confirmed primary | confirmed reportable relative records |
|---|---:|---:|
| guided | 0 | 3 |
| random | 0 | 3 |

The confirmed relative records repeatedly reproduced P2/P4 relative degradation. P6 was intermittent; P1 was not confirmed as a repeated property. Random candidate `e0171` had one confirmation repeat with P7, but P7 was not a required property for that selected candidate.

Because P7 was a stated focus, a separate P7-targeted confirmation was run on the four strongest P7-gap candidates:

| candidate | original P7 gap | P7 repeats |
|---|---:|---:|
| `wave2_statecontam_random_20260703_e0114` | 0.687 | 1/3 |
| `wave2_statecontam_guided_20260703_e0180` | 0.667 | 0/3 |
| `wave2_statecontam_random_20260703_e0145` | 0.601 | 0/3 |
| `wave2_statecontam_guided_20260703_e0170` | 0.538 | 0/3 |

P7 decision: observed as a candidate-level diagnostic signal, not P7-confirmed.

## Conclusion

This is a clean negative for robust state-contamination strict differential failure under the current oracle. The run exercised the new state-contamination plumbing, achieved healthy validity, full random descriptor coverage, and multi-seed confirmation, but found no strict S0/S3 differentials and no primary bugs in 400 main evals.

The positive diagnostic finding is stable P2/P4 relative degradation: `mc_nn` often has smaller positive margins than classical under symmetric state contamination. That is not the project-bearing differential oracle, and it should not be reported as a robust failure by itself.

The P7 hypothesis remains unsupported in this campaign. P7 candidates appeared in both guided and random search, but targeted confirmation reproduced P7 in only 1/12 repeats.

Interpretation for the larger narrative: wave-2 supports pinning the robust differential-failure claim to the switch-transient axis rather than broadening it to steady non-switching estimated-state contamination. This is the publishable negative outcome described in the wave-2 task: it reduces the "only measured switching" objection without forcing a positive.

## Caveats

This is not a formal significance test. The campaign is serial SIH with fixed budgets and top-candidate confirmation.

Continuous rho values remain diagnostic only. Disaster-class continuous rho is not used as a gate.

The state shim is not a bit/timing no-op when disabled because private ring buffers are written before the `M2B_EN` guard. This cleanliness caveat did not explain Gate A and was not hardened in this wave.

Step C timing was intentionally deferred; throughput stayed on the established serial N=1 path.
