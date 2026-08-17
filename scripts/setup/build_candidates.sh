#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
jobs=12
prefix="/opt"
phase="all"
observer_profile="baseline"

while (($#)); do
  case "$1" in
    --jobs)
      jobs="$2"
      shift 2
      ;;
    --prefix)
      prefix="$2"
      shift 2
      ;;
    --phase)
      phase="$2"
      shift 2
      ;;
    --observer-profile)
      observer_profile="$2"
      shift 2
      ;;
    *)
      echo "unsupported argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "${phase}" != "all" && "${phase}" != "source" && \
      "${phase}" != "workspace" && "${phase}" != "upstream-workspace" && \
      "${phase}" != "project-workspace" ]]; then
  echo "--phase must be one of: all, source, workspace, upstream-workspace, project-workspace" >&2
  exit 2
fi
if [[ "${observer_profile}" != "off" && "${observer_profile}" != "baseline" && \
      "${observer_profile}" != "transition" ]]; then
  echo "--observer-profile must be one of: off, baseline, transition" >&2
  exit 2
fi

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "Family A candidates require native aarch64" >&2
  exit 2
fi

# ROS-generated setup files legitimately probe unset tracing variables and
# are not nounset-clean.  Limit the relaxation to the vendor setup itself.
set +u
source /opt/ros/jazzy/setup.bash
set -u
export PYTHONNOUSERSITE=1
# Keep the ROS vendor prefixes added by setup.bash.  In particular,
# gz_tools_vendor places the Harmonic CLI below /opt/ros rather than in
# /usr/bin.  The container starts from a fixed PATH, so retaining these
# additions cannot import host state.
export PATH="/opt/px4-venv/bin:${PATH}"

px4_source="${repository_root}/external/px4_autopilot"
messages_source="${repository_root}/external/px4_msgs"
interface_source="${repository_root}/external/px4_ros2_interface_lib"
agent_source="${repository_root}/external/micro_xrce_dds_agent"
agent_prefix="${prefix}/microxrce"
workspace="${prefix}/family_a_ws"

if [[ "${phase}" == "all" || "${phase}" == "source" ]]; then
  /usr/bin/python3 "${interface_source}/scripts/check-message-compatibility.py" \
    "${messages_source}" "${px4_source}"

  cmake -S "${agent_source}" -B "${agent_source}/build-family-a" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${agent_prefix}" \
    -DUAGENT_SUPERBUILD=OFF \
    -DUAGENT_USE_SYSTEM_FASTDDS=ON \
    -DUAGENT_USE_SYSTEM_FASTCDR=ON \
    -DUAGENT_LOGGER_PROFILE=OFF \
    -DUAGENT_P2P_PROFILE=OFF \
    -DUAGENT_BUILD_TESTS=OFF \
    -Dfastcdr_DIR=/opt/ros/jazzy/lib/cmake/fastcdr \
    -Dfastrtps_DIR=/opt/ros/jazzy/share/fastrtps/cmake \
    -Dfoonathan_memory_DIR=/opt/ros/jazzy/lib/foonathan_memory/cmake
  cmake --build "${agent_source}/build-family-a" --parallel "${jobs}"
  cmake --install "${agent_source}/build-family-a"

  cd "${px4_source}"
  observer_define=""
  if [[ "${observer_profile}" == "off" ]]; then
    observer_define="-DROUTE_OBSERVABILITY_OFF"
  elif [[ "${observer_profile}" == "transition" ]]; then
    observer_define="-DROUTE_OBSERVABILITY_TRANSITION"
  fi
  printf '%s\n' "${observer_profile}" > "${prefix}/family_a_observer_profile"
  if [[ -n "${observer_define}" ]]; then
    make -j"${jobs}" px4_sitl_default \
      PYTHON_EXECUTABLE=/opt/px4-venv/bin/python3 \
      CMAKE_ARGS="-DCMAKE_CXX_FLAGS=${observer_define}"
  else
    make -j"${jobs}" px4_sitl_default PYTHON_EXECUTABLE=/opt/px4-venv/bin/python3
  fi
fi

if [[ "${phase}" == "all" || "${phase}" == "workspace" || \
      "${phase}" == "upstream-workspace" ]]; then
  mkdir -p "${workspace}/src"
  ln -sfn "${messages_source}" "${workspace}/src/px4_msgs"
  ln -sfn "${interface_source}/px4_ros2_cpp" "${workspace}/src/px4_ros2_cpp"

  cd "${workspace}"
  colcon build --merge-install --executor sequential \
    --packages-select px4_msgs px4_ros2_cpp \
    --cmake-args -DBUILD_TESTING=OFF -DPython3_EXECUTABLE=/usr/bin/python3
fi

if [[ "${phase}" == "all" || "${phase}" == "workspace" || \
      "${phase}" == "project-workspace" ]]; then
  if [[ ! -f "${workspace}/install/setup.bash" ]]; then
    echo "upstream ROS workspace is not installed" >&2
    exit 2
  fi
  set +u
  source "${workspace}/install/setup.bash"
  set -u
  for package in "${repository_root}"/runtime/ros2/*; do
    [[ -d "${package}" ]] || continue
    ln -sfn "${package}" "${workspace}/src/$(basename "${package}")"
  done

  cd "${workspace}"
  colcon build --merge-install --executor sequential \
    --packages-select family_a_runtime family_a_modes \
    --cmake-args -DBUILD_TESTING=OFF -DPython3_EXECUTABLE=/usr/bin/python3

  cd "${repository_root}"
  /usr/bin/python3 -m scripts.setup.verify_candidates \
    --px4-binary "${px4_source}/build/px4_sitl_default/bin/px4" \
    --agent-binary "${agent_prefix}/bin/MicroXRCEAgent" \
    --workspace-prefix "${workspace}/install" \
    --output "${prefix}/family_a_candidate_manifest.json"
fi
