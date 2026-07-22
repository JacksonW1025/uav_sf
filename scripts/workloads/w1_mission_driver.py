#!/usr/bin/env python3
"""Drive the preregistered low-risk Aerostack2 mission through public interfaces."""

from __future__ import annotations

import argparse
import json
import math
import time
import uuid
from pathlib import Path
from typing import Any, Callable


def _versioned_topic(base: str, message_type: object) -> str:
    version = int(getattr(message_type, "MESSAGE_VERSION", 0))
    return f"{base}_v{version}" if version else base


def _goal_id(goal_handle: Any) -> str:
    return bytes(goal_handle.goal_id.uuid).hex()


def run(args: argparse.Namespace) -> int:
    try:
        import rclpy
        from action_msgs.msg import GoalStatus
        from as2_msgs.action import FollowPath, GoToWaypoint
        from as2_msgs.msg import PlatformStateMachineEvent, PoseWithID, YawMode
        from as2_msgs.srv import SetPlatformStateMachineEvent
        from px4_msgs.msg import VehicleCommand, VehicleLandDetected, VehicleLocalPosition, VehicleStatus
        from rclpy.action import ActionClient
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from std_srvs.srv import SetBool
    except ImportError as exc:  # pragma: no cover - locked ROS runtime only
        raise SystemExit(f"locked W1 ROS workspaces are required: {exc}") from exc

    args.events.parent.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    class Mission(Node):
        def __init__(self) -> None:
            super().__init__(f"w1_{args.run_id.replace('-', '_')}_mission")
            self.events = args.events.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.status: Any | None = None
            self.position: Any | None = None
            self.land: Any | None = None
            self.feedback_counts = {"go_to": 0, "follow_path": 0}
            self.failure_reason: str | None = None
            self.safety_stop = False
            best_effort = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=20,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            for message_type, topic, callback in (
                (VehicleStatus, "/fmu/out/vehicle_status", self._status),
                (VehicleLocalPosition, "/fmu/out/vehicle_local_position", self._position),
                (VehicleLandDetected, "/fmu/out/vehicle_land_detected", self._land),
            ):
                self.create_subscription(
                    message_type, _versioned_topic(topic, message_type), callback, best_effort
                )
            self.command_pub = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", 10)
            self.arm_client = self.create_client(SetBool, "/drone0/set_arming_state")
            self.offboard_client = self.create_client(SetBool, "/drone0/set_offboard_mode")
            self.state_client = self.create_client(
                SetPlatformStateMachineEvent, "/drone0/platform/state_machine_event"
            )
            self.go_to_client = ActionClient(self, GoToWaypoint, "/drone0/GoToBehavior")
            self.follow_path_client = ActionClient(self, FollowPath, "/drone0/FollowPathBehavior")
            self._event(
                "mission_started",
                run_id=args.run_id,
                replay_mode=args.replay_mode,
                test_environment_gate=True,
                direct_actuator_commands=False,
            )

        def _event(self, event_type: str, **fields: Any) -> None:
            record = {
                "event_type": event_type,
                "monotonic_ns": time.monotonic_ns(),
                "ros_time_ns": self.get_clock().now().nanoseconds,
                **fields,
            }
            self.events.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
            self.events.flush()

        def _phase(self, phase: str) -> None:
            self._event("mission_phase", phase=phase)

        def _status(self, msg: Any) -> None:
            self.status = msg

        def _position(self, msg: Any) -> None:
            self.position = msg
            values = (float(msg.x), float(msg.y), float(msg.z), float(msg.vx), float(msg.vy), float(msg.vz))
            if not all(math.isfinite(value) for value in values):
                self.safety_stop = True
                self.failure_reason = "non-finite vehicle local position or velocity"
            distance = math.hypot(float(msg.x), float(msg.y))
            altitude = -float(msg.z)
            speed = math.sqrt(float(msg.vx) ** 2 + float(msg.vy) ** 2 + float(msg.vz) ** 2)
            if altitude > 3.0 or distance > 5.0 or speed > 3.0:
                self.safety_stop = True
                self.failure_reason = (
                    f"formal safety bound exceeded altitude={altitude:.3f} "
                    f"distance={distance:.3f} speed={speed:.3f}"
                )

        def _land(self, msg: Any) -> None:
            self.land = msg

        def _spin_until(self, predicate: Callable[[], bool], timeout: float, label: str) -> bool:
            deadline = time.monotonic() + timeout
            while rclpy.ok() and time.monotonic() < deadline:
                rclpy.spin_once(self, timeout_sec=0.05)
                if self.safety_stop:
                    return False
                if predicate():
                    return True
            self.failure_reason = f"timeout waiting for {label}"
            return False

        def _future(self, future: Any, timeout: float, label: str) -> Any:
            if not self._spin_until(future.done, timeout, label):
                raise RuntimeError(self.failure_reason)
            result = future.result()
            if result is None:
                raise RuntimeError(f"{label} returned no result")
            return result

        def _service(self, name: str, client: Any, request: Any, timeout: float = 15.0) -> Any:
            if not client.wait_for_service(timeout_sec=timeout):
                raise RuntimeError(f"service unavailable: {name}")
            request_id = uuid.uuid4().hex
            self._event(
                "service_request",
                service=name,
                request_id=request_id,
                request_timestamp_ns=self.get_clock().now().nanoseconds,
                request={
                    key: getattr(request, key)
                    for key in request.get_fields_and_field_types()
                    if isinstance(getattr(request, key), (bool, int, float, str))
                },
            )
            response = self._future(client.call_async(request), timeout, f"service result {name}")
            response_fields = {
                key: getattr(response, key)
                for key in response.get_fields_and_field_types()
                if isinstance(getattr(response, key), (bool, int, float, str))
            }
            self._event(
                "service_result",
                service=name,
                request_id=request_id,
                result_timestamp_ns=self.get_clock().now().nanoseconds,
                response=response_fields,
            )
            if hasattr(response, "success") and not bool(response.success):
                raise RuntimeError(f"service rejected request: {name}")
            return response

        def _set_bool(self, name: str, client: Any, value: bool) -> Any:
            request = SetBool.Request()
            request.data = value
            return self._service(name, client, request)

        def _state_event(self, value: int, label: str) -> None:
            request = SetPlatformStateMachineEvent.Request()
            request.event.event = int(value)
            self._service(f"/drone0/platform/state_machine_event:{label}", self.state_client, request)

        def _command(self, command: int, **params: float) -> None:
            message = VehicleCommand()
            message.timestamp = self.get_clock().now().nanoseconds // 1000
            message.command = int(command)
            for index in range(1, 8):
                setattr(message, f"param{index}", float(params.get(f"param{index}", math.nan)))
            message.target_system = 1
            message.target_component = 1
            message.source_system = 1
            message.source_component = 192
            message.from_external = True
            self.command_pub.publish(message)
            self._event("vehicle_command", command=int(command), params=params, values=params)

        def _periodic_command_until(
            self,
            command: int,
            predicate: Callable[[], bool],
            timeout: float,
            label: str,
            period: float = 0.5,
            **params: float,
        ) -> bool:
            deadline = time.monotonic() + timeout
            last = 0.0
            while rclpy.ok() and time.monotonic() < deadline:
                now = time.monotonic()
                if now - last >= period:
                    self._command(command, **params)
                    last = now
                rclpy.spin_once(self, timeout_sec=0.05)
                if self.safety_stop:
                    return False
                if predicate():
                    return True
            self.failure_reason = f"timeout waiting for {label}"
            return False

        def _feedback(self, action: str, message: Any) -> None:
            self.feedback_counts[action] += 1
            feedback = message.feedback
            values = {
                key: getattr(feedback, key)
                for key in feedback.get_fields_and_field_types()
                if isinstance(getattr(feedback, key), (bool, int, float, str))
            }
            self._event("action_feedback", action=action, feedback=values)

        def _go_to(self) -> None:
            if not self.go_to_client.wait_for_server(timeout_sec=15.0):
                raise RuntimeError("GoToBehavior action unavailable")
            goal = GoToWaypoint.Goal()
            goal.yaw.mode = YawMode.KEEP_YAW
            goal.yaw.angle = 0.0
            goal.target_pose.header.stamp = self.get_clock().now().to_msg()
            goal.target_pose.header.frame_id = "earth"
            goal.target_pose.point.x = 1.5
            goal.target_pose.point.y = 0.0
            goal.target_pose.point.z = 1.5
            goal.max_speed = 0.5
            request_id = uuid.uuid4().hex
            self._event(
                "action_goal_request",
                action="go_to",
                request_id=request_id,
                goal_timestamp_ns=self.get_clock().now().nanoseconds,
                values={"target_enu_m": [1.5, 0.0, 1.5], "max_speed_m_s": 0.5, "yaw_rad": 0.0},
            )
            handle = self._future(
                self.go_to_client.send_goal_async(goal, feedback_callback=lambda msg: self._feedback("go_to", msg)),
                15.0,
                "go-to goal response",
            )
            if not handle.accepted:
                raise RuntimeError("go-to goal rejected")
            goal_id = _goal_id(handle)
            self._event("action_goal_accepted", action="go_to", request_id=request_id, goal_id=goal_id)
            result = self._future(handle.get_result_async(), 45.0, "go-to result")
            self._event(
                "action_result",
                action="go_to",
                goal_id=goal_id,
                status=int(result.status),
                success=bool(result.result.go_to_success),
            )
            if int(result.status) != int(GoalStatus.STATUS_SUCCEEDED) or not result.result.go_to_success:
                raise RuntimeError("go-to did not complete successfully")

        def _follow_path_cancel(self) -> None:
            if not self.follow_path_client.wait_for_server(timeout_sec=15.0):
                raise RuntimeError("FollowPathBehavior action unavailable")
            goal = FollowPath.Goal()
            goal.header.stamp = self.get_clock().now().to_msg()
            goal.header.frame_id = "earth"
            goal.yaw.mode = YawMode.KEEP_YAW
            goal.yaw.angle = 0.0
            goal.max_speed = 0.5
            for name, coordinates in (("w1", (1.5, 1.0, 1.5)), ("w2", (0.5, 1.0, 1.5))):
                point = PoseWithID()
                point.id = name
                point.pose.position.x, point.pose.position.y, point.pose.position.z = coordinates
                point.pose.orientation.w = 1.0
                goal.path.append(point)
            request_id = uuid.uuid4().hex
            self._event(
                "action_goal_request",
                action="follow_path",
                request_id=request_id,
                goal_timestamp_ns=self.get_clock().now().nanoseconds,
                values={
                    "path_enu_m": [[1.5, 1.0, 1.5], [0.5, 1.0, 1.5]],
                    "max_speed_m_s": 0.5,
                    "yaw_rad": 0.0,
                },
            )
            handle = self._future(
                self.follow_path_client.send_goal_async(
                    goal, feedback_callback=lambda msg: self._feedback("follow_path", msg)
                ),
                15.0,
                "follow-path goal response",
            )
            if not handle.accepted:
                raise RuntimeError("follow-path goal rejected")
            goal_id = _goal_id(handle)
            self._event(
                "action_goal_accepted",
                action="follow_path",
                request_id=request_id,
                goal_id=goal_id,
            )
            if not self._spin_until(
                lambda: self.feedback_counts["follow_path"] >= 2,
                5.0,
                "follow-path feedback before cancel",
            ):
                raise RuntimeError(self.failure_reason)
            self._event(
                "action_cancel_request",
                action="follow_path",
                goal_id=goal_id,
                cancel_request_timestamp_ns=self.get_clock().now().nanoseconds,
            )
            cancel = self._future(handle.cancel_goal_async(), 10.0, "follow-path cancel acknowledgement")
            acknowledged = any(bytes(item.goal_id.uuid).hex() == goal_id for item in cancel.goals_canceling)
            self._event(
                "action_cancel_ack",
                action="follow_path",
                goal_id=goal_id,
                acknowledged=acknowledged,
                cancel_ack_timestamp_ns=self.get_clock().now().nanoseconds,
            )
            if not acknowledged:
                raise RuntimeError("follow-path cancel was not acknowledged")
            result = self._future(handle.get_result_async(), 15.0, "follow-path canceled result")
            self._event(
                "action_result",
                action="follow_path",
                goal_id=goal_id,
                status=int(result.status),
                success=bool(result.result.follow_path_success),
            )
            if int(result.status) != int(GoalStatus.STATUS_CANCELED):
                raise RuntimeError(f"follow-path cancel result status was {result.status}")

        def _armed(self) -> bool:
            return self.status is not None and int(self.status.arming_state) == int(VehicleStatus.ARMING_STATE_ARMED)

        def _landed(self) -> bool:
            return self.land is not None and bool(self.land.landed)

        def cleanup(self) -> None:
            if self._armed() and not self._landed():
                self._event("cleanup_land_requested", reason=self.failure_reason)
                self._periodic_command_until(
                    VehicleCommand.VEHICLE_CMD_NAV_LAND,
                    self._landed,
                    25.0,
                    "cleanup landing",
                    period=1.0,
                )
            if self._armed() and self._landed():
                self._event("cleanup_disarm_requested", reason=self.failure_reason)
                self._periodic_command_until(
                    VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM,
                    lambda: not self._armed(),
                    10.0,
                    "cleanup disarm",
                    param1=0.0,
                )

        def execute(self) -> dict[str, Any]:
            status = "FAIL"
            try:
                self._phase("internal_ground")
                if not self._spin_until(
                    lambda: self.status is not None
                    and self.position is not None
                    and self.land is not None
                    and bool(self.position.xy_valid)
                    and bool(self.position.z_valid)
                    and self._landed(),
                    30.0,
                    "ground preconditions",
                ):
                    raise RuntimeError(self.failure_reason)

                self._phase("arm")
                self._set_bool("/drone0/set_arming_state", self.arm_client, True)
                if not self._spin_until(self._armed, 15.0, "PX4 armed state"):
                    raise RuntimeError(self.failure_reason)

                self._phase("internal_takeoff")
                if not self._periodic_command_until(
                    VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF,
                    lambda: self.position is not None and float(self.position.z) <= -1.2,
                    30.0,
                    "1.2 m takeoff altitude",
                ):
                    raise RuntimeError(self.failure_reason)
                self._state_event(PlatformStateMachineEvent.TAKE_OFF, "TAKE_OFF")
                self._state_event(PlatformStateMachineEvent.TOOK_OFF, "TOOK_OFF")

                self._phase("Aerostack2_Offboard")
                self._set_bool("/drone0/set_offboard_mode", self.offboard_client, True)
                if not self._spin_until(
                    lambda: self.status is not None
                    and int(self.status.nav_state) == int(VehicleStatus.NAVIGATION_STATE_OFFBOARD),
                    15.0,
                    "PX4 Offboard nav state",
                ):
                    raise RuntimeError(self.failure_reason)

                self._phase("go_to")
                self._go_to()
                self._phase("follow_path")
                self._follow_path_cancel()
                self._phase("cancel_to_hover")
                if not self._spin_until(lambda: False, 1.0, "hover interval"):
                    if self.failure_reason != "timeout waiting for hover interval":
                        raise RuntimeError(self.failure_reason)
                    self.failure_reason = None

                self._phase("explicit_aircraft_Land")
                self._state_event(PlatformStateMachineEvent.LAND, "LAND")
                if not self._periodic_command_until(
                    VehicleCommand.VEHICLE_CMD_NAV_LAND,
                    self._landed,
                    35.0,
                    "aircraft Land",
                    period=1.0,
                ):
                    raise RuntimeError(self.failure_reason)
                self._state_event(PlatformStateMachineEvent.LANDED, "LANDED")

                self._phase("disarm")
                self._set_bool("/drone0/set_arming_state", self.arm_client, False)
                if not self._spin_until(lambda: not self._armed(), 15.0, "PX4 disarm"):
                    raise RuntimeError(self.failure_reason)
                status = "PASS"
            except Exception as exc:
                if self.failure_reason is None:
                    self.failure_reason = str(exc)
                self._event(
                    "mission_exception",
                    reason=self.failure_reason,
                    formal_safety_stop=self.safety_stop,
                )
                self.cleanup()

            result = {
                "schema_version": "1.0",
                "run_id": args.run_id,
                "replay_mode": args.replay_mode,
                "status": status,
                "reason": "preregistered mission completed" if status == "PASS" else self.failure_reason,
                "formal_safety_stop": self.safety_stop,
                "duration_s": round(time.monotonic() - self.started, 3),
                "feedback_counts": self.feedback_counts,
                "terminal_landed": self._landed(),
                "terminal_disarmed": not self._armed(),
            }
            self._event("mission_finished", **result)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return result

        def close(self) -> None:
            self.events.close()

    rclpy.init()
    node = Mission()
    result = node.execute()
    node.close()
    node.destroy_node()
    rclpy.shutdown()
    return 0 if result["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay-mode", choices=("source", "canonical"), required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.replay_mode == "canonical" and (args.manifest is None or not args.manifest.is_file()):
        parser.error("canonical replay requires --manifest")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
