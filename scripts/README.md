# Active script surface

The active surface is intentionally limited to:

- `setup/`: commit-locked dependency and Family A environment bootstrap;
- `behavior/`: control-interface-independent canonical behavior generation;
- `adapters/`: Offboard and Dynamic External Mode adapters;
- `tracing/`: route-event collection and writer/timestamp attribution;
- `probes/`: small, gated normal-flow probes;
- `analysis/`: compact route-summary analysis;
- `profiles/`: Family A runtime profiles;
- `fuzzer_v0/family_a/`: V0-P static planning, preflight, compact evidence,
  safety, cleanup, residual-process, and port contracts;
- `validation/`: repository and evidence-contract checks.

The default bootstrap is `setup/bootstrap_family_a.sh`. It must not require any
asset under `family_b/`. The optional Family B entry point is
`setup/bootstrap_family_b.sh`, which layers future-case assets on a completed
Family A environment.

Reusable tracing code must record evidence source and timestamp domain; it must
not infer producer or writer identity from a mode label. Runtime output goes to
ignored `runs/`, while compact validated summaries may be promoted to
`data/processed/`.

`probes/run_p0_scenario.sh` is the single normal-flow P0 entry point. It joins
producer JSONL and structured External Mode/Executor lifecycle records with
the patched ULog through `tracing/route_trace_collector.py`; the analysis step
keeps ROS nanoseconds and ULog microseconds in separate domains and records raw
artifact hashes.

`fuzzer_v0/family_a/run_v0p_qualification.py` is the unique V0-P
qualification entry. The current repository permits only its static `plan`
and `preflight` paths. `execute` remains refused by the unchanged independent
DECLINE decision, and comparison strategies are not reachable from this
runner.
