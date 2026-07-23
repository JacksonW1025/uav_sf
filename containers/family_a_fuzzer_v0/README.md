# Family A Fuzzer v0 locked qualification container

This directory defines the sole formal environment for the Family A
State-Space Evaluator v0. The base is the Docker Official Image for ROS 2
Jazzy mirrored by public ECR, locked both to OCI index
`sha256:31daab66eef9139933379fb67159449944f4e2dcf2e22c2d12cc715f29873e0f`
and native `linux/arm64` manifest
`sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd`.

`build_all.sh` creates one image-local workspace containing the locked PX4
SITL target, `px4_msgs`, `px4-ros2-interface-lib`, the Family A adapter
package including C1, Micro-XRCE-DDS-Agent, collectors, Oracles, runner,
schemas, and fixtures. No host ROS workspace is mounted or sourced.

Use the unique repository entry:

```sh
./scripts/fuzzer_v0/family_a/state_space_evaluator.py --container env-build
./scripts/fuzzer_v0/family_a/state_space_evaluator.py --container env-verify
./scripts/fuzzer_v0/family_a/state_space_evaluator.py --container plan
```

The wrapper mounts the repository read-only only for Git authorization
identity checks and mounts a dedicated ignored attempt-output directory.
It passes no host `AMENT_PREFIX_PATH`, `CMAKE_PREFIX_PATH`,
`COLCON_PREFIX_PATH`, `PYTHONPATH`, or ROS package path.

The readiness task permits only environment/static/fixture commands. Formal
`register`, `execute`, and `close` are implemented for a later separately
authorized qualification task and are not invoked while constructing or
reviewing this image.
