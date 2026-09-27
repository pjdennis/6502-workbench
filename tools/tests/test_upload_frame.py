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


def le16(value):
    return bytes([value & 0xff, value >> 8])


class ReverseBitsTest(unittest.TestCase):
    def test_each_byte_reversed(self):
        self.assertEqual(upload_frame.reverse_bits(b'\x01\x80\x0f\xa5'), b'\x80\x01\xf0\xa5')


class ReadIntelHexTest(unittest.TestCase):
    def test_vasm_output_as_contiguous_runs(self):
        text = ':01020000EA13\n:033E0000010203B9\n:00000001FF\n'
        self.assertEqual(upload_frame.read_intel_hex(text), [(0x0200, b'\xea'), (0x3e00, b'\x01\x02\x03')])

    def test_adjacent_records_join(self):
        text = ':020200000102F9\n:0102020003F8\n:00000001FF\n'
        self.assertEqual(upload_frame.read_intel_hex(text), [(0x0200, b'\x01\x02\x03')])

    def test_bad_record_checksum(self):
        with self.assertRaises(ValueError):
            upload_frame.read_intel_hex(':01020000EA14\n:00000001FF\n')


class PackBlocksTest(unittest.TestCase):
    def test_one_segment_is_one_block(self):
        self.assertEqual(upload_frame.pack_blocks([(0x0200, b'abc')]), [upload_frame.Block(0x0200, b'abc')])

    def test_segments_far_enough_apart_stay_separate(self):
        # The second block's data comes 7 header bytes after the first's in the stream: at $0210
        blocks = upload_frame.pack_blocks([(0x0200, bytes(9)), (0x0210, b'x')])
        self.assertEqual(blocks, [upload_frame.Block(0x0200, bytes(9)), upload_frame.Block(0x0210, b'x')])

    def test_segments_too_close_merge_filling_the_gap(self):
        blocks = upload_frame.pack_blocks([(0x0200, bytes(9)), (0x020f, b'x')])
        self.assertEqual(blocks, [upload_frame.Block(0x0200, bytes(15) + b'x')])

    def test_a_first_block_above_ram_start_moves_up(self):
        self.assertEqual(upload_frame.pack_blocks([(0x3000, b'x')]), [upload_frame.Block(0x3000, b'x')])

    def test_all_of_ram(self):
        blocks = upload_frame.pack_blocks([(0x0200, bytes(0x3d00))])
        self.assertEqual(len(blocks[0].data), 0x3d00)

    def test_past_the_limit(self):
        with self.assertRaises(ValueError):
            upload_frame.pack_blocks([(0x0200, bytes(0x3d01))])

    def test_below_ram_start(self):
        with self.assertRaises(ValueError):
            upload_frame.pack_blocks([(0x01ff, b'x')])

    def test_overlapping(self):
        with self.assertRaises(ValueError):
            upload_frame.pack_blocks([(0x0200, b'abc'), (0x0202, b'x')])

    def test_out_of_order_segments_are_sorted(self):
        blocks = upload_frame.pack_blocks([(0x3000, b'y'), (0x0200, b'x')])
        self.assertEqual([b.address for b in blocks], [0x0200, 0x3000])

    def test_nothing_to_upload(self):
        with self.assertRaises(ValueError):
            upload_frame.pack_blocks([])


class BuildUploadTest(unittest.TestCase):
    def test_header_then_block_whose_checksum_covers_everything_before_its_data(self):
        upload = upload_frame.build_upload([upload_frame.Block(0x0200, b'hi')], start=0x0200)
        covered = b'\x02' + le16(0x0200) + le16(2) + le16(0x0200) + b'\x00' + b'hi'
        self.assertEqual(upload, b'\x02' + le16(0x0200) + le16(2) + le16(0x0200) +
                         le16(upload_frame.bsd_checksum(covered)) + b'\x00' + b'hi')

    def test_the_first_block_data_follows_ten_bytes_of_control(self):
        upload = upload_frame.build_upload([upload_frame.Block(0x0200, b'hi')], start=0x0200)
        self.assertEqual(upload.index(b'hi'), 0x0200 - 0x01f6)

    def test_every_block_but_the_last_says_more_follow(self):
        upload = upload_frame.build_upload([upload_frame.Block(0x0200, b'a'), upload_frame.Block(0x0300, b'b')],
                                           start=0x0200)
        self.assertEqual(upload[9], upload_frame.MORE)
        self.assertEqual(upload[17], 0)          # 10 + 1 data byte + 6: the second block's flags
        second = le16(1) + le16(0x0300) + b'\x00' + b'b'
        self.assertEqual(upload[15:17], le16(upload_frame.bsd_checksum(second)))

    def test_zero_fill_block_has_no_data(self):
        upload = upload_frame.build_upload([upload_frame.Block(0x0200, b'a'),
                                            upload_frame.Block(0x0300, fill=0x100)], start=0xffff)
        self.assertEqual(upload[1:3], le16(0xffff))
        self.assertEqual(upload[11:], le16(0x100) + le16(0x0300) +
                         le16(upload_frame.bsd_checksum(le16(0x100) + le16(0x0300) + b'\x02')) + b'\x02')


class Format2Test(unittest.TestCase):
    def test_packed_built_and_bit_reversed(self):
        wire = upload_frame.format_2([(0x0200, b'hi')])
        self.assertEqual(wire, upload_frame.reverse_bits(
            upload_frame.build_upload([upload_frame.Block(0x0200, b'hi')], start=0x0200)))

    def test_start_defaults_to_the_first_address(self):
        wire = upload_frame.reverse_bits(upload_frame.format_2([(0x0400, b'x'), (0x0200, b'y')]))
        self.assertEqual(wire[1:3], le16(0x0200))

    def test_given_start(self):
        wire = upload_frame.reverse_bits(upload_frame.format_2([(0x0200, b'y')], start=0xffff))
        self.assertEqual(wire[1:3], le16(0xffff))


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()

    def path(self, name):
        return os.path.join(self.dir, name)

    def test_writes_a_format_2_upload_of_a_binary(self):
        with open(self.path('p.bin'), 'wb') as f:
            f.write(b'hi')
        upload_frame.main(['--load-address=3000', '--start=ffff', self.path('p.bin'), self.path('out')])
        with open(self.path('out'), 'rb') as f:
            self.assertEqual(f.read(), upload_frame.format_2([(0x3000, b'hi')], start=0xffff))

    def test_intel_hex(self):
        with open(self.path('p.hex'), 'w') as f:
            f.write(':01020000EA13\n:00000001FF\n')
        upload_frame.main([self.path('p.hex'), self.path('out')])
        with open(self.path('out'), 'rb') as f:
            self.assertEqual(f.read(), upload_frame.format_2([(0x0200, b'\xea')]))


if __name__ == '__main__':
    unittest.main()
