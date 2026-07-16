# Switch-Transient Severity Campaign

Date: 2026-06-29 / 2026-06-30
PX4: `3042f906`
Board/mode: `px4_sitl_mcnn_sih`, mode id 23 (`mc_nn`)
Execution: serial N=1, `PX4_SIM_SPEED_FACTOR=1.25`, no EKF2/state-shim/Step C

## Scope And Gates

This campaign redirects the existing MAP-Elites differential fitness to catastrophic severity properties `{P1, P2}`. The primary bug predicate is `strict_s0_vs_s3`: decontaminated/control-level classical severity S0 and decontaminated/control-level `mc_nn` severity S3. Confirmation is severity-triggered: `2/3` seeds is accepted as confirmed, and `3/3` is reported separately.

Fitness and finding gates use decontaminated control severity, not raw terminal severity. Invalid trigger timeouts, decontamination failures, run errors, and identity failures are excluded as invalid and do not enter quadrants.

## Preflight

Route-A regression passed on the final 4-anchor set under the multi-seed severity+sign gate. Pair5 was retained as a probabilistic anchor: fixed seeds `20261803..20262603` produced `8/9` `mc_nn` S3 outcomes, with `20261803 -> S0` and the other eight seeds `-> S3`. This is also used below as seed-level evidence for the RQ3 boundary.

Addendum 4 reachability mapping showed rate was partially coupled to attitude, so the final descriptor was `switch_roll_pitch_bucket x wind_bucket`; rate remains a constrained search variable, not the second descriptor axis.

| attitude bin | reachable actual rate span |
|---|---:|
| 16.0-22.8 deg | 0.648-0.922 rad/s |
| 22.8-29.6 deg | 0.648-1.247 rad/s |
| 29.6-36.4 deg | 0.648-1.615 rad/s |
| 36.4-43.2 deg | 0.747-2.029 rad/s |
| 43.2-50.0 deg | 0.906-2.502 rad/s |

Step-1 probe on the corrected space was healthy: 24 evals, 22 valid, 5 primary `S0∧S3`, 14/25 valid cells, and 0 too-hard valid cells.

## RQ2: Guided vs Random vs Grid

Discovery budgets were equal per stochastic seed: guided `120 x 3`, random `120 x 3`, grid `120 x 1`.

| arm | evals | valid | invalid | first primary evals | primary evals | visited valid cells | primary cells | archive bins | best quality | QD score |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| guided seed0 | 120 | 104 | 16 | 1 | 65 | 20 | 10 | 10 | 20.547 | 197.483 |
| guided seed1 | 120 | 104 | 16 | 8 | 54 | 21 | 10 | 10 | 21.982 | 192.588 |
| guided seed2 | 120 | 99 | 21 | 4 | 60 | 18 | 10 | 10 | 20.815 | 176.342 |
| random seed0 | 120 | 118 | 2 | 9 | 12 | 25 | 7 | 8 | 20.959 | 107.991 |
| random seed1 | 120 | 117 | 3 | 2 | 16 | 25 | 9 | 9 | 21.698 | 158.386 |
| random seed2 | 120 | 116 | 4 | 7 | 12 | 25 | 5 | 8 | 21.881 | 89.708 |
| grid | 120 | 102 | 18 | 75 | 19 | 22 | 7 | 7 | 20.471 | 122.540 |

Aggregate:

| arm | evals | primary evals | primary cells | primary-cell entropy | confirmed top cells 2/3 | confirmed top cells 3/3 |
|---|---:|---:|---:|---:|---:|---:|
| guided | 360 | 179 | 10 | 3.184 bits | 8/10 | 6/10 |
| random | 360 | 40 | 10 | 3.146 bits | 7/10 | 6/10 |
| grid | 120 | 19 | 7 | 2.610 bits | 5/7 | 3/7 |

Conclusion: guided clearly improves discovery density and QD/illumination over random and grid. The yes/no time-to-first advantage over random is modest because random seed1 hit early at eval 2, but guided is far more consistent: `54-65` primary evals per seed versus random `12-16`. Coverage/spread does not show guided merely camping one cell: guided primary outcomes covered all 10 high-risk `rp_3/rp_4 x wind` cells with entropy comparable to random, while producing about 4.5x more primary evals.

## Confirmed Severity Differentials

Guided top-cell confirmation passed the kill-switch: known-region confirmed severity was not zero.

| arm | cell | severity hits |
|---|---|---:|
| guided | `rp_4:wind_4` | 3/3 |
| guided | `rp_4:wind_1` | 2/3 |
| guided | `rp_4:wind_0` | 2/3 |
| guided | `rp_3:wind_1` | 3/3 |
| guided | `rp_4:wind_2` | 0/3 |
| guided | `rp_3:wind_4` | 3/3 |
| guided | `rp_4:wind_3` | 3/3 |
| guided | `rp_3:wind_3` | 1/3 |
| guided | `rp_3:wind_2` | 3/3 |
| guided | `rp_3:wind_0` | 3/3 |
| random | `rp_4:wind_4` | 3/3 |
| random | `rp_4:wind_0` | 1/3 |
| random | `rp_4:wind_2` | 2/3 |
| random | `rp_4:wind_1` | 3/3 |
| random | `rp_3:wind_3` | 1/3 |
| random | `rp_3:wind_0` | 3/3 |
| random | `rp_4:wind_3` | 3/3 |
| random | `rp_3:wind_1` | 3/3 |
| random | `rp_3:wind_2` | 1/3 |
| random | `rp_3:wind_4` | 3/3 |
| grid | `rp_4:wind_2` | 0/3 |
| grid | `rp_4:wind_3` | 0/3 |
| grid | `rp_3:wind_2` | 3/3 |
| grid | `rp_3:wind_0` | 3/3 |
| grid | `rp_3:wind_1` | 3/3 |
| grid | `rp_3:wind_3` | 2/3 |
| grid | `rp_3:wind_4` | 2/3 |

The confirmed set is not just one wind/attitude corner: confirmed cells span both `rp_3` and `rp_4`, and wind buckets 0-4. Some high-quality discovered cells failed confirmation (`rp_4:wind_2`, parts of `rp_3:wind_3`), which supports treating severity as probabilistic near the boundary.

## RQ3: Controlled Dense Sweep

Dense sweep used one fixed boundary baseline and changed one dimension at a time. Each point used seeds `2026062940, 2026062941, 2026062942`. Total: 40 points, 120 evals, 120 valid, 81 strict `S0∧S3`.

### Attitude

| attitude | strict hits | classical severity | neural severity |
|---:|---:|---|---|
| 28 deg | 0/3 | S1x3 | S1x3 |
| 31 deg | 0/3 | S1x3 | S1x3 |
| 34 deg | 0/3 | S1x3 | S1x3 |
| 36 deg | 0/3 | S1x3 | S1x1, S3x2 |
| 38 deg | 0/3 | S1x3 | S1x1, S3x2 |
| 40 deg | 2/3 | S0x3 | S0x1, S3x2 |
| 42 deg | 3/3 | S0x3 | S3x3 |
| 45 deg | 3/3 | S0x3 | S3x3 |
| 48 deg | 1/3 | S0x3 | S0x2, S3x1 |

The boundary is not monotonic. The strict region starts at about 40 deg, is stable at 42-45 deg, then partially recovers at 48 deg.

### Requested Rate

| requested rate | strict hits |
|---:|---:|
| 0.55 | 3/3 |
| 0.75 | 3/3 |
| 0.95 | 3/3 |
| 1.15 | 3/3 |
| 1.35 | 3/3 |
| 1.55 | 1/3 |
| 1.75 | 3/3 |
| 2.05 | 2/3 |
| 2.35 | 3/3 |

Rate is also non-monotonic: `1.55` is a hole, `1.75` recovers to 3/3, and `2.05` is probabilistic. Actual rate remains reachability-constrained by the circle profile.

### Wind

| wind | strict hits |
|---:|---:|
| 0 m/s | 3/3 |
| 1 m/s | 3/3 |
| 2 m/s | 3/3 |
| 3 m/s | 3/3 |
| 4 m/s | 0/3 |
| 5 m/s | 0/3 |
| 6 m/s | 0/3 |

Wind is strongly boundary-shaping, not merely a stress amplifier. At this fixed theta, 0-3 m/s exposes the differential and 4-6 m/s recovers.

### Switch Delay

| delay | strict hits |
|---:|---:|
| 0.00 s | 3/3 |
| 0.03 s | 3/3 |
| 0.06 s | 1/3 |
| 0.09 s | 3/3 |
| 0.12 s | 1/3 |
| 0.15 s | 3/3 |
| 0.18 s | 3/3 |

Delay has temporal holes at 0.06 and 0.12 s. This points to phase/timing sensitivity rather than a simple severity scalar.

### Approach Phase

| phase | strict hits |
|---:|---:|
| 0 | 2/3 |
| pi/4 | 3/3 |
| pi/2 | 3/3 |
| 3pi/4 | 2/3 |
| pi | 3/3 |
| 5pi/4 | 2/3 |
| 3pi/2 | 2/3 |
| 7pi/4 | 2/3 |

Approach phase changes the probability but not the existence of the bug in this baseline. One repeated baseline point differed across identical theta/seed labels in separate sweep axes, confirming residual SIH non-bit-exact behavior near the boundary.

### RQ3 Interpretation

The failure region is a high-dimensional boundary with holes, not a monotonic scalar threshold. Attitude, rate, delay, wind, and phase all affect whether `mc_nn` tumbles while classical remains S0. Pair5's `8/9` anchor result is consistent with this: it is a fixed-theta probabilistic boundary point, not an outlier to hide.

## Throughput

Measured campaign and confirmation eval records averaged 162.8 s per paired eval, or about 22.1 eval/h. Dense sweep measured 20.6 eval/h end-to-end. This is consistent with the expected serial SIH throughput at `PX4_SIM_SPEED_FACTOR=1.25`.

## Caveats

This is not a formal significance test. With three guided seeds and three random seeds, guided's discovery-density/QD advantage is clear, but the top-candidate confirmation counts are close enough that the report should not claim a strong superiority on confirmed-count alone.

Continuous rho values are diagnostic only. Reproduction and confirmation use discrete severity plus violation sign discipline. Invalid trigger/run failures are excluded and not counted as safe or unsafe quadrants.

The campaign remains SIH-only and shim-free. No EKF2/state-shim changes were made, and no Step C work was performed.
