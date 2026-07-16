# Differential Diagnosis

| Differential | Comparison | Primary use |
|---|---|---|
| behavior | hold original controller vs execute switch | Does the transition add risk? |
| controller | Classical→mc_nn vs Classical→RAPTOR | Is the consequence controller-selective? |
| mechanism | original PX4 vs repaired PX4 | Does the implicated handover mechanism cause the consequence? |
| trigger | commanded vs failsafe | Does entry/exit trigger alter the path? |
| history | one switch vs repeated switches; preserve vs reset | Does residual state accumulate or contaminate later control? |
| harness | wall-clock vs sim-time/lockstep | Is the observation a test-time artifact? |

Selection rule: begin with behavior differential, then choose only the differential that isolates the clause implicated by code/trace evidence. Do not infer physical causality from a code difference alone.
