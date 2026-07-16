from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "config" / "dependencies.lock.yaml"
HELPER_PATH = ROOT / "scripts" / "setup" / "verify_dependency_lock.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("verify_dependency_lock", HELPER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lock_is_complete_and_exact() -> None:
    lock = yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))
    helper = load_helper()
    assert helper.validate(lock) == []
    for name in helper.DEPENDENCIES:
        assert re.fullmatch(r"[0-9a-f]{40}", lock[name]["commit"])
        assert lock[name]["repository"].startswith("https://github.com/")
        assert lock[name]["repository"].endswith(".git")


def test_lock_contains_no_floating_dependency_ref() -> None:
    lock = yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))
    forbidden = {"head", "main", "master", "latest", "stable", "develop"}
    for name in load_helper().DEPENDENCIES:
        assert str(lock[name]["commit"]).lower() not in forbidden
    assert not str(lock["container"]["base_image"]).endswith(":latest")


def test_setup_scripts_read_lock_and_verify_checkout() -> None:
    for filename in ("clone_px4.sh", "setup_ros2_ws.sh", "build_microxrce_agent.sh"):
        text = (ROOT / "scripts" / "setup" / filename).read_text(encoding="utf-8")
        assert "dependency_lock_lib.sh" in text
        assert "checkout_locked_repository" in text
        assert "--update-lock" in text
        assert ":-main" not in text
        assert ":-master" not in text


def test_family_a_clone_has_no_family_b_required_submodule() -> None:
    text = (ROOT / "scripts" / "setup" / "clone_px4.sh").read_text(encoding="utf-8")
    family_a = text.split("family_a_submodules=(", 1)[1].split(")", 1)[0]
    assert "mc_raptor" not in family_a
    assert "policy.tar" not in family_a
    assert "rl_tools" not in family_a


def test_profile_boundaries_are_explicit() -> None:
    family_a = (ROOT / "scripts" / "setup" / "bootstrap_family_a.sh").read_text(encoding="utf-8")
    family_b = (ROOT / "scripts" / "setup" / "bootstrap_family_b.sh").read_text(encoding="utf-8")
    assert "family_b/" not in family_a
    assert "--profile family_a" in family_a
    assert "bootstrap_family_a.sh" in family_b
    assert "--profile family_b" in family_b
