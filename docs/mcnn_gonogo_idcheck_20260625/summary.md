# mc_nn_control Controller-ID Check

gate: CONTROLLER-ID
decision: CONFIRMED_MC_NN_CONTROL
date: 2026-06-25
source_ulog: docs/mcnn_gonogo_gate1_20260625/mcnn_gate1_hover.ulg
console_log: docs/mcnn_gonogo_gate1_20260625/mcnn_gate1_px4_console.log

## Conclusion

GATE-1 mode 23 hover was controlled by `mc_nn_control`, not RAPTOR.

Positive evidence:
- Console command at line 164 starts `mc_nn_control`; line 167 reports `NeuralControl mode registration successful ... mode_id: 23`.
- Console `mc_nn_control status` at lines 199 and 339 reports registered mode id 23.
- Commander status at lines 206 and 224 maps External Mode 1 / nav_state 23 to name `Neural Control`.
- ULOG has `neural_control` with 14207 samples. In the active mission window, 6837 `neural_control` samples were logged at about 228 Hz.
- ULOG `neural_control` starts at 30412000 us, after nav_state 23 becomes active at 29760000 us, and continues through the run.
- `neural_control.network_output` has finite, varying values, and a large exact-timestamp subset of `actuator_motors.control[0..3]` matches it exactly: 6452 exact zero-diff samples in the active mission window.
- `raptor_input` is absent from the ULOG topic list: 0 samples, topic not present.
- Console search for `mc_raptor` or `raptor` has no matches.

## Notes

`actuator_motors` contains extra samples that are not one-to-one with `neural_control`, so the alignment check is not interpreted as "every actuator_motors row is a neural_control row." The exact-match subset is sufficient to prove that `mc_nn_control` was actively publishing motor commands during nav_state 23.

No rerun was needed. No GATE-3 or attack evaluation was run.
