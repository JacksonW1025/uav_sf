import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = REPO_ROOT / "patches" / "px4" / "m2b_state_shim.patch"
MCNN_BUILD_SCRIPT = REPO_ROOT / "scripts" / "setup" / "build_px4_mcnn_sih.sh"


class M2BStateShimPatchTest(unittest.TestCase):
    def test_patch_routes_position_velocity_and_angular_rate_channels(self) -> None:
        patch = PATCH_PATH.read_text(encoding="utf-8")

        self.assertIn("M2B_P_PROF", patch)
        self.assertIn("M2B_P_DLY", patch)
        self.assertIn("M2B_P_X", patch)
        self.assertIn("M2B_P_Y", patch)
        self.assertIn("M2B_P_Z", patch)
        self.assertIn("ApplyM2BPositionShim", patch)
        self.assertIn("local_position.x", patch)
        self.assertIn("local_position.y", patch)
        self.assertIn("local_position.z", patch)

        self.assertIn("M2B_V_PROF", patch)
        self.assertIn("ApplyM2BVelocityShim", patch)
        self.assertIn("local_position.vx", patch)
        self.assertIn("M2B_G_PROF", patch)
        self.assertIn("ApplyM2BGyroShim", patch)
        self.assertIn("angular_velocity.xyz", patch)

    def test_mcnn_sih_build_installs_state_shim_overlay(self) -> None:
        script = MCNN_BUILD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("install_m2b_state_shim.sh", script)


if __name__ == "__main__":
    unittest.main()
