# Active script surface

The active surface is intentionally limited to:

- `setup/`: commit-locked dependency and Family A environment bootstrap;
- `behavior/`: control-interface-independent canonical behavior generation;
- `adapters/`: Offboard and Dynamic External Mode adapters;
- `tracing/`: route-event collection and writer/timestamp attribution;
- `probes/`: small, gated normal-flow probes;
- `analysis/`: compact route-summary analysis;
- `profiles/`: Family A runtime profiles;
- `validation/`: repository and evidence-contract checks.

The default bootstrap is `setup/bootstrap_family_a.sh`. It must not require any
asset under `family_b/`. The optional Family B entry point is
`setup/bootstrap_family_b.sh`, which layers future-case assets on a completed
Family A environment.

Reusable tracing code must record evidence source and timestamp domain; it must
not infer producer or writer identity from a mode label. Runtime output goes to
ignored `runs/`, while compact validated summaries may be promoted to
`data/processed/`.
