#!/usr/bin/env python3
"""Switch PX4 to the RAPTOR external mode via MAV_CMD_DO_SET_MODE."""

from __future__ import annotations

import argparse
import sys
import time

try:
    from pymavlink import mavutil
except ImportError as exc:  # pragma: no cover - runtime dependency check
    raise SystemExit("pymavlink is required: python3 -m pip install pymavlink") from exc


PX4_CUSTOM_MAIN_MODE_AUTO = 4
PX4_CUSTOM_SUB_MODE_EXTERNAL1 = 11
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1
NAVIGATION_STATE_EXTERNAL1 = 23


def external_submode(mode_id: int) -> int:
    if not 23 <= mode_id <= 30:
        raise ValueError(f"external mode_id must be in [23, 30], got {mode_id}")
    return PX4_CUSTOM_SUB_MODE_EXTERNAL1 + (mode_id - NAVIGATION_STATE_EXTERNAL1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default="udp:127.0.0.1:14540")
    parser.add_argument("--mode-id", type=int, default=23)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    sub_mode = external_submode(args.mode_id)
    mav = mavutil.mavlink_connection(args.master, source_system=245, source_component=190)
    heartbeat = mav.wait_heartbeat(timeout=args.timeout)
    if heartbeat is None:
        print(f"ERROR: no heartbeat on {args.master}", file=sys.stderr)
        return 1

    target_system = mav.target_system
    target_component = mav.target_component
    print(
        "SEND_DO_SET_MODE "
        f"target={target_system}/{target_component} "
        f"base={MAV_MODE_FLAG_CUSTOM_MODE_ENABLED} "
        f"main={PX4_CUSTOM_MAIN_MODE_AUTO} sub={sub_mode} mode_id={args.mode_id}"
    )

    mav.mav.command_long_send(
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
        0,
        MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        PX4_CUSTOM_MAIN_MODE_AUTO,
        sub_mode,
        0,
        0,
        0,
        0,
    )

    deadline = time.monotonic() + args.timeout
    last_mode = None
    while time.monotonic() < deadline:
        msg = mav.recv_match(type=["COMMAND_ACK", "HEARTBEAT"], blocking=True, timeout=1.0)
        if msg is None:
            continue

        if msg.get_type() == "COMMAND_ACK" and msg.command == mavutil.mavlink.MAV_CMD_DO_SET_MODE:
            print(f"COMMAND_ACK result={msg.result}")

        if msg.get_type() == "HEARTBEAT":
            last_mode = int(msg.custom_mode)
            decoded_main = (last_mode >> 16) & 0xFF
            decoded_sub = (last_mode >> 24) & 0xFF
            print(f"HEARTBEAT custom_mode={last_mode} main={decoded_main} sub={decoded_sub}")
            if decoded_main == PX4_CUSTOM_MAIN_MODE_AUTO and decoded_sub == sub_mode:
                print("RAPTOR_MODE_CONFIRMED_BY_HEARTBEAT=1")
                return 0

    print(f"ERROR: RAPTOR mode not confirmed; last_custom_mode={last_mode}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
