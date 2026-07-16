# Combined Steady Wind + Physics Genome

Date: 2026-06-27

Scope: wave-1 launch pre-fix only. This changes the `steady-wind-physics`
subspace so wind and physics mismatch can be active in one theta. It does not
launch the campaign, does not change Step C, and does not change the switching
or step subspaces.

## Code Changes

- `scripts/theta_genome.py`
  - Added `disturbance_type="steady_combo"` for the steady subspace.
  - `steady_combo` preserves both wind (`wind_speed_m_s`, `wind_direction_rad`)
    and physics (`mass_scale`, inertia scales, `twr_scale`) through
    `normalize_genome()` and `theta_from_genome()`.
  - Added a 2D descriptor for combined steady cases:
    `feature_dimensions=["wind_bucket", "physics_bucket"]`.
  - Archive bins now look like
    `steady_combo:wind_high:physics_high`.
- `scripts/m2_map_elites.py`
  - `--subspace steady-wind-physics` now generates, mutates, crossovers, and
    projects to `steady_combo`.
  - Mutation changes both wind and physics coordinates.
  - Projection repairs old/pure-axis parents into legal combined steady genomes.
- `scripts/campaign_runner.py`
  - Steady grid baseline now samples combined wind+physics stress instead of
    interleaving pure wind and pure physics.

## Step 1 - Offline Operator Evidence

High-corner offline theta:

```json
{
  "disturbance_type": "steady_combo",
  "feature_dimensions": ["wind_bucket", "physics_bucket"],
  "amplitude_bucket": "wind_high:physics_high",
  "wind_n": -1.8371,
  "wind_e": 7.7862,
  "mass": 2.5,
  "ixx": 0.0433334,
  "iyy": 0.0433334,
  "izz": 0.09,
  "hover": 0.57358357
}
```

Unit tests added:

- `test_steady_combo_keeps_wind_and_physics_and_uses_2d_descriptor`
- `test_switching_and_step_subspaces_keep_existing_gates`
- `test_steady_subspace_candidate_operators_combine_wind_and_physics`

Result: random, mutation, crossover, and grid for `steady-wind-physics` all
produce legal `steady_combo` theta with both wind and physics active.
Switching still allows wind but resets physics to nominal; step still resets
wind and physics to nominal.

## Step 2 - Real Combined-Corner Probe

Run root: ignored `runs/campaigns/combined_steady_corner_20260627`.

Command shape:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=combined_steady_corner_20260627 \
  ./docker/run.sh bash -lc "python3 scripts/campaign_runner.py \
  --run-id combined_steady_corner_20260627 --run-root runs/campaigns \
  --budget 1 --bootstrap 1 --seed 20260630 --strategy grid \
  --subspace steady-wind-physics --target-properties behavior \
  --sim-speed-factor 1.25 --skip-build --no-confirm \
  --run-timeout 170 --eval-timeout 360"'
```

Then resumed the same checkpoint to budget 4 to cover the four cardinal wind
directions for the same high physics corner. The runner resumed at eval 1 and
did not rerun eval 0.

High physics corner:

- wind speed: 8.0 m/s
- mass scale: 1.25
- inertia roll/pitch/yaw scales: 1.60 / 1.60 / 1.80
- TWR scale: 1.0
- feature bin: `steady_combo:wind_high:physics_high`

Rho results:

| eval | wind direction rad | best prop | P4 neural | P6 neural | P7 classical | P7 neural | P7 classic margin valid |
|---:|---:|---|---:|---:|---:|---:|---|
| 0 | 0.0000 | P4 | 0.4785 | 0.1908 | 0.6103 | 0.6040 | true |
| 1 | 1.5708 | P7 | 0.4861 | 0.2236 | 0.8027 | 0.3024 | true |
| 2 | 3.1416 | P4 | 0.4931 | 0.1583 | 0.4702 | 0.6557 | true |
| 3 | 4.7124 | P4 | 0.4987 | 0.1891 | 0.8585 | 1.0142 | true |

Reference from Part 2 pure wind: best P7 neural rho was `0.3711` at wind speed
`6.9527 m/s`.

Interpretation:

- The north/east/south/west cardinal sweep found one positive signal:
  direction `pi/2` pushed P7 neural rho to `0.3024`, which is harsher than the
  Part-2 pure-wind `0.3711`.
- Classical remained valid for P7 in all four evals; the best P7 classical rho
  for the harsher direction was `0.8027`, above `margin_c_P7=0.1126242187`.
- The combined corner still did not cross the finding threshold. P7 finding
  requires neural rho `<= -0.4484874426`.

Validity gates:

| eval | decontam classical | decontam mcnn | identity | identity Hz | exact matches | exact fraction |
|---:|---|---|---|---:|---:|---:|
| 0 | true | true | true | 229.21 | 5938 | 0.8959 |
| 1 | true | true | true | 229.88 | 6114 | 0.9015 |
| 2 | true | true | true | 229.93 | 6011 | 0.8980 |
| 3 | true | true | true | 230.39 | 5968 | 0.8972 |

## Conclusion

Step 1 is green: the steady subspace can now search combined wind+physics
stress with a 2D descriptor, and switching/step are unchanged.

Step 2 is mixed but useful: the high combined corner can push P7 harder than
the prior pure-wind smoke while keeping classical safe, so the combined
subspace is worth launching. The observed corner is still far from the P7
finding threshold, so wave 1 should search the 2D high-stress region rather
than assume this single hand-picked corner is enough.

## Verification

- `python3 -m py_compile scripts/theta_genome.py scripts/m2_map_elites.py scripts/campaign_runner.py scripts/validity_automation.py scripts/property_fitness.py scripts/property_oracle.py tests/test_theta_genome.py tests/test_campaign_runner.py tests/test_property_fitness.py tests/test_validity_automation.py`
- `python3 -m unittest tests/test_theta_genome.py tests/test_campaign_runner.py tests/test_property_fitness.py tests/test_validity_automation.py` - 18 tests OK.
- `python3 scripts/theta_genome.py --self-test 300 --seed 20260627`
- Mock campaign structural check:
  `python3 scripts/campaign_runner.py --run-id combined_steady_mock_verify_20260627 --run-root runs/campaigns --budget 3 --bootstrap 1 --seed 20260631 --strategy guided --subspace steady-wind-physics --target-properties behavior --mock-evaluator --no-confirm`
- Real combined-corner probe: 4/4 evals completed with `error=null`.
- `find scripts docker -maxdepth 2 -name '*.sh' -print0 | xargs -0 -n1 bash -n`
- `jq empty` on the combined steady mock/real run JSON files under ignored
  `runs/campaigns/`.
- `git diff --check`
- `git diff --cached --check`
