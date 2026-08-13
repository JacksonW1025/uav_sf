# Qualification evidence

Qualification used the final image and separate study ID
`thor-remediation-qualification-v3`. Neither run is a formal attempt.

| Scenario | Runtime | Gate | Oracle | Clock uncertainty | Central RTF | ULog observations |
| --- | --- | --- | --- | ---: | ---: | ---: |
| executor request before completion | `ACCEPTED` | `ADMISSIBLE` | `PASS` | 0.320 ms | 0.999471 | 895 |
| public RTL to Offboard re-entry | `ACCEPTED` | `ADMISSIBLE` | `PASS` | 1.924 ms | 0.999520 | 1161 |

Both ULogs passed file integrity, dropout, and RouteObservability sequence-gap
checks. The re-entry trace contained exactly two qualifying RTL-to-Offboard
requests and two distinct complete route identities.

Earlier non-formal checks were deliberately not accepted as a basis for the
matrix. One mixed Hold/RTL sequence provided only one qualifying RTL re-entry.
A later fixture attempt exposed a takeoff command sent before armed state and
timed out. The final fixture first observes armed state, then uses repeatable
public takeoff and RTL requests. No threshold or Oracle was changed in response.
