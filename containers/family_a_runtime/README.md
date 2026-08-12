# Thor Family A experiment image

This is the complete ARM64 execution image for the Thor SITL environment. It
builds the exact sources and patches in `config/`, uses Python 3.12 without
host site packages, links Micro XRCE-DDS Agent against the locked Jazzy Fast
DDS and Fast CDR packages, and builds the project ROS workspace plus patched
PX4 SITL.

The Agent logger and peer-discovery profiles are disabled. The logger profile
is not part of the experiment data path and Micro XRCE-DDS Agent 2.4.3 cannot
compile it against Noble's system fmt/spdlog API. Runtime stdout and stderr
remain captured by the experiment runner.

Build only on native ARM64 and record the resulting image digest before any
formal attempt:

```bash
docker buildx build --platform linux/arm64 \
  --file containers/family_a_runtime/Dockerfile \
  --build-arg REPOSITORY_COMMIT="$(git rev-parse HEAD)" \
  --tag uav-sf-family-a-thor:candidate --load .
```

Do not use host ROS, Conda, Gazebo resource paths, or Python site packages in
the container.
