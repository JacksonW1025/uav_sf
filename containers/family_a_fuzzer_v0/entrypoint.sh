#!/usr/bin/env bash
set -euo pipefail

# Docker receives no host ROS variables, but explicitly clear every prefix
# before sourcing the only permitted overlays.
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH PYTHONPATH
unset ROS_PACKAGE_PATH ROS_ETC_DIR

set +u
source /opt/ros/jazzy/setup.bash
source /opt/family_a/workspace/ros/install/setup.bash
set -u

export ROS_DISTRO=jazzy
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export PX4_DIR=/opt/family_a/workspace/src/PX4-Autopilot
export PX4_OBSERVABILITY_DIR="${PX4_DIR}"
export PX4_FRESHNESS_DIR="${PX4_DIR}"
export PX4_C1_DIR="${PX4_DIR}"
export ROS_DISTRO_SETUP=/opt/ros/jazzy/setup.bash
export ROS_WORKSPACE_SETUP=/opt/family_a/workspace/ros/install/setup.bash
export MICROXRCE_AGENT_BIN=/opt/family_a/workspace/dds/MicroXRCEAgent
export MICROXRCE_AGENT_LD_LIBRARY_PATH=/opt/family_a/workspace/dds
export FRESHNESS_AGENT_BUILD=/opt/family_a/workspace/dds
export C1_AGENT_BUILD=/opt/family_a/workspace/dds
export ROUTE_EXTERNAL_MODE_BIN=/opt/family_a/workspace/ros/install/lib/route_transition_external_mode/route_transition_external_mode
export FRESHNESS_PRODUCER_BIN=/opt/family_a/workspace/ros/install/lib/route_transition_external_mode/external_mode_freshness_probe
export C1_MODE_BIN=/opt/family_a/workspace/ros/install/lib/route_transition_external_mode/c1_concurrency_probe
export C1_WORKSPACE_SETUP=/opt/family_a/workspace/ros/install/setup.bash
export FAMILY_A_FORMAL_CONTAINER=1

exec "$@"
