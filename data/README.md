# Data policy

This directory contains only compact, reviewable data products.

- `manifests/`: aggregate external-data provenance. Full per-file inventories stay outside Git.
- `traces/`: schemas or small curated trace examples, never raw runtime trees.
- `processed/`: small derived summaries with a documented producer and source hash.

Raw ULogs, `.log` files, per-evaluation output, checkpoints, ROS/PX4 build trees, and large traces belong outside the repository. The default archive root for the pre-V4 cleanup is recorded in `manifests/PRE_V4_EXTERNAL_ARCHIVE.tsv`.

Do not use `git add -f` to maintain results under an ignored path.
