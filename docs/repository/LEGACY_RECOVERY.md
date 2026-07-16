# Legacy research recovery

The complete pre-route-transition repository state is preserved by Git. It is
not duplicated in the current `main` tree.

- Protected tag: `pre-route-transition-cleanup-20260716`
- Cleanup checkpoint commit: `441308827893809cf7bd0b7fff10adf85f8b7938`
- Pre-V4 archive commit: `db6bc99174e8b6e4f671a08e2f58771eb2e3b358`

Inspect a historical file without changing the working tree:

```bash
git show pre-route-transition-cleanup-20260716:path/to/file
git ls-tree -r --name-only db6bc99174e8b6e4f671a08e2f58771eb2e3b358 archive/pre_v4_baton
```

Create a separate recovery worktree if executable access is needed:

```bash
git worktree add ../uav_sf_legacy pre-route-transition-cleanup-20260716
```

The protected history contains the former BATON narratives, mc_nn and RAPTOR
campaigns, F1/F2-era reports, experiment summaries, figures, configurations,
and analysis/search scripts. Those results were produced under different
questions, interfaces, dependency states, and evidence contracts. They must
not be cited as evidence for the current Family A route-transition narrative
without a new route-aware reproduction and explicit provenance.
