# Historical ignored research artifacts (needs review)

Original path: ignored/untracked files under `docs/`, `runs/`, and historical evaluation directories.

Observed files: raw ULogs and logs, per-evaluation JSON, campaign/runtime output, and build/probe artifacts retained locally under the repository's prior ignore policy.

Probable purpose: multiple historical campaigns and diagnostics predating the BATON classification.

Related commits: source commits vary and are often unknown; externalization manifests were added during the BATON reorganization.

Why classification is uncertain: many paths predate canonical experiment metadata, and assigning every per-evaluation file from its name would violate the evidence discipline.

Needs review: use `data/manifests/HISTORICAL_IGNORED_FILE_MANIFEST.tsv` and `data/manifests/HISTORICAL_IGNORED_NESTED_CACHE_MANIFEST.tsv` to map individual original paths to the appropriate experiment when report/provenance evidence is available.
