# mc_nn_control GATE-3 Position-Error Amplitude Probe

decision: NO-GO
run_id: `mcnn_gonogo_gate3_20260625`
scope: position-error amplitude channel only; no setpoint staleness, velocity, angular-velocity, shim, or RAPTOR run
attack_theta_count: 3 / 3
primary_bug_confirmed: false

## Step 0 Baseline

| controller | tracking RMS mean m | tracking RMS stdev m | samples |
|---|---:|---:|---:|
| classical | 0.4946857457942274 | 0.04518558945308369 | 5 |
| mcnn | 0.382236723709721 | 0.08574156715787161 | 5 |

## Attack Results

| theta | seeds | primary seeds | flight quadrants | classical D3 median | mc_nn D3 median | mc_nn z median | D3 supportive | max error C/M median m |
|---|---:|---:|---|---:|---:|---:|---|---:|
| ramp_x_12m_3s | 3 | 0 | boring_both_flight_safe | 3.651224431133772 | 3.282787119503055 | 10.176686739105074 | false | 5.2697969054560065/3.836683286543796 |
| ramp_x_8m_4s | 3 | 0 | boring_both_flight_safe | 2.3043086357941744 | 1.7737317477356158 | 3.449303506898947 | false | 2.6467038934773552/1.6451087301834475 |
| ramp_x_6m_6s | 3 | 0 | boring_both_flight_safe | 1.7190813894930932 | 0.9388759308185975 | -0.2724916830676409 | false | 1.6307476042969788/0.6249552352129406 |

## Decision Matrix Exit

NO-GO: no tested position-error amplitude theta produced multi-seed mc_nn_control flight-unsafe behavior with classical control-level flight-safe. This is only a position-error amplitude result, not a global mc_nn_control robustness result.

ULOGs are written under this directory but are ignored by git. Per-run `record.json` files contain the ULOG paths, flight quadrant, and D3 ratios.
