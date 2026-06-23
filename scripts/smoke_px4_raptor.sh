#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
LOG_DIR="${REPO_ROOT}/docs"
LOG_FILE="${LOG_DIR}/phase1_smoke.log"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-150}"
mkdir -p "${LOG_DIR}"

cd "${PX4_DIR}"

mkdir -p build/px4_sitl_raptor/rootfs/raptor
cp -f src/modules/mc_raptor/blob/policy.tar build/px4_sitl_raptor/rootfs/raptor/policy.tar

cat > /tmp/uav_sf_px4_smoke.cmds <<'CMDS'
sleep 5
help
param set MC_RAPTOR_ENABLE 1
param set MC_RAPTOR_OFFB 0
mc_raptor start
sleep 5
mc_raptor status
param show MC_RAPTOR*
commander status
uxrce_dds_client status
shutdown
CMDS

{
  echo "# PX4 RAPTOR smoke"
  date -Is
  echo "PX4_SHA=$(git rev-parse HEAD)"
  echo "POLICY_DST=${PX4_DIR}/build/px4_sitl_raptor/rootfs/raptor/policy.tar"
  ls -l build/px4_sitl_raptor/rootfs/raptor/policy.tar
  echo "COMMAND=HEADLESS=1 PX4_SIM_SPEED_FACTOR=${PX4_SIM_SPEED_FACTOR:-1} make px4_sitl_raptor gz_x500 < /tmp/uav_sf_px4_smoke.cmds"
} | tee "${LOG_FILE}"

set +e
{
  timeout "${SMOKE_TIMEOUT}" env HEADLESS=1 PX4_SIM_SPEED_FACTOR="${PX4_SIM_SPEED_FACTOR:-1}" make px4_sitl_raptor gz_x500 < /tmp/uav_sf_px4_smoke.cmds
  run_rc=$?
  echo "PX4_RUN_RC=${run_rc}"
  exit "${run_rc}"
} 2>&1 | tee -a "${LOG_FILE}"
run_rc=${PIPESTATUS[0]}
set -e

pkill -TERM -f "gz sim|/bin/px4" 2>/dev/null || true

if [[ "${run_rc}" -eq 124 ]] && grep -q "Exiting NOW." "${LOG_FILE}"; then
  echo "PX4_SHUTDOWN_OBSERVED=1" | tee -a "${LOG_FILE}"
  exit 0
fi

exit "${run_rc}"
