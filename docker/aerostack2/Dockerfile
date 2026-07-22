# Registry tag at preregistration: ros:humble-ros-base-jammy.
# The arm64 manifest is pinned so the bounded SITL study never depends only on
# a floating container tag.
FROM ros@sha256:9bdda47f584f33aae18456225a8a95fe7bcde821727757f02a3252cbc46e8188

ARG AEROSTACK2_COMMIT=a8e7318b8d1d7c5adc580e8a16374357773bc11a
ARG PIXHAWK_COMMIT=482563ba979baea965df918995c141a362e26637
WORKDIR /opt/aerostack2_spike/src
RUN git clone https://github.com/aerostack2/aerostack2.git aerostack2 \
 && git -C aerostack2 checkout "${AEROSTACK2_COMMIT}" \
 && git clone https://github.com/aerostack2/as2_platform_pixhawk.git as2_platform_pixhawk \
 && git -C as2_platform_pixhawk checkout "${PIXHAWK_COMMIT}"

# This profile documents the isolated Humble boundary. The host spike script
# performs the build because Docker daemon access is unavailable on this host.
