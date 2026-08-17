# 仓库理解与研究问答

## 文档定位

这是一份持续追加的中文读者指南，专门记录“为了真正理解仓库、研究叙事和实验逻辑而提出的问题”。它面向刚接触 PX4 和本仓库的读者，优先解释概念之间的因果关系，而不是代码实现。

本文件不是新的实验计划、冻结报告或新增结论。如果这里的概括与冻结矩阵、证据账本、最终报告或规范性方法文档冲突，以后者为准。当前状态见 [CURRENT_STATUS.md](CURRENT_STATUS.md)，完整研究叙事见 [NEW_NARRATIVE_v7.md](NEW_NARRATIVE_v7.md)。

最近一次跨文档核对：2026-08-17，基于当前 `origin/main` 和仓库中保留的 Thor 实验材料。

---

## 问题一：这个仓库究竟研究什么？当前叙事走到了哪里？

### 一句话回答

这是一个研究 PX4 **控制权切换是否真的完成**的实验仓库。

它不满足于看到“飞行模式变了”或“飞机最后降落了”，而是继续追问：旧控制路径是否及时退出，新路径是否从命令生产者一直贯通到执行器写入端，切换过程中是否既没有两个路径同时生效，也没有无人负责的空档，命令是否新鲜，完成或故障后是否安装了正确的后继路径。

### 仓库要验证的完整问题

一次控制权切换至少包含下面这些义务：

1. 旧路径在期限内被撤销；
2. 新路径完整安装到执行器写入端；
3. 新旧路径的执行器效果保持互斥；
4. 切换边界没有过长的控制空档；
5. 新路径持续消费属于当前实例的新鲜命令；
6. 生命周期和执行器任务的所有者正确；
7. 正常完成后安装预定的后继路径；
8. 计划故障后安装完整的安全路径；
9. 本应失败的注册或激活被明确拒绝。

所以，本仓库研究的对象不是一个孤立的 mode 枚举值，而是一条在运行时真正能把命令变成飞行关键执行器效果的控制路径。

### 当前研究阶段

```text
问题与研究边界                         已完成
Runtime Route Instance 与契约            已完成
Evidence Gate 与在线观测                 已完成
Thor 执行和计账平台                       已完成
Stage A1 最小机制 Motivation              已完成，但结论有边界
Stage A2 移动工作负载现实性桥接             已计划，尚未执行
bounded-random 在线动作后端                尚未实现
state-aware 在线动作后端                  尚未实现
三种策略的固定预算正式比较                  尚未开始
违规复现与源码根因确认                      尚未完成
```

目前 Thor 上有两项彼此独立、事先注册的 Motivation 研究：

| 研究 | 启动次数 | 可采纳证据 | Oracle 结果 |
| --- | ---: | ---: | --- |
| Primary | 180 | 131 | 75 PASS，56 VIOLATION |
| Supplemental | 20 | 20 | 19 PASS，1 VIOLATION |
| 合计 | 200 | 151 | 94 PASS，57 VIOLATION |

Primary 的总体状态仍是 `MEASUREMENT_INSUFFICIENT`：两个 invalid-plan 单元已经达到启动上限，但仍没有得到可采纳证据。Supplemental 只在新的研究身份和账本下补足这两个测量义务，并没有回写或改造 Primary。

V7 叙事还记录了一层更早的 Orin 证据脉络。不过，对应的源报告、账本和紧凑证据不在当前 `origin/main` 中。因此它只能作为带来源说明的研究背景，不能计入 Thor 的 200 次启动，也不能仅靠当前远程分支独立复核。要精确复用这一层，必须另行提供对应的 V6 来源、版本和证据材料。

### 为什么“模式变了”和“最后降落了”都不够

PX4 的导航状态告诉我们系统**宣称自己处于什么状态**，却不能单独证明当前执行器效果来自哪个生产者会话、哪次注册、哪次激活、哪个控制器、哪个分配器、哪个写入端和哪个所有者。

因此，下面三种推断都不成立：

```text
mode 已改变
    不等于目标路径已经完整安装

目标已经 activation
    不等于目标命令已经到达执行器写入端

飞机最终 landed 并 disarmed
    不等于中间每一次控制权交接都正确
```

相同的模式名可以对应两次不同的运行时实例；新模式也可能已经出现，但下游控制链还没有完整接上。

### Stage A1 中飞机具体怎样飞

Stage A1 故意使用很简单的运动目标，目的是把“路径切换机制”从复杂航迹规划中分离出来。它不是多航点任务，也不能代表复杂移动任务已经验证完毕。

#### 位置级轨迹

保留的 Legacy Offboard 位置目标是：

```text
position = [0, 0, -3]
yaw = 0
```

PX4 使用局部 NED 坐标，`z=-3` 表示相对原点约三米高。实际意图是垂直升到三米、在固定点保持，然后切换到 Hold、RTL 或 Land。Dynamic External Mode 和 Mode Executor 在各自有效窗口内也使用同一个固定三米位置目标。

#### 姿态级目标

飞机先通过普通 PX4 动作完成解锁和起飞，然后 Legacy Offboard 提供：

```text
desired quaternion = [1, 0, 0, 0]
body thrust = [0, 0, -0.6]
```

四元数 `[1,0,0,0]` 表示水平姿态；这里给的是固定姿态与推力，而不是位置目标。

#### 角速度级目标

普通起飞后，Legacy Offboard 提供：

```text
roll rate = 0
pitch rate = 0
yaw rate = 0
body thrust = [0, 0, -0.6]
```

这次走的是角速度控制入口，而不是位置或姿态入口。

#### 有效窗口和收尾

正常情况下，目标路径保持约 8 秒。若后继是 Hold 或 RTL，会先观测该后继约 2 秒，再执行清理用的 Land。每次闭合飞行都必须满足终端安全和清理义务，包括降落和解除武装。

### 实验具体改变了什么

#### 正常切换单元

九个正常单元覆盖：

```text
Internal Hold -> Legacy Offboard trajectory -> Land / Hold / RTL
Internal Hold -> Legacy Offboard attitude   -> Land
Internal Hold -> Legacy Offboard body rate  -> Land
Internal Hold -> Dynamic External Mode      -> Land / Hold / RTL
PX4 internal  -> Mode Executor              -> completion -> Land
```

#### 故障与拒绝单元

七个故障单元覆盖：

- Legacy Offboard 生产者在激活约 3 秒后退出；
- Legacy Offboard 的轨迹、姿态或角速度 setpoint 在约 3 秒后停止更新，但 proof-of-life 继续；
- Dynamic External Mode 进程退出，然后触发内部 RTL；
- 健康状态丢失后，Dynamic External Mode 的激活被拒绝；
- 外部公开槽位到达容量时，新的注册被明确拒绝。

setpoint stall 尤其关键：Legacy Offboard 在表面上仍然活着，PX4 却可能持续消费越来越旧的命令。因此 freshness 不能只在 activation 瞬间检查，而要覆盖整个目标控制权窗口。

#### 时序和重复进入单元

Mode Executor 在名义 completion 附近收到相邻的公开 Land 请求，时点分别约为：

- completion 前 250 ms；
- completion 边界；
- completion 后 250 ms。

重复进入单元则执行两次 Legacy Offboard activation，中间必须先观测到一个 Hold 或 RTL 实例。两次进入必须拥有不同且完整的 route epoch 与 activation identity，不能因为 route 名相同就被合并。

### 目前能说出的、有边界的结论

151 条可采纳 Thor trace 中：

- 94 条通过全部适用条款；
- 57 条至少违反一项已注册研究契约；
- 五条正常姿态级 Legacy Offboard trace 全部出现 Route 违规；
- setpoint stall 和生产者退出暴露了旧命令继续被消费的情况，即便飞机最后安全结束；
- 四条 completion 后时序的 Mode Executor trace 落在注册的时序或次序范围之外，虽然 Land 后继本身是完整的；
- 修正后的 RTL 重复进入在所有 Supplemental trace 中都形成了两个完整且不同的路径实例。

这 57 条 trace **不是 57 个已经确认的 PX4 软件缺陷**；`151/200` 也**不是 PX4 控制权切换成功率**。研究阈值是事先注册的判定边界，而这些现象还没有全部完成源码级根因确认。

同一 trace 上的 Oracle 消融结果是：

| 观测层 | PASS | VIOLATION | INCONCLUSIVE |
| --- | ---: | ---: | ---: |
| 完整 Oracle | 94 | 57 | 0 |
| 只看 mode | 143 | 0 | 8 |
| 只看最终结果 | 151 | 0 | 0 |

这说明只看 mode 或最终结果会漏掉路径级问题。阈值敏感性重放还说明，报告结论时必须同时报告阈值。matched-differential 分析在当前 Thor Motivation 数据中没有找到符合正式条件的配对块，所以现有数据不能给 Legacy Offboard、Dynamic External Mode 和 Mode Executor 排名。

### 下一步是什么

当前叙事先安排独立的 Stage A2 移动工作负载，让 Legacy Offboard 和 Dynamic External Mode 执行同一个有边界的移动任务，并在选定运动阶段触发 completion 或故障。这个阶段目前尚未实现 fixture、观测契约、qualification、预注册或正式执行。

完成这一现实性桥接后，主方法仍需要真正可运行的 bounded-random 和 state-aware 动作后端，再与 Official Sequence 进行固定预算比较。

---

## 问题二：什么是 Runtime Route Instance？

### 先建立直觉

飞行模式名回答的是“PX4 现在宣称是哪种模式”；Runtime Route Instance 回答的是：

> **此刻究竟是哪一个具体控制实例，沿着哪一套具体下游链路，在产生飞行关键的执行器效果？**

可以把一次切换想成接力：

```text
一个具体的 PX4 Internal Hold 实例
    -> 一个具体的 Legacy Offboard 实例
    -> 一个具体的 PX4 internal Land 实例
```

`legacy_offboard` 只是路径类型名。它没有告诉我们这是哪个进程会话、哪一次进入、哪一次激活，也没有告诉我们命令最后经过了哪个控制器、分配器和写入端。

### 稳定身份的十个字段

规范实现中的稳定身份是：

```text
RuntimeRouteInstance = (
    route,
    route_epoch,
    producer_session,
    registration_id,
    activation_id,
    controller_id,
    allocator_id,
    writer_id,
    lifecycle_owner,
    executor_owner
)
```

每个 `command_consumed`、`controller_output`、`allocator_output` 和 `actuator_write` 效果事件还必须携带 `command_subject_ns`。它会随着新命令不断变化，因此是绑定在稳定实例上的**动态 freshness 证据**，不是第十一个稳定身份字段。

### 每个字段在回答什么

下表前十行属于稳定身份；最后一行 `command_subject_ns` 是随效果事件更新的动态时间证据。

| 字段 | 它回答的问题 |
| --- | --- |
| `route` | 这是哪一种控制路径？ |
| `route_epoch` | 这是该路径第几次与控制权有关的出现？ |
| `producer_session` | 是哪个具体生产者进程或会话提供命令？ |
| `registration_id` | 使用的是哪一个内建或动态分配的注册？ |
| `activation_id` | 当前激活的是该注册的哪一次具体进入？ |
| `controller_id` | 哪个控制器消费了目标？ |
| `allocator_id` | 哪个 control allocator 处理了控制器输出？ |
| `writer_id` | 哪个软件写入端产生了执行器输出？ |
| `lifecycle_owner` | 谁负责完成、释放和选择后继？ |
| `executor_owner` | 是否由某个 Mode Executor 负责上层任务生命周期？ |
| `command_subject_ns` | 当前被消费的那条命令本身何时产生？ |

### 为什么只有 route 名远远不够

假设飞行顺序是：

```text
Hold                 epoch 1
Legacy Offboard #1   epoch 2
Hold                 epoch 3
Legacy Offboard #2   epoch 4
Land                 epoch 5
```

两段 Legacy Offboard 的 route 名相同，但它们不是同一个实例。`route_epoch` 防止观测器把两次进入错误拼成一条长路径。

如果外部命令生产者退出后重启，新的 `producer_session` 也不能继承旧会话身份；否则旧生产者留下的命令可能被误归到新生产者。

### registration 和 activation 的区别

可以类比成会议室：

- `registration_id`：这个外部模式已经获得一个可用房间；
- `activation_id`：这一次会议已经真正进入这个房间；
- 下游效果链：与会者已经完成工作，并把结果送到了最终执行端。

所以“注册成功”不能证明“正在使用”，“已经激活”也不能证明命令已经到达执行器写入端。

### controller、allocator 和 writer 为什么属于身份

Stage A1 的不同输入层级会进入不同控制器：

| 目标类型 | 典型控制器身份 |
| --- | --- |
| position / trajectory | `mc_position_control` |
| attitude | `mc_attitude_control` |
| body rate | `mc_rate_control` |

控制器输出还必须继续经过 PX4 control allocator 和 actuator writer。只有看到整个链条，才能说目标路径已经完整安装；只看到 activation 或 controller output 都还不够。

### lifecycle owner 和 executor owner

内部路径通常由 PX4 Commander 管理。Legacy Offboard 和 Dynamic External Mode 各自有外部生命周期所有者。Mode Executor 还拥有更高层的任务顺序，例如起飞、发出 completion、请求 Land，并等待 disarm。

这两个字段用来区分“谁正在产生命令”和“谁有权宣布任务完成、释放资源或决定下一条路径”。

### `command_subject_ns` 为什么不是稳定身份

freshness 使用的是：

```text
command age = effect time - command subject time
```

这里不能使用日志写入时间。一条刚刚写入日志的记录，完全可能描述控制器仍在消费数秒前的旧命令。

同一个 Runtime Route Instance 在 8 秒有效窗口里会持续收到新命令，所以 `command_subject_ns` 应不断前进；稳定的十字段身份则应保持一致。两者共同表达的是：**同一个权威实例正在持续消费属于它的新鲜命令。**

---

## 问题三：一次 transition 到底怎样发生？

下面用一条具体路径解释：

```text
Internal Hold -> Legacy Offboard -> internal Land
```

这里的 transition 不是一个瞬时 mode 变化，而是从请求开始，到旧路径撤销、新路径完整安装，再到新路径结束和后继完整安装的一段有边界过程。

### 阶段 1：先确认完整的 source 实例

请求前，观测器先确认 Internal Hold 已经形成完整路径：

```text
internal command
    -> controller output
    -> allocator output
    -> actuator write
```

这一刻的 route epoch 和 owner 被固定下来。后面需要撤销的是这个**具体 source 实例**，不是抽象的“某个 Hold”。

### 阶段 2：目标命令预流送

Legacy Offboard 生产者开始发送 proof-of-life 和 `[0,0,-3]` 位置目标。这个动作只是让 PX4 在切换时有命令可用，并没有转移控制权；此时 source 仍然是 Internal Hold。

### 阶段 3：记录公开切换请求

fixture 发出并记录：

```text
transition_requested
source_route = internal_hold
target_route = legacy_offboard
```

把这个时间记为 `t0`。安装和撤销期限都锚定在事先注册的请求上，不能在飞完之后再挑一个方便的起点。

### 阶段 4：撤销 source

PX4 改变与控制权有关的路径状态，观测器收到 source revocation 证据。当前注册的撤销期限是请求后 300 ms。

同时还要继续检查：旧 source 在被撤销后，尤其是在目标完整安装后，不能再产生执行器写入。否则新旧路径可能同时生效。

### 阶段 5：激活 target

activation 事件建立新的 Legacy Offboard route epoch、producer session、registration、activation、controller、allocator、writer 和 owners。

但 activation 只证明控制平面选中了目标，还没有证明目标命令真正走到了最下游。

### 阶段 6：观察完整安装

target 必须用同一个稳定身份给出有序证据：

```text
activation
    -> command_consumed
    -> controller_output
    -> allocator_output
    -> actuator_write
```

每一个效果事件还必须带有有效的 `command_subject_ns`。只有观测到 `actuator_write`，才算目标完整安装。当前注册的安装期限是请求后 300 ms。

### 阶段 7：检查交接边界

这里有两个彼此独立的性质：

```text
Exclusivity：
    target 完整安装后，source 不能再产生执行器效果

Continuity：
    target 第一个效果 - source 最后一个效果 <= 250 ms
```

Exclusivity 防止两个控制者同时有效；Continuity 防止出现太长的无人控制空档。一个切换可能满足其中一个，却违反另一个。

### 阶段 8：检查整个 target 控制权窗口

直到 target 被撤销前，每一个 target 效果都要持续检查：

- 稳定的十字段路径身份是否一致；
- controller、allocator、writer 链是否完整；
- command age 是否非负；
- command age 是否不超过已注册的 200 ms 上限。

因此，即使安装瞬间完全正确，三秒后发生 setpoint stall，freshness Oracle 仍会抓到旧命令继续被消费。

### 阶段 9：正常完成或发生计划故障

正常 Legacy Offboard 单元在约 8 秒后由 lifecycle owner 报告完成，并请求已注册的后继。

故障单元则要求出现明确的故障证据；若计划规定安全回退，还必须观测回退触发和完整回退路径，不能仅凭“最后没有坠机”判定通过。

### 阶段 10：完整安装 successor

若正常后继是 Land，还要再次证明完整链条：

```text
internal Land activation
    -> command consumption
    -> controller output
    -> allocator output
    -> actuator write
```

当前注册的 successor 期限是 completion 后 300 ms。最终落地不能代替“后继是否及时且完整安装”的过程证据。

### 阶段 11：安全闭合本次 attempt

只有在采集器关闭、外部注册和生产者会话不再活动、安全内部路径已经存在，并按计划完成 landed 与 disarmed 后，这次运行才算安全闭合。

### 把全过程放在一条时间线上

```text
t-1  完整的 Internal Hold source 实例
 |
 |   Legacy Offboard proof-of-life 与命令预流送
 |
t0   transition_requested
 |
t1   source revocation
 |
t2   target activation
 |
t3   command consumed，并携带 subject time
 |
t4   controller output
 |
t5   allocator output + actuator write
 |   到这里 target 才算完整安装
 |
 |   持续检查身份、链路和 freshness
 |
t6   completion 或计划故障
 |
t7   successor 请求或 fallback 触发
 |
t8   完整的内部 successor / fallback 安装
 |
t9   landed、disarmed、采集和清理闭合
```

### 常见观测应该怎样解释

| 观测 | 含义 |
| --- | --- |
| mode 已改变，但缺少下游事件 | target 没有被证明完整安装 |
| target 安装后 source 仍有写入 | exclusivity 违规 |
| source 最后效果到 target 首个效果间隔过大 | continuity 违规 |
| target 消费很旧的 subject | freshness 违规 |
| 同一控制权窗口内效果身份变化 | lineage 违规 |
| lifecycle 或 executor owner 不符 | ownership 违规 |
| 已 completion，但 successor 太晚或不完整 | progression 违规 |
| 关键证据缺失，或时钟无法可靠拼接 | 证据 INCONCLUSIVE，不能当作系统 PASS |

---

## 术语速查

| 术语 | 在本仓库中的含义 |
| --- | --- |
| Route | 能够产生飞行关键执行器效果的控制路径 |
| Runtime Route Instance | 某条路径一次稳定、可区分的运行时出现 |
| Source | transition 请求前拥有控制权的路径 |
| Target | 请求用来替换 source 的路径 |
| Successor | 正常完成后计划进入的路径 |
| Fallback | 故障后计划进入的安全路径 |
| Installation | 从 activation 到 actuator writer 的完整证据 |
| Revocation | 旧路径实例的控制权和效果终止 |
| Lineage | producer 到 controller、allocator、writer 的身份一致性 |
| Freshness | 当前消费命令的时间年龄和时序有效性 |
| Evidence Gate | 在正确性判断前进行的证据准入检查 |
| `ACCEPTED` | 计账结果：这条证据可以进入正确性分析 |
| `PASS` | 可采纳证据上的全部适用条款都通过 |
| `VIOLATION` | 至少一项适用的已注册契约被违反 |
| `INCONCLUSIVE` | 证据不足以支持正确性判断 |

---

## 后续怎样继续记录问答

后续每轮理解性对话都作为新的编号问题追加。每个答案应当：

1. 先给刚接触 PX4 的读者建立直觉；
2. 明确区分当前实现、已经完成的证据和计划中的工作；
3. 至少给出一条具体路径或实验时间线；
4. 始终区分计账上的 `ACCEPTED` 与 Oracle 的 `PASS`；
5. 说明数值阈值是已注册的研究契约；
6. 不把违规 trace 数直接解释为软件缺陷数；
7. 链接到当前主来源文件；
8. 只有完成跨文档和正式材料核对后，才更新本文的核对日期。

主要参考：

- [ROUTE_MODEL.md](ROUTE_MODEL.md)
- [METHOD.md](METHOD.md)
- [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md)
- [Primary Motivation report](../experiments/motivation_thor_v1/FINAL_REPORT.md)
- [Supplemental Motivation report](../experiments/motivation_thor_remediation_v1/FINAL_REPORT.md)
- [Oracle ablation report](../experiments/posthoc_oracle_ablation_v1/FINAL_REPORT.md)
- [Threshold sensitivity report](../experiments/posthoc_threshold_sensitivity_v1/FINAL_REPORT.md)
- [Matched differential report](../experiments/matched_differential_analyzer_v1/FINAL_REPORT.md)
