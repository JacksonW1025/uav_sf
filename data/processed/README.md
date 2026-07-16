# Processed data

Store only compact, reproducible summaries here. Each addition must identify
its source data, producer command/version, timestamp domain, and source
SHA-256. Historical summaries remain recoverable through the protected tag in
`docs/repository/LEGACY_RECOVERY.md` and are not current evidence.

`p0/` contains canonical JSONL traces and summaries for the three gated
normal-flow baselines. Each summary carries source-artifact hashes; ULogs and
process logs remain under ignored `runs/`.
