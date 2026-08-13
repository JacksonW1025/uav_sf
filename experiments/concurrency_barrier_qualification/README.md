# Thor two-phase barrier qualification

This is a non-formal execution qualification. It contributes no attempt to a
Motivation Study ledger and no SUT result to an empirical denominator. It
tests whether live PX4/Gazebo/ROS workloads can finish as one isolated batch
before any ULog, clock-bridge, Evidence Gate, or Oracle processing starts.

The project-layer image was rebuilt from the attested full Thor image:

- image: `uav-sf-family-a-thor:barrier-a5c6584`;
- image ID:
  `sha256:bc0fd71cd4fe87bf746c2700a6a81cfc70e12efd021cc2d64f4e9d06cd81d092`;
- repository revision: `a5c6584651c702ea778a7e17cd82006c56caf4d5`;
- PX4 binary:
  `sha256:168c9a3d2e05d07a54d01f420d7a47dc58977eec0ece544c8c454e4f0c6bf619`;
- ignored attestation: `runs/thor-barrier-a5c6584-attestation.json`;
- attestation SHA-256:
  `929b0edca55352611afd6c2d57a29f7de08e3bfab935555a430c4d1bfebb4574`.

The frozen checks required every live container to stop before processing,
100 percent admissible evidence, complete ULogs without gap or dropout, clock
uncertainty at or below 20 ms, central Gazebo real-time factor at or above
0.97, and no isolation or cleanup failure. The pre-existing requirement that
parallelism not change matched baseline Oracle interpretation also applies.

Four-way regression used the historical CPU sets `0-2`, `3-5`, `6-8`, and
`9-13`, with 24 GiB per attempt. Five-way qualification used five disjoint
two-core sets `0-1` through `8-9`, retained CPUs `10-13` for the host, and
limited each attempt to 16 GiB. The four matched cells used identical
qualification seeds; five-way added one attitude-Offboard cell.

Both batches passed the basic admissibility and performance checks. Five-way
was not promoted because its maximum clock uncertainty increased from 5.505
ms to 15.068 ms and the matched Dynamic cell changed from a Freshness
`VIOLATION` at four-way to `PASS` at five-way. A single batch cannot establish
that this correctness-sensitive difference is independent of resource
contention. Since four-way is sufficient, the formal default remains four and
no new six-way test was run.

Raw qualification evidence and full batch summaries remain ignored under:

- `runs/thor-barrier-concurrency4-q1/`;
- `runs/thor-barrier-concurrency5-q1/`.

The compact result and exact reusable specs are tracked in this directory.

