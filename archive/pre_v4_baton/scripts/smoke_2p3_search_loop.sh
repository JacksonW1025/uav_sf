#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STAMP="${SMOKE_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
USE_DOCKER="${SMOKE_USE_DOCKER:-1}"
MOCK="${SMOKE_MOCK:-0}"
PART="${1:-all}"

PART1_BUDGET="${SMOKE_PART1_BUDGET:-24}"
PART2_BUDGET="${SMOKE_PART2_BUDGET:-24}"
PART3_BUDGET="${SMOKE_PART3_BUDGET:-24}"
BOOTSTRAP="${SMOKE_BOOTSTRAP:-6}"
RUN_TIMEOUT="${SMOKE_RUN_TIMEOUT:-130}"
SIM_SPEED_FACTOR="${SMOKE_SIM_SPEED_FACTOR:-1.0}"
CONFIRM_REPEATS="${SMOKE_CONFIRM_REPEATS:-3}"
MAX_CONFIRM_CANDIDATES="${SMOKE_MAX_CONFIRM_CANDIDATES:-2}"

common_args() {
  printf '%s ' \
    --bootstrap "${BOOTSTRAP}" \
    --run-timeout "${RUN_TIMEOUT}" \
    --sim-speed-factor "${SIM_SPEED_FACTOR}"
  if [[ "${MOCK}" == "1" ]]; then
    printf '%s ' --mock-evaluator --skip-build
  fi
  if [[ "${SMOKE_SKIP_BUILD:-0}" == "1" ]]; then
    printf '%s ' --skip-build
  fi
}

run_shell() {
  local name="$1"
  local command="$2"
  if [[ "${USE_DOCKER}" == "1" ]]; then
    local quoted_command
    printf -v quoted_command '%q' "${command}"
    sg docker -c "cd ${REPO_ROOT} && CONTAINER_NAME=uav_sf_${name} ./docker/run.sh bash -lc ${quoted_command}"
  else
    bash -lc "cd ${REPO_ROOT} && ${command}"
  fi
}

run_part1() {
  run_shell "smoke_2p3_part1_${STAMP}" \
    "python3 scripts/m2_map_elites.py $(common_args) --run-id smoke_2p3_part1_${STAMP} --budget ${PART1_BUDGET} --subspace route-a-switching --target-properties route-a-catastrophic --strategy map-elites --no-confirm"
}

run_part2() {
  local confirm_args="--confirm-repeats ${CONFIRM_REPEATS} --max-confirm-candidates ${MAX_CONFIRM_CANDIDATES}"
  if [[ "${SMOKE_CONFIRM:-1}" == "0" ]]; then
    confirm_args="--no-confirm"
  fi
  run_shell "smoke_2p3_part2_${STAMP}" \
    "python3 scripts/m2_map_elites.py $(common_args) --run-id smoke_2p3_part2_${STAMP} --budget ${PART2_BUDGET} --subspace steady-wind-physics --target-properties behavior --strategy map-elites ${confirm_args}"
}

run_part3() {
  run_shell "smoke_2p3_part3_random_${STAMP}" \
    "python3 scripts/m2_map_elites.py $(common_args) --run-id smoke_2p3_part3_random_${STAMP} --budget ${PART3_BUDGET} --subspace steady-wind-physics --target-properties behavior --strategy random --no-confirm"
}

case "${PART}" in
  part1)
    run_part1
    ;;
  part2)
    run_part2
    ;;
  part3)
    run_part3
    ;;
  all)
    run_part1
    run_part2
    run_part3
    ;;
  *)
    echo "usage: $0 [part1|part2|part3|all]" >&2
    exit 2
    ;;
esac
