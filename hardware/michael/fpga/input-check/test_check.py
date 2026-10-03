import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import check  # noqa: E402

MARKER = ["S C3 01101", "S 3C 01101", "S 00 01101"]


class ExpectedTest(unittest.TestCase):
    def test_starts_with_marker_and_walks_port_b(self):
        exp = check.expected_lines()
        self.assertEqual(exp[:3], MARKER)
        self.assertEqual(exp[3:11], [f"S {1 << i:02X} 01101" for i in range(8)])

    def test_control_lines_one_at_a_time(self):
        exp = check.expected_lines()
        i = exp.index("S AA 01101") + 2
        self.assertEqual(exp[i:i + 8], ["S 00 11101", "S 00 01101", "S 00 00101", "S 00 01101",
                                        "S 00 01001", "S 00 01101", "S 00 01111", "S 00 01101"])

    def test_bytes_with_their_dc_and_no_repeated_state(self):
        exp = check.expected_lines()
        i = exp.index("S 00 00111")
        self.assertEqual(exp[i + 1], "B 2A 10101")
        self.assertEqual(exp[i + 2:i + 258], [f"B {b:02X} 10111" for b in range(256)])
        self.assertEqual(exp[i + 258], "B 2C 10101")
        self.assertEqual(exp[i + 259:i + 323], ["B 00 10111"] * 64)
        # After the fill the state is back to where gd_select left it, so the next line is gd_unselect's
        self.assertEqual(exp[i + 323:], ["S 00 01101", "S E7 01101", "S 7E 01101", "S 00 01101"])


class CompareTest(unittest.TestCase):
    def test_finds_marker_after_startup_noise(self):
        got = ["S FF 01111", "S 00 00111"] + MARKER + ["S 01 01101"]
        self.assertEqual(check.find_start(got), 2)
        self.assertIsNone(check.find_start(["S 00 01101"]))

    def test_identical_report_passes(self):
        exp = check.expected_lines()
        self.assertEqual(check.compare(exp, list(exp)), [])

    def test_names_the_signals_that_differ(self):
        exp = check.expected_lines()
        got = list(exp)
        got[4] = "S 04 01101"  # PB1's step shows d[2] instead
        problems = check.compare(exp, got)
        self.assertEqual(len(problems), 1)
        self.assertIn("PB1 (Cmod 2) expected 1, got 0", problems[0])
        self.assertIn("PB2 (Cmod 3) expected 0, got 1", problems[0])

    def test_control_signal_names(self):
        problems = check.compare(["S 00 11101"], ["S 00 01111"])
        self.assertIn("E/PA0 (Cmod 9) expected 1, got 0", problems[0])
        self.assertIn("DC/PA5 (Cmod 12) expected 0, got 1", problems[0])

    def test_missing_and_extra_lines(self):
        exp = check.expected_lines()
        self.assertIn("missing", check.compare(exp, exp[:-2])[-1])
        self.assertIn("unexpected", check.compare(exp, exp + ["B 11 10111"])[-1])
        self.assertIn("overflow", check.compare(exp, exp[:5] + ["! OVERFLOW"] + exp[5:])[0].lower())


if __name__ == "__main__":
    unittest.main()
