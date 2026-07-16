# NEW_NARRATIVE_v4

# Testing Route-Replacing Authority Transitions in PX4

## 0. 本文叙事是什么

PX4 中的飞行控制权可能来自飞手、内部任务与飞行模式、Offboard 程序、ROS 2 External Mode、飞控内部注册式控制器以及 failsafe。不同机制可以在位置、速度、姿态、角速度、推力/力矩或执行器层级接入，并改变实际参与控制的 setpoint producer、controller graph 和 actuator writer。

本文关注其中一类边界清晰、契约一致且具有安全意义的运行时变化：

> **Route-replacing authority transition：某个飞行关键控制域的主要控制路径从 Route A 转移到 Route B，旧路径需要撤销，新路径需要安装，或者在故障后恢复预期安全路径。**

一条控制路径表示为：

```text
Route = (
    authority identity,
    setpoint producer,
    setpoint level,
    controller graph,
    actuator writer,
    fallback route
)
```

本文的核心研究问题是：

> 当 PX4 声明主要控制路径已经从 Route A 转移到 Route B 时，旧路径是否及时撤销，新路径是否完整安装，转换窗口是否满足预期的独占性与连续性，故障后安全路径是否完整恢复？

本文建立两个并列的 subject family：

1. **伴随计算机侧的外部自治路径交接**：PX4 内部路径与 ROS 2 Offboard、Dynamic External Mode 之间的交接，其中 External Mode 是主要对象，Offboard 是现实 baseline；
2. **飞控内部的控制器路径交接**：经典级联控制与使用 External Component Registration 接入的学习型控制路径之间的交接，例如 mc_nn 与 RAPTOR 类路径。

两个 family 分别发生在控制栈的上游和下游，却共享同一组软件契约：

```text
Old Route Revocation
        ↓
New Route Installation
        ↓
Exclusive and Continuous Transition
        ↓
Fallback and Recovery
```

本文提出的上位抽象是 **runtime authority reconfiguration**，正式测试范围限定为其中的 **route-replacing authority transitions**。长期共享控制、终端输出门控、飞行器构型转换以及同一路径内部的参数调整属于相邻问题，在本文中用于澄清边界，不进入主实验。

---

# 1. Motivation

## 1.1 上层自主软件会真实触发控制路径交接

上层导航、任务、行为树和控制软件经常运行在伴随计算机上。它们持续产生轨迹和运动目标，也会在任务阶段、组件故障、人工接管和安全恢复过程中改变由谁向 PX4 提供飞行关键控制命令。

需要区分两类上层事件：

```text
轨迹或目标更新
    → 同一 producer 在同一接口上继续发布
    → 通常不构成本文研究的交接

控制接口、模式或 controller owner 变化
    → 主要控制路径身份发生变化
    → 构成本文研究的交接
```

因此，上层软件在本文中承担两种角色：

1. **动力学上下文生成器**：产生转弯、加速、下降、跟踪、避障重规划等真实飞行状态；
2. **交接事件生成器**：产生外部自治进入/退出、任务取消、任务完成、进程故障、人工接管、failsafe 和恢复事件。

## 1.2 典型场景一：Takeoff → External Autonomy → RTL/Land

现实任务通常先使用 PX4 内部 Takeoff，再进入外部自治，任务完成后交回 PX4 的 RTL 或 Land：

```text
Internal Takeoff Route
        ↓
Offboard / External Mode Route
        ↓
Internal RTL or Land Route
```

MAVSDK 的官方 Offboard 示例就采用了内部起飞、启动 Offboard、停止 Offboard以及最终内部降落的完整流程。Mode Executor 的官方示例则显式编排：

```text
Takeoff → Custom External Mode → RTL → Wait Until Disarmed
```

这类任务天然包含多次交接，并要求：

- 起飞路径在外部路径接管时停止产生有效控制；
- 外部路径退出后不再影响后续 RTL/Land；
- 多次进入和退出后没有旧 setpoint、旧 controller state 或旧 module configuration 残留；
- 任务阶段边界发生在高速或转弯状态时，物理瞬态仍处于可接受范围。

## 1.3 典型场景二：Mode Executor 编排多个控制路径

Dynamic External Mode 支持由 Mode Executor 组织任务流程。一个现实任务可以包含：

```text
Takeoff
  → External Survey
  → External Tracking
  → Internal RTL
  → Land
```

或：

```text
Internal Mission
  → Custom External Behavior
  → Task Cancel
  → Hold / RTL
```

此类流程中的风险集中在异步边界：

- External A 完成与 External B 激活同时发生；
- External Mode 退出与 RC/GCS 模式请求同时发生；
- External Mode 激活期间触发 failsafe；
- failsafe 清除后 executor 尝试恢复任务；
- node restart 后旧 executor 状态与 PX4 当前模式不一致。

模式状态机可能给出一个明确结果，producer、消息新鲜度和控制模块却可能停留在不同生命周期阶段。

## 1.4 典型场景三：外部模式替换 PX4 内部安全模式

Dynamic External Mode 可以替换 PX4 内部模式，例如由伴随计算机实现自定义 RTL：

```text
RTL Requested
      ↓
External Custom RTL
      ↓ node/process failure
Internal PX4 RTL Fallback
```

这个流程包含连续两次安全关键交接：

1. 原任务路径交给外部 RTL；
2. 外部 RTL 失效后交给内部 RTL。

此时仅观察 `nav_state = RTL` 无法确认真正执行的是哪条 RTL 路径。测试需要进一步确认：

- 外部 RTL 的 producer 是否已经获得权限；
- 内部 RTL 是否按设计被替换或保留为 fallback；
- 外部 RTL 失效后内部位置、姿态、角速度和 allocation 链是否完整恢复；
- 最后一条外部 setpoint 是否在 fallback 后继续作用；
- 重复进入时是否复用了上一次外部 RTL 的状态。

## 1.5 典型场景四：伴随计算机故障触发外部到内部回退

伴随计算机上的自主程序可能发生：

- ROS 2 node 崩溃；
- callback stall；
- executor starvation；
- CPU/GPU 过载；
- DDS 延迟、丢包或重连；
- planner/controller 死锁；
- heartbeat 与 setpoint stream 单独停止；
- process restart。

Offboard 依靠持续 proof-of-life 维持外部控制，超时后进入配置的 fallback。External Mode 则具有注册、激活、unresponsive detection、mode replacement 和 executor 等更显式的生命周期机制。

这类场景的重要问题包括：

```text
External Route Active
        ↓ partial or total failure
Failure Detection
        ↓
Old Route Revocation
        ↓
Safe Route Installation
        ↓
Physical Recovery
```

风险可能表现为：

- 模式已回退，旧 setpoint 仍被消费；
- heartbeat 存活，实际 setpoint 已停止；
- lifecycle heartbeat 消失，setpoint producer 仍持续发布；
- fallback mode 已声明，内部 controller graph 尚未完整恢复；
- 外部和内部 writer 出现短时重叠；
- 中间出现没有有效命令源的 gap；
- 切回安全路径时 actuator output 出现不连续。

## 1.6 典型场景五：飞手或 GCS 中断外部自治

飞手和 GCS 需要能够随时中断外部任务：

```text
External Survey / Tracking
          ↓ RC or GCS request
Internal Position / Hold / RTL
```

这种交接具有很强的安全要求：

- 人工接管请求应及时生效；
- 外部 producer 即使继续发送消息，也不应继续影响飞行；
- PX4 内部路径应从有效状态开始接管；
- 后续重新进入外部模式应重新经过准入和安装流程；
- RC、GCS、executor 与 failsafe 的并发请求应得到唯一、可解释的最终控制路径。

## 1.7 典型场景六：高性能控制器向机载安全控制器回退

无人机系统可能在伴随计算机或边缘设备上运行 MPC、优化控制或学习型控制器，并保留机载经典控制器作为安全路径：

```text
External / Learned High-Performance Controller
                ↓ failure or policy decision
Onboard Classical Safety Controller
```

PX4 内部的 mc_nn 和 RAPTOR 类模块进一步将学习型控制器部署到飞控内部，并通过 External Component Registration 注册成可选择的模式。它们可以替换经典级联的部分或全部组件，甚至直接发布 actuator motor command。

这类交接需要验证：

- 经典 controller 是否及时停止或被绕过；
- direct actuator writer 是否在正确时刻获得独占权限；
- learned controller 失败后经典级联是否完整恢复；
- 经典 controller 的积分器、setpoint 和状态是否适合直接接管；
- 网络或策略恢复后是否产生反复切换；
- 同一 registration facility 在伴随计算机和飞控内部实现中是否具有共同失效模式。

## 1.8 为什么上层导航和行为栈值得进入实验

真实上层软件并非论文的正确性测试对象。它们提供三项价值：

1. **真实任务阶段**：Takeoff、Search、Track、Return、Land 和 Cancel；
2. **真实交接触发条件**：任务完成、任务失败、人工接管、通信故障和安全管理；
3. **真实切换状态**：高速飞行、转弯、升降、接近控制饱和和障碍触发重规划。

普通 waypoint 更新、同一 producer 内部的 planner 切换以及同一路径上的目标改变不会自动计为 authority transition。是否进入测试范围，由 PX4 运行时 Route 是否改变决定。

## 1.9 现有测试缺口

官方示例和已有测试通常能够验证：

- 模式能否注册；
- 模式能否进入；
- 正常行为能否执行；
- node loss 是否触发某个 fallback；
- mode replacement 和 executor 能否完成基本流程。

本文进一步检查：

> **声明的模式和控制路径，是否与运行时真正活动的 producer、setpoint、controller graph、actuator writer 和 fallback route 一致。**

典型缺口包括：

- 当前 writer 身份是否符合模式声明；
- 旧 producer 是否在交接后继续发布或继续被消费；
- 新 producer 是否在模式声明变化前提前生效；
- controller enable/bypass 配置是否匹配 setpoint level；
- heartbeat、setpoint freshness 和 mode lifecycle 是否同步；
- repeated entry 后是否残留旧 route；
- fallback 是否恢复完整控制链；
- 并发 authority event 是否产生唯一结果；
- 物理异常是否源于 route mismatch，而非 controller 本身能力不足。

---

# 2. 研究对象层级

## 2.1 系统位置

本文研究层位于上层自主软件和最终执行器之间，跨越伴随计算机—飞控边界，并向下延伸到 PX4 内部 controller graph 与 actuator writer：

```text
┌──────────────────────────────────────────────────────┐
│ Mission / Navigation / Planning / Behavior Tree      │
│ 产生任务阶段、轨迹、取消、失败和恢复事件              │
│ 角色：上下文与事件生成器                               │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│ Companion-Side Autonomy                               │
│ Offboard Producer / External Mode / Mode Executor     │
│ 角色：外部控制路径实现                                 │
└─────────────────────────┬────────────────────────────┘
                          │ DDS / MAVLink
========================== PX4 =============================
                          │
┌─────────────────────────▼────────────────────────────┐
│ Commander / Mode Management / Failsafe                │
│ Registration / Admission / Activation / Replacement   │
│ 角色：控制平面，声明谁应当获得控制权                   │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│ Setpoint Routing / VehicleControlMode / uORB          │
│ Freshness / Module Enablement / Bypass                │
│ 角色：数据平面，将声明落实为运行路径                   │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│ Position → Attitude → Rate → Control Allocator        │
│ 或 Registered Learned Controller → Actuator Writer    │
│ 角色：可替换的 controller graph                        │
└─────────────────────────┬────────────────────────────┘
                          │
                  Actuator / Motor Output
```

## 2.2 控制平面

控制平面负责：

- 当前声明的 flight mode / nav state；
- 外部组件的注册和注销；
- arming requirement 与 admission；
- mode activation、deactivation 和 replacement；
- controller/setpoint configuration；
- RC/GCS/mode executor 请求的仲裁；
- 故障检测后的 fallback 选择；
- failsafe defer 与恢复策略。

核心组件包括：

- Commander；
- Mode Management；
- External Component Registration；
- Health and Arming Checks；
- Failsafe；
- Mode Executor；
- Mode Replacement；
- Vehicle Control Mode configuration。

## 2.3 数据平面

数据平面负责：

- 实际哪个 producer 发布 setpoint；
- setpoint 进入哪个 uORB topic；
- 消息是否新鲜并持续更新；
- 哪些位置、姿态、角速度控制模块处于有效状态；
- 哪些模块被绕过；
- 哪个模块向 torque/thrust 或 actuator topic 写入；
- Control Allocator 是否参与；
- actuator output 来自哪条路径。

本文的核心观察视角是：

```text
Declared Authority and Route
              vs
Observed Producer, Messages, Modules and Actuation
```

## 2.4 与上层算法和底层控制性能的边界

```text
上层自主算法
决定任务目标、轨迹与行为阶段
             ↓
本文研究层
决定谁在何时拥有哪一级控制路径，
旧路径何时撤销，新路径何时生效，
故障后哪条路径恢复
             ↓
控制器与飞行动力学
决定如何跟踪目标以及产生物理响应
```

本文不评价 planner 最优性、SLAM 精度、感知正确性或学习策略质量。控制器跟踪性能用于构建 baseline 和解释物理后果，主要 oracle 始终落在控制路径一致性上。

---

# 3. 测试对象

## 3.1 Subject Family A：伴随计算机侧外部自治路径交接

### 主要对象：Dynamic External Mode

Dynamic External Mode 将伴随计算机上的自定义飞行行为纳入 PX4 模式管理体系，包含：

- 动态注册；
- arming requirements；
- 显式激活与释放；
- setpoint type 声明；
- mode executor；
- mode replacement；
- failure handling；
- fallback 与恢复；
- 多个外部模式的组合和切换。

本文测试其完整 lifecycle 是否真正落实为运行时 route installation、revocation 和 restoration。

### 现实 baseline：ROS 2 Offboard

Offboard 是成熟且广泛使用的外部运动控制方式，支持通过持续 proof-of-life 和 setpoint stream 控制 PX4。它提供：

- 现实部署基础；
- 相对隐式的外部控制生命周期；
- timeout 与 fallback 机制；
- 与 External Mode 共享的 setpoint 层级；
- 可控的机制差分条件。

本文比较两种机制在相同轨迹、setpoint level、初始状态、故障时刻和 fallback 目标下的：

- activation latency；
- revocation latency；
- stale command window；
- overlap/gap；
- fallback correctness；
- repeated entry residue；
- physical recovery。

比较目标是识别通用外部控制边界问题和 External Mode 特有的注册/重配置问题。

### 典型 transition

```text
Internal → Offboard → Internal
Internal → External Mode → Internal
External A → External B
External Mode → Internal Fallback
External Replacement Mode → Original Internal Mode
External Mode → RC/GCS Requested Mode
```

## 3.2 Subject Family B：飞控内部控制器路径交接

主要对象是使用 External Component Registration 接入的飞控内部控制路径，例如：

- PX4 classic cascade；
- mc_nn；
- RAPTOR；
- 其他注册式 direct-control module。

典型路径是：

```text
Classic Cascade
Position → Attitude → Rate → Allocator → Motors
```

切换为：

```text
Registered Learned Controller
State + Target → Policy → ActuatorMotors
```

或者替换经典链中的某一段：

```text
Position Producer
      ↓
Learned Attitude/Rate/Actuator Subgraph
```

该 family 用于回答：

- registration facility 能否正确配置 controller graph；
- 被替换的经典模块是否及时失效；
- direct actuator writer 是否按声明独占；
- learned controller 退出后 control allocator 和经典级联是否恢复；
- 同一注册与模式管理设施在外部和内部组件上是否出现共同缺陷。

## 3.3 两个 family 的关系

两个 family 的现实成熟度和集成位置不同：

| 维度 | Family A | Family B |
|---|---|---|
| 位置 | 伴随计算机—PX4 边界 | PX4 飞控内部 |
| 主要变化 | producer、模式生命周期、setpoint route | controller graph、allocator、actuator writer |
| 现实成熟度 | Offboard 广泛使用，External Mode 持续发展 | 注册式学习控制器属于较新的深层案例 |
| 主要价值 | 外部自治进入、退出、故障和人工接管 | 高性能/学习控制与经典安全路径交接 |
| 共享机制 | mode state、registration、control configuration、fallback | mode state、registration、control configuration、fallback |

本文以 Family A 作为主要现实对象，以 Family B 作为同一 route-handoff 问题在更深 setpoint/actuator 层级上的代表性实例。

---

# 4. 研究范围与概念边界

## 4.1 上位问题空间

PX4 中广义的 runtime authority reconfiguration 包含：

1. exclusive route handoff；
2. partial/shared authority；
3. supervisory failsafe takeover；
4. terminal output gating；
5. controller graph reconfiguration；
6. VTOL/airframe configuration transition。

## 4.2 本文正式范围

本文选择其中具有统一交接契约的一类：

> **Route-replacing authority transition：主要控制路径的身份发生离散变化，使旧路径需要撤销，新路径需要安装，或故障后安全路径需要恢复。**

判断一个事件是否属于本文范围，依据运行时 Route 是否变化：

```text
Route = (
    authoritative producer,
    setpoint level,
    controller graph,
    actuator writer,
    fallback target
)
```

至少一个关键元素发生 authority-level replacement，并伴随明确的撤销/安装语义，该事件进入本文范围。

### 属于本文范围

- Internal Takeoff → Offboard；
- Offboard → Position/RTL/Land；
- Internal Mode → External Mode；
- External A → External B；
- External replacement RTL → Internal RTL fallback；
- RC/GCS 取回外部控制权；
- Classic cascade → registered learned controller；
- learned controller → classic fallback；
- setpoint level 改变并重配置 controller graph；
- failure-triggered route recovery。

### 不自动属于本文范围

- waypoint 更新；
- 同一 planner 生成新轨迹；
- 避障器修改下一段目标；
- 同一 Offboard producer 更新速度或姿态；
- 同一路径中的 gain scheduling；
- controller 参数更新；
- estimator 内部传感器切换；
- 普通 actuator saturation。

## 4.3 明确排除的相邻问题

### 长期共享或局部 authority

例如飞手控制 XY、PX4 保持高度，或者避障模块长期修改速度约束。这类系统需要 scope、axis、priority、composition 和 veto oracle。合法 overlap 是其正常语义，和本文的路径替换契约不同。

### Terminal safety gating

Disarm、kill、lockdown 和 flight termination 会从输出门控层终止或抑制正常控制输出。其核心契约是安全输出和终止语义，和保持飞行连续性的 route handoff 不同。

### VTOL 与飞行器构型转换

多旋翼—固定翼转换会引入动力学、actuator blending、transition controller 和 airframe state machine。它属于独立的构型重配置问题。

### 同一路径内部的自适应

参数调整、积分器变化和内部控制状态更新没有改变主要 route identity，本文不将其视为 authority handoff。

## 4.4 范围选择的理由

该边界满足四项要求：

1. **统一契约**：所有主实验都可检查撤销、安装、独占、连续和恢复；
2. **跨层代表性**：覆盖 companion-side producer handoff 和 onboard controller handoff；
3. **现实触发充分**：任务阶段、人工接管、进程故障、mode replacement 和 failsafe 都会触发；
4. **实验可执行**：无需同时解决共享权限组合、终端门控和 VTOL 动力学等异质问题。

---

# 5. Unified System Model

## 5.1 Route Profile

每条预期控制路径定义为：

```text
RouteProfile = (
    route_id,
    declared_mode,
    authority_source,
    setpoint_level,
    expected_producers,
    allowed_topics,
    enabled_modules,
    bypassed_modules,
    expected_actuator_writer,
    update_rate_range,
    freshness_policy,
    exclusivity_policy,
    fallback_policy
)
```

运行时观测为：

```text
ObservedRoute = (
    nav_state,
    registration_state,
    active_writers,
    topic_updates,
    message_age,
    controller_status,
    module_state,
    allocator_input,
    actuator_writer,
    actuator_output,
    failsafe_state
)
```

核心判定：

```text
Expected RouteProfile
          vs
Observed Runtime Route
```

## 5.2 Transition Model

一条 transition 表示为：

```text
Transition = (
    source_route,
    target_route,
    trigger,
    preconditions,
    revocation_deadline,
    installation_deadline,
    overlap_policy,
    continuity_policy,
    fallback_route
)
```

生命周期抽象为：

```text
Request / Failure
       ↓
Admission and Selection
       ↓
Declared Mode Change
       ↓
Old Route Revocation
       ↓
New Route Installation
       ↓
Stable Execution
       ↓
Release / Failure
       ↓
Fallback and Recovery
```

每一步由不同异步组件完成。它们不同步时可能产生无声违约。

## 5.3 Handoff Contract

### Revocation

- 旧 producer 在规定窗口内停止产生有效命令；
- 旧 setpoint 在撤销后不再被消费；
- 被替换 controller/module 停止参与；
- 旧 actuator writer 失去写入权限。

### Installation

- 新 producer 已启动并持续更新；
- setpoint level 与 controller graph 一致；
- 必要模块已启用；
- 被绕过模块已退出；
- 目标 actuator writer 已生效。

### Exclusivity

- 交接后只存在 policy 允许的 authoritative writer；
- overlap 只在 route specification 明确允许的窗口内出现；
- 新路径在获得权限前不会提前作用。

### Continuity

- 交接窗口内存在有效控制命令；
- 不出现超出 policy 的 route gap；
- setpoint、controller state 和 actuator output 不产生无法解释的不连续。

### Fallback and Recovery

- 故障路径在规定时间内失效；
- 预期安全路径完整安装；
- 恢复后不残留旧 producer、module configuration 或 actuator writer；
- repeated entry 从一致的初始状态开始。

## 5.4 Workload Model

```text
BehaviorProfile = (
    mission_phase,
    motion_goal,
    setpoint_level,
    setpoint_generator,
    update_rate,
    activation_condition,
    termination_condition,
    failure_condition,
    expected_fallback
)
```

测试用例定义为：

```text
TestCase =
    SourceRoute
  × TargetRoute
  × BehaviorProfile
  × VehicleState
  × LifecycleEventSequence
  × TimingParameters
  × FailureInjection
```

---

# 6. Input and Workload Design

## 6.1 输入设计原则

route handoff 的安全后果强烈依赖飞行状态。同一故障发生在悬停和高速转弯阶段，物理结果可能完全不同。

需要覆盖：

- 速度、加速度和 jerk；
- 上升、下降和高度余量；
- 航向变化与高 yaw rate；
- 接近姿态、推力或 actuator saturation；
- position、attitude、rate 和 direct actuator 层级；
- 不同更新率和时延；
- transition 发生在轨迹的不同相位。

## 6.2 三层工作负载

### Layer 1：确定性合成行为

用于开发、归因和 testcase minimization：

- hover；
- 两点直线；
- 多段 waypoint；
- 圆形与八字轨迹；
- acceleration–braking；
- ascent–translation–descent；
- yaw sweep；
- position、attitude 和 rate step。

### Layer 2：官方生命周期种子

至少包含：

- PX4/MAVSDK Takeoff → Offboard → Land；
- PX4 ROS 2 External Mode 官方流程；
- Mode Executor：Takeoff → Custom Mode → RTL；
- External RTL replacement 与 internal fallback；
- 官方支持的多种 setpoint API。

这些种子用于建立合法 RouteProfile 和 baseline lifecycle。

### Layer 3：真实上层任务栈或 trace

选择一至两个具有代表性的系统：

- ROS 2 UAV behavior-tree / mission framework；
- 具有 PX4 adapter 的导航或控制栈；
- 具有 task cancel、failsafe、emergency landing 或 controller fallback 的系统。

它们在本文中提供：

- 真实任务阶段；
- 真实 event sequence；
- 真实 motion trace；
- 真实 failure/recovery trigger。

完整系统集成成本过高时，记录其 setpoint、mode request 和 behavior state trace，再通过实验 adapter 回放。

## 6.3 Common Behavior Core and Dual Adapters

为了对比 Offboard 与 External Mode：

```text
                  Common Behavior Core
          trajectory / waypoint / motion policy
                            │
                  Canonical Motion Command
                            │
               ┌────────────┴────────────┐
               │                         │
       Offboard Adapter        External Mode Adapter
               │                         │
 OffboardControlMode /         ModeBase / SetpointType
 TrajectorySetpoint            Registration / update()
               │                         │
               └──────────── PX4 ────────┘
```

控制变量包括：

- 相同轨迹；
- 相同 setpoint level；
- 相同更新频率；
- 相同初始状态；
- 相同故障时刻；
- 相同 fallback 目标；
- 相同物理环境。

## 6.4 Transition-Aware Trace Replay

trace 至少记录：

```text
timestamp
behavior_state
mode_request
setpoint_type
position / velocity / acceleration
attitude / body_rate
thrust / torque
update_interval
failure_event
expected_target_route
```

同一 trace 可以：

- 分别通过 Offboard 与 External Mode 输入；
- 在经典和学习控制路径间复用目标；
- 在不同 transition phase 注入故障；
- 支持 testcase replay 与 differential analysis。

---

# 7. Research Questions

## RQ1：Declared-to-Observed Route Consistency

> 在正常进入、退出、替换和重复进入过程中，PX4 声明的 source/target route 是否与运行时 producer、setpoint level、controller graph 和 actuator writer 一致？

关注：

- route installation；
- route revocation；
- writer identity；
- module enable/bypass；
- overlap、gap、premature activation；
- previous-route residue。

## RQ2：Failure, Fallback and Recovery Consistency

> 当外部进程、heartbeat、setpoint stream、registered controller 或通信链路异常时，PX4 是否及时撤销故障路径并完整恢复预期安全路径？

关注：

- failure detection latency；
- stale command lifetime；
- fallback route correctness；
- controller graph restoration；
- process alive / setpoint stalled；
- setpoint alive / lifecycle lost；
- repeated recovery。

## RQ3：State and Timing Dependence

> route-handoff violation 是否依赖飞行状态、setpoint 层级、更新率和异步事件顺序？

关注：

- hover、acceleration、turning、ascent/descent；
- position、attitude、rate、direct actuator；
- activation/failure/failsafe concurrency；
- RC/GCS request concurrency；
- repeated switching；
- timing mutation。

## RQ4：Offboard vs Dynamic External Mode

> 在相同运动工作负载、故障条件和 fallback 目标下，Offboard 与 Dynamic External Mode 在 route lifecycle、stale command、fallback 和物理恢复方面有何差异？

目标：

- 建立现实 baseline；
- 识别显式注册和模式生命周期带来的保证；
- 识别 External Mode 特有缺陷；
- 区分通用外部控制边界问题与 registration-specific 问题。

## RQ5：Cross-Layer Generality

> 同一 route-handoff abstraction 和 oracle 是否能够同时发现 companion-side producer handoff 与 onboard controller-path handoff 中的问题？

该问题用于验证抽象和方法的泛化能力，不要求两个 family 具有相同部署规模或相同具体失效实现。

## RQ6：Workload Realism

> 合成行为、官方任务流程和真实上层任务 trace 是否会触发不同的 route state、timing window 和物理后果？

该问题验证真实上层软件作为上下文与事件生成器的价值。

---

# 8. Fuzzing Method Overview

## 8.1 Seed Construction

```text
Seed = (
    source_route,
    target_route,
    behavior,
    setpoint_level,
    lifecycle_sequence,
    trigger,
    fault_type,
    fault_time,
    expected_fallback
)
```

种子来源：

- 官方 Offboard 正常流程；
- 官方 External Mode 正常流程；
- Mode Executor 任务；
- mode replacement；
- classic ↔ learned controller flow；
- 合成轨迹；
- 真实任务 trace。

## 8.2 Mutation Dimensions

### Route and Lifecycle Mutation

- Internal → External → Internal；
- External A → External B；
- Classic → Learned → Classic；
- activate / deactivate；
- register / unregister；
- duplicate registration；
- repeated re-entry；
- mode replacement；
- executor interruption；
- fallback during activation；
- recovery followed by immediate reactivation。

### Authority Event Mutation

- RC mode request；
- GCS command；
- task cancel；
- task completion；
- failsafe trigger/clear；
- concurrent mode requests；
- learned-controller health failure；
- fallback policy change。

### Communication and Process Mutation

- process kill；
- process pause；
- callback stall；
- heartbeat stop；
- setpoint stop；
- heartbeat on + setpoint off；
- heartbeat off + setpoint on；
- DDS delay；
- burst；
- reorder；
- update-rate degradation；
- process restart。

### Motion-Context Mutation

- hover；
- acceleration；
- braking；
- turning；
- ascent/descent；
- high yaw-rate；
- near-saturation；
- trajectory phase；
- setpoint level。

## 8.3 Feedback Signals

- new source→target route pair；
- new lifecycle state transition；
- new producer combination；
- new module-state combination；
- new actuator-writer combination；
- route mismatch category；
- stale-message age bucket；
- overlap/gap duration；
- fallback route；
- physical anomaly severity；
- log signature；
- optional code coverage。

## 8.4 Reproduction and Minimization

每个异常保存：

- source/target RouteProfile；
- lifecycle sequence；
- task/behavior trace；
- ROS 2 timing；
- PX4 log；
- uORB writer/source trace；
- module state；
- allocator input；
- actuator writer/output；
- simulator state。

最小化目标：

- 缩短 lifecycle sequence；
- 简化 behavior；
- 缩小 timing window；
- 删除无关 event；
- 保留最小 route mismatch 和物理后果。

---

# 9. Core Oracle

## 9.1 Control-Route Consistency Oracle

```text
DeclaredRoute(
    mode,
    registration,
    setpoint_config,
    fallback_policy
)

                vs

ObservedRoute(
    producers,
    topics,
    modules,
    freshness,
    actuator_writer
)
```

## 9.2 Revocation Oracle

验证：

- source route 的 producer 是否在 deadline 内失效；
- 旧 setpoint 是否停止被消费；
- 被替换 controller 是否停止参与；
- 旧 actuator writer 是否停止作用；
- external process 继续发布时，PX4 是否仍然屏蔽其权限。

## 9.3 Installation Oracle

验证：

- target producer 是否已持续发布；
- setpoint level 是否正确；
- 所需 controller module 是否启用；
- 应绕过模块是否退出；
- actuator writer 是否符合 RouteProfile；
- route installation 是否在 deadline 内完成。

## 9.4 Exclusivity and Transition Oracle

检测：

- **Illegal overlap**：旧、新路径同时具有不允许的控制效力；
- **Route gap**：没有有效 target/source route；
- **Stale command**：撤销后的旧命令继续作用；
- **Premature command**：新路径在获得权限前提前生效；
- **Wrong route**：命令进入错误 setpoint/controller 层级；
- **Writer mismatch**：声明路径与实际 actuator writer 不一致。

## 9.5 Freshness Oracle

验证：

- message timestamp；
- receive timestamp；
- sequence continuity；
- update interval；
- heartbeat age；
- setpoint age；
- revocation 后旧消息的有效寿命；
- lifecycle heartbeat 与 command freshness 的一致性。

## 9.6 Recovery Oracle

验证：

- fallback route 是否符合 policy；
- 内部 controller graph 是否完整恢复；
- allocator 是否恢复正确输入；
- 上一次 route configuration 是否残留；
- process restart/re-entry 是否从一致状态开始；
- failsafe clear 后是否出现意外自动夺回控制。

## 9.7 Physical Consequence Oracle

物理结果用于衡量影响：

- attitude peak；
- angular-rate peak；
- trajectory deviation；
- altitude loss；
- actuator discontinuity；
- recovery time；
- flip/crash/loss of control。

物理异常需要与 route evidence 联合报告，以区分 handoff violation 和 controller capability limitation。

---

# 10. Core Test Scenarios

## 10.1 Normal External Activation

```text
Internal Route
      ↓
Offboard / External Mode Activation
      ↓
External Route Stable
```

检查 old route revocation、new route installation、overlap/gap 和 physical transient。

## 10.2 Normal External Release

```text
External Route
      ↓
Task Complete / Cancel / Mode Request
      ↓
Internal Route Restored
```

检查 external producer、stale setpoint、internal controller restoration 和 repeated entry。

## 10.3 Mode Executor Chain

```text
Takeoff
  → External A
  → External B / Internal RTL
  → Land
```

检查连续多次交接及 executor callback 时序。

## 10.4 Process or Communication Loss

```text
External Route Active
      ↓
Process Kill / Pause / DDS Failure
      ↓
Failsafe Detection
      ↓
Safe Internal Route
```

检查 detection latency、last-command lifetime 和 fallback completeness。

## 10.5 Partial Failure

```text
heartbeat on  + setpoint off
heartbeat off + setpoint on
```

检查 lifecycle 与 command freshness 分离。

## 10.6 External Replacement Mode Failure

```text
Internal Mission
      ↓ RTL request
External Custom RTL
      ↓ node failure
Internal RTL
```

检查 replacement identity、fallback target 和 route restoration。

## 10.7 RC/GCS Concurrent Takeover

```text
External Activation / Release
          +
RC or GCS Mode Request
          +
Optional Failsafe
```

检查最终 route 是否唯一、可解释且满足优先级。

## 10.8 Classic–Learned Controller Handoff

```text
Classic Cascade
      ↓
Registered Learned Controller
      ↓ fault/release
Classic Cascade
```

检查 classic module shutdown、direct writer exclusivity、allocator state 和 classic restoration。

## 10.9 Re-entry and Restart

```text
External / Learned Route
      ↓ failure or release
Internal Route
      ↓ process restart / re-register
External / Learned Route Again
```

检查 mode id、setpoint、controller state、configuration 和 writer residue。

---

# 11. Difference from SA-Fuzz

SA-Fuzz 可概括为：

```text
Application State × PX4 Flight Mode
```

核心问题是任务和环境条件下是否进入正确模式，以及模式转换是否满足状态机预期。

本文抽象为：

```text
Declared Route Transition × Observed Runtime Route
```

核心问题是模式状态或 authority declaration 变化后，producer、setpoint、controller graph 和 actuator writer 是否真正完成对应的撤销、安装与恢复。

| 维度 | SA-Fuzz | 本工作 |
|---|---|---|
| 核心抽象 | 应用状态与飞行模式 | source/target route 与运行路径 |
| 主要对象 | 模式状态机 | registration、producer、routing、controller graph、writer |
| Oracle | 状态/模式行为 | declared–observed route consistency |
| 典型发现 | 错误模式、错误转换 | overlap、gap、stale command、wrong writer、incomplete recovery |
| 关注层次 | 模式级行为 | 控制平面—数据平面—执行器跨层一致性 |
| 上层软件作用 | 产生应用状态 | 产生上下文与 handoff event |

本文不扩张为 PX4 全部 flight-mode transition 的通用测试。

---

# 12. Motivation Study

正式大规模 fuzzing 前完成以下调查。

## M1：真实任务中的 Handoff Inventory

从官方示例和真实上层软件提取：

```text
Task Phase
  × Mode/Controller Request
  × Source Route
  × Target Route
  × Trigger
  × Expected Fallback
```

重点统计：

- 正常任务包含多少次 route handoff；
- 哪些由任务阶段触发；
- 哪些由人工或 GCS 触发；
- 哪些由故障和 failsafe 触发；
- 哪些上层状态变化不改变 route。

## M2：External Mode and Registration Importance

调查：

- PX4 release history；
- Control Interface 与 setpoint API 演进；
- mode executor 和 mode replacement；
- External Mode examples 与 CI；
- mc_nn/RAPTOR 类内部注册式 controller；
- 社区使用与 issue/PR。

目标是建立“成熟 Offboard baseline + 显式 External Mode architecture + 深层 registered controller case”的现实和技术背景。

## M3：Existing Lifecycle Problems

搜索和分类：

```text
external mode
registration
mode replacement
offboard loss
setpoint stale
node loss
fallback
writer conflict
re-entry
controller residue
control allocation
```

建立矩阵：

```text
Issue
  × Lifecycle Stage
  × Source/Target Route
  × Control-Plane Symptom
  × Data-Plane Symptom
  × Existing Detection
  × Proposed Oracle
```

## M4：Official Test Coverage Gap

分析：

- unit tests；
- integration/SITL tests；
- ROS 2 examples；
- mode executor tests；
- mode replacement tests；
- neural-controller tests；
- failsafe tests。

区分：

```text
已有覆盖：
registration / entry / basic execution / expected fallback

本文验证：
writer identity / freshness / route installation /
route revocation / controller residue / overlap / gap /
full recovery
```

## M5：Real Workload Sources

选择一至两个代表性系统，评估：

- 是否支持 PX4；
- 是否包含任务阶段与取消/失败分支；
- 是否能输出 setpoint 与 mode request trace；
- 是否可在 SITL 运行；
- 是否具有 emergency/fallback logic；
- 是否能通过 adapter 或 replay 接入两个外部机制；
- 集成成本与可重复性。

---

# 13. Motivation Probe Experiments

## P0：Official Handoff Flow

运行：

```text
Takeoff → External Mode → RTL/Land
```

采集：

- task/executor state；
- mode request；
- nav state；
- producer identity；
- setpoint level；
- controller state；
- actuator writer/output。

目标：建立合法 RouteProfile 和端到端 trace。

## P1：Handoff Frequency in a Real Task

运行一个完整任务：

```text
Takeoff
  → External Waypoint Flight
  → Turning/Tracking
  → Task Cancel or Complete
  → RTL
  → Land
```

统计：

- route handoff 次数；
- trigger 类型；
- 飞行状态；
- 每次 handoff 的异步组件数量；
- 普通 trajectory update 与真正 handoff 的比例。

## P2：Process Loss and Last-Command Lifetime

```text
External Route Active
      ↓
Kill / Pause Process
      ↓
Measure Last Command Lifetime
      ↓
Observe Safe Route Installation
```

比较 Offboard 与 External Mode 的 detection、stale window、fallback 和恢复。

## P3：Heartbeat–Setpoint Decoupling

四种情况：

```text
heartbeat on  + setpoint on
heartbeat on  + setpoint off
heartbeat off + setpoint on
heartbeat off + setpoint off
```

目标是确认 lifecycle 存活与 command freshness 的耦合关系。

## P4：External RTL Replacement

```text
Mission
  → RTL request
  → External RTL
  → Node Loss
  → Internal RTL
```

验证在相同 `RTL` 语义下能否识别实际执行路径，并测量 fallback completeness。

## P5：Controlled Offboard–External Differential

使用 Common Behavior Core：

```text
same trajectory
same setpoint level
same update rate
same vehicle state
same failure time
same fallback target
```

比较：

- activation/revocation latency；
- overlap/gap；
- stale command；
- route residue；
- physical recovery。

## P6：Classic–Learned Deep Route Trace

```text
Classic Cascade
  → Registered Learned Controller
  → Classic Fallback
```

记录：

- control configuration；
- classic controller outputs；
- learned-controller output；
- allocator participation；
- actuator writer；
- fallback restoration。

目标是验证同一 oracle 能否覆盖更深的 controller-path replacement。

## P7：Concurrent Authority Events

组合：

- external activation + RC request；
- external release + failsafe；
- node loss + GCS command；
- executor transition + process pause；
- learned-controller failure + classic reactivation；
- failsafe clear + external re-entry。

目标是测试最终 route 的唯一性与线性化结果。

## P8：Real-Stack Trace Replay

从真实任务/行为栈记录：

- behavior state；
- trajectory；
- mode requests；
- cancel/failure/recovery events。

回放到 Offboard、External Mode 或 controller-handoff harness 中，确认问题能够在现实 event sequence 和 motion context 下复现。

---

# 14. Evaluation Plan

## 14.1 Subjects

核心：

- PX4 Dynamic External Mode；
- PX4 ROS 2 Offboard；
- PX4 classic cascade；
- mc_nn / RAPTOR 类 registered learned controller。

工作负载：

- deterministic synthetic behaviors；
- official examples；
- one or two real ROS 2 task/autonomy stacks or traces。

## 14.2 Setpoint Levels

优先覆盖：

1. position / velocity / acceleration；
2. attitude + thrust；
3. body rate + thrust/torque；
4. direct actuator for registered learned controller。

Offboard 与 External Mode 的差分实验使用共同支持的层级。External Mode 或内部注册控制器特有的低层接口单独评估。

## 14.3 Transition Matrix

```text
Source Family
  × Target Family
  × Setpoint Level
  × Trigger
  × Vehicle State
  × Failure Type
  × Fallback Route
```

重点 transition：

- Internal ↔ Offboard；
- Internal ↔ External Mode；
- External A ↔ External B；
- External Replacement ↔ Internal Original；
- Classic ↔ Learned；
- External/Learned → Safe Internal Route。

## 14.4 Metrics

- route-pair coverage；
- lifecycle-stage coverage；
- producer combination coverage；
- controller/module-state coverage；
- actuator-writer coverage；
- unique violation count；
- activation latency；
- revocation latency；
- stale setpoint lifetime；
- overlap duration；
- gap duration；
- fallback correctness；
- recovery completeness；
- reproduction rate；
- physical recovery time；
- testcase minimization ratio；
- false-positive rate。

## 14.5 Baselines

- mode-state-only oracle；
- physical-anomaly-only oracle；
- official timeout/failsafe detection；
- random timing/event mutation；
- Offboard mechanism baseline；
- route oracle without writer tracing；
- route oracle without module-state tracing。

## 14.6 Ablation

分析：

- 无真实 workload 时的发现能力；
- 无 timing mutation 时的漏报；
- 无 route tracing 时的漏报；
- mode-only、physical-only 与 full route oracle；
- 不同 setpoint level；
- 不同 vehicle state；
- Offboard baseline 对归因的贡献；
- Family B 对跨层泛化结论的贡献。

---

# 15. Expected Contributions

## C1：Problem Formulation

提出：

> **Route-Replacing Authority Transition Testing**

将 PX4 模式切换与控制器替换统一为主要控制路径的运行时交接问题。

## C2：System Abstraction

提出：

> **Control Plane–Data Plane Route Model**

统一描述 mode state、registration、producer、setpoint level、controller graph、actuator writer、freshness 和 fallback。

## C3：Handoff Contract

系统化定义：

- route revocation；
- route installation；
- exclusivity；
- continuity；
- fallback and recovery。

## C4：Control-Route Consistency Oracle

自动识别：

- old-route residue；
- illegal overlap；
- route gap；
- stale command；
- premature activation；
- wrong setpoint route；
- wrong actuator writer；
- incomplete fallback；
- incomplete controller restoration。

## C5：Stateful Fuzzing Method

构建面向：

- route pair；
- lifecycle event；
- authority-event concurrency；
- asynchronous timing；
- communication/process failure；
- motion context；
- setpoint level；

的状态化 fuzzing 方法。

## C6：Cross-Family Empirical Study

系统比较：

- Offboard 与 Dynamic External Mode；
- companion-side producer handoff 与 onboard controller handoff；
- synthetic、official 和 real-stack workloads。

## C7：Empirical Findings

发现、复现、最小化并归因 route lifecycle defect，分析其软件根因、触发窗口和物理安全影响。

---

# 16. Scope and Non-goals

## Included

- PX4 with companion computer；
- ROS 2 Offboard；
- Dynamic External Mode；
- mode registration / admission / activation；
- mode executor and replacement；
- release / failure / fallback / recovery；
- RC/GCS interruption as handoff event；
- setpoint producer lifecycle；
- position、attitude、rate 和 direct actuator 层级；
- controller graph enable/bypass；
- classic ↔ registered learned controller；
- uORB route and message freshness；
- actuator writer identity；
- synthetic、official 和 real-stack workloads；
- physical impact validation。

## Excluded

- 长期 shared/partial authority composition；
- per-axis authority arbitration；
- collision-prevention correctness；
- terminal kill/lockdown/flight-termination testing；
- VTOL airframe transition；
- generic PX4 flight-mode state-machine fuzzing；
- SLAM accuracy；
- perception correctness；
- planner optimality；
- obstacle-detection quality；
- generic navigation scenario fuzzing；
- controller performance ranking；
- neural-policy quality comparison；
- estimator switching correctness；
- security attack as the main topic；
- companion computer only providing perception or mission upload。

---

# 17. Claims and Narrative Guardrails

## 可以声称

- PX4 自主系统存在运行时主要控制路径交接；
- 上层任务、人工接管、进程故障、mode replacement 和 failsafe 会触发真实交接；
- Offboard 是成熟的外部运动控制 baseline；
- Dynamic External Mode 提供显式注册、模式生命周期、executor、replacement 和 fallback 集成；
- mc_nn/RAPTOR 类模块展示了 registration facility 在飞控内部深层 controller replacement 中的使用；
- mode state 正确无法单独证明 runtime route 正确；
- 控制平面声明与运行时 producer/controller/writer 的一致性需要系统验证；
- 两个 subject family 共享 route revocation、installation 和 recovery 契约。

## 避免声称

- 本文覆盖 PX4 中全部 authority transition；
- 所有上层任务状态变化都会触发控制权交接；
- 所有配有伴随计算机的 PX4 都使用 External Mode；
- External Mode 已经替代 Offboard；
- External Mode 或 Offboard 完全缺少测试；
- 两个 subject family 具有相同部署规模；
- 所有轨迹偏差都来自 handoff mechanism；
- 真实上层自主栈本身是本文的主要被测对象；
- shared authority、terminal gating 和 VTOL transition 属于本文未完成的主实验。

---

# 18. Final Narrative

本文研究 PX4 中一类会替换主要飞行控制路径的运行时 authority transition。

现实自主任务经常执行：

```text
Takeoff
  → External Autonomy
  → Task Completion / Cancel / Failure
  → RTL / Land / Manual Recovery
```

外部模式还可以替换内部安全模式；伴随计算机故障后，PX4 需要恢复内部 fallback；高性能或学习型控制器失效后，经典控制路径需要重新接管。这些交接发生在不同 setpoint 层级和不同计算节点，却都依赖同一组跨层机制：

```text
Mode and Authority Declaration
            ↓
Producer and Setpoint Routing
            ↓
Controller Graph Configuration
            ↓
Actuator Writer Selection
            ↓
Fallback and Recovery
```

本文将上层导航、任务和行为软件作为真实上下文与 handoff-event 生成器，将 PX4 模式管理、setpoint routing、controller configuration 和 actuator writer 作为核心被测系统。

本文建立两个 subject family：

1. PX4 内部路径与 Offboard/Dynamic External Mode 之间的外部自治交接；
2. 经典级联与注册式学习控制器之间的飞控内部交接。

核心观察是：

```text
Declared Source → Target Route
               vs
Observed Runtime Producer, Controller and Writer
```

核心问题可以浓缩为：

> **当 PX4 声明主要控制路径已经完成交接时，旧路径是否真正停手，新路径是否真正接棒，故障后安全路径是否真正恢复？**

---

# 19. Primary Source Anchors

V4 叙事中的机制和示例主要对应以下官方或原始实现：

- PX4-Autopilot: `docs/en/flight_modes/offboard.md`
- PX4-Autopilot: `docs/en/ros2/px4_ros2_control_interface.md`
- PX4-Autopilot: `docs/en/neural_networks/nn_module_utilities.md`
- PX4-Autopilot: `src/modules/commander/ModeManagement.cpp`
- PX4-Autopilot: `src/modules/mc_nn_control/`
- PX4-Autopilot: `src/modules/mc_raptor/`
- px4-ros2-interface-lib: `examples/cpp/modes/executor_with_multiple_modes/`
- px4-ros2-interface-lib: `examples/cpp/modes/rtl_replacement/`
- MAVSDK: `cpp/examples/offboard/offboard.cpp`

