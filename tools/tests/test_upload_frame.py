"""Tests for tools/upload/upload_frame.py (the board loaders' upload format).

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'upload'))

import upload_frame  # noqa: E402


class BsdChecksumTest(unittest.TestCase):
    def test_matches_sum_r(self):
        # printf 'Hello, Wendy!' | sum -r  ->  61870
        self.assertEqual(upload_frame.bsd_checksum(b'Hello, Wendy!'), 61870)

    def test_empty_is_zero(self):
        self.assertEqual(upload_frame.bsd_checksum(b''), 0)


class BuildFrameTest(unittest.TestCase):
    def test_length_payload_checksum_little_endian(self):
        frame = upload_frame.build_frame(b'Hello, Wendy!')
        self.assertEqual(frame, b'\x0d\x00' + b'Hello, Wendy!' + bytes([61870 & 0xff, 61870 >> 8]))

    def test_largest_payload_accepted(self):
        frame = upload_frame.build_frame(bytes(0xffff))
        self.assertEqual(frame[:2], b'\xff\xff')
        self.assertEqual(len(frame), 0xffff + 4)

    def test_payload_over_ffff_rejected(self):
        with self.assertRaises(ValueError):
            upload_frame.build_frame(bytes(0x10000))


class SendDurationTest(unittest.TestCase):
    def test_start_data_stop_bits_plus_two_percent(self):
        # 10 bytes x (1 start + 8 data + 1 stop) at 115200, plus 2%
        self.assertAlmostEqual(upload_frame.send_duration(10, 115200, 1), 100 / 115200 * 1.02)

    def test_two_stop_bits(self):
        self.assertAlmostEqual(upload_frame.send_duration(10, 9600, 2), 110 / 9600 * 1.02)


if __name__ == '__main__':
    unittest.main()
