import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import check  # noqa: E402

GOOD = ["FPGA BUS CHECK", "ID OK", "ECHO BAD 0000", "UNDERFLOW OK", "HOLD A KEY", "KEYBOARD BAD 0000",
        "KEYS 002A", "DONE"]
COUNTS = "C 1234 5678 0009"


class AssessTest(unittest.TestCase):
    def test_a_clean_run_passes_and_reports_the_pauses(self):
        problems, pauses = check.assess(GOOD, COUNTS)
        self.assertEqual(problems, [])
        self.assertEqual(pauses, 9)

    def test_junk_and_an_earlier_run_before_the_start_are_ignored(self):
        problems, _ = check.assess(["~~", "FPGA BUS CHECK", "ID BAD"] + GOOD, COUNTS)
        self.assertEqual(problems, [])

    def test_mismatches_are_reported_with_their_count(self):
        lines = GOOD[:2] + ["ECHO BAD 0005"] + GOOD[3:5] + ["KEYBOARD BAD 0010"] + GOOD[6:]
        problems, _ = check.assess(lines, COUNTS)
        self.assertEqual(len(problems), 2)
        self.assertIn("5 bytes read back wrong", problems[0])
        self.assertIn("16 bytes read back wrong", problems[1])
        self.assertIn("keyboard", problems[1])

    def test_failed_id_and_underflow_are_reported(self):
        lines = [GOOD[0], "ID BAD", GOOD[2], "UNDERFLOW BAD"] + GOOD[4:]
        problems, _ = check.assess(lines, COUNTS)
        self.assertEqual(len(problems), 2)
        self.assertIn("ID", problems[0])
        self.assertIn("UNDERFLOW", problems[1])

    def test_a_run_that_stops_early_says_where(self):
        problems, _ = check.assess(GOOD[:4], COUNTS)
        self.assertEqual(len(problems), 1)
        self.assertIn("HOLD A KEY", problems[0])

    def test_no_start_marker(self):
        problems, _ = check.assess(["junk"], None)
        self.assertEqual(len(problems), 1)
        self.assertIn("never started", problems[0])

    def test_the_interlock_must_be_exercised(self):
        problems, _ = check.assess(GOOD[:6] + ["KEYS 0000"] + GOOD[7:], COUNTS)
        self.assertEqual(len(problems), 1)
        self.assertIn("no keys", problems[0])
        problems, _ = check.assess(GOOD, "C 1234 5678 0000")
        self.assertEqual(len(problems), 1)
        self.assertIn("no read was paused", problems[0])

    def test_missing_counts(self):
        problems, pauses = check.assess(GOOD, None)
        self.assertEqual(len(problems), 1)
        self.assertIn("counts", problems[0])
        self.assertIsNone(pauses)


if __name__ == "__main__":
    unittest.main()
