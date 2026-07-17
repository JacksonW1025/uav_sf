#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPEATS=3
QUEUES=(1 4 8 16 32)

while (($#)); do
  case "$1" in
    --repeats) shift; REPEATS="${1:-}" ;;
    --queue-length) shift; QUEUES=("${1:-}") ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
if [[ ! "${REPEATS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "repeats must be a positive integer" >&2
  exit 2
fi

for queue_length in "${QUEUES[@]}"; do
  build_output="$("${REPO_ROOT}/scripts/setup/build_observability_profile.sh" \
    --profile TRANSITION --queue-length "${queue_length}")"
  px4_dir="$(printf '%s\n' "${build_output}" | sed -n 's/^PX4_OBSERVABILITY_DIR=//p')"
  build_provenance="$(printf '%s\n' "${build_output}" | sed -n 's/^BUILD_PROVENANCE=//p')"
  test -n "${px4_dir}"
  test -f "${build_provenance}"

  for repeat in $(seq 1 "${REPEATS}"); do
    run_id="queue_q${queue_length}_r${repeat}_20260717"
    run_root="${REPO_ROOT}/runs/phase_a2/queue_benchmark/q${queue_length}/repeat${repeat}/raw"
    processed_root="${REPO_ROOT}/runs/phase_a2/queue_benchmark/q${queue_length}/repeat${repeat}/processed"
    PX4_OBSERVABILITY_DIR="${px4_dir}" \
    P0_RUN_ROOT="${run_root}" \
    P0_PROCESSED_ROOT="${processed_root}" \
    P0_ACTIVE_DURATION_S=8 \
    P0_HOVER_ONLY=1 \
    P0_OBSERVATION_PROFILE=TRANSITION \
    P0_UORB_QUEUE_LENGTH="${queue_length}" \
    P0_BUILD_PROVENANCE="${build_provenance}" \
      "${REPO_ROOT}/scripts/probes/run_p0_scenario.sh" offboard "${run_id}"

    python3 "${REPO_ROOT}/scripts/analysis/measure_observation_profile.py" \
      --ulog "${run_root}/${run_id}/raw/flight.ulg" \
      --output "${processed_root}/${run_id}/observation_measurement.json" \
      --queue-length "${queue_length}" \
      --run-id "${run_id}"
  done
done
