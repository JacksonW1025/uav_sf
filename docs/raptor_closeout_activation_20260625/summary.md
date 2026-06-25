# RAPTOR closeout activation transient

Classical and RAPTOR fly the same finite setpoint; approach cases enter classical Offboard before RAPTOR activation.

| case | compare quadrant | flight quadrant | activation bug | pre-switch roll C/R | pre-switch rate C/R | safe C/R | track max C/R | reasons C/R |
|---|---|---|---:|---:|---:|---|---:|---|
| hover_activation | boring_both_safe | boring_both_flight_safe | false | 1.76/2.33 | 0.309/0.202 | true/true | 0.837/0.788 | -/- |
| circle_30deg | too_hard_not_bug | boring_both_flight_safe | false | 15.7/18.1 | 0.619/0.608 | false/false | 3.62/3.79 | tracking_error_rms/tracking_error_rms |
| circle_45deg | too_hard_not_bug | boring_both_flight_safe | false | 26.3/25.2 | 1.13/1.05 | false/false | 4.14/4.17 | tracking_error_max,tracking_error_rms/tracking_error_max,tracking_error_rms |
| circle_45deg_wind | too_hard_not_bug | boring_both_flight_safe | false | 29.7/19.3 | 1.03/1.18 | false/false | 4.11/4.15 | tracking_error_max,tracking_error_rms/task_not_complete,tracking_error_max,tracking_error_rms |
