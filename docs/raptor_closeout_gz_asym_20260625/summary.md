# RAPTOR closeout Gazebo plant asymmetry

Each row is one modified Gazebo x500 plant flown by both classical and RAPTOR.

| case | quadrant | primary_bug | classical safe/reasons | RAPTOR safe/reasons | track max C/R | roll max C/R | rate max C/R |
|---|---|---:|---|---|---:|---:|---:|
| motor0_080 | boring_both_safe | false | true/- | true/- | 1.39/1.63 | 9.22/9.21 | 0.372/0.361 |
| motor0_065 | boring_both_safe | false | true/- | true/- | 1.62/1.79 | 12.2/12.8 | 0.579/0.646 |
| motor0_050 | too_hard_not_bug | false | false/angular_rate_diverged,attitude_diverged,ground_contact,task_not_complete,tracking_error_max,tracking_error_rms | false/angular_rate_diverged,ground_contact,task_not_complete,tracking_error_max,tracking_error_rms | 4.6/4.65 | 79.7/59.4 | 30.4/16.1 |
| com_x_002 | boring_both_safe | false | true/- | true/- | 1.62/1.55 | 12/11.7 | 0.673/0.579 |
| com_x_004 | boring_both_safe | false | true/- | true/- | 1.59/1.65 | 12.1/11.2 | 0.651/2.09 |
| com_x_006 | boring_both_safe | false | true/- | true/- | 1.7/1.6 | 13.3/11.3 | 0.532/0.568 |
