#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="${1:-}"
if [[ -z "${RUN_ID}" ]]; then
  echo "usage: $0 RUN_ID" >&2
  exit 2
fi

set +u
source /opt/ros/jazzy/setup.bash
source "${REPO_ROOT}/ros2_ws/install/setup.bash"
set -u

PX4_DIR="${REPO_ROOT}/external/PX4-Autopilot-route-observability"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
AGENT_PREFIX="${REPO_ROOT}/external/install/microxrce_agent"
RAW_DIR="${REPO_ROOT}/runs/p0d/${RUN_ID}/raw"
PROCESSED_DIR="${REPO_ROOT}/data/processed/p0d/${RUN_ID}"
mkdir -p "${RAW_DIR}" "${PROCESSED_DIR}"
START_MARKER="${RAW_DIR}/run.start"
touch "${START_MARKER}"

PX4_PID=""
AGENT_PID=""
MODE_PID=""
RUNNER_PID=""
FIFO="${RAW_DIR}/px4.stdin"
SHUTDOWN_REQUEST="${RAW_DIR}/mode_shutdown.request"
SHUTDOWN_DONE="${RAW_DIR}/mode_shutdown.done"
rm -f "${FIFO}" "${SHUTDOWN_REQUEST}" "${SHUTDOWN_DONE}"
mkfifo "${FIFO}"
exec 3<>"${FIFO}"

stop_process() {
  local pid="${1:-}"
  local signal="${2:-TERM}"
  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then return; fi
  kill -"${signal}" "${pid}" 2>/dev/null || true
  for _ in $(seq 1 50); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "${pid}" 2>/dev/null; then kill -TERM "${pid}" 2>/dev/null || true; fi
  for _ in $(seq 1 50); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "${pid}" 2>/dev/null; then kill -KILL "${pid}" 2>/dev/null || true; fi
  wait "${pid}" 2>/dev/null || true
}

cleanup() {
  set +e
  stop_process "${MODE_PID}" INT
  stop_process "${RUNNER_PID}" INT
  if [[ -n "${PX4_PID}" ]] && kill -0 "${PX4_PID}" 2>/dev/null; then echo shutdown >&3; fi
  stop_process "${PX4_PID}" TERM
  while read -r gz_pid; do stop_process "${gz_pid}" TERM; done < <(pgrep -P "$$" -f '^gz sim ' 2>/dev/null || true)
  stop_process "${AGENT_PID}" TERM
  exec 3>&-
  rm -f "${FIFO}"
}
trap cleanup EXIT

LD_LIBRARY_PATH="${AGENT_PREFIX}/lib"   "${AGENT_PREFIX}/bin/MicroXRCEAgent" udp4 -p 8888   >"${RAW_DIR}/microxrce_agent.log" 2>&1 &
AGENT_PID=$!

(
  cd "${PX4_DIR}"
  HEADLESS=1 PX4_SIM_MODEL=gz_x500 "${PX4_BUILD}/bin/px4" -i 0 <"${FIFO}"
) >"${RAW_DIR}/px4.log" 2>&1 &
PX4_PID=$!

for _ in $(seq 1 120); do
  if grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null; then break; fi
  if ! kill -0 "${PX4_PID}" 2>/dev/null; then exit 10; fi
  sleep 0.25
done
grep -q "pxh>" "${RAW_DIR}/px4.log"
echo "param set COM_RC_IN_MODE 4" >&3
echo "param set NAV_RCL_ACT 0" >&3
echo "param set NAV_DLL_ACT 0" >&3
echo "param set COM_ARM_WO_GPS 1" >&3
echo "param set RTL_RETURN_ALT 3" >&3
echo "param set RTL_DESCEND_ALT 2" >&3
sleep 2

RESULT_FILE="${RAW_DIR}/runner_result.json"
python3 "${REPO_ROOT}/scripts/probes/p0d_post_disarm_reentry.py"   --output "${RESULT_FILE}"   --shutdown-request "${SHUTDOWN_REQUEST}"   --shutdown-done "${SHUTDOWN_DONE}"   --timeout 240 >"${RAW_DIR}/runner.log" 2>&1 &
RUNNER_PID=$!
"${REPO_ROOT}/ros2_ws/install/route_transition_external_mode/lib/route_transition_external_mode/route_transition_external_mode"   >"${RAW_DIR}/external_mode.log" 2>&1 &
MODE_PID=$!

while kill -0 "${RUNNER_PID}" 2>/dev/null && [[ ! -e "${SHUTDOWN_REQUEST}" ]]; do sleep 0.2; done
if [[ -e "${SHUTDOWN_REQUEST}" ]]; then
  stop_process "${MODE_PID}" INT
  MODE_PID=""
  touch "${SHUTDOWN_DONE}"
fi
set +e
wait "${RUNNER_PID}"
RUNNER_RC=$?
set -e
RUNNER_PID=""

echo shutdown >&3
for _ in $(seq 1 200); do
  kill -0 "${PX4_PID}" 2>/dev/null || break
  sleep 0.1
done
wait "${PX4_PID}" || true
PX4_PID=""
sleep 1

mapfile -t ULOGS < <(find "${PX4_BUILD}/rootfs/0/log" -type f -name '*.ulg' -newer "${START_MARKER}" -printf '%T@ %p\n' 2>/dev/null | sort -n | cut -d' ' -f2-)
if [[ "${#ULOGS[@]}" -lt 1 ]]; then
  echo "P0-D produced no ULog segments" >&2
  exit 12
fi
collector_ulogs=()
summary_sources=()
for index in "${!ULOGS[@]}"; do
  segment="${RAW_DIR}/flight_$(printf '%02d' "$((index + 1))").ulg"
  cp "${ULOGS[$index]}" "${segment}"
  collector_ulogs+=(--ulog "${segment}")
  summary_sources+=(--source "${segment}")
done

python3 "${REPO_ROOT}/scripts/tracing/route_trace_collector.py"   "${collector_ulogs[@]}"   --output "${PROCESSED_DIR}/route_trace.jsonl"   --run-id "${RUN_ID}"   --producer-events "${RAW_DIR}/producer_events.jsonl"   --lifecycle-log "${RAW_DIR}/external_mode.log"
python3 "${REPO_ROOT}/scripts/analysis/summarize_route_trace.py"   --trace "${PROCESSED_DIR}/route_trace.jsonl"   --result "${RESULT_FILE}"   --output "${PROCESSED_DIR}/route_summary.json"   --scenario-label p0d   "${summary_sources[@]}"   --source "${RAW_DIR}/producer_events.jsonl"   --source "${RAW_DIR}/external_mode.log"
python3 "${REPO_ROOT}/scripts/oracles/route_oracle_v0.py"   --trace "${PROCESSED_DIR}/route_trace.jsonl"   --output "${PROCESSED_DIR}/route_oracle.json"

echo "P0D_SCENARIO=$([[ "${RUNNER_RC}" -eq 0 ]] && echo PASS || echo FAIL) run_id=${RUN_ID}"
