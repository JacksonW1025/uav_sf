# RQ2 Archive Reanalysis

Date: 2026-07-05

Scope: pure reanalysis of existing switch-severity artifacts. No simulator, ULOG reparse, oracle change, or new eval was run.

## Verdict

The guided archives do partially illuminate the RQ3 boundary: they independently concentrate on the `rp_3/rp_4 x wind` high-risk cells, and they strongly reproduce the 42-45 deg attitude band. They do not, by themselves, recover the controlled dense-sweep holes for requested rate or the fixed-baseline wind recovery at 4-6 m/s. The honest framing is therefore: guided MAP-Elites rapidly delivers a compact, high-yield boundary-localizing archive, while the detailed non-monotonic hole structure remains a dense-sweep result.

Core dense-boundary feature completeness from the archive: 2.0/5 (40.0%).

## Source Artifacts

- `runs/campaigns/switch_severity_guided_0_20260629`
- `runs/campaigns/switch_severity_guided_1_20260630`
- `runs/campaigns/switch_severity_guided_2_20260630`
- dense sweep: `runs/campaigns/switch_severity_dense_sweep_20260630/sweep_results.jsonl`

## Guided Archive Coverage

| run | evals | valid | primary evals | archive primary elites | primary cells | first primary eval | evals to 5/8/10 cells | QD score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| switch_severity_guided_0_20260629 | 120 | 104 | 65 | 10/10 | 10 | 2 | 14 / 35 / 44 | 197.483 |
| switch_severity_guided_1_20260630 | 120 | 104 | 54 | 10/10 | 10 | 9 | 17 / 40 / 61 | 192.588 |
| switch_severity_guided_2_20260630 | 120 | 99 | 60 | 10/10 | 10 | 5 | 17 / 32 / 88 | 176.342 |

All three guided runs ended with 10/10 final archive elites in the high-risk `rp_3/rp_4 x wind_0..4` cells. Those 10 cells were first covered by eval 44, 61, and 88 respectively, versus 120 paired evals in the RQ3 dense sweep.

## Final Elite Distribution

| quantity | min | median | max |
| --- | --- | --- | --- |
| switch attitude deg | 38.75 | 43.22 | 50.00 |
| wind m/s | 0.00 | 3.01 | 5.33 |
| actual switch rate rad/s | 0.983 | 1.076 | 1.203 |
| switch delay s | 0.000 | 0.127 | 0.180 |
| elite eval index | 10 | 75 | 119 |

Archive attitude bands: `{"36-<40": 5, "40-<42": 3, "42-45": 11, "45-<48": 5, ">=48": 6}`

Archive wind bands: `{"0-<1": 6, "1-<2": 6, "2-<3": 3, "3-<4": 5, "4-<5": 4, "5-6": 6}`

Archive rate bands: `{"<1.45": 30}`

## RQ3 Feature Check

| feature | archive status | archive evidence | dense-sweep evidence |
| --- | --- | --- | --- |
| attitude onset near 40 deg | partial | final elite min attitude 38.75 deg; 36-<40 eval bucket 17/60 (28.3%); the search archive does not supply a controlled lower-safe side | 38:0/3, 40:2/3, 42:3/3 |
| 42-45 deg stable strict band | strong | 11/30 final elites are in 42-45 deg; eval bucket 57/73 (78.1%) | 42:3/3, 45:3/3 |
| 48 deg partial recovery | partial | 6 final elites remain primary at >=48 deg; eval bucket 22/30 (73.3%) versus 45-<48 bucket 53/58 (91.4%) | 45:3/3, 48:1/3 |
| rate 1.55 hole / 1.75 recovery | not_shown | archive actual rate range 0.983-1.203 rad/s; high-rate final elites >=1.45 rad/s: 0/30 | 1.55:1/3, 1.75:3/3 |
| wind 0-3 exposure / 4-6 recovery at fixed baseline | not_shown | archive keeps 10 primary elites at wind >=4 m/s; eval buckets 4-<5 19/42 (45.2%), 5-6 23/35 (65.7%) | 0:3/3, 3:3/3, 4:0/3, 6:0/3 |
| delay 0.06/0.12 temporal holes | not_shown | archive has 7 elites in the dense-sweep hole-adjacent delay buckets; eval buckets 0.06-<0.09 22/38 (57.9%), 0.12-<0.15 26/48 (54.2%) | 0.06:1/3, 0.12:1/3 |

## Interpretation For Paper Framing

- Strong claim supported by archive reanalysis: guided search rapidly finds and preserves high-quality elites across the same broad attitude-wind cells later used in RQ3.
- Claim not supported by archive alone: the full high-dimensional hole boundary. Rate, delay, and fixed-baseline high-wind recovery require the dense sweep.
- Recommended RQ2/RQ3 linkage: use the fuzzer archive as boundary-localizing evidence and use the dense sweep as the controlled causal characterization. Do not write that the fuzzer alone delivered the RQ3 boundary.
