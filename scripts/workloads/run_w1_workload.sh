#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="${W1_RUN_ID:?W1_RUN_ID is required}"
PHASE="${W1_PHASE:?W1_PHASE is required}"
SIMULATION_SEED="${W1_SIMULATION_SEED:?W1_SIMULATION_SEED is required}"
[[ "${PHASE}" =~ ^(W1-B|W1-D)$ ]] || { echo "W1_PHASE must be W1-B or W1-D" >&2; exit 2; }
[[ "${SIMULATION_SEED}" =~ ^[0-9]+$ ]] || { echo "invalid W1 simulation seed" >&2; exit 2; }

set +u
source /opt/ros/humble/setup.bash
source "${REPO_ROOT}/ros2_ws_humble_live/install/setup.bash"
source "${REPO_ROOT}/ros2_ws_aerostack2/install/setup.bash"
set -u

PX4_DIR="${W1_PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot-oracle-validation-control}"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
AGENT_BUILD="${W1_AGENT_BUILD:-${REPO_ROOT}/runs/freshness_agent_build}"
AGENT_BIN="${AGENT_BUILD}/MicroXRCEAgent"
AGENT_LIBRARY_PATH="${AGENT_BUILD}:${AGENT_BUILD}/temp_install/fastrtps-2.14/lib:${AGENT_BUILD}/temp_install/fastcdr-2.2.0/lib:${AGENT_BUILD}/temp_install/microxrcedds_client-2.4.3/lib"
RAW_DIR="${W1_RAW_ROOT:-${REPO_ROOT}/runs/motivation/w1_workload/${RUN_ID}/raw}"
PROCESSED_DIR="${RAW_DIR}/processed"
LOGGER_TOPICS_FILE="${REPO_ROOT}/config/freshness_logger_topics.txt"
LOGGER_TOPICS_TARGET="${PX4_BUILD}/rootfs/0/etc/logging/logger_topics.txt"
RUNTIME_CONFIG="${REPO_ROOT}/config/w1_aerostack2_runtime.yaml"
PID_CONFIG="${REPO_ROOT}/config/w1_pid_speed_controller.yaml"
ROSBAG_TOPICS="${REPO_ROOT}/config/w1_rosbag_topics.txt"
MANIFEST="${W1_TRACE_MANIFEST:-${REPO_ROOT}/experiments/motivation/w1_workload/trace_manifest.json}"

[[ -x "${PX4_BUILD}/bin/px4" ]] || { echo "locked W1 PX4 binary is unavailable" >&2; exit 4; }
[[ -x "${AGENT_BIN}" ]] || { echo "locked W1 DDS Agent is unavailable" >&2; exit 4; }
[[ -x "${REPO_ROOT}/ros2_ws_aerostack2/install/as2_platform_pixhawk/lib/as2_platform_pixhawk/as2_platform_pixhawk_node" ]] || {
  echo "locked Aerostack2 platform build is unavailable" >&2; exit 4;
}
[[ "$(sha256sum "${PX4_BUILD}/bin/px4" | awk '{print $1}')" == "d5cd7df0efd24f7f5509e8c4e5699a709cd8e4df42b0b64e453edab815471612" ]] || {
  echo "W1 PX4 binary identity mismatch" >&2; exit 4;
}
[[ "$(git -C "${REPO_ROOT}" branch --show-current)" == "main" ]] || {
  echo "W1 formal runtime requires main" >&2; exit 4;
}
[[ -z "$(git -C "${REPO_ROOT}" status --porcelain)" ]] || {
  echo "W1 formal runtime requires a clean worktree" >&2; exit 4;
}
[[ "$(git -C "${REPO_ROOT}" rev-parse HEAD)" == "$(git -C "${REPO_ROOT}" rev-parse origin/main)" ]] || {
  echo "W1 formal runtime requires HEAD aligned with pushed origin/main" >&2; exit 4;
}
[[ "$(git -C "${REPO_ROOT}/external/aerostack2" rev-parse HEAD)" == "a8e7318b8d1d7c5adc580e8a16374357773bc11a" ]] || {
  echo "Aerostack2 source identity mismatch" >&2; exit 4;
}
[[ "$(git -C "${REPO_ROOT}/ros2_ws_aerostack2/src/as2_platform_pixhawk" rev-parse HEAD)" == "482563ba979baea965df918995c141a362e26637" ]] || {
  echo "Aerostack2 PX4 platform plugin identity mismatch" >&2; exit 4;
}
[[ "$(git -C "${REPO_ROOT}/ros2_ws_aerostack2/src/as2_platform_pixhawk" diff | sha256sum | awk '{print $1}')" == "6f82c7012ee5d56cf015f6f41752c1ab7839332bf27faae715d1af6bf9245bc1" ]] || {
  echo "Aerostack2 compatibility patch identity mismatch" >&2; exit 4;
}
[[ ! -e "${RAW_DIR}" ]] || { echo "refusing to overwrite W1 raw attempt: ${RAW_DIR}" >&2; exit 3; }
if [[ "${PHASE}" == "W1-D" && ! -f "${MANIFEST}" ]]; then
  echo "canonical replay requires the accepted source trace manifest" >&2
  exit 4
fi
if ss -H -lun "sport = :8888" 2>/dev/null | grep -q .; then
  echo "W1 DDS port 8888 is occupied" >&2
  exit 5
fi

mkdir -p "${RAW_DIR}" "${PROCESSED_DIR}"
touch "${RAW_DIR}/run.start"
python3 - "${RAW_DIR}/source_identity.json" "${RUN_ID}" "${PHASE}" "${SIMULATION_SEED}" <<'PY'
import json, subprocess, sys
path, run_id, phase, seed = sys.argv[1:]
root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
result = {
    "schema_version": "1.0",
    "run_id": run_id,
    "phase": phase,
    "simulation_seed": int(seed),
    "repository_head": subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"], text=True).strip(),
    "repository_origin_main": subprocess.check_output(["git", "-C", root, "rev-parse", "origin/main"], text=True).strip(),
    "aerostack2_commit": "a8e7318b8d1d7c5adc580e8a16374357773bc11a",
    "px4_platform_plugin_commit": "482563ba979baea965df918995c141a362e26637",
    "simulation_project_commit": "22d945c956ae234839b3c48555ab2c1ba40eaee3",
    "px4_commit": "4ae21a5e569d3d89c2f6366688cbacb3e93437c9",
    "px4_msgs_commit": "18ecff03041c6f8d8a0012fbc63af0b23dd60af1",
}
open(path, "w", encoding="utf-8").write(json.dumps(result, indent=2, sort_keys=True) + "\n")
PY
install -D -m 0644 "${LOGGER_TOPICS_FILE}" "${LOGGER_TOPICS_TARGET}"
rm -f "${PX4_BUILD}/rootfs/0/parameters.bson" "${PX4_BUILD}/rootfs/0/parameters_backup.bson"

GZ_PARTITION_NAME="uav_sf_w1_${RUN_ID//[^a-zA-Z0-9_]/_}"
FIFO="${RAW_DIR}/px4.stdin"
mkfifo "${FIFO}"
exec 3<>"${FIFO}"

declare -a PROCESS_GROUPS=()
PX4_PID=""
GZ_PID=""
AGENT_PID=""
SIDECAR_PID=""
BAG_PID=""
CLEANED=0
LAST_GROUP_PID=""

start_group() {
  setsid "$@" &
  LAST_GROUP_PID=$!
  PROCESS_GROUPS+=("${LAST_GROUP_PID}")
}

stop_group() {
  local pid="${1:-}"
  local selected_signal="${2:-TERM}"
  [[ -n "${pid}" ]] || return 0
  if kill -0 "${pid}" 2>/dev/null; then
    kill -"${selected_signal}" -- "-${pid}" 2>/dev/null || true
    for _ in $(seq 1 100); do
      kill -0 "${pid}" 2>/dev/null || break
      sleep 0.1
    done
  fi
  if kill -0 "${pid}" 2>/dev/null; then
    kill -KILL -- "-${pid}" 2>/dev/null || true
  fi
  wait "${pid}" 2>/dev/null || true
}

controlled_cleanup() {
  (( CLEANED == 0 )) || return 0
  CLEANED=1
  set +e
  stop_group "${BAG_PID}" INT
  stop_group "${SIDECAR_PID}" INT
  for (( index=${#PROCESS_GROUPS[@]}-1; index>=0; index-- )); do
    local pid="${PROCESS_GROUPS[index]}"
    if [[ "${pid}" != "${PX4_PID}" && "${pid}" != "${GZ_PID}" && "${pid}" != "${AGENT_PID}" && "${pid}" != "${BAG_PID}" && "${pid}" != "${SIDECAR_PID}" ]]; then
      stop_group "${pid}" INT
    fi
  done
  if [[ -n "${PX4_PID}" ]] && kill -0 "${PX4_PID}" 2>/dev/null; then
    echo shutdown >&3
    for _ in $(seq 1 150); do
      kill -0 "${PX4_PID}" 2>/dev/null || break
      sleep 0.1
    done
  fi
  stop_group "${PX4_PID}" TERM
  stop_group "${GZ_PID}" TERM
  stop_group "${AGENT_PID}" TERM
  exec 3>&-
  rm -f "${FIFO}" "${LOGGER_TOPICS_TARGET}"
}
trap controlled_cleanup EXIT

LD_LIBRARY_PATH="${AGENT_LIBRARY_PATH}" setsid "${AGENT_BIN}" udp4 -p 8888 \
  >"${RAW_DIR}/microxrce_agent.log" 2>&1 &
AGENT_PID=$!
PROCESS_GROUPS+=("${AGENT_PID}")

(
  export GZ_SIM_RESOURCE_PATH=
  export GZ_SIM_SYSTEM_PLUGIN_PATH=
  export GZ_SIM_SERVER_CONFIG_PATH=
  set +u
  source "${PX4_BUILD}/rootfs/gz_env.sh"
  set -u
  exec setsid env GZ_PARTITION="${GZ_PARTITION_NAME}" gz sim --seed "${SIMULATION_SEED}" \
    --verbose=1 -r -s "${PX4_DIR}/Tools/simulation/gz/worlds/default.sdf"
) >"${RAW_DIR}/gazebo.log" 2>&1 &
GZ_PID=$!
PROCESS_GROUPS+=("${GZ_PID}")
for _ in $(seq 1 150); do
  GZ_PARTITION="${GZ_PARTITION_NAME}" gz topic -l 2>/dev/null | grep -q '/world/default/clock' && break
  kill -0 "${GZ_PID}" 2>/dev/null || { echo "Gazebo exited before readiness" >&2; exit 10; }
  sleep 0.1
done
GZ_PARTITION="${GZ_PARTITION_NAME}" gz topic -l 2>/dev/null | grep -q '/world/default/clock' || {
  echo "Gazebo readiness timeout" >&2; exit 10;
}

(
  cd "${PX4_DIR}"
  GZ_PARTITION="${GZ_PARTITION_NAME}" PX4_GZ_STANDALONE=1 GZ_SIM_RESOURCE_PATH='' \
    PX4_PARAM_SDLOG_MODE=0 PX4_PARAM_SDLOG_PROFILE=0 HEADLESS=1 PX4_SIM_MODEL=gz_x500 \
    exec setsid "${PX4_BUILD}/bin/px4" -i 0 <"${FIFO}"
) >"${RAW_DIR}/px4.log" 2>&1 &
PX4_PID=$!
PROCESS_GROUPS+=("${PX4_PID}")
for _ in $(seq 1 160); do
  grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null && break
  kill -0 "${PX4_PID}" 2>/dev/null || { echo "PX4 exited before readiness" >&2; exit 10; }
  sleep 0.25
done
grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null || { echo "PX4 readiness timeout" >&2; exit 10; }

for command in \
  "param set COM_RC_IN_MODE 4" \
  "param set NAV_RCL_ACT 0" \
  "param set NAV_DLL_ACT 0" \
  "param set COM_ARM_WO_GPS 1" \
  "param set COM_MODE_ARM_CHK 1" \
  "param set MIS_TAKEOFF_ALT 1.5" \
  "param set MPC_TKO_SPEED 0.5" \
  "param set MPC_LAND_SPEED 0.5"; do
  echo "${command}" >&3
done
sleep 2

start_group ros2 launch as2_platform_pixhawk pixhawk_launch.py \
  namespace:=drone0 platform_config_file:="${RUNTIME_CONFIG}" \
  >"${RAW_DIR}/as2_platform.log" 2>&1
start_group ros2 launch as2_state_estimator state_estimator_launch.py \
  namespace:=drone0 config_file:="${RUNTIME_CONFIG}" plugin_name:=raw_odometry \
  >"${RAW_DIR}/as2_state_estimator.log" 2>&1
start_group ros2 launch as2_motion_controller controller_launch.py \
  namespace:=drone0 config_file:="${RUNTIME_CONFIG}" plugin_name:=pid_speed_controller \
  plugin_config_file:="${PID_CONFIG}" >"${RAW_DIR}/as2_controller.log" 2>&1
start_group ros2 launch as2_behaviors_motion motion_behaviors_launch.py \
  namespace:=drone0 config_file:="${RUNTIME_CONFIG}" >"${RAW_DIR}/as2_behaviors.log" 2>&1
sleep 4

setsid python3 "${REPO_ROOT}/scripts/workloads/w1_sidecar_recorder.py" \
  --run-id "${RUN_ID}" --output "${RAW_DIR}/sidecar_events.jsonl" \
  >"${RAW_DIR}/sidecar.log" 2>&1 &
SIDECAR_PID=$!
PROCESS_GROUPS+=("${SIDECAR_PID}")

mapfile -t BAG_TOPICS < <(sed '/^[[:space:]]*$/d' "${ROSBAG_TOPICS}")
setsid ros2 bag record --include-hidden-topics -o "${RAW_DIR}/rosbag" "${BAG_TOPICS[@]}" \
  >"${RAW_DIR}/rosbag.log" 2>&1 &
BAG_PID=$!
PROCESS_GROUPS+=("${BAG_PID}")
sleep 2

set +e
MISSION_ARGS=(
  --run-id "${RUN_ID}"
  --events "${RAW_DIR}/mission_events.jsonl"
  --output "${RAW_DIR}/mission_result.json"
  --replay-mode "$([[ "${PHASE}" == "W1-B" ]] && echo source || echo canonical)"
)
if [[ "${PHASE}" == "W1-D" ]]; then
  MISSION_ARGS+=(--manifest "${MANIFEST}")
fi
python3 "${REPO_ROOT}/scripts/workloads/w1_mission_driver.py" "${MISSION_ARGS[@]}" \
  >"${RAW_DIR}/mission.log" 2>&1
MISSION_STATUS=$?
set -e

stop_group "${BAG_PID}" INT
BAG_PID=""
stop_group "${SIDECAR_PID}" INT
SIDECAR_PID=""
controlled_cleanup
trap - EXIT
sleep 1

ULOG=$(find "${PX4_BUILD}/rootfs/0/log" -type f -name '*.ulg' -newer "${RAW_DIR}/run.start" \
  -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)
if [[ -n "${ULOG}" && -f "${ULOG}" ]]; then
  cp "${ULOG}" "${RAW_DIR}/flight.ulg"
  set +e
  python3 "${REPO_ROOT}/scripts/tracing/route_trace_collector.py" \
    --ulog "${RAW_DIR}/flight.ulg" --output "${PROCESSED_DIR}/route_trace.full.jsonl" \
    --run-id "${RUN_ID}" --producer-events "${RAW_DIR}/sidecar_events.jsonl" \
    --lifecycle-log "${RAW_DIR}/mission_events.jsonl"
  ROUTE_STATUS=$?
  set -e
  if (( ROUTE_STATUS == 0 )); then
    python3 "${REPO_ROOT}/scripts/tracing/compact_route_trace.py" \
      --input "${PROCESSED_DIR}/route_trace.full.jsonl" \
      --output "${PROCESSED_DIR}/route_trace.jsonl" --stride 10 \
      --report "${PROCESSED_DIR}/route_trace_compaction.json"
  fi
fi

set +e
python3 "${REPO_ROOT}/scripts/workloads/w1_clock_sample_filter.py" \
  --input "${RAW_DIR}/sidecar_events.jsonl" \
  --output "${PROCESSED_DIR}/clock_bridge_samples.jsonl"
CLOCK_FILTER_STATUS=$?
python3 "${REPO_ROOT}/scripts/tracing/clock_bridge_collector.py" \
  --samples "${PROCESSED_DIR}/clock_bridge_samples.jsonl" \
  --output "${PROCESSED_DIR}/clock_bridge.json"
CLOCK_STATUS=$?
set -e

python3 "${REPO_ROOT}/scripts/workloads/w1_compact_trace.py" \
  --mission-events "${RAW_DIR}/mission_events.jsonl" \
  --sidecar-events "${RAW_DIR}/sidecar_events.jsonl" \
  --output "${PROCESSED_DIR}/workload_trace.jsonl" \
  --summary "${PROCESSED_DIR}/workload_trace_summary.json" --run-id "${RUN_ID}"

RESIDUAL_PIDS=()
for pid in "${PROCESS_GROUPS[@]}"; do
  kill -0 "${pid}" 2>/dev/null && RESIDUAL_PIDS+=("${pid}")
done
PORT_OCCUPIED=false
ss -H -lun "sport = :8888" 2>/dev/null | grep -q . && PORT_OCCUPIED=true
python3 - "${RAW_DIR}/cleanup.json" "${PORT_OCCUPIED}" "${RESIDUAL_PIDS[*]:-}" <<'PY'
import json, sys
path, port, pids = sys.argv[1:]
residual = [int(value) for value in pids.split() if value]
result = {
    "schema_version": "1.0",
    "controlled_local_process_stop": True,
    "port_8888_occupied": port == "true",
    "residual_owned_process_ids": residual,
    "clean": port == "false" and not residual,
}
open(path, "w", encoding="utf-8").write(json.dumps(result, indent=2, sort_keys=True) + "\n")
PY

python3 "${REPO_ROOT}/scripts/workloads/w1_artifact_manifest.py" \
  --root "${RAW_DIR}" --output "${PROCESSED_DIR}/raw_artifact_manifest.json" --run-id "${RUN_ID}"

set +e
python3 "${REPO_ROOT}/scripts/workloads/w1_evaluate_attempt.py" \
  --run-id "${RUN_ID}" --phase "${PHASE}" --raw "${RAW_DIR}" \
  --processed "${PROCESSED_DIR}" --cleanup "${RAW_DIR}/cleanup.json" \
  --output "${PROCESSED_DIR}/attempt_result.json"
EVALUATION_STATUS=$?
set -e
echo "W1_RUN=${RUN_ID} PHASE=${PHASE} MISSION_STATUS=${MISSION_STATUS} CLOCK_FILTER_STATUS=${CLOCK_FILTER_STATUS} CLOCK_STATUS=${CLOCK_STATUS} EVALUATION_STATUS=${EVALUATION_STATUS}"
exit "${EVALUATION_STATUS}"
