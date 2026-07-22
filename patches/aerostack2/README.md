# Aerostack2 bounded SITL compatibility patch

`px4_msgs_current_compatibility.patch` is applied only to the exact
`as2_platform_pixhawk` commit frozen by W1. It removes aliases no longer present
in `VehicleAttitudeSetpoint` and maps current GPS and battery observation fields
to their ROS counterparts with the current units.

The patch changes only build compatibility and observation topic mapping. It
does not change mission logic, route selection, setpoint selection, mode
requests, fallback, behavior cancel/completion, controller lifecycle, or writer
behavior. The setup script first verifies the exact upstream commit, then
applies the tracked patch. Formal runtime use requires the W1 compatibility
amendment and patch hash to be pushed to `origin/main`.
