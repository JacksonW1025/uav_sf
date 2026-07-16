# Tier 1 Campaign Runner

Date: 2026-06-27

Scope: Tier 1 §3.2 checkpoint/resume plus §3.1 baseline wiring. This is
campaign infrastructure only, not a wave-1 campaign launch.

## Code

- Added `scripts/campaign_runner.py`.
- Default output root is ignored: `runs/campaigns/<run_id>`.
- Reuses `m2_map_elites.evaluate_theta()` for real evals, so guided, random,
  and grid share the same theta generator, evaluator, property oracle, and
  §3.4 validity gates.
- N=1 sequential orchestration only. Metadata records PX4 `3042f906`, speed
  factor, budget, strategy, checkpoint path, and validity automation settings.
- Per-eval checkpoint: `checkpoint.json` contains archive elites, eval count,
  Python search RNG state, results, progress records, theta/seed/ulog map, and
  validity records. Writes use same-directory temp file + fsync + atomic
  `os.replace`.
- Resume loads checkpoint state, rewrites derived JSONL/JSON files from
  checkpoint truth, restores RNG, and continues at the next eval.
- Single eval failures are converted to `EvalResult(returncode=1, error=...)`
  and recorded in progress/checkpoint; later evals continue.

## Strategies

- `guided` / `map-elites`: existing MAP-Elites parent selection, mutation, and
  optional crossover.
- `random`: same harness with parent selection disabled.
- `grid`: added. For `steady-wind-physics`, this was originally a pure-wind /
  pure-physics interleaving because the genome encoded one disturbance type per
  theta. That limitation was removed by `docs/genome_combined_steady_20260627.md`;
  the steady grid now samples combined wind+physics stress.

## Resume Evidence

Persistent mock runs in ignored `runs/campaigns/`:

- Full uninterrupted: `campaign_runner_full_mock_20260627`, budget 6.
- Interrupted/resumed: `campaign_runner_resume_mock_20260627`, first process
  stopped after checkpoint at eval 2 using `--max-evals-this-run 3`, then resumed
  to budget 6 from `checkpoint.json`.

Comparison script result:

```json
{
  "archive_signature_equal": true,
  "full_eval_count": 6,
  "genome_trace_equal": true,
  "resumed_eval_count": 6,
  "rng_state_equal": true
}
```

Checkpoint structure after resume:

```json
{
  "eval_count": 6,
  "completed": true,
  "has_rng": true,
  "theta_ulog_map_len": 6,
  "validity_records_len": 6,
  "progress_len": 6
}
```

Unit coverage additionally asserts the resumed guided run has the same genome
trace, archive signature, and final RNG state as the uninterrupted run.

## Guided + Random Real Gate Smoke

Both real smokes used the container entrypoint, N=1, speed 1.25, budget 1,
`--skip-build`, `--no-confirm`, subspace `steady-wind-physics`, target
`behavior`.

| run | strategy | result | best property | quality | gate evidence |
|---|---|---:|---|---:|---|
| `campaign_runner_guided_real_20260627` | guided | pass | P4 | 0.1993 | decontam passed both controllers; identity passed |
| `campaign_runner_random_real_20260627` | random | pass | P4 | 0.1570 | decontam passed both controllers; identity passed |

Real checkpoint evidence:

- guided identity: 232.24 Hz, 5998 exact output/actuator matches, 0.8804 match
  fraction, `raptor_input_present=false`.
- random identity: 230.54 Hz, 6106 exact output/actuator matches, 0.9076 match
  fraction, `raptor_input_present=false`.
- Both checkpoints include `(theta, seed) -> {classical,mcnn}.ulg` paths under
  `theta_ulog_map`.

## Matched Mock Baselines

Budget 3, same seed/subspace/target, mock evaluator:

| strategy | evals | best quality | archive bins | QD-score | source |
|---|---:|---:|---:|---:|---|
| guided | 3 | 1.2770 | 2 | 2.1622 | `bootstrap_random`, `elite_mutation` |
| random | 3 | 1.3066 | 1 | 1.3066 | `random_baseline` |
| grid | 3 | 0.8167 | 2 | 1.0448 | `grid_baseline` |

## Failure Tolerance Evidence

`tests/test_campaign_runner.py` injects a fake evaluator crash on eval 1.
Result: the run finishes 4/4 evals, records
`RuntimeError: forced evaluator crash` for eval 1, and evals 2-3 continue.

## Verification

- `python3 -m py_compile scripts/campaign_runner.py scripts/m2_map_elites.py scripts/validity_automation.py scripts/theta_genome.py scripts/property_fitness.py scripts/property_oracle.py tests/test_campaign_runner.py tests/test_property_fitness.py tests/test_theta_genome.py tests/test_validity_automation.py`
- `python3 -m unittest tests/test_campaign_runner.py tests/test_property_fitness.py tests/test_theta_genome.py tests/test_validity_automation.py` - 15 tests OK.
- `find scripts docker -maxdepth 2 -name '*.sh' -print0 | xargs -0 -n1 bash -n`
- `jq empty` on the campaign runner mock/real run JSON files under ignored
  `runs/campaigns/campaign_runner_*_20260627`.
- `git diff --check`
- `git diff --cached --check`
- Real guided/random smoke commands above completed with `error=null`.
