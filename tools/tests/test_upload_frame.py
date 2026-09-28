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

def srec(kind, address, data=b''):
    """An S-record line: kind 1/9 have 2-byte addresses, 2/8 3-byte, 3/7 4-byte."""
    width = {0: 2, 1: 2, 2: 3, 3: 4, 5: 2, 7: 4, 8: 3, 9: 2}[kind]
    body = bytes([width + len(data) + 1]) + address.to_bytes(width, 'big') + data
    return 'S%d%s%02X' % (kind, body.hex().upper(), ~sum(body) & 0xff)


class ReadSrecTest(unittest.TestCase):
    VASM_S19 = ('S00F00006F7267303030313A32303030EB\nS1052000EA6090\n'
                'S00F00006F7267303030323A33303030E9\nS10530000102C7\nS9032001DB\n')
    VASM_S37 = ('S00F00006F7267303030313A32303030EB\nS30700002000EA608E\n'
                'S00F00006F7267303030323A33303030E9\nS307000030000102C5\nS70500002001D9\n')

    def test_vasm_s19_output(self):
        # vasm -Fsrec -s19 -exec of: .org $2000 / nop / start: rts / .org $3000 / .byte 1,2
        self.assertEqual(upload_frame.read_srec(self.VASM_S19),
                         ([(0x2000, b'\xea\x60'), (0x3000, b'\x01\x02')], 0x2001))

    def test_vasm_s37_output(self):
        self.assertEqual(upload_frame.read_srec(self.VASM_S37),
                         ([(0x2000, b'\xea\x60'), (0x3000, b'\x01\x02')], 0x2001))

    def test_a_start_address_of_zero_is_none(self):
        # What vasm writes without -exec
        text = srec(1, 0x2000, b'\xea') + '\n' + srec(9, 0) + '\n'
        self.assertEqual(upload_frame.read_srec(text), ([(0x2000, b'\xea')], None))

    def test_adjacent_records_join(self):
        text = '\n'.join([srec(1, 0x2002, b'c'), srec(1, 0x2000, b'ab'), srec(9, 0x2000)])
        self.assertEqual(upload_frame.read_srec(text), ([(0x2000, b'abc')], 0x2000))

    def test_count_records_are_ignored(self):
        text = '\n'.join([srec(1, 0x2000, b'a'), srec(5, 1), srec(9, 0x2000)])
        self.assertEqual(upload_frame.read_srec(text), ([(0x2000, b'a')], 0x2000))

    def test_bad_checksum(self):
        with self.assertRaises(ValueError):
            upload_frame.read_srec('S1052000EA6091\nS9032001DB\n')

    def test_bad_length(self):
        with self.assertRaises(ValueError):
            upload_frame.read_srec('S1062000EA608F\nS9032001DB\n')

    def test_not_an_srecord(self):
        with self.assertRaises(ValueError):
            upload_frame.read_srec(':01020000EA13\n')


Block = upload_frame.Block


class PackEntriesTest(unittest.TestCase):
    def pack(self, segments, **options):
        return upload_frame.pack_entries(segments, **options)

    def test_one_segment_is_one_entry(self):
        self.assertEqual(self.pack([(0x0200, b'abc')]), [Block(0x0200, b'abc')])

    def test_adjacent_segments_join(self):
        self.assertEqual(self.pack([(0x0202, b'c'), (0x0200, b'ab')]), [Block(0x0200, b'abc')])

    def test_segments_an_entry_or_less_apart_merge_with_zeros_between(self):
        # A 5-byte gap costs no more than another entry
        self.assertEqual(self.pack([(0x0200, b'a'), (0x0206, b'b')]), [Block(0x0200, b'a' + bytes(5) + b'b')])

    def test_segments_further_apart_stay_separate(self):
        self.assertEqual(self.pack([(0x0200, b'a'), (0x0207, b'b')]), [Block(0x0200, b'a'), Block(0x0207, b'b')])

    def test_alternating_single_bytes_become_one_entry(self):
        segments = [(0x0200 + 2 * i, bytes([i + 1])) for i in range(50)]
        self.assertEqual(self.pack(segments), [Block(0x0200, b''.join(bytes([i + 1, 0]) for i in range(50))[:-1])])

    def test_zero_page_is_one_entry(self):
        self.assertEqual(self.pack([(0x00f0, b'b'), (0x0010, b'a')]), [Block(0x0010, b'a' + bytes(0xdf) + b'b')])

    def test_zero_page_and_ram_stay_separate(self):
        self.assertEqual(self.pack([(0x00ff, b'a'), (0x0200, b'b')]), [Block(0x00ff, b'a'), Block(0x0200, b'b')])

    def test_page_1(self):
        for address in (0x0100, 0x01ff):
            with self.assertRaises(ValueError):
                self.pack([(address, b'x')])

    def test_from_zero_page_into_page_1(self):
        with self.assertRaises(ValueError):
            self.pack([(0x00ff, b'ab')])

    def test_past_ram(self):
        with self.assertRaises(ValueError):
            self.pack([(0x3eff, b'ab')])

    def test_overlapping(self):
        with self.assertRaises(ValueError):
            self.pack([(0x0200, b'abc'), (0x0202, b'x')])

    def test_nothing_to_upload(self):
        with self.assertRaises(ValueError):
            self.pack([])

    def test_long_runs_of_zeros_are_zero_filled(self):
        self.assertEqual(self.pack([(0x0200, b'a' + bytes(64) + b'b')]),
                         [Block(0x0200, b'a'), Block(0x0201, fill=64), Block(0x0241, b'b')])

    def test_shorter_runs_of_zeros_are_sent(self):
        self.assertEqual(self.pack([(0x0200, b'a' + bytes(63) + b'b')]), [Block(0x0200, b'a' + bytes(63) + b'b')])

    def test_a_segment_of_zeros(self):
        self.assertEqual(self.pack([(0x0300, bytes(0x100))]), [Block(0x0300, fill=0x100)])

    def test_too_many_entries_merge_the_smallest_gaps(self):
        segments = [(0x0200, b'a'), (0x0300, b'b'), (0x0400, b'c'), (0x0410, b'd')]
        self.assertEqual(self.pack(segments, max_entries=3),
                         [Block(0x0200, b'a'), Block(0x0300, b'b'), Block(0x0400, b'c' + bytes(15) + b'd')])

    def test_at_most_32_entries_for_michael(self):
        segments = [(0x0200 + 0x10 * i, b'x') for i in range(40)]
        self.assertEqual(len(self.pack(segments)), 32)

    def test_zero_fill_entries_merge_as_zero_fill(self):
        self.assertEqual(self.pack([(0x0200, bytes(100)), (0x0300, bytes(100))], max_entries=1),
                         [Block(0x0200, fill=0x164)])

    def test_zero_fill_merges_with_data_as_zeros_sent(self):
        self.assertEqual(self.pack([(0x0200, b'a' + bytes(64))], max_entries=1), [Block(0x0200, b'a' + bytes(64))])

    def test_one_entry_fills_ram(self):
        self.assertEqual(self.pack([(0x0200, b'\x11' * 0x3d00)]), [Block(0x0200, b'\x11' * 0x3d00)])

    def test_the_stream_must_fit(self):
        # Another entry puts the data 5 bytes higher: RAM filled and zero page too won't fit
        with self.assertRaises(ValueError):
            self.pack([(0x0200, b'\x11' * 0x3d00), (0x0010, b'z')])


class BuildUpload3Test(unittest.TestCase):
    def test_one_entry(self):
        upload = upload_frame.build_upload_3([Block(0x0200, b'hi')], start=0x0201)
        rest = le16(upload_frame.bsd_checksum(b'hi')) + le16(0x0200) + le16(2) + b'\x00'
        header_sum = upload_frame.bsd_checksum(b'\x03' + le16(0x0201) + b'\x01' + rest)
        self.assertEqual(upload, b'\x03' + le16(0x0201) + b'\x01' + le16(header_sum) + rest + b'hi')

    def test_one_entrys_data_lands_at_0200(self):
        upload = upload_frame.build_upload_3([Block(0x0200, b'hi')], start=0x0200)
        self.assertEqual(upload_frame.STREAM_START_3 + upload.index(b'hi'), 0x0200)

    def test_each_further_entry_is_5_bytes(self):
        upload = upload_frame.build_upload_3([Block(0x0010, b'z'), Block(0x0200, b'hi')], start=0x0200)
        self.assertEqual(upload[3], 2)
        self.assertEqual(upload[13:18], le16(0x0200) + le16(2) + b'\x00')
        self.assertEqual(upload[18:], b'zhi')

    def test_zero_fill_entries_have_the_flag_and_no_data(self):
        upload = upload_frame.build_upload_3([Block(0x0200, b'a'), Block(0x0300, fill=0x100)], start=0xffff)
        self.assertEqual(upload[13:], le16(0x0300) + le16(0x100) + b'\x01' + b'a')

    def test_the_data_checksum_covers_all_the_data_in_order(self):
        upload = upload_frame.build_upload_3([Block(0x0010, b'z'), Block(0x0200, b'hi')], start=0x0200)
        self.assertEqual(upload[6:8], le16(upload_frame.bsd_checksum(b'zhi')))


class Format3Test(unittest.TestCase):
    def test_packed_built_and_bit_reversed(self):
        self.assertEqual(upload_frame.format_3([(0x0200, b'hi')], start=0x0200),
                         upload_frame.reverse_bits(upload_frame.build_upload_3([Block(0x0200, b'hi')], 0x0200)))

    def test_start_defaults_to_the_lowest_address_outside_zero_page(self):
        wire = upload_frame.reverse_bits(upload_frame.format_3([(0x0400, b'x'), (0x0300, b'y'), (0x0010, b'z')]))
        self.assertEqual(wire[1:3], le16(0x0300))


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()

    def path(self, name):
        return os.path.join(self.dir, name)

    def test_writes_a_format_3_upload_of_a_binary(self):
        with open(self.path('p.bin'), 'wb') as f:
            f.write(b'hi')
        upload_frame.main(['--load-address=3000', '--start=ffff', self.path('p.bin'), self.path('out')])
        with open(self.path('out'), 'rb') as f:
            self.assertEqual(f.read(), upload_frame.format_3([(0x3000, b'hi')], start=0xffff))

    def test_a_binary_loads_at_2000_by_default(self):
        with open(self.path('p.bin'), 'wb') as f:
            f.write(b'hi')
        upload_frame.main([self.path('p.bin'), self.path('out')])
        with open(self.path('out'), 'rb') as f:
            self.assertEqual(f.read(), upload_frame.format_3([(0x2000, b'hi')]))

    def test_srecords_start_where_they_say(self):
        with open(self.path('p.s19'), 'w') as f:
            f.write(ReadSrecTest.VASM_S19)
        upload_frame.main([self.path('p.s19'), self.path('out')])
        with open(self.path('out'), 'rb') as f:
            self.assertEqual(f.read(), upload_frame.format_3([(0x2000, b'\xea\x60'), (0x3000, b'\x01\x02')],
                                                             start=0x2001))

    def test_start_overrides_the_files(self):
        with open(self.path('p.s19'), 'w') as f:
            f.write(ReadSrecTest.VASM_S19)
        upload_frame.main(['--start=ffff', self.path('p.s19'), self.path('out')])
        with open(self.path('out'), 'rb') as f:
            self.assertEqual(upload_frame.reverse_bits(f.read())[1:3], le16(0xffff))

if __name__ == '__main__':
    unittest.main()
