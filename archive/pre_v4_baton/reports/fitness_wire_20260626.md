# Tier 0.5 Fitness Wire

Date: 2026-06-26

Scope: Tier 0.5 step 2.2 only. This wires differential property fitness into the MAP-Elites driver. It is not a 2.3 convergence or behavior-class finding campaign.

## Fitness Definition

Implemented in `scripts/property_fitness.py`.

Search fitness is the maximum valid per-property gap:

`gap_i = rho_i(classical) - rho_i(mcnn)`

A property is valid for fitness only when `rho_i(classical) >= margin_c_i` and the property is not vacuous. If no target property is valid, fitness is `-1e9`.

Driver target properties are:

- steady/default: P4, P6, P7
- step theta: P4, P5, P6, P7
- excluded from driver target set: P1, P2, P3

P1/P2 are still computed and used for validation and reporting, including Route-A regression. P3 is computed but not used as a driver target.

Single-objective MAP-Elites is used for this step: elite quality is `max_i gap_i`. Multi-objective P4/P6/P7 objectives are left for 2.3/campaign work; the result schema keeps per-property gaps so that split is mechanical later.

## Margins

`docs/oracle_calibration.md` now replaces scalar `margin_c=0.02` with per-property margins:

| property | margin |
|---|---:|
| P1 | 0.4548139946 |
| P2 | 2.3421337853 |
| P3 | 0.1500000000 |
| P4 | 0.2023303610 |
| P5 | 0.1083387278 |
| P6 | 0.0759150636 |
| P7 | 0.1126242187 |

P1/P2/P3/P4/P6/P7 use 30% of recomputed classical-only nominal margins. P5 uses 30% of the non-vacuous pure-step classical minimum.

## Step 1 Checks

Synthetic unit tests:

- command: `python3 -m unittest tests.test_property_fitness tests.test_theta_genome`
- result: 7 tests, OK
- checked ordering: boring fitness `0`, too-hard fitness `-1e9`, behavior differential P6 high and flagged, catastrophic P1/P2 high and flagged
- checked driver targeting: P1/P2 clean differentials remain reported but are not target properties for the search driver
- checked vacuity: vacuous P5 is not fitness-valid

Route-A ULOG-only regression:

- command: `python3 scripts/route_a_property_fitness_check.py --output docs/route_a_property_fitness_20260626.json`
- result: 4/4 strict decontamination pairs passed
- P1/P2 fitness range: 13.811474 to 20.203324
- best property for all 4 pairs: P2
- mc_nn identity: confirmed for all 4 at 229.31-231.00 Hz, `raptor_input_present=false`

The Route-A strict label is taken from the existing decontamination result. Property fitness remains per-property: a P1/P2 clean differential is not invalidated by unrelated P6/P7 behavior-class rho values in the same scene.

## Step 2 Driver Smoke

`scripts/m2_map_elites.py` now uses:

- genome and bins from `scripts/theta_genome.py`
- evaluator path: theta -> classical SITL + mc_nn SITL -> property oracle -> differential gap fitness
- archive quality: property gap fitness
- parent selection: top archive elites by quality
- mode-23 identity gate: `mcnn_confirmed=true`, neural output rate over 100 Hz, `raptor_input` absent

Mock MAP-Elites smoke:

- command: `python3 scripts/m2_map_elites.py --run-id tier05_fitness_wire_mock_20260626 --budget 8 --bootstrap 3 --seed 20260626 --mock-evaluator --no-confirm`
- result: archive/parent logic closed
- example evidence: eval 3 selected parent `tier05_fitness_wire_mock_20260626_e0002` with quality `1.85`; eval 6 selected parent `tier05_fitness_wire_mock_20260626_e0001` with quality `1.341333`

Real SITL smoke:

- command used inside the project container with ROS sourced:
  `python3 scripts/m2_map_elites.py --run-id tier05_fitness_wire_sitl3_20260626 --budget 3 --bootstrap 1 --seed 20260627 --skip-build --no-confirm --run-timeout 170 --eval-timeout 360 --sim-speed-factor 1`
- result: 3/3 evals completed, 0 runner errors, 1 archive bin filled: `physics_mismatch:high`
- eval 0: bootstrap random, best P4, fitness `0.1951850146`
- eval 1: selected parent eval 0, parent quality `0.1951850146`, best P4, fitness `0.1965801552`, archive updated
- eval 2: selected parent eval 1, parent quality `0.1965801552`, best P4, fitness `0.1935170650`
- mc_nn identity sample from eval 1: `mcnn_confirmed=true`, neural rate `230.6302 Hz`, `raptor_input_present=false`, exact output/actuator timestamp-equal count `6143`

This demonstrates end-to-end closure and fitness-based parent selection. No monotonic improvement claim is made.

## Notes

The first real SITL attempt exposed a P5 vacuity edge: a non-driver/non-settling step-like setpoint change could produce "detected step but no settling candidates". `property_oracle.py` now treats that case as vacuous instead of an eval error, matching the P5 non-step rule.

Raw `.ulg` and `.log` outputs from SITL smoke runs are local-only and are not part of the commit.
