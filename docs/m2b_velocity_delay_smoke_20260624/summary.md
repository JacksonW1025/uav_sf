# M2b-1 Velocity Delay Verification

run_dir: `docs/m2b_velocity_delay_smoke_20260624`
mitigation_switch_found: false
mitigation_note: PX4 mc_raptor at 3042f906 has no vehicle_acceleration/sensor_accel subscription and no S2 accelerometer-IIR parameter or code path; this run measures the default no-IIR module.

## results
- delay=20ms quadrant=boring_both_safe primary=False quality=0.0 fair_state=True classical_rms=0.3651840959468142 raptor_rms=0.33201332799063005 theta=`docs/m2b_velocity_delay_smoke_20260624/theta/m2b_velocity_delay_smoke_20260624_vdelay_020ms.json` fairness=`/workspace/docs/m2b_velocity_delay_smoke_20260624/evals/m2b_velocity_delay_smoke_20260624_vdelay_020ms/m2b_1_fairness_m2b_velocity_delay_smoke_20260624_vdelay_020ms.json`
