# Pre-V4 BATON archive

Archived: 2026-07-16
Protection tag: `pre-route-transition-cleanup-20260716`
Checkpoint commit: `4413088a9c1165af2ef6f38e08dfb87720804f63`

## Original scope

This archive contains the research line that preceded **Testing Route-Replacing Authority Transitions in PX4**: BATON narratives and S1–S4 planning, classical↔mc_nn differential campaigns, RAPTOR campaigns and unclipped ablation, F1/F2/F2a activation/severity work, wave1/wave2 and multi-policy experiments, wall-clock boundary/search work, route-A anchor and tier-0.5 studies, mechanism/delivered-state audits, article figures, and the associated scripts/configuration/tests.

The archived reports contain their original result status and caveats. Archival does not strengthen those claims. Compact campaign summaries and verdict/provenance records remain in Git; per-evaluation/runtime data was externalized.

## Value for V4 Family B

The following remain useful historical evidence for the representative deep-route family:

- reproducible mc_nn/RAPTOR/classical board, patch, task, metric, and differential structure;
- evidence that controller and writer attribution require data-plane observation beyond declared mode;
- completed activation, severity, fallback, delivered-state, mechanism, and race-causality audits;
- retained compact summaries, candidate records, frozen rules, and provenance for prior campaigns.

These materials may motivate route fields and probes. They are **not** direct evidence for Family A and are **not** part of the current Motivation Study by default.

## Must be revalidated

Before any archived result is used as a current cross-family claim, rerun or re-evaluate it with:

- the V4 runtime route tuple and explicit registration/authority/producer/writer evidence;
- a justified timestamp-domain mapping for revocation, installation, overlap, and gap;
- a complete fallback-route installation check;
- clean, reproducible PX4 patches/overlays from a known source revision;
- current official handoff-flow and coverage evidence.

The old trajectory/property oracle is retained for Family B compatibility but is not the V4 route-transition oracle.

## Layout

```text
archive/pre_v4_baton/
├── narratives/   # V5 and the prior project context
├── experiments/  # compact campaign summaries, tier-0.5 verdicts, old workspace/tests
├── reports/      # completed reports and structured report attachments
├── configs/      # old campaign configs and ablation-only overlays
├── scripts/      # old campaign runners, analyses, plots, and utilities
├── figures/      # prior article/analysis figures
└── indexes/      # old indexes plus cleanup mappings/inventories
```

## Original-to-archive mapping

| Original path | Archive path / action |
|---|---|
| `docs/NEW_NARRATIVE_v5.md` | `narratives/NEW_NARRATIVE_v5.md` (recovered from the pre-checkpoint commit) |
| `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md` | `narratives/PROJECT_NARRATIVE_CONTEXT_v8 (1).md` |
| other pre-V4 `docs/**` | `reports/**` preserving the path below `docs/` |
| `docs/indexes/**` | `indexes/**` |
| old `experiments/**` | `experiments/workspace/**` |
| retained `runs/campaigns/<id>` summaries | `experiments/campaign_summaries/<id>/**` |
| retained tier-0.5 rules/verdicts/provenance | `experiments/tier05_fork_20260712T090728Z/**` |
| old `config/**` | `configs/config/**`; only the minimal active Family B files returned to `config/` |
| old campaign `scripts/**` | `scripts/**` |
| old campaign tests | `experiments/tests/**` |
| `img/**` | `figures/**` |
| unclipped board/patch | `configs/boards/**`, `configs/patches/**` |
| raw runtime/checkpoint/per-eval trees | external archive; see `data/manifests/PRE_V4_EXTERNAL_ARCHIVE.tsv` |

Exact script dispositions are in `indexes/SCRIPT_INVENTORY.tsv`; removal groups and reasons are in `indexes/DELETION_INDEX.tsv`.
