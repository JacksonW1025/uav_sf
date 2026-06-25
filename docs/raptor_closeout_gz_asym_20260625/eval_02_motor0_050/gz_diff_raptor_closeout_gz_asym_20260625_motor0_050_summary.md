# M1 diff summary: raptor_closeout_gz_asym_20260625_motor0_050

quadrant: too_hard_not_bug
primary_bug: false

## safe
classical_safe: false reasons=['angular_rate_diverged', 'attitude_diverged', 'ground_contact', 'task_not_complete', 'tracking_error_max', 'tracking_error_rms']
classical_usable_for_primary: false infrastructure=[]
raptor_safe: false reasons=['angular_rate_diverged', 'ground_contact', 'task_not_complete', 'tracking_error_max', 'tracking_error_rms']

## key metrics
classical tracking max/rms/final: 4.600404510652746 / 3.0698218078293786 / 2.707752868925852
raptor tracking max/rms/final: 4.652399478749715 / 3.530802187071478 / 3.8413102951854734
classical roll_pitch_max_deg: 79.73457565277947
raptor roll_pitch_max_deg: 59.38877910941148
classical angular_rate_max_rad_s: 30.3898334081546
raptor angular_rate_max_rad_s: 16.078313060812192
divergence_quality: 0.0
time_to_divergence_s: 0.0
