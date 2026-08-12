#!/usr/bin/env python3
"""Create a canonical Thor host and formal-container environment attestation."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any


class AttestationError(RuntimeError):
    """The host or container identity cannot be attested."""


def _command(*arguments: str, check: bool = True) -> str:
    result = subprocess.run(arguments, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise AttestationError(
            f"command failed ({result.returncode}): {' '.join(arguments)}: "
            + result.stderr.strip()
        )
    return result.stdout.strip()


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _dpkg(package: str) -> str | None:
    value = _command(
        "dpkg-query", "-W", "-f=${db:Status-Abbrev}|${Version}", package, check=False
    )
    return value if value.startswith("ii ") else None


def _text_values(pattern: str) -> list[str]:
    values: set[str] = set()
    for name in glob.glob(pattern):
        try:
            value = Path(name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            values.add(value)
    return sorted(values)


def _memory_total_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024
    raise AttestationError("MemTotal is absent from /proc/meminfo")


def _container_json(image: str, path: str) -> dict[str, Any]:
    text = _command(
        "docker",
        "run",
        "--rm",
        "--runtime",
        "runc",
        "--network",
        "none",
        "--read-only",
        image,
        "python3",
        "-c",
        f"from pathlib import Path; print(Path({path!r}).read_text())",
    )
    value = json.loads(text)
    if not isinstance(value, dict):
        raise AttestationError(f"container JSON is not an object: {path}")
    return value


def attest(image: str, environment_id: str) -> dict[str, Any]:
    image_data = json.loads(_command("docker", "image", "inspect", image))[0]
    docker_info = json.loads(_command("docker", "info", "--format", "{{json .}}"))
    candidate = _container_json(image, "/opt/family_a_candidate_manifest.json")
    preflight = json.loads(
        _command(
            "docker",
            "run",
            "--rm",
            "--runtime",
            "runc",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec",
            image,
        )
    )
    if preflight.get("status") != "PASS":
        raise AttestationError("container preflight did not pass")
    os_release = platform.freedesktop_os_release()
    payload = {
        "schema_version": "1.0",
        "environment_id": environment_id,
        "host": {
            "machine": platform.machine(),
            "model": Path("/proc/device-tree/model").read_bytes().rstrip(b"\0").decode(),
            "l4t_release": Path("/etc/nv_tegra_release").read_text(encoding="utf-8").strip(),
            "nvidia_l4t_core": _dpkg("nvidia-l4t-core"),
            "nvidia_jetpack": _dpkg("nvidia-jetpack"),
            "operating_system": os_release.get("PRETTY_NAME"),
            "kernel": platform.release(),
            "logical_cpu_count": os.cpu_count(),
            "memory_total_bytes": _memory_total_bytes(),
            "cpu_governors": _text_values(
                "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
            ),
            "nvpmodel": _command("nvpmodel", "-q", check=False),
            "nvidia_driver": _command(
                "nvidia-smi",
                "--query-gpu=driver_version",
                "--format=csv,noheader",
                check=False,
            ),
            "docker_version": docker_info.get("ServerVersion"),
            "docker_default_runtime": docker_info.get("DefaultRuntime"),
            "experiment_container_runtime": "runc",
            "docker_runtimes": sorted(docker_info.get("Runtimes", {})),
            "nvidia_container_toolkit": _command("nvidia-ctk", "--version", check=False),
            "cuda_toolkit": _command("nvcc", "--version", check=False),
        },
        "container": {
            "image_reference": image,
            "image_id": image_data["Id"],
            "repo_digests": sorted(image_data.get("RepoDigests") or []),
            "platform": f"{image_data['Os']}/{image_data['Architecture']}",
            "candidate": candidate,
            "preflight": preflight,
        },
    }
    payload_digest = _digest(payload)
    px4_digest = candidate["binaries"]["px4_sitl"]["sha256"]
    return {
        "schema_version": "1.0",
        "attestation_payload": payload,
        "attestation_payload_digest": payload_digest,
        "execution_environment": {
            "environment_id": environment_id,
            "execution_host_id": "agx-thor-local",
            "collector_host_id": "agx-thor-local",
            "target_kind": "sitl",
            "architecture": "aarch64",
            "operating_system": "Ubuntu 24.04 Noble container on L4T R38.2.1",
            "px4_binary_digest": px4_digest,
            "environment_manifest_digest": payload_digest,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        value = attest(args.image, args.environment_id)
        if args.output.exists():
            raise AttestationError(f"refusing to overwrite: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, KeyError, ValueError, AttestationError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": "PASS", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
