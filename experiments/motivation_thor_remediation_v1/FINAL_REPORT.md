# Thor supplemental study final report

## Decision

The preregistered supplemental study is `COMPLETE`. Both cells reached 10
accepted evidence sets after 10 launches, so no rejected launch or unused cap
was silently replaced. This result is separate from and does not modify the
primary study.

## Accounting and evidence quality

- formal launches: 20; accepted: 20; all other outcomes: 0;
- ledger events: 60; chain head:
  `8d2ef402c62a7fb750850374783d57fc563d1f3a31cf16ec66a270bf42b3d2c7`;
- Evidence Gate: 20 `ADMISSIBLE`;
- ULog integrity: 20/20 pass, with no dropout, sequence gap, or file-corruption
  indication;
- clock uncertainty: minimum 0.555 ms, median 1.373 ms, maximum 4.385 ms;
- central Gazebo real-time factor: minimum 0.998548, median 0.998952;
- RouteObservability records per ULog: minimum 881, median 1023.5, maximum
  1170.

Performance and evidence-quality values do not determine correctness except at
their preregistered admissibility bounds.

## Executor request before completion

All 10 traces were admissible. In every trace the adjacent Land request arrived
within the frozen 7.65--7.85 s post-activation interval, legitimately preempted
completion, and produced a complete Land successor. Thus a missing completion
event was not manufactured and was not treated as missing evidence.

Nine traces passed every applicable Oracle clause. One trace retained a real
Freshness violation: command age reached 352.058 ms against the frozen 200 ms
bound. Its timing/order and Land-successor clauses still passed. The violation
is retained as independent detection value rather than removed by changing a
threshold.

## RTL re-entry

All 10 traces passed every applicable Oracle clause. Each trace established RTL
through public arm, takeoff, and RTL requests, then produced exactly two
RTL-to-Offboard requests. Each request had a complete installation and the two
route epochs and activation IDs were distinct. The fixture never modified PX4
internal state.

## Combined interpretation

The primary study remains `MEASUREMENT_INSUFFICIENT` under its original matrix
and caps. This supplemental study closes the two invalid-plan obligations with
new preregistered Thor evidence. Together they complete the currently declared
Family A motivation scope without changing a primary attempt, threshold,
Oracle, denominator, or result.

The bounded findings remain: declared mode and terminal outcome do not prove a
complete authority handoff; Route, Freshness, and Successor checks expose
different failures; and the attested Thor container can produce admissible
evidence under isolated parallel execution. Later state-aware experiments may
use this environment and runtime, but require their own matrix, seeds, and
preregistration.
