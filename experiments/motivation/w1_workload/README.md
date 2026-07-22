# W1 real-workload runtime/trace spike

This directory freezes and records a bounded SITL study of Aerostack2 runtime
consistency, lifecycle transition, route conformance, trace acquisition, and
deterministic replay. It uses public flight-control interfaces and
observation-only instrumentation.

The preregistration commit must be present on `origin/main` before a formal
runtime attempt. Any W1 implementation added after that freeze must be
hash-locked in `source_lock.yaml` and pushed in a non-semantic checkpoint before
formal use. Such a checkpoint cannot change the frozen question, mission,
attempt caps, acceptance criteria, safety bounds, route classification, Native
Adapter Gate, or final dispositions.

Raw rosbag, ULog, build output, environment snapshots, and large logs belong in
the ignored `runs/motivation/w1_workload/` tree. Only compact processed evidence,
hashes, manifests, the append-only attempt ledger, report, and Gate may be
tracked.

The exact next phase after W1 is B1, but W1 does not start B1 and does not
authorize a random campaign or full Stateful Testing.
