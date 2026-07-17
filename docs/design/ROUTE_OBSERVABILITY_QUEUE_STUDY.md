# RouteObservability uORB queue study

Date: 2026-07-17. Locked PX4: `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`.

## Method

Five independent TRANSITION-profile builds used queue lengths 1, 4, 8, 16,
and 32. Each generated uORB header was checked against the requested value.
Each build then ran three identical 8 s Offboard hovers with the same simulator,
logger configuration, observation publishers, and flight runner. No shell
diagnostic command ran during the measured flights. The complete 15-row record
is [queue_benchmark.tsv](../../data/processed/phase_a2/queue_benchmark.tsv).

The locked `uorb top` implementation does not expose a per-subscription lost
message counter. Publisher-local `sequence` is therefore the authoritative
uORB-overwrite counter. ULog's dropout records independently measure logger
write failures; all 15 runs reported zero.

## Results

| queue | repeats with complete global/critical coverage | missing final-writer events | logger write dropouts | mean CPU-load range |
|---:|---:|---:|---:|---:|
| 1 | 0/3 | 13–19 | 0 | 0.266–0.267 |
| 4 | 3/3 | 0 | 0 | 0.265–0.267 |
| 8 | 3/3 | 0 | 0 | 0.266–0.267 |
| 16 | 3/3 | 0 | 0 | 0.269–0.272 |
| 32 | 3/3 | 0 | 0 | 0.265–0.268 |

At q1, allocator and final-writer streams both contain isolated single-sequence
holes while ULog reports no write dropout. This confirms overwrite between the
high-rate publisher and logger subscriber, rather than storage failure. All
larger queues remove those holes under the same workload.

## Decision

`ORB_QUEUE_LENGTH = 4` is the smallest queue for which all three runs have:

- zero target critical-window sequence gaps;
- 100% critical-window coverage;
- 100% global publisher-sequence coverage; and
- zero logger write dropouts.

The canonical observation patch therefore uses q4. q8/q16/q32 are positive
controls, not evidence that a larger queue is necessary.
