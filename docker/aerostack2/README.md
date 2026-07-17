# Aerostack2 spike container boundary

This profile mirrors the Ubuntu 22.04 / ROS 2 Humble environment required by
the selected Aerostack2 commit. It is deliberately separate from the canonical
Jazzy workspace. The profile was not executed on the evaluation host because
the current user cannot access `/var/run/docker.sock`; the ignored host Humble
workspace is the recorded runtime path instead.
