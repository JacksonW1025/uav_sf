#!/usr/bin/env bash
set -euo pipefail

set +u
source /opt/ros/jazzy/setup.bash
source /opt/family_a_ws/install/setup.bash
set -u
export PATH="/opt/px4-venv/bin:/opt/microxrce/bin:${PATH}"
export LD_LIBRARY_PATH="/opt/microxrce/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="/opt/uav_sf${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
cd /opt/uav_sf
exec "$@"
