# Control-authority Contract Model

| Clause | Required property | Current evidence | Status |
|---|---|---|---|
| Admission | Preconditions and every consumed reply field are valid before activation. | Incomplete reply initialization and weak/uneven guards are present in code. | `mechanism_observed` |
| Handover | The selected controller is active; the previous actuator writer has stopped; ownership/configuration is fresh and observable. | Allocation config becomes stale, allocator remains active, and `actuator_motors` is dual-written. | `mechanism_observed` |
| Residual | Persistent state has an explicit reset/preserve/transfer policy. | Classical integrator persistence and RAPTOR activation reset differ; physical consequence is untested. | `planned` |
| Fallback | Commanded and failsafe exits restore authority through a defined safe path. | Scenario and oracle design exist; physical experiments are incomplete. | `planned` |

Status terms are evidence grades, not severity labels. A code-level mechanism can be observed without its physical consequence being confirmed.
