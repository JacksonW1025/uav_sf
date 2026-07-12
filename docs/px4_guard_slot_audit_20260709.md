# PX4 Guard-Slot Audit
PX4 HEAD: 3042f906abaab7ab59ae838ad5a530a9ef3df9a6   Date: 2026-07-09   Auditor: Codex

Scope note: source paths below are relative to `external/PX4-Autopilot/`. The audit used read-only source inspection plus this report write. `git -C external/PX4-Autopilot rev-parse HEAD` returned the required SHA. Caveat: the PX4 worktree was already dirty before report writing; `src/modules/mc_raptor/` was later diffed against `HEAD`, and the RAPTOR arming/reset evidence below was rechecked against pristine `HEAD`.

## 0. 判定摘要
- C1 槽位存在且拦截 in-flight 模式切换： CONFIRMED. Failing requirements clear `can_run`; while armed, `UserModeIntention::change()` rejects modes whose `canRun()` bit is clear, and commander ACKs `TEMPORARILY_REJECTED`.
- C2 词汇表 = N 个固定布尔，其中 <k> 条为 availability 类、<m> 条为 value 类： CONFIRMED WITH CORRECTION. This SHA has N=14 `mode_req_*` fields, not 13: 11 availability/resource/signal, 1 environment/time value (`wind_and_flight_time_compliance`), 2 policy/other.
- C3 无任何一条 requirement 是对载具连续动力学状态取值的谓词： CONFIRMED for the fixed `mode_req_*` vocabulary and `getModeRequirements()`. Estimator validity flags may use timestamp/finite/accuracy checks, but there is no requirement like `attitude < threshold` or `|omega| < threshold`.
- C4 internal mode 的 requirement 为编译期常量： REFUTED if read literally. Built-in mode requirements are a static table plus discrete `vehicle_type` branches; external nav states are handled outside and can be changed by `ArmingCheckReply`.
- C5 mc_nn_control / mc_raptor 均未注册任何状态相关准入检查： REFUTED as written. Both register a mode and arming check via `register_ext_component_request`; however their explicit check code does not implement a handover continuous-state threshold such as attitude/rate bounds.
- C6 external mode 可否表达任意状态谓词： CONFIRMED, but only as an externally computed boolean. The fixed requirement fields are fixed booleans; `can_arm_and_run` can encode an arbitrary predicate computed by the external component, sampled through the request/reply loop.
- C7 切回经典时积分器是否重置： CODE-CONDITIONAL, LOG-RESOLVED FOR CURRENT DATASET. Code allows either fresh external-mode config or stale safe defaults. In all scanned SUT ULOGs with nav_state 23, both `mc_nn_control` and `mc_raptor` show safe-default effective control flags (`flag_control_rates_enabled=true`, `flag_multicopter_position_control_enabled=true`, `source_id=0`) and `rate_ctrl_status` continues publishing, so rate I is not frozen in these logs.

### 0.1 反馈后补充核查

1. `git -C external/PX4-Autopilot diff -- src/modules/mc_raptor/` shows local changes only in RAPTOR observation clipping and `module.yaml` parameter additions. The local diff does not touch `can_arm`, `updateArmingCheckReply()`, or activation reset. Pristine `HEAD` still contains `this->reset()` on activation at `src/modules/mc_raptor/mc_raptor.cpp:540`.
2. `mc_nn_control` explicitly publishes a zero-initialized `vehicle_control_mode_s` without assigning `flag_control_rates_enabled`, so that explicit message has the rates flag false. It does set `flag_control_climb_rate_enabled = true`; Commander then recomputes `flag_multicopter_position_control_enabled` from generic altitude/climb/position/velocity/acceleration flags before publishing `vehicle_control_mode`. Therefore `mc_nn_control` does not force the position-controller disabled/reset path. `mc_raptor` can force that path only if Commander accepts its fresh config; if the cached config is stale, Commander uses safe defaults instead.
3. Generated `arming_check_reply_s` headers in the existing build trees have no constructor or default member initializers. Because both modules declare `arming_check_reply_s arming_check_reply;`, unassigned scalar fields are indeterminate. Both modules set `num_events = 0`, so the event loop is not expected to consume `events[]`, but `mode_req_local_position_relaxed`, `mode_req_global_position_relaxed`, health booleans, padding, and event bytes are not cleanly initialized by those functions.
4. `can_arm_and_run` is consumed from `_registrations[reg_idx].reply`, a cached copy updated by the request/reply loop. There is no synchronous recomputation on handover. The visible request cadence is 300 ms, with 50 ms request timeout and three missed established replies before an external mode is flagged unresponsive; therefore "≤300 ms stale" is the nominal responsive cadence, not a hard age bound at consumption.

### 0.2 ULOG 实证补充

Scanned with `pyulog`, read-only, no simulation. Scope:

- `runs/campaigns`: 2851 SUT logs ending in `_mcnn.ulg` or `_raptor.ulg` (`mcnn=1899`, `raptor=952`).
- `docs`: 97 archived SUT logs (`mcnn=78`, `raptor=19`).
- Topics read: `vehicle_status`, `vehicle_control_mode`, `rate_ctrl_status`.
- Window: first contiguous interval where `vehicle_status.nav_state == 23`.

Results:

| set | nav_state 23 logs | first effective `vehicle_control_mode` after switch | `rate_ctrl_status` during nav_state 23 |
|---|---:|---|---|
| `runs/campaigns` mcnn | 1899/1899 | `rates=1`, `mc_pos=1`, generic position/velocity/altitude/climb/accel/attitude/allocation all `1`, `termination=0`, `source_id=0` | 1899/1899 continued publishing |
| `runs/campaigns` raptor | 952/952 | same safe-default signature | 952/952 continued publishing |
| `docs` mcnn | 77/78 (`1` no nav_state 23) | same safe-default signature | 77/77 continued publishing |
| `docs` raptor | 19/19 | same safe-default signature | 19/19 continued publishing |

Representative log records:

- `runs/campaigns/combined_steady_corner_20260627/evals/combined_steady_corner_20260627_e0002/mcnn_gate3_combined_steady_corner_20260627_e0002_mcnn.ulg`: nav_state 23 starts at `32936000 us`; first active flags are `rates=1`, `mc_pos=1`, `source_id=0`; `rate_ctrl_status` first active sample at `+112 ms`.
- `runs/campaigns/raptor_gate0_anchor_boundary_20260705/evals/raptor_gate0_anchor_boundary_20260705_pair4_rp36_44_rate1p55_2p15_w3_r4_f038_s20262302/m1_raptor_gate0_anchor_boundary_20260705_pair4_rp36_44_rate1p55_2p15_w3_r4_f038_s20262302_raptor.ulg`: nav_state 23 starts at `26252000 us`; first active flags are `rates=1`, `mc_pos=1`, `source_id=0`; `rate_ctrl_status` first active sample at `+36 ms`.

Interpretation: for the logged dataset, Commander did not use the modules' fresh `config_control_setpoints` at handover. It used the safe-default path visible in `ModeManagement.cpp:551`, so `mc_rate_control` remained active and continued publishing `rate_ctrl_status` while nav_state was 23. This empirically refutes the "rate integrator freezes during mc_nn_control/mc_raptor" hypothesis for these logs.

## 1. 证据表
| # | 主张 | file:line | 逐字片段 | 支持/反对 |
|---|---|---|---|---|
| 1 | Guard vocabulary has 14 fields | `msg/FailsafeFlags.msg:8` | `# Per-mode requirements`<br>`uint32 mode_req_angular_velocity`<br>`uint32 mode_req_attitude`<br>`uint32 mode_req_local_alt`<br>`uint32 mode_req_local_position`<br>`uint32 mode_req_local_position_relaxed`<br>`uint32 mode_req_global_position`<br>`uint32 mode_req_global_position_relaxed` | Supports C2 and refutes the 13-field count |
| 2 | Remaining fields include wind/time, prevent arming, manual, other | `msg/FailsafeFlags.msg:16` | `uint32 mode_req_mission`<br>`uint32 mode_req_offboard_signal`<br>`uint32 mode_req_home_position`<br>`uint32 mode_req_wind_and_flight_time_compliance # if set, mode cannot be entered if wind or flight time limit exceeded`<br>`uint32 mode_req_prevent_arming    # if set, cannot arm while in this mode`<br>`uint32 mode_req_manual_control`<br>`uint32 mode_req_other             # other requirements, not covered above (for external modes)` | Supports C2 |
| 3 | `getModeRequirements()` has only `vehicle_type` input plus output flags | `src/modules/commander/ModeUtil/mode_requirements.cpp:46` | `void getModeRequirements(uint8_t vehicle_type, failsafe_flags_s &flags)` | Supports C3/C4 nuance |
| 4 | Function initializes fixed mode_req fields | `src/modules/commander/ModeUtil/mode_requirements.cpp:48` | `flags.mode_req_angular_velocity = 0;`<br>`flags.mode_req_attitude = 0;`<br>`flags.mode_req_local_position = 0;`<br>`flags.mode_req_local_position_relaxed = 0;`<br>`flags.mode_req_global_position = 0;`<br>`flags.mode_req_global_position_relaxed = 0;`<br>`flags.mode_req_local_alt = 0;`<br>`flags.mode_req_mission = 0;` | Supports C2/C3 |
| 5 | External nav states are not in the static table | `src/modules/commander/ModeUtil/mode_requirements.cpp:223` | `// NAVIGATION_STATE_EXTERNALx: handled outside`<br><br>`static_assert(vehicle_status_s::NAVIGATION_STATE_MAX == 31, "update mode requirements");` | Supports C4/C5 nuance |
| 6 | Requirement failure clears `can_run` | `src/modules/commander/HealthAndArmingChecks/checks/modeCheck.cpp:50` | `// Failing mode requirements generally also clear the can_run bits which prevents mode switching and`<br>`// might trigger a failsafe if already in that mode.` | Supports C1 |
| 7 | Armed mode change checks `canRun()` | `src/modules/commander/UserModeIntention.cpp:55` | `if (!always_allow) {`<br>`	allow_change = _health_and_arming_checks.canRun(user_intended_nav_state);` | Supports C1 |
| 8 | Rejected user mode does not update intended nav state | `src/modules/commander/UserModeIntention.cpp:72` | `if (allow_change) {`<br>`	_had_mode_change = true;`<br>`	_user_intented_nav_state = user_intended_nav_state;` | Supports C1 |
| 9 | Commander returns temporary rejection | `src/modules/commander/Commander.cpp:1060` | `} else {`<br>`	if (cmd.from_external && cmd.source_component == 190) { // MAV_COMP_ID_MISSIONPLANNER`<br>`		printRejectMode(desired_nav_state);`<br>`	}`<br><br>`	main_ret = TRANSITION_DENIED;`<br>`}` | Supports C1 |
| 10 | ACK result on denied mode set | `src/modules/commander/Commander.cpp:1069` | `if (main_ret != TRANSITION_DENIED) {`<br>`	cmd_result = vehicle_command_ack_s::VEHICLE_CMD_RESULT_ACCEPTED;`<br><br>`} else {`<br>`	cmd_result = vehicle_command_ack_s::VEHICLE_CMD_RESULT_TEMPORARILY_REJECTED;`<br>`}` | Supports C1 |
| 11 | Health/arming checks run at 10 Hz or on change | `src/modules/commander/Commander.cpp:2045` | `// Run arming checks @ 10Hz`<br>`if ((now >= _last_health_and_arming_check + 100_ms) || _status_changed || nav_state_or_failsafe_changed) {` | Supports C1 |
| 12 | Wind/time compliance consumed by clearing can_run | `src/modules/commander/HealthAndArmingChecks/checks/modeCheck.cpp:186` | `if ((reporter.failsafeFlags().flight_time_limit_exceeded || reporter.failsafeFlags().wind_limit_exceeded)`<br>`    && reporter.failsafeFlags().mode_req_wind_and_flight_time_compliance != 0) {`<br>`	// Already reported`<br>`	reporter.clearCanRunBits((NavModes)reporter.failsafeFlags().mode_req_wind_and_flight_time_compliance);`<br>`}` | Supports C2/C3 |
| 13 | Wind threshold is environmental wind vs `COM_WIND_MAX` | `src/modules/commander/HealthAndArmingChecks/checks/windCheck.cpp:47` | `if (_wind_sub.copy(&wind_estimate)) {`<br>`	const matrix::Vector2f wind(wind_estimate.windspeed_north, wind_estimate.windspeed_east);`<br><br>`	// publish a warning if it's the first since in air or 60s have passed since the last warning`<br>`	const bool warning_timeout_passed = _last_wind_warning == 0 || now - _last_wind_warning > 60_s;`<br>`	const bool wind_limit_exceeded = _param_com_wind_max.get() > FLT_EPSILON && wind.longerThan(_param_com_wind_max.get());` | Supports C3 |
| 14 | Flight-time threshold uses takeoff time and `COM_FLT_TIME_MAX` | `src/modules/commander/HealthAndArmingChecks/checks/flightTimeCheck.cpp:38` | `if (_param_com_flt_time_max.get() > FLT_EPSILON && context.status().takeoff_time != 0 &&`<br>`    (hrt_absolute_time() - context.status().takeoff_time) > (1_s * _param_com_flt_time_max.get())) {`<br>`	reporter.failsafeFlags().flight_time_limit_exceeded = true;` | Supports C3 |
| 15 | External reply fixed fields and `can_arm_and_run` | `msg/versioned/ArmingCheckReply.msg:24` | `bool can_arm_and_run # True if the component can arm. For navigation mode components, true if the component can arm in the mode or switch to the mode when already armed`<br><br>`uint8 num_events # Number of queued failure messages (Event) in the events field` | Supports C6 |
| 16 | FMU merges reply mode requirements into fixed flags | `src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:168` | `setOrClearRequirementBits(reply.mode_req_angular_velocity, nav_mode_id, replaces_nav_state,`<br>`			  reporter.failsafeFlags().mode_req_angular_velocity);`<br>`setOrClearRequirementBits(reply.mode_req_attitude, nav_mode_id, replaces_nav_state,`<br>`			  reporter.failsafeFlags().mode_req_attitude);` | Supports C6 |
| 17 | FMU uses `can_arm_and_run` as a boolean from reply | `src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:162` | `if (!reply.can_arm_and_run) {`<br>`	setOrClearRequirementBits(true, nav_mode_id, replaces_nav_state, reporter.failsafeFlags().mode_req_other);`<br>`}` | Supports C6 |
| 18 | mc_nn_control is a compiled PX4 module | `src/modules/mc_nn_control/CMakeLists.txt:38` | `px4_add_module(`<br>`	MODULE mc_nn_control`<br>`	MAIN mc_nn_control` | Supports Q3 |
| 19 | mc_nn_control registers mode and arming check | `src/modules/mc_nn_control/mc_nn_control.cpp:158` | `register_ext_component_request_s register_ext_component_request{};`<br>`register_ext_component_request.timestamp = hrt_absolute_time();`<br>`strncpy(register_ext_component_request.name, "Neural Control", sizeof(register_ext_component_request.name) - 1);`<br>`register_ext_component_request.request_id = _mode_request_id;`<br>`register_ext_component_request.px4_ros2_api_version = 1;`<br>`register_ext_component_request.register_arming_check = true;`<br>`register_ext_component_request.register_mode = true;` | Refutes "no arming check" |
| 20 | mc_nn_control explicit arming reply assignments are unconditional except fixed requirements | `src/modules/mc_nn_control/mc_nn_control.cpp:207` | `arming_check_reply.can_arm_and_run = true;`<br>`arming_check_reply.mode_req_angular_velocity = true;`<br>`arming_check_reply.mode_req_local_position = true;`<br>`arming_check_reply.mode_req_attitude = true;`<br>`arming_check_reply.mode_req_local_alt = true;` | Supports no continuous-state guard |
| 21 | mc_raptor registers mode and arming check | `src/modules/mc_raptor/mc_raptor.cpp:254` | `register_ext_component_request_s register_ext_component_request{};`<br>`register_ext_component_request.timestamp = hrt_absolute_time();`<br>`strncpy(register_ext_component_request.name, "RAPTOR", sizeof(register_ext_component_request.name) - 1);`<br>`register_ext_component_request.request_id = Raptor::EXT_COMPONENT_REQUEST_ID;`<br>`register_ext_component_request.px4_ros2_api_version = 1;`<br>`register_ext_component_request.register_arming_check = true;`<br>`register_ext_component_request.register_mode = true;` | Refutes "no arming check" |
| 22 | mc_raptor explicit reply assignments depend on `can_arm` and fixed requirements | `src/modules/mc_raptor/mc_raptor.cpp:428` | `arming_check_reply.can_arm_and_run = can_arm;`<br>`arming_check_reply.mode_req_angular_velocity = true;`<br>`arming_check_reply.mode_req_local_position = true;`<br>`arming_check_reply.mode_req_attitude = true;`<br>`arming_check_reply.mode_req_local_alt = true;` | Supports Q3 |
| 23 | mc_raptor resets recurrent executor on activation | `src/modules/mc_raptor/mc_raptor.cpp:538` | `bool next_active = timestamp_last_vehicle_status_set && _vehicle_status.nav_state == ext_component_mode_id;`<br><br>`if (!previous_active && next_active) {`<br>`	this->reset();`<br>`	PX4_INFO("Resetting Inference Executor (Recurrent State)");` | Supports C7 hidden-state part |
| 24 | Rate controller I reset is not a mode-edge reset | `src/modules/mc_rate_control/MulticopterRateControl.cpp:189` | `if (_vehicle_control_mode.flag_control_rates_enabled) {`<br><br>`	// reset integral if disarmed`<br>`	if (!_vehicle_control_mode.flag_armed || _vehicle_status.vehicle_type != vehicle_status_s::VEHICLE_TYPE_ROTARY_WING) {`<br>`		_rate_control.resetIntegral();`<br>`	}` | Supports C7 |
| 25 | Position controller resets I when disabled | `src/modules/mc_pos_control/MulticopterPositionControl.cpp:619` | `} else {`<br>`	// an update is necessary here because otherwise the takeoff state doesn't get skipped with non-altitude-controlled modes`<br>`	_takeoff.updateTakeoffState(_vehicle_control_mode.flag_armed, _vehicle_land_detected.landed, false, 10.f, true,`<br>`				    vehicle_local_position.timestamp_sample);`<br>`	_control.resetIntegral();`<br>`}` | Supports conditional C7 |
| 26 | Generated reply struct has plain fields, no default initializers | `build/px4_sitl_mcnn_sih/uORB/topics/arming_check_reply.h:53` | `struct __EXPORT arming_check_reply_s {`<br>`#else`<br>`struct arming_check_reply_s {`<br>`#endif`<br>`	uint64_t timestamp;` | Supports uninitialized reply caveat |
| 27 | Commander recomputes multicopter-position flag | `src/modules/commander/Commander.cpp:2766` | `_vehicle_control_mode.flag_armed = isArmed();`<br>`_vehicle_control_mode.flag_multicopter_position_control_enabled =`<br>`	(_vehicle_status.vehicle_type == vehicle_status_s::VEHICLE_TYPE_ROTARY_WING)`<br>`	&& (_vehicle_control_mode.flag_control_altitude_enabled`<br>`	    || _vehicle_control_mode.flag_control_climb_rate_enabled` | Supports C7 correction |
| 28 | External `can_arm_and_run` is consumed from cached reply | `src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:130` | `arming_check_reply_s &reply = *_registrations[reg_idx].reply;`<br><br>`int8_t nav_mode_id = _registrations[reply.registration_id].nav_mode_id;` | Supports Q4 cache conclusion |

## 2. 逐题详答

### Q1 - 守卫词汇表的完整枚举与语义分类

Conclusion: The source vocabulary is 14 fixed `mode_req_*` fields. `getModeRequirements()` takes only `uint8_t vehicle_type` and output `failsafe_flags_s &flags`; it does not receive attitude, angular velocity, local position values, or `nav_state`. Requirements for built-in modes are generated by a static table with discrete `vehicle_type` branches. None of those requirement values depends on current attitude/rate/position magnitudes.

The exact "Per-mode requirements" message block:

`msg/FailsafeFlags.msg:8`
```msg
# Per-mode requirements
uint32 mode_req_angular_velocity
uint32 mode_req_attitude
uint32 mode_req_local_alt
uint32 mode_req_local_position
uint32 mode_req_local_position_relaxed
uint32 mode_req_global_position
uint32 mode_req_global_position_relaxed
```

`msg/FailsafeFlags.msg:16`
```msg
uint32 mode_req_mission
uint32 mode_req_offboard_signal
uint32 mode_req_home_position
uint32 mode_req_wind_and_flight_time_compliance # if set, mode cannot be entered if wind or flight time limit exceeded
uint32 mode_req_prevent_arming    # if set, cannot arm while in this mode
uint32 mode_req_manual_control
uint32 mode_req_other             # other requirements, not covered above (for external modes)
```

`getModeRequirements()` signature and assignment coverage:

`src/modules/commander/ModeUtil/mode_requirements.cpp:46`
```cpp
void getModeRequirements(uint8_t vehicle_type, failsafe_flags_s &flags)
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:48`
```cpp
	flags.mode_req_angular_velocity = 0;
	flags.mode_req_attitude = 0;
	flags.mode_req_local_position = 0;
	flags.mode_req_local_position_relaxed = 0;
	flags.mode_req_global_position = 0;
	flags.mode_req_global_position_relaxed = 0;
	flags.mode_req_local_alt = 0;
	flags.mode_req_mission = 0;
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:56`
```cpp
	flags.mode_req_offboard_signal = 0;
	flags.mode_req_home_position = 0;
	flags.mode_req_wind_and_flight_time_compliance = 0;
	flags.mode_req_prevent_arming = 0;
	flags.mode_req_manual_control = 0;
	flags.mode_req_other = 0;
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:64`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_MANUAL, flags.mode_req_manual_control);

	// NAVIGATION_STATE_ALTCTL
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ALTCTL, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ALTCTL, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ALTCTL, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ALTCTL, flags.mode_req_manual_control);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:73`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ALTITUDE_CRUISE, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ALTITUDE_CRUISE, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ALTITUDE_CRUISE, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ALTITUDE_CRUISE,
		       flags.mode_req_manual_control); // COM_RCL_EXCEPT can override this
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:80`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_POSCTL, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_POSCTL, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_POSCTL, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_POSCTL, flags.mode_req_local_position_relaxed);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_POSCTL, flags.mode_req_manual_control);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:87`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_POSITION_SLOW, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_POSITION_SLOW, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_POSITION_SLOW, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_POSITION_SLOW, flags.mode_req_local_position_relaxed);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_POSITION_SLOW, flags.mode_req_manual_control);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:94`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_MISSION, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_MISSION, flags.mode_req_attitude);

	if (vehicle_type == vehicle_status_s::VEHICLE_TYPE_FIXED_WING) {
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_MISSION, flags.mode_req_global_position_relaxed);
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_MISSION, flags.mode_req_local_position_relaxed);

	} else {
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_MISSION, flags.mode_req_global_position);
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_MISSION, flags.mode_req_local_position);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:106`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_MISSION, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_MISSION, flags.mode_req_mission);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_MISSION, flags.mode_req_wind_and_flight_time_compliance);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:111`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER, flags.mode_req_attitude);

	if (vehicle_type == vehicle_status_s::VEHICLE_TYPE_FIXED_WING) {
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER, flags.mode_req_global_position_relaxed);
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER, flags.mode_req_local_position_relaxed);

	} else {
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER, flags.mode_req_global_position);
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER, flags.mode_req_local_position);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:123`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER, flags.mode_req_wind_and_flight_time_compliance);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:127`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_GUIDED_COURSE, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_GUIDED_COURSE, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_GUIDED_COURSE, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_GUIDED_COURSE, flags.mode_req_wind_and_flight_time_compliance);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_GUIDED_COURSE, flags.mode_req_local_position_relaxed);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:134`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_RTL, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_RTL, flags.mode_req_attitude);

	if (vehicle_type == vehicle_status_s::VEHICLE_TYPE_FIXED_WING) {
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_RTL, flags.mode_req_global_position_relaxed);
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_RTL, flags.mode_req_local_position_relaxed);

	} else {
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_RTL, flags.mode_req_global_position);
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_RTL, flags.mode_req_local_position);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:146`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_RTL, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_RTL, flags.mode_req_home_position);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_RTL, flags.mode_req_prevent_arming);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:151`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ACRO, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ACRO, flags.mode_req_manual_control);

	// NAVIGATION_STATE_DESCEND
	setRequirement(vehicle_status_s::NAVIGATION_STATE_DESCEND, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_DESCEND, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_DESCEND, flags.mode_req_prevent_arming);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:160`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_TERMINATION, flags.mode_req_prevent_arming);

	// NAVIGATION_STATE_OFFBOARD
	setRequirement(vehicle_status_s::NAVIGATION_STATE_OFFBOARD, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_OFFBOARD, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_OFFBOARD, flags.mode_req_offboard_signal);

	// NAVIGATION_STATE_STAB
	setRequirement(vehicle_status_s::NAVIGATION_STATE_STAB, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_STAB, flags.mode_req_attitude);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:170`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_STAB, flags.mode_req_manual_control);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:173`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_TAKEOFF, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_TAKEOFF, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_TAKEOFF, flags.mode_req_local_alt);

	if (vehicle_type == vehicle_status_s::VEHICLE_TYPE_ROTARY_WING) {
		// only require local position for rotary wing vehicles, fixed wing vehicles can take off without it
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_TAKEOFF, flags.mode_req_local_position);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:183`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LAND, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LAND, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LAND, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LAND, flags.mode_req_local_position_relaxed);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_LAND, flags.mode_req_prevent_arming);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:190`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_FOLLOW_TARGET, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_FOLLOW_TARGET, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_FOLLOW_TARGET, flags.mode_req_local_position);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_FOLLOW_TARGET, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_FOLLOW_TARGET, flags.mode_req_prevent_arming);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_FOLLOW_TARGET, flags.mode_req_wind_and_flight_time_compliance);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:198`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_PRECLAND, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_PRECLAND, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_PRECLAND, flags.mode_req_local_position);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_PRECLAND, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_PRECLAND, flags.mode_req_prevent_arming);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:205`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ORBIT, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ORBIT, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ORBIT, flags.mode_req_local_position);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ORBIT, flags.mode_req_local_alt);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ORBIT, flags.mode_req_prevent_arming);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_ORBIT, flags.mode_req_wind_and_flight_time_compliance);
```

`src/modules/commander/ModeUtil/mode_requirements.cpp:213`
```cpp
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_VTOL_TAKEOFF, flags.mode_req_angular_velocity);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_VTOL_TAKEOFF, flags.mode_req_attitude);
	setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_VTOL_TAKEOFF, flags.mode_req_local_alt);

	if (vehicle_type == vehicle_status_s::VEHICLE_TYPE_FIXED_WING) {
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_VTOL_TAKEOFF, flags.mode_req_local_position_relaxed);

	} else {
		setRequirement(vehicle_status_s::NAVIGATION_STATE_AUTO_VTOL_TAKEOFF, flags.mode_req_local_position);
```

Classification:

| Field | Class | Assignment dependency in `getModeRequirements()` | Continuous vehicle-state predicate? |
|---|---|---|---|
| `mode_req_angular_velocity` | availability | static nav_state table | No |
| `mode_req_attitude` | availability | static nav_state table | No |
| `mode_req_local_alt` | availability | static nav_state table | No |
| `mode_req_local_position` | availability | static table plus discrete `vehicle_type` branch for mission/loiter/RTL/takeoff/VTOL takeoff | No |
| `mode_req_local_position_relaxed` | availability | static table plus discrete `vehicle_type` branch | No |
| `mode_req_global_position` | availability | static table plus discrete `vehicle_type` branch | No |
| `mode_req_global_position_relaxed` | availability | static table plus discrete `vehicle_type` branch | No |
| `mode_req_mission` | resource availability | static nav_state table | No |
| `mode_req_offboard_signal` | signal availability | static nav_state table | No |
| `mode_req_home_position` | resource availability | static nav_state table | No |
| `mode_req_wind_and_flight_time_compliance` | environment/time value | static nav_state table | No vehicle dynamics predicate; compares wind and flight time |
| `mode_req_prevent_arming` | policy | static nav_state table | No |
| `mode_req_manual_control` | signal availability | static nav_state table | No |
| `mode_req_other` | external/other failure bucket | zero in static table; set by external checks | Not a typed predicate; can reflect external-computed boolean failure |

Special wind/flight-time consumer:

`src/modules/commander/HealthAndArmingChecks/checks/modeCheck.cpp:186`
```cpp
	if ((reporter.failsafeFlags().flight_time_limit_exceeded || reporter.failsafeFlags().wind_limit_exceeded)
	    && reporter.failsafeFlags().mode_req_wind_and_flight_time_compliance != 0) {
		// Already reported
		reporter.clearCanRunBits((NavModes)reporter.failsafeFlags().mode_req_wind_and_flight_time_compliance);
	}
```

Wind threshold source:

`src/modules/commander/HealthAndArmingChecks/checks/windCheck.cpp:47`
```cpp
	if (_wind_sub.copy(&wind_estimate)) {
		const matrix::Vector2f wind(wind_estimate.windspeed_north, wind_estimate.windspeed_east);

		// publish a warning if it's the first since in air or 60s have passed since the last warning
		const bool warning_timeout_passed = _last_wind_warning == 0 || now - _last_wind_warning > 60_s;
		const bool wind_limit_exceeded = _param_com_wind_max.get() > FLT_EPSILON && wind.longerThan(_param_com_wind_max.get());
```

Flight-time threshold source:

`src/modules/commander/HealthAndArmingChecks/checks/flightTimeCheck.cpp:38`
```cpp
	if (_param_com_flt_time_max.get() > FLT_EPSILON && context.status().takeoff_time != 0 &&
	    (hrt_absolute_time() - context.status().takeoff_time) > (1_s * _param_com_flt_time_max.get())) {
		reporter.failsafeFlags().flight_time_limit_exceeded = true;
```

Contrary evidence checked: `EstimatorChecks` does read attitude/angular/local-position topics to produce validity flags. Example:

`src/modules/commander/HealthAndArmingChecks/checks/estimatorCheck.cpp:817`
```cpp
	vehicle_attitude_s attitude;

	if (_vehicle_attitude_sub.copy(&attitude)) {
		const matrix::Quatf q{attitude.q};
		const float eps = 1e-5f;
		const bool no_element_larger_than_one = (fabsf(q(0)) <= 1.f + eps)
```

But those checks are validity/integrity checks (`timestamp`, finite, quaternion norm, position accuracy), not per-mode requirement expressions such as `roll < 40 deg` or `|omega| < 1.5 rad/s`.

Refutation search process:
- `rg -n "Per mode requirements|mode_req_" msg/FailsafeFlags.msg`
- `rg -n "getModeRequirements|mode_req_" src/modules/commander/ModeUtil`
- `rg -n "mode_req_[a-z_]+\\s*(\\||&)?=" src msg`
- `rg -n "wind_limit_exceeded|flight_time_limit_exceeded|COM_FLT_TIME_MAX|COM_WIND_MAX" src/modules/commander`
- `rg -n "vehicle_attitude|vehicle_angular_velocity|vehicle_local_position|Eulerf|Quatf|fabsf" src/modules/commander/...`

### Q2 - 槽位是否真的拦截飞行中的模式切换

Conclusion: Yes. Requirement failures clear `can_run`; while armed, user mode changes are rejected if `canRun()` is false. Rejection produces `VEHICLE_CMD_RESULT_TEMPORARILY_REJECTED` for mode commands. Checks run at 10 Hz or immediately on relevant status/mode/failsafe change. No commander mode-switch path was found that reads attitude/rate values and gates on their magnitudes.

Call sequence from command to effective nav state:

1. `src/modules/commander/Commander.cpp:2079` - `_vehicle_command_sub.updated()` detects a command.
2. `src/modules/commander/Commander.cpp:2084` - command is copied, then `handle_command(cmd)` is called.
3. `src/modules/commander/Commander.cpp:925` - `VEHICLE_CMD_DO_SET_MODE` branch parses base/custom modes.
4. `src/modules/commander/Commander.cpp:993` - external custom submodes map to `NAVIGATION_STATE_EXTERNAL1 + ...`.
5. `src/modules/commander/Commander.cpp:1056` - commander calls `_user_mode_intention.change(...)`.
6. `src/modules/commander/UserModeIntention.cpp:55` - while armed, `change()` checks `_health_and_arming_checks.canRun(...)`.
7. `src/modules/commander/HealthAndArmingChecks/Common.hpp:223` - `canRun()` returns whether the `can_run` mode bit is set.
8. `src/modules/commander/HealthAndArmingChecks/checks/modeCheck.cpp:53` and following - failing requirements clear `can_run`.
9. `src/modules/commander/Commander.cpp:1069` - accepted vs temporarily rejected ACK result is selected.
10. `src/modules/commander/Commander.cpp:2528` - if accepted and selected by failsafe/mode management, `_vehicle_status.nav_state` is updated.

Armed rejection point:

`src/modules/commander/UserModeIntention.cpp:52`
```cpp
	// Always allow mode change while disarmed
	bool always_allow = force || !isArmed();
	bool allow_change = true;

	if (!always_allow) {
		allow_change = _health_and_arming_checks.canRun(user_intended_nav_state);
```

If not allowed, the new intended mode is not stored:

`src/modules/commander/UserModeIntention.cpp:72`
```cpp
	if (allow_change) {
		_had_mode_change = true;
		_user_intented_nav_state = user_intended_nav_state;
```

Commander result after `_user_mode_intention.change()` fails:

`src/modules/commander/Commander.cpp:1054`
```cpp
				const bool force = desired_nav_state == vehicle_status_s::NAVIGATION_STATE_AUTO_LAND;

				if (_user_mode_intention.change(desired_nav_state, getSourceFromCommand(cmd), false, force)) {
					main_ret = TRANSITION_CHANGED;

				} else {
```

`src/modules/commander/Commander.cpp:1069`
```cpp
			if (main_ret != TRANSITION_DENIED) {
				cmd_result = vehicle_command_ack_s::VEHICLE_CMD_RESULT_ACCEPTED;

			} else {
				cmd_result = vehicle_command_ack_s::VEHICLE_CMD_RESULT_TEMPORARILY_REJECTED;
			}
```

ACK publication:

`src/modules/commander/Commander.cpp:2816`
```cpp
	case vehicle_command_ack_s::VEHICLE_CMD_RESULT_TEMPORARILY_REJECTED:
		PX4_DEBUG("command %" PRIu32 " temporarily rejected", cmd.command);
		tune_negative(true);
		break;
```

`src/modules/commander/Commander.cpp:2832`
```cpp
	vehicle_command_ack_s command_ack{};
	command_ack.command = cmd.command;
	command_ack.result = result;
	command_ack.target_system = cmd.source_system;
	command_ack.target_component = cmd.source_component;
	command_ack.timestamp = hrt_absolute_time();
	_vehicle_command_ack_pub.publish(command_ack);
```

Health check frequency:

`src/modules/commander/Commander.cpp:2045`
```cpp
		// Run arming checks @ 10Hz
		if ((now >= _last_health_and_arming_check + 100_ms) || _status_changed || nav_state_or_failsafe_changed) {
			_last_health_and_arming_check = now;
```

External reply request frequency:

`src/modules/commander/HealthAndArmingChecks/checks/externalChecks.hpp:69`
```cpp
	static constexpr hrt_abstime REQUEST_TIMEOUT = 50_ms;
	static constexpr hrt_abstime UPDATE_INTERVAL = 300_ms;
	static_assert(REQUEST_TIMEOUT < UPDATE_INTERVAL, "keep timeout < update interval");
	static constexpr int NUM_NO_REPLY_UNTIL_UNRESPONSIVE = 3; ///< Mode timeout = this value * UPDATE_INTERVAL
```

No value-gate found in command-to-activation path. Searches:
- `rg -n "vehicle_attitude|vehicle_angular_velocity|vehicle_local_position|Eulerf|Quatf|roll|pitch|xyz\\[|q\\[|fabsf|abs\\(" Commander.cpp UserModeIntention.cpp ModeManagement.cpp modeCheck.cpp framework.cpp`
- Hits in `Commander.cpp` were command parameter parsing or unrelated manual throttle/home-position handling, not mode requirement gating.
- Hits in `HealthAndArmingChecks/checks/estimatorCheck.cpp` were validity/accuracy/finite/timestamp checks feeding `*_invalid` flags, not current-state threshold admission.

### Q3 - `mc_nn_control` 与 `mc_raptor` 的注册方式与准入检查

#### mc_nn_control

Conclusion: It is a compiled PX4 module, not a companion ROS 2 process. It does not include `px4_ros2` APIs, but it does use the external-component uORB registration protocol. It registers both an arming check and a mode. Its explicit arming reply code sets `can_arm_and_run = true` unconditionally and assigns fixed availability requirements; no attitude/rate/position magnitude guard was found.

Compiled module evidence:

`src/modules/mc_nn_control/CMakeLists.txt:38`
```cmake
px4_add_module(
	MODULE mc_nn_control
	MAIN mc_nn_control
	COMPILE_FLAGS
	SRCS
```

`src/modules/mc_nn_control/Kconfig:1`
```kconfig
menuconfig MODULES_MC_NN_CONTROL
	bool "mc_nn_control"
	default n
```

`boards/px4/sitl/mcnn_sih.px4board:54`
```text
CONFIG_MODULES_MC_NN_CONTROL=y
CONFIG_MODULES_MC_POS_CONTROL=y
CONFIG_MODULES_MC_RAPTOR=y
```

uORB includes, no `#include <px4_ros2...>`:

`src/modules/mc_nn_control/mc_nn_control.hpp:64`
```cpp
// Subscriptions
#include <uORB/topics/vehicle_local_position.h>
#include <uORB/topics/trajectory_setpoint.h>
#include <uORB/topics/vehicle_attitude.h>
#include <uORB/topics/vehicle_angular_velocity.h>
#include <uORB/topics/vehicle_status.h>
#include <uORB/topics/register_ext_component_reply.h>
```

Mode and arming-check registration:

`src/modules/mc_nn_control/mc_nn_control.cpp:155`
```cpp
void MulticopterNeuralNetworkControl::RegisterNeuralFlightMode()
{
	// Register the neural flight mode with the commander
	register_ext_component_request_s register_ext_component_request{};
	register_ext_component_request.timestamp = hrt_absolute_time();
```

`src/modules/mc_nn_control/mc_nn_control.cpp:160`
```cpp
	strncpy(register_ext_component_request.name, "Neural Control", sizeof(register_ext_component_request.name) - 1);
	register_ext_component_request.request_id = _mode_request_id;
	register_ext_component_request.px4_ros2_api_version = 1;
	register_ext_component_request.register_arming_check = true;
	register_ext_component_request.register_mode = true;
	_register_ext_component_request_pub.publish(register_ext_component_request);
```

Assigned nav state is read from `RegisterExtComponentReply`, not from `getModeRequirements()`:

`src/modules/mc_nn_control/mc_nn_control.cpp:226`
```cpp
	while (_register_ext_component_reply_sub.update(&register_ext_component_reply) && --tries >= 0) {
		if (register_ext_component_reply.request_id == _mode_request_id && register_ext_component_reply.success) {
			_arming_check_id = register_ext_component_reply.arming_check_id;
			_mode_id = register_ext_component_reply.mode_id;
			PX4_INFO("NeuralControl mode registration successful, arming_check_id: %d, mode_id: %d", _arming_check_id, _mode_id);
```

`getModeRequirements()` explicitly excludes external states:

`src/modules/commander/ModeUtil/mode_requirements.cpp:223`
```cpp
	// NAVIGATION_STATE_EXTERNALx: handled outside

	static_assert(vehicle_status_s::NAVIGATION_STATE_MAX == 31, "update mode requirements");
```

Arming check / mode requirements body:

`src/modules/mc_nn_control/mc_nn_control.cpp:198`
```cpp
void MulticopterNeuralNetworkControl::ReplyToArmingCheck(int8 request_id)
{
	arming_check_reply_s arming_check_reply;
	arming_check_reply.timestamp = hrt_absolute_time();
	arming_check_reply.request_id = request_id;
	arming_check_reply.registration_id = _arming_check_id;
```

`src/modules/mc_nn_control/mc_nn_control.cpp:207`
```cpp
	arming_check_reply.can_arm_and_run = true;
	arming_check_reply.mode_req_angular_velocity = true;
	arming_check_reply.mode_req_local_position = true;
	arming_check_reply.mode_req_attitude = true;
	arming_check_reply.mode_req_local_alt = true;
```

`src/modules/mc_nn_control/mc_nn_control.cpp:212`
```cpp
	arming_check_reply.mode_req_home_position = false;
	arming_check_reply.mode_req_mission = false;
	arming_check_reply.mode_req_global_position = false;
	arming_check_reply.mode_req_prevent_arming = false;
	arming_check_reply.mode_req_manual_control = false;
	_arming_check_reply_pub.publish(arming_check_reply);
```

Generated-code caveat: this function does not explicitly assign every field in `arming_check_reply_s` (`mode_req_local_position_relaxed`, `mode_req_global_position_relaxed`, health booleans, padding, and `events[]` are not assigned in the visible body), and the local variable is declared as `arming_check_reply_s arming_check_reply;`, not `arming_check_reply_s arming_check_reply{};`. The generated header has no constructor/default member initializers, so the omitted fields are indeterminate except where later consumers ignore them.

`build/px4_sitl_mcnn_sih/uORB/topics/arming_check_reply.h:53`
```cpp
struct __EXPORT arming_check_reply_s {
#else
struct arming_check_reply_s {
#endif
	uint64_t timestamp;
```

`build/px4_sitl_mcnn_sih/uORB/topics/arming_check_reply.h:69`
```cpp
	bool mode_req_local_position;
	bool mode_req_local_position_relaxed;
	bool mode_req_global_position;
	bool mode_req_global_position_relaxed;
	bool mode_req_mission;
```

Activation path and first control tick:

`src/modules/mc_nn_control/mc_nn_control.cpp:459`
```cpp
void MulticopterNeuralNetworkControl::Run()
{
	if (should_exit()) {
		_angular_velocity_sub.unregisterCallback();

		if (_sent_mode_registration) {
			UnregisterNeuralFlightMode(_arming_check_id, _mode_id);
		}
```

`src/modules/mc_nn_control/mc_nn_control.cpp:493`
```cpp
	if (_vehicle_status_sub.updated()) {
		_vehicle_status_sub.copy(&vehicle_status);
		_use_neural = vehicle_status.nav_state == _mode_id;
	}
```

`src/modules/mc_nn_control/mc_nn_control.cpp:505`
```cpp
	if (!_use_neural) {
		// If the neural network flight mode is not enabled, do nothing
		perf_end(_loop_perf);
		return;
	}
```

`src/modules/mc_nn_control/mc_nn_control.cpp:517`
```cpp
	if (_angular_velocity_sub.update(&_angular_velocity)) {
		const float dt = math::constrain(((_angular_velocity.timestamp_sample - _last_run) * 1e-6f), 0.0002f, 0.02f);
		_last_run = _angular_velocity.timestamp_sample;

		if (_attitude_sub.updated()) {
			_attitude_sub.copy(&_attitude);
		}
```

The attitude/rate values are used as neural network inputs, not admission predicates:

`src/modules/mc_nn_control/mc_nn_control.cpp:348`
```cpp
	matrix::Quatf attitude = matrix::Quatf(_attitude.q);
	matrix::Dcmf _attitude_local_mat = frame_transf * (frame_transf_2 * matrix::Dcmf(attitude)) * frame_transf.transpose();

	matrix::Vector3f angular_vel_local = matrix::Vector3f(_angular_velocity.xyz[0], _angular_velocity.xyz[1],
					     _angular_velocity.xyz[2]);
```

Searches:
- `rg -n "ArmingCheck|arming_check|registerArmingCheck|modeRequirements|RegisterExtComponent|register_ext_component" src/modules/mc_nn_control`
- `rg -n "#include .*px4_ros2|px4_ros2::" src/modules/mc_nn_control` returned no hits.
- `rg -n "roll|pitch|attitude|angular|omega|vehicle_attitude|vehicle_angular_velocity" src/modules/mc_nn_control` found observation/input use, not entry rejection.

#### mc_raptor

Conclusion: It is also a compiled PX4 module, not a companion ROS 2 process. It registers through the external-component uORB protocol, including an arming check and a mode. Its explicit `can_arm_and_run` assignment is `can_arm`, which is set by observation freshness/timeouts. No handover attitude-angle or angular-rate magnitude threshold was found. It does reset recurrent state on activation.

Compiled module evidence:

`src/modules/mc_raptor/CMakeLists.txt:5`
```cmake
px4_add_module(
	MODULE modules__mc_raptor
	MAIN mc_raptor
	STACK_MAIN 4000
```

`src/modules/mc_raptor/Kconfig:1`
```kconfig
menuconfig MODULES_MC_RAPTOR
	bool "mc_raptor"
	default n
```

`boards/px4/sitl/raptor.px4board:53`
```text
CONFIG_MODULES_MC_RAPTOR=y
CONFIG_MODULES_MC_RATE_CONTROL=y
CONFIG_MODULES_NAVIGATOR=y
```

uORB includes, no `#include <px4_ros2...>`:

`src/modules/mc_raptor/mc_raptor.hpp:19`
```cpp
#include <uORB/topics/vehicle_attitude.h>
#include <uORB/topics/vehicle_angular_velocity.h>
#include <uORB/topics/actuator_motors.h>
#include <uORB/topics/trajectory_setpoint.h>
#include <uORB/topics/register_ext_component_request.h>
#include <uORB/topics/register_ext_component_reply.h>
```

Registration:

`src/modules/mc_raptor/mc_raptor.cpp:254`
```cpp
	register_ext_component_request_s register_ext_component_request{};
	register_ext_component_request.timestamp = hrt_absolute_time();
	strncpy(register_ext_component_request.name, "RAPTOR", sizeof(register_ext_component_request.name) - 1);
	register_ext_component_request.request_id = Raptor::EXT_COMPONENT_REQUEST_ID;
	register_ext_component_request.px4_ros2_api_version = 1;
```

`src/modules/mc_raptor/mc_raptor.cpp:259`
```cpp
	register_ext_component_request.register_arming_check = true;
	register_ext_component_request.register_mode = true;
	register_ext_component_request.enable_replace_internal_mode = _param_mc_raptor_offboard.get();
	register_ext_component_request.replace_internal_mode = vehicle_status_s::NAVIGATION_STATE_OFFBOARD;
	register_ext_component_request.request_offboard_setpoints = true;
	_register_ext_component_request_pub.publish(register_ext_component_request);
```

Mode id assignment:

`src/modules/mc_raptor/mc_raptor.cpp:466`
```cpp
	if (_register_ext_component_reply_sub.update(&register_ext_component_reply)) {
		if (register_ext_component_reply.request_id == Raptor::EXT_COMPONENT_REQUEST_ID && register_ext_component_reply.success) {
			ext_component_arming_check_id = register_ext_component_reply.arming_check_id;
			ext_component_mode_id = register_ext_component_reply.mode_id;
```

Arming check / requirements:

`src/modules/mc_raptor/mc_raptor.cpp:416`
```cpp
void Raptor::updateArmingCheckReply()
{
	if (flightmode_state == FlightModeState::CONFIGURED) {
		if (_arming_check_request_sub.updated()) {
```

`src/modules/mc_raptor/mc_raptor.cpp:428`
```cpp
			arming_check_reply.can_arm_and_run = can_arm;
			arming_check_reply.mode_req_angular_velocity = true;
			arming_check_reply.mode_req_local_position = true;
			arming_check_reply.mode_req_attitude = true;
			arming_check_reply.mode_req_local_alt = true;
```

`src/modules/mc_raptor/mc_raptor.cpp:433`
```cpp
			arming_check_reply.mode_req_home_position = false;
			arming_check_reply.mode_req_mission = false;
			arming_check_reply.mode_req_global_position = false;
			arming_check_reply.mode_req_prevent_arming = false;
			arming_check_reply.mode_req_manual_control = false;
```

Generated-code caveat: as with `mc_nn_control`, the reply object is declared as `arming_check_reply_s arming_check_reply;` at `src/modules/mc_raptor/mc_raptor.cpp:422`, not brace-initialized. The generated header has no default initialization, and `mode_req_local_position_relaxed` / `mode_req_global_position_relaxed` are not explicitly assigned in the visible body. This does not create a continuous-state guard, but it does make the reply publication a likely upstream initialization bug.

Activation path:

`src/modules/mc_raptor/mc_raptor.cpp:444`
```cpp
void Raptor::Run()
{
	if (should_exit()) {
		_vehicle_angular_velocity_sub.unregisterCallback();

		if (flightmode_state >= FlightModeState::REGISTERED) {
```

`src/modules/mc_raptor/mc_raptor.cpp:538`
```cpp
	bool next_active = timestamp_last_vehicle_status_set && _vehicle_status.nav_state == ext_component_mode_id;

	if (!previous_active && next_active) {
		this->reset();
		PX4_INFO("Resetting Inference Executor (Recurrent State)");
```

`can_arm` false paths are observation availability/freshness:

`src/modules/mc_raptor/mc_raptor.cpp:636`
```cpp
	if (!timestamp_last_angular_velocity_set || !timestamp_last_local_position_set || !timestamp_last_attitude_set) {
		status.exit_reason = raptor_status_s::EXIT_REASON_NOT_ALL_OBSERVATIONS_SET;
		status.vehicle_angular_velocity_stale = !timestamp_last_angular_velocity_set;
		status.vehicle_local_position_stale = !timestamp_last_local_position_set;
		status.vehicle_attitude_stale = !timestamp_last_attitude_set;
```

`src/modules/mc_raptor/mc_raptor.cpp:646`
```cpp
		can_arm = false;
		updateArmingCheckReply();
		return;
	}
```

`src/modules/mc_raptor/mc_raptor.cpp:651`
```cpp
	if ((current_time - timestamp_last_angular_velocity) > OBSERVATION_TIMEOUT_ANGULAR_VELOCITY) {
		status.exit_reason = raptor_status_s::EXIT_REASON_ANGULAR_VELOCITY_STALE;
```

`src/modules/mc_raptor/mc_raptor.cpp:753`
```cpp
	if ((current_time - timestamp_last_attitude) > OBSERVATION_TIMEOUT_ATTITUDE) {
		status.exit_reason = raptor_status_s::EXIT_REASON_ATTITUDE_STALE;
```

`src/modules/mc_raptor/mc_raptor.cpp:773`
```cpp
	can_arm = true;
	updateArmingCheckReply();
```

GRU/recurrent state reset:

`src/modules/mc_raptor/mc_raptor.cpp:40`
```cpp
void Raptor::reset()
{

	trajectory_setpoint_dt_index = 0;
	trajectory_setpoint_dts_full = false;
```

`src/modules/mc_raptor/mc_raptor.cpp:50`
```cpp
	for (TI action_i = 0; action_i < EXECUTOR_SPEC::OUTPUT_DIM; action_i++) {
		this->previous_action[action_i] = RESET_PREVIOUS_ACTION_VALUE;
	}

	rlt::reset(device, executor, policy, rng);
```

Searches:
- `rg -n "ArmingCheck|arming_check|registerArmingCheck|modeRequirements|RegisterExtComponent|register_ext_component" src/modules/mc_raptor`
- `rg -n "#include .*px4_ros2|px4_ros2::" src/modules/mc_raptor` returned no hits.
- `rg -n "can_arm|roll|pitch|attitude|angular|omega|vehicle_attitude|vehicle_angular_velocity|hidden|gru" src/modules/mc_raptor` found observation freshness/timeouts and inference input use, not handover value thresholds.

### Q4 - external mode 的扩展点到底能表达什么

Conclusion: External mode replies expose the same fixed boolean requirement fields listed in `ArmingCheckReply.msg`, except that this message does not include every `FailsafeFlags` field (`mode_req_offboard_signal`, `mode_req_wind_and_flight_time_compliance`, and `mode_req_other` are not reply fields). They also expose `can_arm_and_run`, a boolean computed by the external component. Therefore external modes can implement arbitrary predicates only by computing them externally and returning a boolean failure; the FMU API does not carry a predicate expression or continuous threshold.

External mode range:

`msg/versioned/VehicleStatus.msg:55`
```msg
uint8 NAVIGATION_STATE_EXTERNAL1 = 23
uint8 NAVIGATION_STATE_EXTERNAL2 = 24
uint8 NAVIGATION_STATE_EXTERNAL3 = 25
uint8 NAVIGATION_STATE_EXTERNAL4 = 26
uint8 NAVIGATION_STATE_EXTERNAL5 = 27
uint8 NAVIGATION_STATE_EXTERNAL6 = 28
uint8 NAVIGATION_STATE_EXTERNAL7 = 29
uint8 NAVIGATION_STATE_EXTERNAL8 = 30
```

Registration request fields:

`msg/versioned/RegisterExtComponentRequest.msg:15`
```msg
bool register_arming_check
bool register_mode                 # registering a mode also requires arming_check to be set
bool register_mode_executor        # registering an executor also requires a mode to be registered (which is the owned mode by the executor)

bool enable_replace_internal_mode  # set to true if an internal mode should be replaced
```

ModeManagement validates and registers:

`src/modules/commander/ModeManagement.cpp:241`
```cpp
		if (request.register_mode_executor && !request.register_mode) {
			request_valid = false;
		}

		if (request.register_mode && !request.register_arming_check) {
			request_valid = false;
		}
```

`src/modules/commander/ModeManagement.cpp:290`
```cpp
				if (request.register_mode) {
					Modes::Mode mode{};
					strncpy(mode.name, request.name, sizeof(mode.name));

					if (request.enable_replace_internal_mode) {
```

`src/modules/commander/ModeManagement.cpp:300`
```cpp
					nav_mode_id = _modes.addExternalMode(mode);
					reply.mode_id = nav_mode_id;
				}
```

`src/modules/commander/ModeManagement.cpp:316`
```cpp
				if (request.register_arming_check) {
					int8_t replace_nav_state = request.enable_replace_internal_mode ? request.replace_internal_mode : -1;
					int registration_id = _external_checks.addRegistration(nav_mode_id, replace_nav_state);
```

Reply fields:

`msg/versioned/ArmingCheckReply.msg:24`
```msg
bool can_arm_and_run # True if the component can arm. For navigation mode components, true if the component can arm in the mode or switch to the mode when already armed

uint8 num_events # Number of queued failure messages (Event) in the events field
```

`msg/versioned/ArmingCheckReply.msg:31`
```msg
bool mode_req_angular_velocity # Requires angular velocity estimate (e.g. from gyroscope)
bool mode_req_attitude # Requires an attitude estimate
bool mode_req_local_alt # Requires a local altitude estimate
bool mode_req_local_position # Requires a local position estimate
bool mode_req_local_position_relaxed # Requires a more relaxed global position estimate
bool mode_req_global_position # Requires a global position estimate
```

`msg/versioned/ArmingCheckReply.msg:37`
```msg
bool mode_req_global_position_relaxed # Requires a relaxed global position estimate
bool mode_req_mission # Requires an uploaded mission
bool mode_req_home_position # Requires a home position (such as RTL/Return mode)
bool mode_req_prevent_arming # Prevent arming (such as in Land mode)
bool mode_req_manual_control # Requires a manual controller
```

FMU consumes reply:

`src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:162`
```cpp
				if (!reply.can_arm_and_run) {
					setOrClearRequirementBits(true, nav_mode_id, replaces_nav_state, reporter.failsafeFlags().mode_req_other);
				}

				// Mode requirements
```

`src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:168`
```cpp
				setOrClearRequirementBits(reply.mode_req_angular_velocity, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_angular_velocity);
				setOrClearRequirementBits(reply.mode_req_attitude, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_attitude);
```

`src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:172`
```cpp
				setOrClearRequirementBits(reply.mode_req_local_alt, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_local_alt);
				setOrClearRequirementBits(reply.mode_req_local_position, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_local_position);
```

`src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:176`
```cpp
				setOrClearRequirementBits(reply.mode_req_local_position_relaxed, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_local_position_relaxed);
				setOrClearRequirementBits(reply.mode_req_global_position, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_global_position);
```

`src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:180`
```cpp
				setOrClearRequirementBits(reply.mode_req_global_position_relaxed, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_global_position_relaxed);
				setOrClearRequirementBits(reply.mode_req_mission, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_mission);
```

`src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:184`
```cpp
				setOrClearRequirementBits(reply.mode_req_home_position, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_home_position);
				setOrClearRequirementBits(reply.mode_req_prevent_arming, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_prevent_arming);
```

`src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:188`
```cpp
				setOrClearRequirementBits(reply.mode_req_manual_control, nav_mode_id, replaces_nav_state,
							  reporter.failsafeFlags().mode_req_manual_control);
```

So `|attitude| < 40 deg` is feasible only as: external component obtains attitude by its own data path, computes the predicate in that process, publishes `can_arm_and_run=false` plus an event when it fails, and FMU maps that to `mode_req_other`/`can_run` clearing. The FMU side does not store the predicate or its threshold. The handover check consumes the cached `_registrations[reg_idx].reply`, not a synchronous callback into the component. Latency/frequency limits visible in code are `ExternalChecks::UPDATE_INTERVAL = 300_ms`, `REQUEST_TIMEOUT = 50_ms`, three missed established replies before unresponsive mode, and commander health checks at 10 Hz or on changes.

`src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:130`
```cpp
		arming_check_reply_s &reply = *_registrations[reg_idx].reply;

		int8_t nav_mode_id = _registrations[reply.registration_id].nav_mode_id;
```

`src/modules/commander/HealthAndArmingChecks/checks/externalChecks.cpp:249`
```cpp
			if (_registrations[reply.registration_id].reply) {
				*_registrations[reply.registration_id].reply = reply;
			}
```

Searches:
- `rg -n "can_arm_and_run|mode_req_angular_velocity|ArmingCheckReply" msg src`
- `rg -n "RegisterExtComponent|register_ext_component|addRegistration|setExternalNavStates|EXTERNAL1|EXTERNAL8" msg src/modules/commander`

### Q5 - 经典控制器积分器的跨模式重置语义

Conclusion: In code, there is no single universal "reset on returning from mc_nn_control/mc_raptor" rule. In the scanned ULOG dataset, however, every `mc_nn_control` and `mc_raptor` log with nav_state 23 used the safe-default effective control mode (`flag_control_rates_enabled=true`, `flag_multicopter_position_control_enabled=true`, `source_id=0`), and `rate_ctrl_status` continued publishing throughout the external-mode interval. Thus the logged runs do not support "rate I freezes during the external mode"; they show the classic rate controller continuing to run.

Rate controller:
- Runs only under `flag_control_rates_enabled`.
- It resets I only when disarmed or vehicle type is not rotary wing.
- Therefore, if the aircraft is armed rotary wing and rate control were disabled during the NN/RAPTOR mode, switching back to a classic rate-controlled mode would not itself reset the rate I in this code path. The ULOGs do not show that disabled-rate-control case: they show `flag_control_rates_enabled=true` and active `rate_ctrl_status`.

`src/modules/mc_rate_control/MulticopterRateControl.cpp:189`
```cpp
		if (_vehicle_control_mode.flag_control_rates_enabled) {

			// reset integral if disarmed
			if (!_vehicle_control_mode.flag_armed || _vehicle_status.vehicle_type != vehicle_status_s::VEHICLE_TYPE_ROTARY_WING) {
				_rate_control.resetIntegral();
			}
```

`src/lib/rate_control/rate_control.hpp:99`
```cpp
	/**
	 * Set the integral term to 0 to prevent windup
	 * @see _rate_int
	 */
	void resetIntegral() { _rate_int.zero(); }
```

Position controller:
- `mc_nn_control` and `mc_raptor` both publish `config_control_setpoints` with `flag_multicopter_position_control_enabled = false`.
- They do not assign `flag_control_rates_enabled`; because the local `vehicle_control_mode_s config_control_setpoints{}` is value-initialized, their explicit message has that flag false.
- Commander overwrites `flag_multicopter_position_control_enabled` before publication, based on vehicle type and generic altitude/climb/position/velocity/acceleration flags.
- Therefore the prior hard conclusion "position I resets while the external mode is active" is too strong. Fresh `mc_nn_control` config sets `flag_control_climb_rate_enabled = true`, so Commander recomputes `flag_multicopter_position_control_enabled = true` and the position-controller disabled/reset branch is not forced. Fresh `mc_raptor` config sets those generic position/climb flags false, so Commander can publish `flag_multicopter_position_control_enabled = false` and force the reset branch. If an external-mode config is stale at activation, Commander uses safe defaults, which also make the multicopter position flag true.
- The ULOGs show the stale safe-default outcome for both modules: `flag_multicopter_position_control_enabled=true`, so the position-controller disabled/reset branch is not forced in the logged external-mode intervals.

`src/modules/mc_nn_control/mc_nn_control.cpp:184`
```cpp
	vehicle_control_mode_s config_control_setpoints{};
	config_control_setpoints.timestamp = hrt_absolute_time();
	config_control_setpoints.source_id = mode_id;
	config_control_setpoints.flag_multicopter_position_control_enabled = false;
	config_control_setpoints.flag_control_manual_enabled = _param_manual_control.get();
	config_control_setpoints.flag_control_offboard_enabled = false;
```

`src/modules/mc_raptor/mc_raptor.cpp:476`
```cpp
		vehicle_control_mode_s config_control_setpoints{};
		config_control_setpoints.timestamp = hrt_absolute_time();
		config_control_setpoints.source_id = ext_component_mode_id;
		config_control_setpoints.flag_multicopter_position_control_enabled = false;
		config_control_setpoints.flag_control_manual_enabled = false;
		config_control_setpoints.flag_control_offboard_enabled = false;
```

No explicit rates flag assignment in either module:

`src/modules/mc_nn_control/mc_nn_control.cpp:190`
```cpp
	config_control_setpoints.flag_control_position_enabled = false;
	config_control_setpoints.flag_control_climb_rate_enabled = true;
	config_control_setpoints.flag_control_allocation_enabled = false;
	config_control_setpoints.flag_control_termination_enabled = true;
	_config_control_setpoints_pub.publish(config_control_setpoints);
```

Commander safe defaults:

`src/modules/commander/ModeManagement.hpp:92`
```cpp
	config_control_setpoint_.flag_control_position_enabled = true;
	config_control_setpoint_.flag_control_velocity_enabled = true;
	config_control_setpoint_.flag_control_altitude_enabled = true;
	config_control_setpoint_.flag_control_climb_rate_enabled = true;
	config_control_setpoint_.flag_control_acceleration_enabled = true;
	config_control_setpoint_.flag_control_attitude_enabled = true;
	config_control_setpoint_.flag_control_rates_enabled = true;
```

Commander recomputes the multicopter-position flag after external mode management:

`src/modules/commander/Commander.cpp:2766`
```cpp
	_vehicle_control_mode.flag_armed = isArmed();
	_vehicle_control_mode.flag_multicopter_position_control_enabled =
		(_vehicle_status.vehicle_type == vehicle_status_s::VEHICLE_TYPE_ROTARY_WING)
		&& (_vehicle_control_mode.flag_control_altitude_enabled
		    || _vehicle_control_mode.flag_control_climb_rate_enabled
```

`src/modules/commander/Commander.cpp:2771`
```cpp
		    || _vehicle_control_mode.flag_control_position_enabled
		    || _vehicle_control_mode.flag_control_velocity_enabled
		    || _vehicle_control_mode.flag_control_acceleration_enabled);
	_vehicle_control_mode.timestamp = hrt_absolute_time();
```

`src/modules/commander/ModeManagement.cpp:551`
```cpp
		// Refuse a cached config_control_setpoints entry that predates the current
		// activation of this nav_state; publish safe defaults until a fresh one arrives.
		const bool stale = (mode.config_control_setpoint.timestamp == 0)
				   || (mode.config_control_setpoint.timestamp + 10_ms < _last_served_change_us);
```

`src/modules/mc_pos_control/MulticopterPositionControl.cpp:619`
```cpp
		} else {
			// an update is necessary here because otherwise the takeoff state doesn't get skipped with non-altitude-controlled modes
			_takeoff.updateTakeoffState(_vehicle_control_mode.flag_armed, _vehicle_land_detected.landed, false, 10.f, true,
						    vehicle_local_position.timestamp_sample);
			_control.resetIntegral();
```

`src/modules/mc_pos_control/PositionControl/PositionControl.hpp:160`
```cpp
	/**
	 * Set the integral term in xy to 0.
	 * @see _vel_int
	 */
	void resetIntegral() { _vel_int.setZero(); }
	void resetIntegralXY() { _vel_int.xy() = matrix::Vector2f(); }
```

Attitude controller:
- Search did not find an attitude-controller I term reset analogous to rate/position in `src/modules/mc_att_control`; the code resets manual input filters/yaw setpoint when not running attitude control, not an I term.

`src/modules/mc_att_control/mc_att_control_main.cpp:377`
```cpp
		} else {
			_man_roll_input_filter.reset(0.f);
			_man_pitch_input_filter.reset(0.f);
			_yaw_setpoint_stabilized = NAN;
			_stick_yaw.reset(Eulerf(q).psi(), _unaided_heading);
```

mc_raptor recurrent/GRU hidden-state reset:

`src/modules/mc_raptor/mc_raptor.cpp:538`
```cpp
	bool next_active = timestamp_last_vehicle_status_set && _vehicle_status.nav_state == ext_component_mode_id;

	if (!previous_active && next_active) {
		this->reset();
		PX4_INFO("Resetting Inference Executor (Recurrent State)");
```

`src/modules/mc_raptor/mc_raptor.cpp:50`
```cpp
	for (TI action_i = 0; action_i < EXECUTOR_SPEC::OUTPUT_DIM; action_i++) {
		this->previous_action[action_i] = RESET_PREVIOUS_ACTION_VALUE;
	}

	rlt::reset(device, executor, policy, rng);
```

Searches:
- `rg -n "resetIntegral|_rate_control.resetIntegral|resetIntegrals|_vel_int.setZero" src/modules/mc_rate_control src/modules/mc_att_control src/modules/mc_pos_control src/lib/rate_control`
- `rg -n "hidden|gru|rlt::reset|void Raptor::reset|previous_active|next_active" src/modules/mc_raptor`

## 3. 我不确定的地方
- PX4 HEAD matches `3042f906...`, but `git -C external/PX4-Autopilot status --short` showed a dirty worktree before this report, including modified `src/modules/mc_raptor/mc_raptor.cpp`, `src/modules/mc_raptor/module.yaml`, and untracked SITL board files. I did inspect `git diff -- src/modules/mc_raptor/`; the RAPTOR diff does not touch `can_arm`, `updateArmingCheckReply()`, or activation reset. Other dirty files outside `src/modules/mc_raptor/` were not exhaustively audited.
- Generated headers were inspected for `arming_check_reply_s`, and they do not provide default initialization. That makes the uninitialized reply fields in `mc_nn_control` and `mc_raptor` a source-level defect candidate, not merely an unknown. I did not build or run to observe the published bytes.
- I did not run build, simulation, unit tests, or any new runtime experiment. Timing conclusions are from scheduler constants, code paths, and existing ULOG records only.
- For C7, the code path remains conditional in principle, because the effective `vehicle_control_mode` at handover depends on fresh vs stale external-mode config. The scanned ULOGs resolve the current dataset: all observed `mc_nn_control`/`mc_raptor` nav_state 23 intervals used safe defaults. This is still a log-dataset result, not a proof that every future run must do the same.
- For Q4, an external mode can encode arbitrary predicates only if it has an independent way to observe the needed state. The FMU API shown here carries the boolean result, not the state or predicate expression.

## 4. 与项目笔记冲突之处
- The background says the "Per mode requirements" list has 13 flags. In this SHA's source it has 14 because `mode_req_global_position_relaxed` is present at `msg/FailsafeFlags.msg:15`.
- If project notes say `mc_nn_control` is a ROS 2 Interface Library mode: code evidence here says it is compiled as a PX4 module (`px4_add_module`, Kconfig, board config) and contains no `#include <px4_ros2...>` or `px4_ros2::` use. It does use the external-component uORB registration messages and sets `px4_ros2_api_version`.
- If project notes say `mc_nn_control` registers a mode and arming check: that part is true. It sets `register_arming_check = true` and `register_mode = true` at `src/modules/mc_nn_control/mc_nn_control.cpp:163`.
- If project notes say `mc_nn_control` or `mc_raptor` have no arming check registration: that is false. Both publish `register_ext_component_request` with arming check and mode enabled.
- If the intended paper claim is "no handover continuous-state admission check exists for mc_nn_control/mc_raptor": this is still supported by the inspected code. The required wording should not claim "they do not register arming checks"; it should say "their registered checks do not test handover attitude/rate/position magnitudes."
