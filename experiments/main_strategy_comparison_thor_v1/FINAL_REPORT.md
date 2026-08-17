# Fixed-budget live strategy comparison

Status: **COMPLETE WITH BOUNDED CLAIMS**.

The formal denominator closed at 18/18 launches, with 18 accepted, 18 Evidence Gate admissible, 18 physically valid, and 18 state-conditioned action requests. All 18 Oracle outcomes were `VIOLATION`, and every violation had the same `freshness_lineage:freshness` signature.

| Mechanism | Strategy | Accepted | Timing boundaries | Violation signatures | Median request error (ms) |
|---|---|---:|---:|---:|---:|
| Dynamic External Mode | official sequence | 3/3 | 1 | 1 | 11.430 |
| Dynamic External Mode | bounded random timing | 3/3 | 3 | 1 | 15.101 |
| Dynamic External Mode | state-aware | 3/3 | 3 | 1 | 16.378 |
| Legacy Offboard | official sequence | 3/3 | 1 | 1 | 10.872 |
| Legacy Offboard | bounded random timing | 3/3 | 3 | 1 | 7.147 |
| Legacy Offboard | state-aware | 3/3 | 3 | 1 | 11.299 |

Across both mechanisms, official sequence exercised one timing bin (`boundary`). Bounded random timing exercised three (`pre_boundary`, `post_boundary`, and `late`), while state-aware exercised three (`pre_boundary`, `boundary`, and `post_boundary`). Each strategy reached the first admissible violation on its first launch. All cells evaluated the same 16 applicable contract clauses.

The state-aware feedback loop is operational: its second and third decisions in each mechanism consume only prior live `action_requested` coverage and choose previously uncovered bins. In this fixed sample, however, bounded random timing also reached three bins. The study therefore supports backend executability and a coverage increase over the fixed official sequence, but not a ranking between bounded random timing and state-aware search.

This is a Section 7 Main Evaluation vertical slice for one moving healthy setpoint-stall action. It does not complete the route corpus, establish general search effectiveness, diagnose a PX4 bug, quantify real-flight risk, or rank the two control mechanisms.
