"""The environment entries `output image`, `output raw` and `exit stop` (lathe/host/README.md,
"The environment file"), by the linker and by the assembler path.

Every expected byte was worked out by hand from lathe/docs/object-format.md.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import Obj, link, HOST_ENV, EITHER, NEVER  # noqa: E402
from test_lk_identity import frames_program, loop_program  # noqa: E402

BOARD = 'cpu 65c02\nzeropage $00 $FF\ncode $2000 $3EFF\ndata $0200 $1FFF\nstack $FF\n'


def simple():
    o = Obj('t', cpu=1)
    o.func('main', b'\x60')
    return o


def with_data():
    """main, a constant after it and a second function: the raw file ends with the function."""
    o = Obj('t', cpu=1)
    c = o.code()
    c.abs(0xAD, o.d('t.$1')).abs(0x20, o.f('t.f')).raw(0x60)
    o.func('main', c, calls=[(o.f('t.f'), 0, 0xFFFF)])
    o.data('t.$1', b'HI\0')
    o.func('f', b'\xEA\x60')
    return o


class ExitStop(unittest.TestCase):
    def test_start_code_ends_with_stp(self):
        r = link([simple()], BOARD + 'exit stop\noutput raw\n')
        self.assertEqual((r.status, r.errors), (0, ''))
        # LDX #$FF / TXS / CLD / JSR main / STP
        self.assertEqual(r.image, bytes.fromhex('A2FF9A D8 200820 DB 60'))
        self.assertEqual(r.map_text, 'F 2000 0008 $start\nF 2008 0001 t.main\n')

    def test_with_an_image(self):
        r = link([simple()], BOARD + 'exit stop\n')
        self.assertEqual(r.at(0x2000, 9), bytes.fromhex('A2FF9A D8 200820 DB 60'))
        self.assertEqual(len(r.image), 0x10000 - 0x2000)
        self.assertEqual(r.at(0xFFFC, 2), b'\x00\x20')

    def test_needs_a_65c02(self):
        o = Obj('t')
        o.func('main', b'\x60')
        r = link([o], BOARD.replace('65c02', '6502') + 'exit stop\n')
        self.assertEqual(r.status, 1)
        self.assertTrue(r.errors.startswith('link error 39: environment file: exit stop needs cpu 65c02: '),
                        r.errors)

    def test_the_order_of_the_entries_does_not_matter(self):
        r = link([simple()], 'exit stop\noutput raw\n' + BOARD)
        self.assertEqual(r.image, bytes.fromhex('A2FF9A D8 200820 DB 60'))


class OutputRaw(unittest.TestCase):
    def test_ends_with_the_last_byte_placed(self):
        r = link([with_data()], BOARD + 'exit stop\noutput raw\n')
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual(r.map_text, 'F 2000 0008 $start\nF 2008 0007 t.main\nF 2012 0002 t.f\n'
                                     'D 200F 0003 t.$1\n')
        self.assertEqual(r.image, bytes.fromhex('A2FF9A D8 200820 DB  AD0F20 201220 60  484900  EA60'))

    def test_is_the_start_of_the_image(self):
        """host.env with `output raw` gives the first bytes of the `output image` file."""
        for program in (loop_program(), frames_program()):
            image = link([program], HOST_ENV)
            raw = link([program], HOST_ENV + 'output raw\n')
            self.assertEqual((raw.status, raw.errors), (0, ''))
            end = max(int(m[1], 16) + int(m[2], 16) for m in raw.map if m[0] in 'FD')
            self.assertEqual(len(raw.image), end - 0x0200)
            self.assertEqual(raw.image, image.image[:len(raw.image)])
            self.assertEqual(raw.map_text, image.map_text)

    def test_output_image_is_the_default(self):
        a = link([simple()], BOARD + 'exit return\n')
        b = link([simple()], BOARD + 'exit return\noutput image\n')
        self.assertEqual((b.status, b.errors), (0, ''))
        self.assertEqual(a.image, b.image)
        self.assertEqual(len(b.image), 0x10000 - 0x2000)

    def test_bad_output_entries(self):
        for line in ('output', 'output rom', 'output raw\noutput raw', 'output raw image'):
            r = link([simple()], BOARD + 'exit return\n' + line + '\n')
            self.assertTrue(r.errors.startswith('link error 3: environment file: bad entry: '), line)

    def test_code_may_end_at_ffff(self):
        """Raw output has no vectors, so code can use the top of memory."""
        o = Obj('t', cpu=1)
        o.func('main', b'\xEA' * 7 + b'\x60')
        r = link([o], BOARD.replace('$2000 $3EFF', '$FFF0 $FFFF') + 'exit stop\noutput raw\n')
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual(len(r.image), 16)


class Identity(unittest.TestCase):
    """The assembler path gives the same file for both output forms."""

    def same(self, objects, environment):
        r = link(objects, environment, asm=True)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual(r.image, r.asm_image, r.asm_text)
        return r

    def test_raw_with_stop(self):
        r = self.same([with_data()], BOARD + 'exit stop\noutput raw\n')
        self.assertIn('.byte $DB', r.asm_text)
        self.assertNotIn('$FFFC', r.asm_text)

    def test_image_with_stop(self):
        self.same([with_data()], BOARD + 'exit stop\n')

    def test_raw_on_the_host_layout(self):
        for program in (loop_program(), frames_program()):
            self.same([program], HOST_ENV + 'output raw\n')


if __name__ == '__main__':
    unittest.main()
