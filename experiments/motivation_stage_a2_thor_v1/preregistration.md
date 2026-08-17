# Stage A2 preregistration

This study is the moving-workload realism bridge in paper Section 6,
Motivation Study. It does not evaluate the state-aware generation method in
Section 7 and it changes no Stage A1 result or denominator.

The locked task is public Takeoff, sustained physical readiness, activation of
the tested external route, constant-altitude position-only straight-line
translation, normal completion or healthy setpoint-stream stall, and public
Land. Legacy Offboard and Dynamic External Mode share the task, schedule,
observer, simulation seed within each matched block, successor, and physical
analysis plan.

The four formal cells are the two mechanisms crossed with normal and
`SETPOINT_STALL_HEALTHY`. Normal cells target five accepted traces and cap ten
launches. Fault cells target eight accepted traces and cap sixteen launches.
Every launch enters the append-only ledger. Invalid physical execution,
observability rejection, timeout, environment failure, or safety stop consumes
the cap but does not enter a matched estimate.

An admissible A2 attempt requires local position, at least 0.5 m takeoff held
for 0.5 s, at least 0.75 m observed along-track progress before the logical
injection phase, and at least 2.5 m profile coverage in nominal arms. The
selected transition observer is approximately 125 Hz. The safety supervisor is
independent; intervention is retained as `FORMAL_SAFETY_STOP`, a censored
physical endpoint, never Oracle PASS.

The primary physical outputs are along-track lag, cross-track error, integrated
absolute along-track error, exposure duration and distance, peak horizontal
speed, and recovery distance. Results are bounded to the attested Thor SITL
environment. A null result is retained. Neither a contract violation nor a
simulated displacement is promoted to a PX4 bug or real-flight risk without
separate evidence.
