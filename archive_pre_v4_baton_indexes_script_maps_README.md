# Script Classification

Legacy script paths remain stable because reports, container commands, imports, and campaign provenance refer to them directly. This file is the canonical classification; category subdirectories contain maps, not relocated implementations.

- `runners/`: experiment/campaign launchers and PX4 build/install entry points.
- `analysis/`: log readers, metrics, reanalysis, and figure/table generation.
- `monitors/`: property oracles, fitness, validity, and contract checks.
- `diagnostics/`: writer attribution, causality, mechanism, and state-shim investigations.
- `utilities/`: provenance, genome, setup, and general helpers.

Harness-sensitive runners must select `legacy` or `hardened` explicitly where supported. No criterion or core control algorithm is changed by this organization layer.
