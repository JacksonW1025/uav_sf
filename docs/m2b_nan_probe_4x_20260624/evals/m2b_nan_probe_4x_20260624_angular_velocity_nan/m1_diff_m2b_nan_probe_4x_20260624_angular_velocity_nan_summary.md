# M1 diff summary: m2b_nan_probe_4x_20260624_angular_velocity_nan

quadrant: too_hard_not_bug
primary_bug: false

## safe
classical_safe: false reasons=['attitude_diverged', 'controller_mode_not_confirmed', 'failsafe', 'ground_contact', 'task_not_complete', 'tracking_error_max', 'tracking_error_rms', 'unexpected_disarm']
classical_usable_for_primary: false infrastructure=['classical_nav_state_exit', 'offboard_control_signal_lost']
raptor_safe: false reasons=['attitude_diverged', 'controller_mode_not_confirmed', 'failsafe', 'ground_contact', 'task_not_complete', 'tracking_error_max', 'tracking_error_rms', 'unexpected_disarm']

## key metrics
classical tracking max/rms/final: 18.51139474334523 / 17.443340914101714 / 18.024028533931705
raptor tracking max/rms/final: 19.314964887479835 / 14.755705565458877 / 19.24290061091833
classical roll_pitch_max_deg: 107.90117335463835
raptor roll_pitch_max_deg: 179.99872436822142
classical angular_rate_max_rad_s: 0.32548483241944987
raptor angular_rate_max_rad_s: 0.5167205956081913
divergence_quality: 0.0
time_to_divergence_s: 2.9013904109589035
