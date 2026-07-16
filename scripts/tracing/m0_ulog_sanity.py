#!/usr/bin/env python3
"""M0-only ULOG topic, mode-switch, and NaN sanity check."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

try:
    import numpy as np
    from pyulog import ULog
except ImportError as exc:  # pragma: no cover - runtime dependency check
    raise SystemExit("pyulog and numpy are required: python3 -m pip install pyulog numpy") from exc


REQUIRED_TOPICS = [
    "raptor_status",
    "raptor_input",
    "trajectory_setpoint",
    "vehicle_local_position",
    "vehicle_angular_velocity",
    "vehicle_attitude",
    "vehicle_status",
    "actuator_motors",
]


def first_dataset(ulog: ULog, name: str):
    matches = [dataset for dataset in ulog.data_list if dataset.name == name]
    return matches[0] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ulog", type=Path)
    parser.add_argument("--active-motors", type=int, default=4)
    args = parser.parse_args()

    ulog = ULog(str(args.ulog))
    names = sorted({dataset.name for dataset in ulog.data_list})
    print(f"ULOG={args.ulog}")
    print(f"START_TIMESTAMP_US={ulog.start_timestamp}")
    print(f"DATASETS={len(ulog.data_list)}")

    missing = [topic for topic in REQUIRED_TOPICS if topic not in names]
    for topic in REQUIRED_TOPICS:
        print(f"TOPIC_{topic}={'present' if topic in names else 'missing'}")

    status = first_dataset(ulog, "vehicle_status")
    first_raptor_us = None
    if status and "nav_state" in status.data:
        nav = status.data["nav_state"].astype(int)
        ts = status.data["timestamp"]
        unique_nav = []
        for value in nav.tolist():
            if value not in unique_nav:
                unique_nav.append(value)
        print("VEHICLE_STATUS_NAV_STATES=" + ",".join(str(v) for v in unique_nav))
        idx = np.where(nav == 23)[0]
        if len(idx) > 0:
            first = int(idx[0])
            first_raptor_us = int(ts[first])
            print(f"RAPTOR_NAV_STATE_23_FIRST_US={first_raptor_us}")
            print(f"RAPTOR_NAV_STATE_23_FIRST_S={(first_raptor_us - ulog.start_timestamp) / 1e6:.3f}")
        else:
            print("RAPTOR_NAV_STATE_23_FIRST_US=missing")
    else:
        print("VEHICLE_STATUS_NAV_STATES=missing")

    total_nan_count = 0
    active_nan_count = 0
    unused_nan_count = 0
    motors = first_dataset(ulog, "actuator_motors")
    if motors:
        for field, values in motors.data.items():
            if field == "timestamp":
                continue
            if np.issubdtype(values.dtype, np.floating):
                field_nan_count = int(np.isnan(values).sum())
                total_nan_count += field_nan_count
                if field.startswith("control[") and field.endswith("]"):
                    control_idx = int(field[len("control[") : -1])
                    if control_idx < args.active_motors:
                        active_nan_count += field_nan_count
                    else:
                        unused_nan_count += field_nan_count
        print(f"ACTUATOR_MOTORS_TOTAL_NAN_COUNT={total_nan_count}")
        print(f"ACTUATOR_MOTORS_ACTIVE_0_{args.active_motors - 1}_NAN_COUNT={active_nan_count}")
        print(f"ACTUATOR_MOTORS_UNUSED_NAN_COUNT={unused_nan_count}")
    else:
        print("ACTUATOR_MOTORS_TOTAL_NAN_COUNT=missing")
        print(f"ACTUATOR_MOTORS_ACTIVE_0_{args.active_motors - 1}_NAN_COUNT=missing")
        print("ACTUATOR_MOTORS_UNUSED_NAN_COUNT=missing")

    disarmed_after_raptor = "unknown"
    if status and "arming_state" in status.data and "nav_state" in status.data:
        nav = status.data["nav_state"].astype(int)
        arm = status.data["arming_state"].astype(int)
        raptor_idx = np.where(nav == 23)[0]
        if len(raptor_idx) > 0:
            # PX4 vehicle_status arming_state: 2 is ARMED in this message version.
            arm_after_raptor = arm[raptor_idx[0] :]
            disarmed_after_raptor = str(bool(np.any(arm_after_raptor != 2))).lower()
            print("ARMING_STATES_AFTER_RAPTOR=" + ",".join(str(v) for v in sorted(set(arm_after_raptor.tolist()))))
    print(f"DISARMED_AFTER_RAPTOR={disarmed_after_raptor}")

    if first_raptor_us is not None:
        local_position = first_dataset(ulog, "vehicle_local_position")
        if local_position and all(key in local_position.data for key in ["timestamp", "x", "y", "z"]):
            lp_ts = local_position.data["timestamp"]
            mask = lp_ts >= first_raptor_us
            if np.any(mask):
                print(f"LOCAL_POSITION_AFTER_RAPTOR_X_LAST={float(local_position.data['x'][mask][-1]):.3f}")
                print(f"LOCAL_POSITION_AFTER_RAPTOR_Y_LAST={float(local_position.data['y'][mask][-1]):.3f}")
                print(f"LOCAL_POSITION_AFTER_RAPTOR_Z_MIN={float(np.nanmin(local_position.data['z'][mask])):.3f}")
                print(f"LOCAL_POSITION_AFTER_RAPTOR_Z_MAX={float(np.nanmax(local_position.data['z'][mask])):.3f}")

        angular_velocity = first_dataset(ulog, "vehicle_angular_velocity")
        if angular_velocity and all(key in angular_velocity.data for key in ["timestamp", "xyz[0]", "xyz[1]", "xyz[2]"]):
            av_ts = angular_velocity.data["timestamp"]
            mask = av_ts >= first_raptor_us
            if np.any(mask):
                max_abs = max(
                    float(np.nanmax(np.abs(angular_velocity.data["xyz[0]"][mask]))),
                    float(np.nanmax(np.abs(angular_velocity.data["xyz[1]"][mask]))),
                    float(np.nanmax(np.abs(angular_velocity.data["xyz[2]"][mask]))),
                )
                print(f"ANGULAR_VELOCITY_AFTER_RAPTOR_MAX_ABS_RAD_S={max_abs:.3f}")

        attitude = first_dataset(ulog, "vehicle_attitude")
        if attitude and all(key in attitude.data for key in ["timestamp", "q[0]", "q[1]", "q[2]", "q[3]"]):
            att_ts = attitude.data["timestamp"]
            mask = att_ts >= first_raptor_us
            if np.any(mask):
                finite = all(bool(np.all(np.isfinite(attitude.data[f"q[{idx}]"][mask]))) for idx in range(4))
                print(f"ATTITUDE_QUATERNION_AFTER_RAPTOR_FINITE={str(finite).lower()}")

    if missing:
        print("MISSING_TOPICS=" + ",".join(missing))
        return 2

    if status is None or motors is None:
        return 2

    if math.isnan(float(total_nan_count)):
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
