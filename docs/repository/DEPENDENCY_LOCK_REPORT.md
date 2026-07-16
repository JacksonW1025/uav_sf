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
The Ubuntu 24.04 multi-platform manifest digest is
`sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90`;
the audited arm64 platform manifest is
`sha256:7f622ca8766bccb22f04242ecb6f19f770b2f08827dc4b8c707de5e78a6da7ab`.

The tracked package, Python, and toolchain snapshots describe the aarch64 host
used to generate the lock. The container file defines the repeatable Ubuntu
24.04 / ROS 2 Jazzy / Gazebo Harmonic build baseline. Package repositories can
change independently of the base-image digest, so the version snapshot remains
part of each run's provenance and must be regenerated after an explicit lock or
image update.
