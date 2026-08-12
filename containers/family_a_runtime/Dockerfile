ARG BASE_IMAGE=public.ecr.aws/docker/library/ros@sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG BUILD_JOBS=12
ARG REPOSITORY_COMMIT=UNCOMMITTED

LABEL org.opencontainers.image.title="PX4 Family A Thor experiment runtime" \
      org.opencontainers.image.base.digest="sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd" \
      org.opencontainers.image.platform="linux/arm64"

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Etc/UTC \
    ROS_DISTRO=jazzy \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    VIRTUAL_ENV=/opt/px4-venv \
    PATH=/opt/px4-venv/bin:/opt/microxrce/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY containers/family_a_runtime/runtime-apt-packages.lock /tmp/locks/runtime-apt-packages.lock
COPY containers/family_a_runtime/runtime-ros-packages.lock /tmp/locks/runtime-ros-packages.lock

RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && mapfile -t apt_packages < <(grep -Ev '^[[:space:]]*(#|$)' /tmp/locks/runtime-apt-packages.lock) \
    && mapfile -t ros_packages < <(grep -Ev '^[[:space:]]*(#|$)' /tmp/locks/runtime-ros-packages.lock) \
    && apt-get install -y --no-install-recommends "${apt_packages[@]}" "${ros_packages[@]}" \
    && dpkg-query -W -f='${binary:Package}=${Version}\n' | LC_ALL=C sort > /opt/family_a_installed_deb_packages.lock \
    && rm -rf /var/lib/apt/lists/*

COPY containers/family_a_runtime/python-packages.lock /tmp/locks/python-packages.lock
RUN /usr/bin/python3 -m venv /opt/px4-venv \
    && /opt/px4-venv/bin/python -m pip install --no-cache-dir 'pip==26.2' \
    && /opt/px4-venv/bin/python -m pip install --no-cache-dir --requirement /tmp/locks/python-packages.lock \
    && /opt/px4-venv/bin/python -m pip check \
    && /opt/px4-venv/bin/python -m pip freeze --all | LC_ALL=C sort > /opt/family_a_installed_python_packages.lock

WORKDIR /opt/uav_sf

# Source acquisition is its own cacheable layer.  Runtime-only edits must not
# trigger another network checkout of the immutable upstream candidates.
COPY config/dependencies.lock.json config/patches.lock.json /opt/uav_sf/config/
COPY patches /opt/uav_sf/patches
COPY scripts/setup/prepare_sources.py /opt/uav_sf/scripts/setup/prepare_sources.py
RUN /usr/bin/python3 scripts/setup/prepare_sources.py --with-px4-submodules

# Expensive immutable-source candidates are compiled before project runtime
# files are copied.  Runtime and oracle edits therefore cannot silently alter
# or repeatedly rebuild the selected PX4 and Agent binaries.
COPY scripts/setup/build_candidates.sh /opt/uav_sf/scripts/setup/build_candidates.sh
RUN ./scripts/setup/build_candidates.sh --jobs "${BUILD_JOBS}" --prefix /opt --phase source
RUN ./scripts/setup/build_candidates.sh --jobs "${BUILD_JOBS}" --prefix /opt --phase upstream-workspace

COPY . /opt/uav_sf
RUN printf '%s\n' "${REPOSITORY_COMMIT}" > /opt/family_a_repository_revision \
    && ./scripts/validation/validate_repo.sh \
    && ./scripts/setup/build_candidates.sh --jobs "${BUILD_JOBS}" --prefix /opt --phase project-workspace

# Keep the source revision in the project layer. Changing the repository
# revision must not invalidate immutable apt, upstream-source, or PX4 layers.
LABEL org.opencontainers.image.revision="${REPOSITORY_COMMIT}"

ENTRYPOINT ["/opt/uav_sf/containers/family_a_runtime/entrypoint.sh"]
CMD ["python3", "-m", "scripts.runtime.preflight", "--self-check"]
