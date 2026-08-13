# Concurrency qualification

Formal concurrency is frozen at four attempts. Each slot has its own PX4
instance and system identity, Gazebo partition, ROS domain, XRCE Agent port,
MAVLink ports, run and temporary directories, process group, and CPU set.

The four-way isolation trial ran Legacy Offboard trajectory, Legacy Offboard
body-rate, Dynamic External Mode, and Mode Executor concurrently. All four
were accepted by runtime semantics and admitted by the Evidence Gate; all
ULogs had continuous RouteObservability sequences. Clock uncertainties were
3.102, 6.721, 4.417, and 1.275 ms. Central Gazebo real-time factors were
0.998754, 0.998915, 0.998737, and 0.998738. System identities 1–4, ROS domains
40–43, and Agent ports 8888–8891 remained distinct, and cleanup left no study
containers running.

At concurrency six, five attempts remained admissible but one was rejected
because clock uncertainty exceeded the frozen 20 ms Gate. Several central
real-time factors also fell below the four-way trial. The formal setting is
therefore four, using CPU sets `0-2`, `3-5`, `6-8`, and `9-13`, with 24 GiB
per attempt. The clock bound is not relaxed to admit concurrency six.
