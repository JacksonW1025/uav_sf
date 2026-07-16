# Dependency lock report

Generated: 2026-07-16 UTC

The dependency lock records the upstream state observed at the start of this
phase. Git dependencies use complete commit IDs; normal setup never resolves a
branch. The only mutation path is an explicit `--update-lock`, which resolves a
new remote HEAD and requires all validation and build evidence to be repeated.

| Dependency | Exact commit | Selection |
|---|---|---|
| PX4-Autopilot | `4ae21a5e569d3d89c2f6366688cbacb3e93437c9` | audited upstream HEAD |
| px4_msgs | `18ecff03041c6f8d8a0012fbc63af0b23dd60af1` | audited upstream HEAD |
| px4-ros2-interface-lib | `c3e410f035806e8c56246708432ded09c976434b` | audited official Auterion repository HEAD |
| Micro-XRCE-DDS-Agent | `73622810d984349b80bbac0ef55fc0b694d62222` | existing clean v2.4.3 release checkout |

The interface library's official compatibility checker reported all required
message definitions compatible between the locked px4_msgs and PX4 commits.
The Ubuntu 24.04 Docker Official Image mirror is
`public.ecr.aws/docker/library/ubuntu`; the locally inspected arm64 repository
digest is
`sha256:786a8b558f7be160c6c8c4a54f9a57274f3b4fb1491cf65146521ae77ff1dc54`.
The mirror was selected after Docker Hub's registry endpoint timed out; the
experiment still consumes an immutable digest rather than a floating tag.

The tracked package, Python, and toolchain snapshots describe the successfully
built aarch64 Family A experiment container. The container file defines the
repeatable Ubuntu 24.04 / ROS 2 Jazzy / Gazebo Harmonic build baseline. Package repositories can
change independently of the base-image digest, so the version snapshot remains
part of each run's provenance and must be regenerated after an explicit lock or
image update.
