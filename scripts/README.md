# Script inventory

Only the scripts listed as active below are current entry points. Historical BATON campaign code is under `archive/pre_v4_baton/scripts/` and indexed in `archive/pre_v4_baton/indexes/SCRIPT_INVENTORY.tsv`.

| script | category | active_or_legacy | supported_family | purpose | inputs | outputs | dependencies | canonical_entrypoint | replacement | status |
|---|---|---|---|---|---|---|---|---|---|---|
| `setup/clone_px4.sh` | setup | active | A+B | clone/pin PX4 and required submodules | PX4 env overrides | ignored setup log and source tree | git | yes | — | supported |
| `setup/setup_ros2_ws.sh` | setup | active | A | initialize/build px4_msgs workspace | ROS/PX4 env overrides | ignored ROS workspace/build log | ROS 2, colcon, git | yes | — | supported |
| `setup/build_microxrce_agent.sh` | setup | active | A | clone/build Micro XRCE-DDS Agent | agent env overrides | ignored build tree/log | cmake, git | yes | — | supported |
| `setup/install_m1_sih_x500.sh` | setup | active | B | install tracked SIH airframe overlay | `PX4_DIR` | PX4 working-tree overlay | POSIX shell | no | — | supported |
| `setup/install_mcnn_sih_board.sh` | setup | active | B | install mc_nn board overlay | `PX4_DIR` | PX4 board file | POSIX shell | no | — | supported |
| `setup/install_raptor_sih_board.sh` | setup | active | B | install RAPTOR board overlay | `PX4_DIR` | PX4 board file | POSIX shell | no | — | supported |
| `setup/install_m2b_state_shim.sh` | setup | active | B | apply tracked state-shim patch idempotently | `PX4_DIR` | patched PX4 source | git apply | no | — | supported |
| `setup/build_px4_mcnn_sih.sh` | setup | active | B | canonical mc_nn SIH build | PX4 env overrides | ignored PX4 build/log | PX4 toolchain | yes | — | supported |
| `setup/build_px4_raptor_sih.sh` | setup | active | B | canonical RAPTOR SIH build | PX4 env overrides | ignored PX4 build/log | PX4 toolchain | yes | — | supported |
| `tracing/install_dds_groundtruth.sh` | tracing | active | A+B | install reproducible DDS ground-truth topic overlay | `PX4_DIR` | patched DDS topic YAML | awk, install | no | — | supported |
| `tracing/m0_ulog_sanity.py` | tracing | active | A+B | inspect basic ULog integrity | ULog path | console summary | pyulog, numpy | no | — | supported |
| `tracing/px4_actuator_attribution_audit.py` | tracing | active | A+B | attribute actuator-path evidence | ULog/trace arguments | structured audit output | pyulog, numpy | no | — | provisional for route model |
| `probes/m1_offboard_task.py` | probe | active | A+B | reusable ROS 2 Offboard workload/trace producer | theta/profile arguments | runtime task JSON | ROS 2, px4_msgs | no | — | legacy-compatible reusable surface |
| `probes/m1_diff_runner.py` | probe | active | B | minimal classical↔RAPTOR reproduction/replay | theta and safety config | ignored run tree | PX4 SITL, ROS 2 | yes (Family B only) | — | legacy evidence; revalidate before cross-family use |
| `analysis/m1_metrics.py` | analysis | active | B | compute compact ULog metrics | ULog, theta, safety config | JSON metrics | pyulog, numpy | no | — | legacy-compatible |
| `analysis/m1_compare.py` | analysis | active | B | compare compact classical/learned results | metrics JSON | comparison JSON | numpy, property modules | no | — | legacy-compatible |
| `analysis/property_oracle.py` | analysis | active | B | evaluate retained P1–P7 oracle | ULog and thresholds | property result | pyulog, numpy | no | route oracle not yet implemented | legacy-compatible |
| `analysis/property_fitness.py` | analysis | active | B | score retained differential properties | property results | score/findings | Python | no | route fitness not yet implemented | legacy-compatible |
| `analysis/validity_automation.py` | analysis | active | B | shared decontamination, identity, and jitter gates | ULog/result structures | validity decisions | Python, numpy | no | route validity gates not yet implemented | legacy-compatible |
| `validation/check_markdown_links.py` | validation | active | A+B | check active local Markdown links | tracked Markdown | pass/fail report | Python, git | no | — | supported |
| `validation/validate_repo.sh` | validation | active | A+B | run all repository hygiene checks | repository snapshot | pass/fail report | bash, Python, jq, PyYAML, pytest | yes | — | supported |

Rules for active scripts:

- Shell scripts use `set -euo pipefail`.
- Paths derive from the repository location or explicit environment/CLI parameters; no username or machine-local mount is embedded.
- Runtime output defaults to ignored `runs/` or tool-specific build trees.
- PX4 source modifications are installed from tracked patches/boards/config, never preserved only in `external/PX4-Autopilot`.
- The old property oracle is retained for Family B compatibility and is not the route-transition oracle.
