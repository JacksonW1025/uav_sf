# RAPTOR closeout activation transient

Classical and RAPTOR fly the same finite setpoint; approach cases enter classical Offboard before RAPTOR activation.

| case | compare quadrant | flight quadrant | activation bug | pre-switch roll C/R | pre-switch rate C/R | safe C/R | track max C/R | reasons C/R |
|---|---|---|---:|---:|---:|---|---:|---|
| circle_60deg | too_hard_not_bug | boring_both_flight_safe | false | 37.6/34.9 | 1.7/1.71 | false/false | 6.29/6.29 | tracking_error_max,tracking_error_rms/task_not_complete,tracking_error_max,tracking_error_rms |
