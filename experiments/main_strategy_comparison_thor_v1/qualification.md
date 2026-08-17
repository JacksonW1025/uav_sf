# Live strategy backend qualification

Status: **PASS**. These six attempts are non-formal qualification flights and
are excluded from the fixed 18-launch formal denominator.

The exact candidate image was exercised in two three-way concurrency batches:
one Legacy Offboard batch and one Dynamic External Mode batch. Each batch ran
the official sequence, bounded random timing, and state-aware strategy against
the same moving healthy-setpoint-stall action. Offline processing began only
after all three live containers in a batch had stopped.

All 6/6 attempts were runtime `ACCEPTED`, Evidence Gate `ADMISSIBLE`, ULog
integrity `PASS`, and physical-execution `PASS`. Each attempt retained one
strategy decision, one state-conditioned action request, one owned-process
stall marker, and one observed `fault_detected` event. All six Oracle results
were admissible `VIOLATION` evidence, as expected for the deliberately stopped
setpoint stream.

| Mechanism | Strategy | Selected boundary | Planned offset (s) | Request error (ms) |
|---|---|---:|---:|---:|
| Legacy Offboard | official sequence | boundary | 5.000 | 14.650 |
| Legacy Offboard | bounded random timing | boundary | 4.756 | 10.085 |
| Legacy Offboard | state-aware | boundary | 5.000 | 13.026 |
| Dynamic External Mode | official sequence | boundary | 5.000 | 7.167 |
| Dynamic External Mode | bounded random timing | pre-boundary | 4.241 | 9.335 |
| Dynamic External Mode | state-aware | boundary | 5.000 | 2.924 |

Every action request recorded `route_active=true` and `motion_entered=true`.
The observed absolute request error range was 2.924--14.650 ms. The minimum
central real-time factor in each attempt exceeded 0.9987, and the maximum clock
bridge uncertainty was 4.683 ms, below the frozen 20 ms limit.

Qualified image:
`sha256:0900076eea14aecfbe446d2adc6458f5eec80f4feb3cf564b388d92bf7e8eee5`.
Qualified revision: `ea2381c8cecfe2b885a92a68b5c803481da3e6e2`.
The frozen specs and compact batch results are retained beside this report;
raw qualification inputs remain under `runs/main-strategy-*-qualification-v1/`.

This qualification establishes backend executability, live-state gating,
timing accuracy, evidence completeness, and three-way concurrent feasibility.
It does not compare strategy effectiveness and does not generalize beyond the
one moving setpoint-stall action.
