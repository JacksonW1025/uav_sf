from __future__ import annotations

import unittest

from scripts.runtime.moving_workload import progress_from_origin, straight_line_target


class MovingWorkloadTests(unittest.TestCase):
    def test_target_holds_then_moves_and_saturates(self) -> None:
        values = [straight_line_target(t, settle_s=1.0, speed_m_s=0.75, distance_m=3.5) for t in (0.0, 1.0, 3.0, 10.0)]
        self.assertEqual(values, [0.0, 0.0, 1.5, 3.5])

    def test_reverse_motion_does_not_satisfy_progress(self) -> None:
        self.assertEqual(progress_from_origin(-1.0, 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
