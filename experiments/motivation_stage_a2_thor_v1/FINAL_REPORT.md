# Stage A2 primary execution report

Status: **MEASUREMENT_INSUFFICIENT**. This primary ledger is closed and will
not be extended or rewritten.

The study consumed 51 formal launches: 18 `ACCEPTED`, 31
`OBSERVABILITY_REJECTED`, and two `INCONCLUSIVE`. Dynamic stall reached its
8/8 target. Dynamic normal reached 4/5, Offboard stall 6/8, and Offboard normal
0/5 before their launch caps. Both inconclusive attempts missed the frozen
nominal physical-coverage contract and were correctly excluded.

The 31 observability rejections share a processing signature: an early
command-consumption record can carry a subject timestamp outside the fitted
clock bridge's validity interval. The closer filters downstream records with
unbound subjects but did not apply the same fail-closed filter to the consumed
command itself. This is an experiment-infrastructure defect, not a PX4 result.

The primary ledger, compact evidence, and denominator remain immutable. Its
accepted traces may be described, but it cannot close Stage A2 or support a
matched mechanism comparison. A separately preregistered remediation may fix
only the trace-closure contract and rerun a new matrix under a new image,
environment, ledger, seeds, and denominator.
