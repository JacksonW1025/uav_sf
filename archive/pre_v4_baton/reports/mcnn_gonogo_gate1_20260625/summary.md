# mc_nn_control GO/NO-GO GATE-1

gate: GATE-1
decision: PASS
px4_sha: 3042f906abaab7ab59ae838ad5a530a9ef3df9a6
board: px4_sitl_mcnn_sih
theta: /workspace/config/mcnn_gate1_hover.json
ulog: /workspace/docs/mcnn_gonogo_gate1_20260625/mcnn_gate1_hover.ulg
mode_id: 23
controller_safe: True
safe_reasons: []

## Evidence
- source module: external/PX4-Autopilot/src/modules/mc_nn_control
- docs state the embedded network is trained for X500 V2: external/PX4-Autopilot/docs/en/neural_networks/mc_neural_network_control.md
- enable flags: CONFIG_LIB_TFLM=y, CONFIG_MODULES_MC_NN_CONTROL=y
- build note: mcnn_sih also compiles mc_raptor/RLtools so the local M2b shim parameter definitions are generated; MC_RAPTOR_ENABLE remains false and RAPTOR is not started.
- switch path: MAV_CMD_DO_SET_MODE main=4/sub=11 -> nav_state 23
- console: /workspace/docs/mcnn_gonogo_gate1_20260625/mcnn_gate1_px4_console.log
- task json: /workspace/docs/mcnn_gonogo_gate1_20260625/mcnn_gate1_task.json
- metrics json: /workspace/docs/mcnn_gonogo_gate1_20260625/mcnn_gate1_metrics.json

## Gate Contract
Stopped at GATE-1. GATE-2 and GATE-3 were not run in this invocation.
