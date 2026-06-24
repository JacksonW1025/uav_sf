#!/usr/bin/env python3
"""M1 failure-injection wrapper using MAV_CMD_INJECT_FAILURE."""

from __future__ import annotations

import argparse
import sys
import time

from pymavlink import mavutil


FAILURE_UNITS = {
    "gyro": 0,
    "accel": 1,
    "mag": 2,
    "baro": 3,
    "gps": 4,
    "optical_flow": 5,
    "vio": 6,
    "distance_sensor": 7,
    "airspeed": 8,
    "battery": 100,
    "motor": 101,
    "servo": 102,
    "avoidance": 103,
    "rc_signal": 104,
    "mavlink_signal": 105,
}

FAILURE_TYPES = {
    "ok": 0,
    "off": 1,
    "stuck": 2,
    "garbage": 3,
    "wrong": 4,
    "slow": 5,
    "delayed": 6,
    "intermittent": 7,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default="udp:127.0.0.1:14540")
    parser.add_argument("--unit", choices=sorted(FAILURE_UNITS), required=True)
    parser.add_argument("--type", choices=sorted(FAILURE_TYPES), required=True)
    parser.add_argument("--instance", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    mav = mavutil.mavlink_connection(args.master, source_system=245, source_component=191)
    heartbeat = mav.wait_heartbeat(timeout=args.timeout)
    if heartbeat is None:
        print(f"ERROR: no heartbeat on {args.master}", file=sys.stderr)
        return 1

    unit = FAILURE_UNITS[args.unit]
    failure_type = FAILURE_TYPES[args.type]
    print(
        f"SEND_INJECT_FAILURE target={mav.target_system}/{mav.target_component} "
        f"unit={args.unit}({unit}) type={args.type}({failure_type}) instance={args.instance}"
    )
    mav.mav.command_long_send(
        mav.target_system,
        mav.target_component,
        mavutil.mavlink.MAV_CMD_INJECT_FAILURE,
        0,
        float(unit),
        float(failure_type),
        float(args.instance),
        0,
        0,
        0,
        0,
    )

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        msg = mav.recv_match(type="COMMAND_ACK", blocking=True, timeout=1.0)
        if msg is None:
            continue
        if msg.command == mavutil.mavlink.MAV_CMD_INJECT_FAILURE:
            print(f"COMMAND_ACK result={msg.result}")
            return 0 if msg.result == mavutil.mavlink.MAV_RESULT_ACCEPTED else 2

    print("ERROR: timeout waiting for COMMAND_ACK", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
