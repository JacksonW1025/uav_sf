# Data policy

This directory contains only compact, reviewable data products.

- `traces/`: schemas or small curated trace examples, never raw runtime trees.
- `processed/`: small derived summaries with a documented producer and source hash.

Raw ULogs, `.log` files, per-evaluation output, checkpoints, and ROS/PX4 build
trees belong outside the repository. P0 summaries record raw-artifact names,
sizes, and SHA-256 digests without tracking the raw files.

Do not use `git add -f` to maintain results under an ignored path.
