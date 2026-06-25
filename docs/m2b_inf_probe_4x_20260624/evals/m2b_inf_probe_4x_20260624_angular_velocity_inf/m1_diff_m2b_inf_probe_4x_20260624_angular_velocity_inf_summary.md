# M1 diff summary: m2b_inf_probe_4x_20260624_angular_velocity_inf

quadrant: too_hard_not_bug
primary_bug: false

## safe
classical_safe: false reasons=['controller_mode_not_confirmed', 'failsafe', 'ground_contact', 'task_not_complete', 'tracking_error_max', 'tracking_error_rms', 'unexpected_disarm']
classical_usable_for_primary: false infrastructure=['classical_nav_state_exit', 'offboard_control_signal_lost']
raptor_safe: false reasons=['controller_mode_not_confirmed', 'failsafe', 'ground_contact', 'task_not_complete', 'tracking_error_max', 'tracking_error_rms', 'unexpected_disarm']

## key metrics
classical tracking max/rms/final: 116.55513360062406 / 89.48212293959895 / 116.21363115314867
raptor tracking max/rms/final: 46.94778379752172 / 43.127668657398566 / 46.19736502138785
classical roll_pitch_max_deg: 14.991119879475784
raptor roll_pitch_max_deg: 39.02430216703404
classical angular_rate_max_rad_s: None
raptor angular_rate_max_rad_s: None
divergence_quality: 0.0
time_to_divergence_s: 3.4525993150684933
