from __future__ import annotations

import math
import time

import rclpy
from px4_msgs.msg import VehicleCommand, VehicleStatus
from rclpy.node import Node

from family_a_runtime.common import DurableJsonl, PX4_QOS, versioned_topic


class ManualRequester(Node):
    """Issue one public Land request at a frozen offset from external activation."""

    def __init__(self) -> None:
        super().__init__("family_a_manual_requester")
        self.declare_parameter("run_id", "")
        self.declare_parameter("output_path", "")
        self.declare_parameter("request_delay_s", 8.0)
        self.declare_parameter("timing_bucket", "near")
        self._run_id = str(self.get_parameter("run_id").value)
        output_path = str(self.get_parameter("output_path").value)
        self._delay_ns = int(float(self.get_parameter("request_delay_s").value) * 1e9)
        self._bucket = str(self.get_parameter("timing_bucket").value)
        if not self._run_id or not output_path or self._delay_ns < 0:
            raise RuntimeError("run_id, output_path, and a non-negative request delay are required")
        if self._bucket not in {"before", "near", "after"}:
            raise RuntimeError("unsupported timing_bucket")
        self._log = DurableJsonl(output_path)
        self._activation_ns: int | None = None
        self._sent = False
        self._publisher = self.create_publisher(
            VehicleCommand, "/fmu/in/vehicle_command", PX4_QOS
        )
        self.create_subscription(
            VehicleStatus,
            versioned_topic("/fmu/out/vehicle_status", VehicleStatus),
            self._status,
            PX4_QOS,
        )
        self.create_timer(0.01, self._tick)
        self._log.append(
            "manual_requester_started",
            run_id=self._run_id,
            timing_bucket=self._bucket,
            request_delay_ns=self._delay_ns,
        )

    def _status(self, message: VehicleStatus) -> None:
        if self._activation_ns is None and 23 <= int(message.nav_state) <= 30:
            self._activation_ns = time.monotonic_ns()
            self._log.append(
                "manual_request_anchor",
                run_id=self._run_id,
                nav_state=int(message.nav_state),
            )

    def _tick(self) -> None:
        if self._sent or self._activation_ns is None:
            return
        elapsed_ns = time.monotonic_ns() - self._activation_ns
        if elapsed_ns < self._delay_ns:
            return
        message = VehicleCommand()
        message.timestamp = self.get_clock().now().nanoseconds // 1000
        message.command = VehicleCommand.VEHICLE_CMD_NAV_LAND
        message.param1 = math.nan
        message.param2 = math.nan
        message.param3 = math.nan
        message.param4 = math.nan
        message.param5 = math.nan
        message.param6 = math.nan
        message.param7 = math.nan
        message.target_system = 1
        message.target_component = 1
        message.source_system = 1
        message.source_component = 192
        message.from_external = True
        self._publisher.publish(message)
        self._sent = True
        self._log.append(
            "adjacent_request",
            run_id=self._run_id,
            route="internal_land",
            timing_bucket=self._bucket,
            requested_delay_ns=self._delay_ns,
            observed_delay_ns=elapsed_ns,
        )

    def destroy_node(self) -> bool:
        self._log.close()
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = ManualRequester()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
