from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy


PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


def versioned_topic(base: str, message_type: type[object]) -> str:
    """Return the DDS topic name required by the px4_msgs message contract."""
    version = int(getattr(message_type, "MESSAGE_VERSION", 0))
    return f"{base}_v{version}" if version else base


class DurableJsonl:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        if self.path.exists():
            raise RuntimeError(f"refusing to overwrite sidecar: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("x", encoding="utf-8")
        self._sequence = 0

    def append(self, kind: str, **payload: Any) -> None:
        record = {
            "schema_version": "1.0",
            "sequence": self._sequence,
            "kind": kind,
            "received_monotonic_ns": time.monotonic_ns(),
            **payload,
        }
        self._handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._sequence += 1

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()
