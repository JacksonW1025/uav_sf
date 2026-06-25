# M2b-1 D3 Low-Noise Ratio Diagnostic

run_dir: `docs/m2b_1_diag_d3_ratio_20260624`
records: 20

## baseline RMS
- classical: mean=0.4853063463470485 range=0.424194048753274 stdev=0.16092589840959085
- raptor: mean=0.42382515598590975 range=0.24950823973899955 stdev=0.1155086920013371

## scenario ratios, tracking_error_rms_m
- baseline: classical_median=1.0272352814024788 raptor_median=1.0315943820133395 delta=0.0043591006108607555 fairness_all_true=None
- velocity_noise_y0308: classical_median=0.7778318806088443 raptor_median=1.113736838281896 delta=0.3359049576730516 fairness_all_true=True
- gyro_bias_x0153: classical_median=1.102300009313772 raptor_median=1.1872735642630692 delta=0.08497355494929715 fairness_all_true=True
- velocity_delay_030ms: classical_median=0.9647472697689271 raptor_median=1.2363708840060714 delta=0.2716236142371443 fairness_all_true=True
