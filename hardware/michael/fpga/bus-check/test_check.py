import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import check  # noqa: E402

GOOD = ["FPGA BUS CHECK", "ID OK", "ECHO BAD 0000", "UNDERFLOW OK", "HOLD A KEY", "KEYBOARD BAD 0000",
        "KEYS 002A ROUNDS 07", "DONE"]
# What the FPGA should count for GOOD. Reads: ID 4 + status, 32 echo passes of 256 + status, the underflow's
# read and two status reads, and 7 rounds of 16 passes: 5 + 8224 + 3 + 28784 = 37016 ($9098). Writes: RESET
# and ID, ECHO and 256 bytes per pass (8224 + 28784), and each report line's characters, CR LF, and its
# SERIAL_SEND commands (two per line, three for KEYS): 18+9+17+16+14+21+24+8 = 127. 37137 is $9111. Of the
# writes, 163 ($A3) are commands: RESET, ID, an ECHO per pass (144) and the report's SERIAL_SENDs (17).
COUNTS = "C 9111 9098 0009 0040 0000 00A3 0000 0000"


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
        problems, _ = check.assess(GOOD[:6] + ["KEYS 0000 ROUNDS 40"] + GOOD[7:], None)
        self.assertIn("no keys", problems[0])
        problems, _ = check.assess(GOOD, "C 9111 9098 0000 0040 0000 00A3 0000 0000")
        self.assertEqual(len(problems), 1)
        self.assertIn("no read was paused", problems[0])

    def test_soeb_never_seen_names_the_wiring(self):
        problems, _ = check.assess(GOOD, "C 9111 9098 0000 0000 0000 00A3 0000 0000")
        self.assertEqual(len(problems), 1)
        self.assertIn("never saw SOEB", problems[0])
        self.assertIn("Cmod pin 18", problems[0])

    def test_transfers_the_program_didnt_make_are_reported(self):
        problems, _ = check.assess(GOOD, "C 9111 909C 0009 0040 0000 00A3 0000 0000")
        self.assertEqual(len(problems), 1)
        self.assertIn("4 more reads", problems[0])
        problems, _ = check.assess(GOOD, "C 910F 9098 0009 0040 0000 00A3 0000 0000")
        self.assertEqual(len(problems), 1)
        self.assertIn("2 fewer writes", problems[0])

    def test_extra_writes_are_split_into_commands_and_data_with_the_short_ones(self):
        problems, _ = check.assess(GOOD, "C 9114 9098 0009 0040 0000 00A3 0002 0000")
        self.assertEqual(len(problems), 1)
        self.assertIn("3 more writes", problems[0])
        self.assertIn("0 commands and 3 data bytes", problems[0])
        self.assertIn("2 writes had E pulses shorter than Michael's", problems[0])
        problems, _ = check.assess(GOOD, "C 9114 9098 0009 0040 0000 00A6 0000 0000")
        self.assertIn("3 commands and 0 data bytes", problems[0])

    def test_glitches_and_bounces_on_e_are_not_a_failure(self):
        """The bus filters them out; check.py reports how many."""
        problems, _ = check.assess(GOOD, "C 9111 9098 0009 0040 0003 00A3 0000 01CD")
        self.assertEqual(problems, [])

    def test_missing_counts(self):
        problems, pauses = check.assess(GOOD, None)
        self.assertEqual(len(problems), 1)
        self.assertIn("counts", problems[0])
        self.assertIsNone(pauses)


if __name__ == "__main__":
    unittest.main()
