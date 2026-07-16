ARG BASE_IMAGE=public.ecr.aws/docker/library/ubuntu@sha256:786a8b558f7be160c6c8c4a54f9a57274f3b4fb1491cf65146521ae77ff1dc54
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG USERNAME=px4
ARG USER_UID=1000
ARG USER_GID=1000

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    TZ=Etc/UTC \
    ROS_DISTRO=jazzy

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n' > /etc/apt/apt.conf.d/80-uav-sf-retries

RUN unset HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy \
    && apt-get update && apt-get install -y --no-install-recommends \
    bash-completion \
    astyle \
    build-essential \
    ca-certificates \
    ccache \
    cmake \
    cppcheck \
    curl \
    dbus \
    dnsutils \
    file \
    g++ \
    gcc \
    gdb \
    git \
    gnupg2 \
    iproute2 \
    iputils-ping \
    lcov \
    less \
    libssl-dev \
    libxml2-dev \
    libxml2-utils \
    libasio-dev \
    libtinyxml2-dev \
    locales \
    lsb-release \
    make \
    nano \
    net-tools \
    ninja-build \
    pkg-config \
    procps \
    psmisc \
    python-is-python3 \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    protobuf-compiler \
    rsync \
    shellcheck \
    software-properties-common \
    sudo \
    tzdata \
    unzip \
    vim \
    wget \
    xz-utils \
    zip \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    argcomplete \
    cerberus \
    coverage \
    'empy<4,>=3.3' \
    future \
    'jinja2>=2.8' \
    jsonschema \
    kconfiglib \
    lark \
    lxml \
    'matplotlib>=3.0' \
    'numpy>=1.13' \
    'nunavut>=1.1.0' \
    packaging \
    'pandas>=0.21' \
    pkgconfig \
    psutil \
    pycryptodome \
    pygments \
    pymavlink \
    pynacl \
    pyros-genmsg \
    pyserial \
    'pyulog>=0.5.0' \
    pyyaml \
    requests \
    'setuptools<=81.0.0,>=39.2.0' \
    'six>=1.12.0' \
    'sympy>=1.10.1' \
    'toml>=0.9' \
    'wheel>=0.31.1'

RUN curl --retry 5 --retry-delay 3 --retry-all-errors --http1.1 -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME}") main" \
    > /etc/apt/sources.list.d/ros2.list \
    && unset HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3-argcomplete \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    ros-dev-tools \
    ros-jazzy-ros-base \
    && rm -rf /var/lib/apt/lists/*

RUN curl --retry 5 --retry-delay 3 --retry-all-errors --http1.1 -fsSL https://packages.osrfoundation.org/gazebo.gpg \
    -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(. /etc/os-release && echo "${UBUNTU_CODENAME}") main" \
    > /etc/apt/sources.list.d/gazebo-stable.list \
    && unset HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy \
    && apt-get update && apt-get install -y --no-install-recommends \
    bc \
    cppzmq-dev \
    dmidecode \
    gstreamer1.0-libav \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-ugly \
    gz-harmonic \
    libeigen3-dev \
    libgstreamer-plugins-base1.0-dev \
    libimage-exiftool-perl \
    libopencv-dev \
    libunwind-dev \
    && rm -rf /var/lib/apt/lists/*

RUN if ! getent group "${USER_GID}" >/dev/null; then groupadd --gid "${USER_GID}" "${USERNAME}"; fi \
    && existing_user="$(getent passwd "${USER_UID}" | cut -d: -f1 || true)" \
    && if [[ -n "${existing_user}" && "${existing_user}" != "${USERNAME}" ]]; then \
      usermod --login "${USERNAME}" --home "/home/${USERNAME}" --move-home "${existing_user}"; \
    elif [[ -z "${existing_user}" ]]; then \
      useradd --uid "${USER_UID}" --gid "${USER_GID}" --create-home --shell /bin/bash "${USERNAME}"; \
    fi \
    && usermod --gid "${USER_GID}" --shell /bin/bash "${USERNAME}" \
    && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${USERNAME}" \
    && chmod 0440 "/etc/sudoers.d/${USERNAME}"

RUN rosdep init

USER ${USERNAME}
WORKDIR /workspace

RUN rosdep update \
    && printf '\nsource /opt/ros/jazzy/setup.bash\nexport PX4_DIR=/workspace/external/PX4-Autopilot\n' >> "${HOME}/.bashrc"

ENV PX4_DIR=/workspace/external/PX4-Autopilot

CMD ["/bin/bash"]
