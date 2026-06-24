# AGENT.md — `uav_sf` 工作指南（给编码 Agent）

> 这是 `uav_sf` 仓库的 onboarding 文档。**新会话先读这一份**，再读 `docs/M0.md`、`docs/M1.md` 和叙事 `docs/differential-fuzzing-learned-uav-controllers.md`。
> 目的：把已踩过的坑、已固定的版本、已验证的事实集中记下，让你不必从零重新摸索。

---

## 1. 这个项目是什么

差分场景模糊测试：在**同一 PX4 固件、同一机架、同一任务**下，把**经典控制器**当作**内建差分 Oracle**，搜索"经典守得住、学习型守不住"的场景，发现学习型 UAV 飞控特有的失效。第一版被测对象是 **RAPTOR**（`mc_raptor`，免训、开箱即用的四旋翼基础策略），跑在 **PX4 SITL**，**不依赖真机**。

判失败的判据（四象限，只报一类）：**当且仅当经典 safe 且 RAPTOR unsafe** → primary bug。

---

## 2. 当前进度与范围纪律（重要）

| 里程碑 | 状态 | commit | 内容 |
|---|---|---|---|
| Phase 1 环境 | ✅ | `62d0383` | Docker + `ubuntu:24.04` 容器 + RAPTOR SITL build |
| M0 bring-up | ✅ | `b1be614` | 经典起飞→切 RAPTOR→ulog；stale-setpoint guard 发现 |
| M1 Oracle MVP | ✅ | `6c944b9` | X500 v2、offboard 任务、指标、四象限 runner、锚点 θ |
| M2 搜索 | ⬜ 下一步 | — | NSGA-II / MAP-Elites（**未开始**） |
| M3 评估 | ⬜ | — | baseline / 消融 / 失败分类 / 重复 |

**范围纪律（每轮严格遵守）**：
- **只做当前里程碑，做完即止**，不要顺手开始下一个。M1 完成后**不要**自己开 M2 搜索器。
- 任务边界由分配你的 prompt 定义；不确定就停下问，不要扩张 scope。
- 部分完成也要**固化、提交、写清现状与阻塞点**，不要把半成品留在未跟踪状态。

---

## 3. 硬件与环境

- **宿主**：Jetson AGX Orin 64GB，**L4T 36.7 ≈ Ubuntu 22.04，arch = aarch64/arm64**。角色仅为 **Docker host**，不要破坏性改动宿主已有的 PX4/ROS 2/Gazebo。
- **容器**：镜像 `uav_sf:phase1`（`FROM ubuntu:24.04`，arm64）。一切构建/运行在容器内。Docker Engine 29.3.0，data-root 已迁到 `/mnt/nvme/docker`。
- **CPU-only**：RAPTOR=RLtools（2084 参数）在 SITL 进程里跑，**不吃 GPU**；GPU 只训练才用，本阶段免训。容器里**不要**折腾 CUDA。
- **arm64 警告**：很多教程默认 x86_64；选镜像/装 apt 包/装 ROS 2 时确认 arm64 可用。
- 工作区：`/mnt/nvme/uav_sf`。当前 shell 可能未继承 docker 组：用 `sg docker -c '...'`。

---

## 4. 软件栈与已固定版本

- **PX4**：`main` 固定 **`3042f906abaab7ab59ae838ad5a530a9ef3df9a6`**（v1.18 alpha）。RAPTOR 只在 `main`，**不在 v1.17**。源码在 `external/PX4-Autopilot`（**gitignored**，可再生成）。
- **ROS 2**：Jazzy（匹配 24.04）+ `px4_msgs`，工作区 `ros2_ws`（**gitignored**）。
- **DDS 桥**：Micro-XRCE-DDS-Agent，`MicroXRCEAgent udp4 -p 8888`。
- **仿真器**：**SIH 为主**（headless、lockstep、确定性、最快）；Gazebo 仅少量可视化。
- **机架**：**X500 v2**，在 SIH 里用参数近似（见 §6）。

---

## 5. 必须知道的关键事实（重新发现很贵，直接用）

1. **RAPTOR 观测误差裁剪（决定整个搜索策略）**：`src/modules/mc_raptor/mc_raptor.hpp:115-116` 写死 `max_position_error=0.5`、`max_velocity_error=1.0`；`mc_raptor.cpp:388-401` 在策略推理前把 position error 裁到 ±0.5 m、velocity error 裁到 ±1.0 m/s。**含义：按 setpoint 幅度攻击是徒劳的**（>0.5 m 的误差在策略眼里都一样）。要压 RAPTOR 得攻**裁剪管不到的维度**：状态估计污染（尤其姿态/角速率这两个观测通道未见被裁剪）、物理参数失配（plant 非观测）、时序/瞬态。
2. **stale/missing setpoint guard**：缺/陈旧 setpoint 时 RAPTOR 200 ms 超时后合成"当前位姿 hold"喂策略（finite，不是 NaN）。**单纯停发 setpoint 触发不了失败**。`actuator_motors` 的 NaN 只出现在**未用通道 `control[4..11]`**（PX4 sentinel），active `control[0..3]` 正常时 0 NaN。
3. **RAPTOR external mode**：`mode_id=23`。headless 切换用 `MAV_CMD_DO_SET_MODE`，custom_mode 编码 **main=4, sub=11**（`custom_mode=184811520=0x0B040000`）。
4. **频率对齐**：RAPTOR 训练频率 100 Hz。`IMU_GYRO_RATEMAX` 必须是 100 的整数倍——用 **400**（force_sync_native=4），**不要 250**（2.5x，会告警）。
5. **故障注入的 SIH 限制**：`SYS_FAILURE_EN=1` 启用，停电机需 `CA_FAILURE_MODE=1`，用 `failure` 命令 / `MAV_CMD_INJECT_FAILURE`。但官方说 failure injection "需仿真器支持、在 Gazebo Classic 支持"——**SIH 是否支持电机/传感器故障未验证**。**风用 `SIH_WIND_N`/`SIH_WIND_E`、质量/惯量用 `SIH_MASS`/`SIH_IXX/IYY/IZZ`，不走 failure 插件**。
6. **DDS 输出 topic 带版本号**：本环境是 `/fmu/out/vehicle_status_v4`、`/fmu/out/vehicle_local_position_v1`（不是无后缀名）。
7. **rcS CWD 坑**：`make px4_sitl_raptor_sih sihsim_quadx` 生成的 run 命令从错误子目录启动、找不到 `etc/init.d-posix/rcS`。**用直接 launch**：在 `build/px4_sitl_raptor_sih` 下 `PX4_SIMULATOR=sihsim PX4_SIM_MODEL=sihsim_quadx ./bin/px4 .`。
8. **确定性噪声地板**：SIH lockstep，但**非 bit-exact**。同 θ 重复跑：姿态 max 差 ~1°、tracking RMS 差 ~0.04 m。**任何分歧/失败信号必须高过这个地板**。
9. **常用参数**：`NAV_DLL_ACT=0`、`COM_DISARM_LAND=-1`、`COM_RC_IN_MODE=4`、`COM_RCL_EXCEPT=8`、`MC_RAPTOR_ENABLE=1`、`MC_RAPTOR_OFFB=0`、`MC_RAPTOR_INTREF=0`(hold)/`1`(Lissajous)。
10. **RAPTOR 确实跟踪外部 setpoint**：`MC_RAPTOR_OFFB=0` 下，持续发布**新鲜 finite** `trajectory_setpoint`，RAPTOR 会跟踪移动目标（M1 已验证），无需 `OFFB=1`。

---

## 6. 仓库布局与约定

```
uav_sf/
├─ AGENT.md                       # 本文件
├─ README.md                      # 各阶段概览
├─ docker/                        # Dockerfile / build.sh / run.sh
├─ boards/px4/sitl/
│  └─ raptor_sih.px4board         # SIH + RAPTOR 板级（default SITL + RAPTOR − Gazebo）
├─ config/
│  ├─ px4/init.d-posix/airframes/
│  │  └─ 10046_sihsim_x500_v2     # SIH-X500 v2 airframe（tracked）
│  └─ m1_anchor_*.json            # 手工固定 θ 定义
├─ scripts/                       # 见下
└─ docs/                          # M0.md / M1.md / *.ulg / *.json / *.log 证据
```

关键脚本：`build_px4_raptor_sih.sh`、`install_raptor_sih_board.sh`、`install_m1_sih_x500.sh`、`m0_set_raptor_mode.py`、`m0_ulog_sanity.py`、`m1_offboard_task.py`、`m1_metrics.py`、`m1_compare.py`、`m1_diff_runner.py`、`m1_inject_failure.py`。

**铁律 — 可再生成资产的入库方式**：`external/PX4-Autopilot` 与 `ros2_ws` 被 `.gitignore`。任何对它们的改动（板级配置、airframe、PX4 源码补丁）**必须以 tracked 文件 + installer 脚本**形式入库（见 `boards/`+`install_raptor_sih_board.sh`、`config/`+`install_m1_sih_x500.sh`），**不要**依赖未跟踪文件，否则复现会丢。

---

## 7. 怎么构建与运行

进容器干活的统一模式：
```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc "cd /workspace && <cmd>"'
```

构建（含安装 tracked 板级/airframe 到 ignored 树）：
```bash
./scripts/build_px4_raptor_sih.sh
```

跑一个固定 θ 端到端（经典 + RAPTOR 各一遍 + 四象限）：
```bash
source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash
python3 -m pip install --break-system-packages pymavlink pyulog numpy -q
./scripts/m1_diff_runner.py --theta config/m1_anchor_sine_5hz.json --skip-build
```
另起 DDS agent：`MicroXRCEAgent udp4 -p 8888`。SIH 用 §5.7 的直接 launch。

---

## 8. 工作纪律（每轮遵守）

- **动宿主系统前先告知**（装包、改 docker daemon、改宿主 PX4/ROS 2）。能进容器就进容器。
- **版本/commit/seed/θ/阈值全部 pin 并写进配置与文档**；不要用魔法数字。
- **关键命令的真实输出留痕进 `docs/`**，不要只说"成功了"。失败/null 结果**如实记录**，不要为"造出想要的结果"去硬编旁路或伪造。
- **遇到与 §5 关键事实冲突的现象，停下来如实报告**，不要硬编一个看似能过的旁路。
- 提交前过 `python3 -m py_compile`、`bash -n`、JSON `jq` 校验、`git diff --cached --check`。
- 中文汇报；命令/路径/参数保持英文原样。
- **完成当前里程碑即止，不要越界到下一个。**