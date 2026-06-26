# mc_nn_control GO/NO-GO

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
- task json: /workspace/docs/mcnn_gonogo_gate1_20260625/mcnn_gate1_task.json
- metrics json: /workspace/docs/mcnn_gonogo_gate1_20260625/mcnn_gate1_metrics.json
- raw console/task logs and ULOGs are local ignored evidence, not tracked artifacts

## Gate Contract
Stopped at GATE-1. GATE-2 and GATE-3 were not run in this invocation.

## 2026-06-25 Continuation

### Segment A: safe push

status: COMPLETE
remote: origin/main
push_range: d0da939..32ea65a
backup_path: /mnt/nvme/px4_work/uav_sf_ulog_backup

The three unpushed local commits were rewritten only in the unpushed range and pushed:
- adb7d68 Add M2b diagnostics and artifacts
- 84d8bd5 Add RAPTOR closeout artifacts
- 32ea65a Add mc_nn_control GATE-1 bringup

ULOG handling:
- `*.ulg` is ignored and HEAD tracks zero ULOG files.
- Local workspace ULOG files may remain on disk as ignored evidence, including `docs/mcnn_gonogo_gate1_20260625/mcnn_gate1_hover.ulg`.
- Old ULOG blobs may remain in Git history unless a separate full-history rewrite is performed. New commits should not add ULOGs.

### Segment B: controller ID

status: PASS
report: docs/mcnn_gonogo_idcheck_20260625/summary.md

GATE-1 hover is positively identified as `mc_nn_control`: `neural_control` is active in mode 23, it publishes motor-command values matching `actuator_motors` for a large exact-timestamp subset, and `raptor_input` is absent from the ULOG.

### Segment C: GATE-2

status: COMPLETE
report: docs/mcnn_gonogo_gate2_20260625.md

Source review found no observation/error magnitude clipping in `mc_nn_control`. The 0.495 m GATE-1 maximum tracking error is not a source-level 0.5 m clamp. No GATE-3 or exploit evaluation was run.
