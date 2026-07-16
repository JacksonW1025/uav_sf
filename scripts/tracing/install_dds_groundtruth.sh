#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
DDS_TOPICS="${PX4_DIR}/src/modules/uxrce_dds_client/dds_topics.yaml"

if [[ ! -f "${DDS_TOPICS}" ]]; then
  echo "Missing PX4 DDS topics file: ${DDS_TOPICS}" >&2
  exit 1
fi

if grep -q '/fmu/out/vehicle_angular_velocity_groundtruth' "${DDS_TOPICS}"; then
  echo "FUZZ-1b DDS groundtruth topics already installed in ${DDS_TOPICS}"
  exit 0
fi

tmp_file="$(mktemp)"
awk '
  /^  # - topic: \/fmu\/out\/vehicle_angular_velocity$/ && !inserted {
    print "  - topic: /fmu/out/vehicle_angular_velocity"
    print "    type: px4_msgs::msg::VehicleAngularVelocity"
    print "    rate_limit: 100."
    print ""
    print "  - topic: /fmu/out/vehicle_angular_velocity_groundtruth"
    print "    type: px4_msgs::msg::VehicleAngularVelocity"
    print "    rate_limit: 100."
    print ""
    print "  - topic: /fmu/out/vehicle_attitude_groundtruth"
    print "    type: px4_msgs::msg::VehicleAttitude"
    print "    rate_limit: 100."
    print ""
    print "  - topic: /fmu/out/vehicle_local_position_groundtruth"
    print "    type: px4_msgs::msg::VehicleLocalPosition"
    print "    rate_limit: 100."
    print ""
    inserted = 1
    next
  }
  /^  #   type: px4_msgs::msg::VehicleAngularVelocity$/ && inserted {
    next
  }
  { print }
  END {
    if (!inserted) {
      exit 42
    }
  }
' "${DDS_TOPICS}" > "${tmp_file}" || {
  rc=$?
  rm -f "${tmp_file}"
  if [[ ${rc} -eq 42 ]]; then
    echo "Could not find vehicle_angular_velocity insertion point in ${DDS_TOPICS}" >&2
  fi
  exit "${rc}"
}

install -m 0644 "${tmp_file}" "${DDS_TOPICS}"
rm -f "${tmp_file}"
echo "Installed FUZZ-1b DDS groundtruth topics into ${DDS_TOPICS}"
