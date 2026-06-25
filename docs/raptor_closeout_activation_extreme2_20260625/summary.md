# RAPTOR closeout activation transient

Classical and RAPTOR fly the same finite setpoint; approach cases enter classical Offboard before RAPTOR activation.

| case | compare quadrant | flight quadrant | activation bug | pre-switch roll C/R | pre-switch rate C/R | safe C/R | track max C/R | reasons C/R |
|---|---|---|---:|---:|---:|---|---:|---|
| circle_75deg | too_hard_not_bug | boring_both_flight_safe | false | 43/42.8 | 2.24/2.36 | false/false | 9.73/8.98 | tracking_error_max,tracking_error_rms/task_not_complete,tracking_error_max,tracking_error_rms |
