ARG BASE_IMAGE=public.ecr.aws/docker/library/ros@sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

LABEL org.opencontainers.image.title="PX4 Family A validation and reference tooling" \
      org.opencontainers.image.base.digest="sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd" \
      org.opencontainers.image.platform="linux/arm64"

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Etc/UTC \
    ROS_DISTRO=jazzy \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    PYTHONDONTWRITEBYTECODE=1

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY containers/family_a/apt-packages.lock /tmp/locks/apt-packages.lock
COPY containers/family_a/ros-packages.lock /tmp/locks/ros-packages.lock

RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && mapfile -t apt_packages < <(grep -Ev '^[[:space:]]*(#|$)' /tmp/locks/apt-packages.lock) \
    && mapfile -t ros_packages < <(grep -Ev '^[[:space:]]*(#|$)' /tmp/locks/ros-packages.lock) \
    && apt-get install -y --no-install-recommends "${apt_packages[@]}" "${ros_packages[@]}" \
    && rm -rf /var/lib/apt/lists/*

COPY containers/family_a/validation-packages.lock /tmp/locks/validation-packages.lock

RUN apt-get update \
    && mapfile -t validation_packages < <(grep -Ev '^[[:space:]]*(#|$)' /tmp/locks/validation-packages.lock) \
    && apt-get install -y --no-install-recommends "${validation_packages[@]}" \
    && rm -rf /var/lib/apt/lists/*

COPY . /opt/uav_sf
WORKDIR /opt/uav_sf

RUN ./scripts/validation/validate_repo.sh

ENTRYPOINT ["python3", "-m", "scripts.evaluator.evaluate_trace"]
