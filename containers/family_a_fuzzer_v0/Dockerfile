ARG BASE_IMAGE=public.ecr.aws/docker/library/ros@sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd
FROM ${BASE_IMAGE}

ARG BASE_INDEX_DIGEST
ARG BASE_PLATFORM_DIGEST
ARG DEBIAN_FRONTEND=noninteractive

LABEL org.opencontainers.image.title="Family A Fuzzer v0 qualification environment" \
      org.opencontainers.image.base.name="public.ecr.aws/docker/library/ros" \
      org.opencontainers.image.base.index.digest="${BASE_INDEX_DIGEST}" \
      org.opencontainers.image.base.platform.digest="${BASE_PLATFORM_DIGEST}" \
      org.opencontainers.image.platform="linux/arm64" \
      org.opencontainers.image.runtime-authorized="false"

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Etc/UTC \
    ROS_DISTRO=jazzy \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    FAMILY_A_FORMAL_CONTAINER=1 \
    FAMILY_A_CONTAINER_WORKSPACE=/opt/family_a/workspace \
    FAMILY_A_REPOSITORY=/opt/family_a/repository \
    FAMILY_A_AUTHORIZATION_REPO=/authorization/repository \
    FAMILY_A_ATTEMPT_ROOT=/attempts \
    SOURCE_DATE_EPOCH=0

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY containers/family_a_fuzzer_v0/apt-packages.lock /tmp/locks/apt-packages.lock
COPY containers/family_a_fuzzer_v0/ros-packages.lock /tmp/locks/ros-packages.lock
COPY containers/family_a_fuzzer_v0/python-requirements.lock /tmp/locks/python-requirements.lock

RUN unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY \
    && apt_update() { \
         for update_attempt in 1 2 3 4 5; do \
           if apt-get update; then \
             return 0; \
           fi; \
           rm -rf /var/lib/apt/lists/*; \
           sleep "$((update_attempt * 10))"; \
         done; \
         return 1; \
       } \
    && printf 'Acquire::Retries "5";\nAcquire::http::Timeout "60";\nAcquire::https::Timeout "60";\n' \
      > /etc/apt/apt.conf.d/80-family-a-retries \
    && curl --retry 5 --retry-delay 2 --retry-all-errors -fsSL \
      https://packages.osrfoundation.org/gazebo.gpg \
      -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=arm64 signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable noble main" \
      > /etc/apt/sources.list.d/gazebo-stable.list \
    && apt_update \
    && mapfile -t apt_packages < <(grep -Ev '^[[:space:]]*(#|$)' /tmp/locks/apt-packages.lock) \
    && mapfile -t ros_packages < <(grep -Ev '^[[:space:]]*(#|$)' /tmp/locks/ros-packages.lock) \
    && install_status=1 \
    && for attempt in 1 2 3 4 5; do \
         if apt-get install -y --no-install-recommends "${apt_packages[@]}" "${ros_packages[@]}"; then \
           install_status=0; \
           break; \
         fi; \
         sleep "$((attempt * 2))"; \
         apt_update; \
       done \
    && test "${install_status}" -eq 0 \
    && python3 -m pip install --break-system-packages --no-cache-dir \
      --require-hashes --no-deps -r /tmp/locks/python-requirements.lock \
    && rm -rf /var/lib/apt/lists/*

ARG REPOSITORY_COMMIT
LABEL org.opencontainers.image.revision="${REPOSITORY_COMMIT}"
ENV FAMILY_A_IMPLEMENTATION_COMMIT=${REPOSITORY_COMMIT}

COPY . /opt/family_a/repository
WORKDIR /opt/family_a/repository

RUN containers/family_a_fuzzer_v0/build_all.sh \
    && ln -s /opt/family_a/workspace/ros /opt/family_a/repository/ros2_ws

RUN python3 -m compileall -q scripts \
    && containers/family_a_fuzzer_v0/verify_environment.sh --build-time

ENTRYPOINT ["/opt/family_a/repository/containers/family_a_fuzzer_v0/entrypoint.sh"]
CMD ["python3", "/opt/family_a/repository/scripts/fuzzer_v0/family_a/state_space_evaluator.py", "--inside-container", "status"]
