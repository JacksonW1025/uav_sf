# Gate A 预注册阈值（Stage 2）

- 冻结时间（UTC）：2026-07-12T09:46:55Z
- 适用对象：pair1，固定 `theta=rp48_62_rate2p45_2p90_w6_r6_f045`、`seed=20262001`，`timing_mode=hardened`，`PX4_SIM_SPEED_FACTOR=1.25`，CPU 8–11，串行 10 个 valid run。
- legacy 对照：`stage0_legacy/gate_results.json` 中 pair1 的 10 个 valid run。
- 冻结分类器：`scripts/fuzz1c_decontam_analyze.py` SHA-256 `11568fe11729751fa6952a90e472d91ccf8d76e5765e22802c237dbe051adc4a`；严重度证据/分类调用沿用 `scripts/fuzz1c_severity_scan.py` SHA-256 `301955cc3aba9a4efef9d6491dcb9a095a554edc3948b64a980450b399fc24dd`，不得改判据。

## Valid run

run 必须同时满足：`run_error=null`、task exit code 0、state trigger fired、mode confirmed、存在 ULOG、分类器完成、`post_switch_failsafe=false`。无效 run 原记录保留并补位，直到 10 个 valid 或 Gate A 总尝试达到 30。

## Timing 门

legacy pair1 trigger elapsed span = `2.223921 s`。hardened 10-run span 必须 `<=0.2223921 s`，即至少缩小 10×。

## State-dispersion 门

状态向量固定为 `[roll_deg, pitch_deg, angular_rate_norm_rad_s]`。用 10 个样本、`ddof=1` 的三维样本协方差矩阵计算 generalized variance `det(cov)`。

- legacy `det(cov)=0.0025654189993854037`；hardened 必须 `<=0.00025654189993854037`（至少缩小 10×）。
- 同时 hardened 三个分量的样本标准差不得超过 legacy：roll `0.33958803 deg`、pitch `3.77160100 deg`、`||omega||` `0.06598521 rad/s`。

Timing 门与 state-dispersion 门必须同时通过。否则不得进入 Stage 3；按顺序考虑 CPU pinning（已从 baseline 起固定）、DDS 配置、lockstep 显式开启、主机隔离。当前 PX4 build 已含 `-DENABLE_LOCKSTEP_SCHEDULER`，故不得把“重新打开同一个 flag”冒充新增杠杆。
