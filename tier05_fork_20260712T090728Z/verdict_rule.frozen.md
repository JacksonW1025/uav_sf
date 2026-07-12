# Tier 0.5 FORK 预注册判定规则（冻结）

- 冻结时间（UTC）：2026-07-12T10:16:10Z
- 冻结发生在任何 Stage 3 run 之前；本文件从此只读。
- 总 eval 上限：160。已用：Stage 0=20、Stage 1 smoke=4、Stage 2=20，共 44；Stage 3 初始 60，最多可追加 56。
- 执行条件：全程串行，CPU 8–11，`PX4_SIM_SPEED_FACTOR=1.25`，`timing_mode=hardened`。
- 冻结分类器：`scripts/fuzz1c_decontam_analyze.py` SHA-256 `11568fe11729751fa6952a90e472d91ccf8d76e5765e22802c237dbe051adc4a`；证据/严重度调用沿用 `scripts/fuzz1c_severity_scan.py` SHA-256 `301955cc3aba9a4efef9d6491dcb9a095a554edc3948b64a980450b399fc24dd`。
- Gate A 已通过，阈值与结果见 `gate_a_rule.prefrozen.md`；Stage 3 不再改 timing 实现、QoS、PX4 binary 或分类器。

## 固定配置与历史分布

1. `dense_low_modal`：飞行参数 scenario key `34.5|42.5|0.6278|1.3278|0|3.1614|0.25|0|0.09`，seed `2026062942`，复用 `switch_severity_dense_sweep_20260630_wind_m_s_0_s2026062942.json`。当前结构化产物 outcome 为 S3=15/19、S0=4/19，modal=S3，flip=4/19；modal Wilson 95% upper=`0.9149232336708375`，flip CI=`[0.08507676632916253,0.43334278443814167]`。
2. `pair4`：`rp36_44_rate1p55_2p15_w3_r4_f038`，seed `20261902`，modal=S3。历史 R4 2/3 S3、Stage 0 legacy 10/10 S3，合计 modal=12/13、flip=1/13；modal upper=`0.9862895787574435`，flip CI=`[0.013710421242556586,0.3331395092109959]`。
3. `pair1`：`rp48_62_rate2p45_2p90_w6_r6_f045`，seed `20262001`，modal=S3。历史 R4 3/3 S3、Stage 0 legacy 10/10 S3，合计 modal=13/13、flip=0/13；modal upper=`1.0`（浮点实现可为 0.9999999999999999），flip CI=`[0,0.22809537235419838]`。

密扫前提：`81 strict` 与当前 `87 S3` 分别是 `primary_bug` 与 mc_nn outcome severity，语义不同；本实验的 flip 定义是 outcome class 偏离 modal，故使用 S3=87 的字段。若最终审计推翻这一字段语义，dense 证据作废，最终不得给无保留 α/β，只能 γ 或明确降级。

## Run 有效性与 flip

valid 必须同时满足：`run_error=null`、task exit 0、state trigger fired、mode confirmed、ULOG 存在、分类完成、`post_switch_failsafe=false`。无效 run 全部保留并按同配置补位；连续 5 次环境级失败则停止并判 γ。每配置先取得 20 个 valid run。

outcome class 取冻结分类器 S0–S4。上述三个配置的 modal 均为 S3；任何非 S3 valid outcome 均记 1 flip。

## 统计

- Wilson CI：two-sided 95%，`z=1.959963984540054`。
- 每配置报告 outcome 计数与 flip rate Wilson CI。
- 成对一致率：所有 valid run 两两组合中 outcome 相同的比例，并给 Wilson CI；注明 pair 并非独立样本。
- β 的零翻转强度：`P0=product_i(pu_i ** n_i)`，`pu_i` 为上列历史 modal Wilson upper。

## 残余协变量关联门

对每配置分别取 `[trigger_elapsed_s, roll_deg, pitch_deg, angular_rate_norm_rad_s]`。以该配置全部 valid run 的 median 与 `1.4826*MAD` 标准化（MAD=0 时退回样本标准差；仍为 0 则该维记 0），每 run 的 residual score 为四维 `abs(z)` 最大值，`score>3.5` 为 outlier。

flip 与 residual 的“显著关联”定义为任一条件成立：(a) 所有 flip 都是 outlier；(b) flip×outlier 的 two-sided Fisher exact `p<0.05`；(c) flip/non-flip residual score 的 two-sided Mann–Whitney `p<0.05`。若成立，不能判 α，回 Stage 2 收紧；若预算不足则 γ。

## 三态规则

- **β**：全部 Stage 3 valid run 零 flip，且 `P0<0.01`。初始 20+20+20 时预期 `P0=0.12816870967701496`，不足；向信息量最大的 `dense_low_modal` 追加 +20，仍不足则再 +20。dense n=60、pair4/pair1 各 n=20 时预期 `P0=0.0036573646470336695`。
- **α**：合计 flip `>=3`；每个配置的 Stage 3 flip-rate Wilson CI 与上列对应历史 flip CI 有非空交集；且残余协变量关联门不触发。
- **自适应 1–2 flip**：对出现 flip 的每个配置追加 +20；若因此将超过总预算，跑到预算上限。之后重新应用 α/γ，不能转用 β（已有 flip）。
- **γ**：其余一切，包括 Gate A 后硬化退化、统计不相容、残余协变量关联、dense 语义前提被推翻、环境失败或预算耗尽。

规则优先级：先 valid/环境与 residual 门，再 α/β，最后 γ。任何 run 开始后不得修改本文件。
