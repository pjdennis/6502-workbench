"""The placer on the emulated BBC (lathe/rt/bbc/module.asm, `place`; lathe/rt/rt_place.lth;
lathe/docs/bbc.md, "One image for every machine with sideways RAM"): a program whose region is
`dynamic` (lathe/host/lk_dyn.py), its code linked from $1F00, as the command of an eight-bank
module image of its own, run at PAGE $1900 and $1F00, every run --bbc-strict on filled memory,
so that a write below PAGE or into the screen is a fault.

The program fills a table of its region, sums it, and writes the sum and where the table is; the
same program linked with the region in its sideways slot as before is what it is compared with:
the same sum (its blocks still map a slot: the module's own; lk_dyn.py). A region too large for
the main RAM there is goes to the first free sideways RAM, from its first page, and with none is
refused. A region with a capacity variable gets the area that gives it the most, and the
variable says how much. PAGE above $1F00 is refused by the module before it copies anything.
"""
import dataclasses
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_bbc_bank as bank  # noqa: E402
import boards  # noqa: E402
import bbcrom  # noqa: E402
import test_bbc_rom128 as rom128  # noqa: E402
import build  # noqa: E402
import mapenv  # noqa: E402
import places  # noqa: E402

PROGRAM = '''module dynreg

import bbc

var table: [SIZE]byte in work
var other: [8]byte in work

func digit(d: byte)
  if d < 10 then
    bbc.put_byte('0' + d)
  else
    bbc.put_byte('A' + d - 10)
  end
end

func hex(w: word)
  digit(hi(w) >> 4)
  digit(hi(w) & $0F)
  digit(lo(w) >> 4)
  digit(lo(w) & $0F)
end

; One element, in a block of its own: a block a call.
func get(i: word): byte
  with work do
    return table[i]
  end
end

pub func main()
  var i: word
  var sum: word
  var where: word
  with work do
    for i = 0 until SIZE do
      table[i] = lo(i)
    end
    other[3] = 7
  end
  sum = 0
  for i = 0 until SIZE do
    sum += get(i)
  end
  with work do
    sum += other[3]
    where = word(@table)
  end
  hex(sum)
  bbc.put_byte(' ')
  hex(where)
  bbc.put_byte(10)
end
'''

# With a capacity variable, `room`, which the placer sets and the program writes after the rest.
ROOM_PROGRAM = PROGRAM.replace('var other: [8]byte in work\n',
                               'var other: [8]byte in work\npub var room: word\n').replace(
    '  hex(where)\n', '  hex(where)\n  bbc.put_byte(\' \')\n  hex(room)\n')

LINES = ['bank      WIN 32 $0C', 'region    work WIN 32 dynamic', 'placer    rt_place']
ROOM_LINES = ['bank      WIN 32 $0C', 'region    work WIN 32 dynamic dynreg.room', 'placer    rt_place']
STATIC = ['bank      WIN 32 $0C', 'region    work WIN 32']


def expected_sum(size):
    return (sum(i & 0xFF for i in range(size)) + 7) & 0xFFFF


@unittest.skipUnless(bank.HAVE_TOOLS, 'compiler or emulator missing')
class Placed(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lathe-bbc-place-')
        self.addCleanup(shutil.rmtree, self.dir, True)

    def build(self, name, size, lines, code_hi=None, program=PROGRAM):
        """The program's ROM form (bbcrom.rom_env), command DYN of an eight-bank module image of its
        own, whose module code holds the placer: the image's path."""
        work = os.path.join(self.dir, name)
        os.makedirs(work)
        source = os.path.join(work, 'dynreg.lth')
        with open(source, 'w') as f:
            f.write(program.replace('SIZE', str(size)))
        env = bank.bank_env(os.path.join(work, 'dynreg.env'), lines)
        with open(env) as f:
            text = f.read()
        text = re.sub(r'(?m)^define\s+ADFS\s+0', 'define    ADFS 1', text)
        if code_hi:
            text = text.replace('when      ADFS code $1F00 $6BFF', 'when      ADFS code $1F00 $%04X' % code_hi)
        with open(env, 'w') as f:
            f.write(text)
        rom = os.path.join(work, 'dynreg-rom.env')
        bbcrom.rom_env(env, rom, 0, 8)
        resident = os.path.join(work, 'DYN')
        build.build(source, resident, rom, keep=os.path.join(work, 'work'))
        image = os.path.join(work, 'MODULE')
        bbcrom.image([('DYN', resident, rom, os.path.join(work, 'work', 'dynreg.map'))], image, banks=8)
        return image

    def run_at(self, image, page, model=()):
        """*DYN at PAGE `page`: (status, output, what the MOS said, CPU cycles)."""
        base = boards.BOARDS['bbc']
        board = dataclasses.replace(base, options=base.options + ('--bbc-page', page) + tuple(model))
        with rom128.scheme(), tempfile.TemporaryDirectory(dir=self.dir) as disk:
            code, out, err, cycles = boards.run_module(board, image, disk, 'DYN', raw=True)
        status, said, cycles = boards.bbc_status(code, err.decode('latin-1'))
        return status, boards.bbc_output(out), said, cycles

    def test_a_small_region_goes_to_main_ram_at_either_page(self):
        image = self.build('small', 300, LINES)
        static = self.build('static', 300, STATIC)
        s_status, s_out, s_err, s_cycles = self.run_at(static, '1F00')
        self.assertEqual((s_status, s_err), (0, b''))
        total, at = s_out.split()
        self.assertEqual(int(total, 16), expected_sum(300))
        self.assertGreaterEqual(int(at, 16), 0x8000)                            # in its slot
        for page in ('1900', '1F00'):
            with self.subTest(page=page):
                status, out, err, cycles = self.run_at(image, page)
                self.assertEqual((status, err), (0, b''))
                total, at = out.split()
                self.assertEqual(int(total, 16), expected_sum(300))
                at = int(at, 16)
                self.assertLess(at, 0x7C00)                                     # in main RAM
                self.assertGreaterEqual(at, int(page, 16))
                print('\n  PAGE &%s: the table at &%04X, %d cycles (in its slot: %d)' % (page, at, cycles, s_cycles))

    def test_below_the_fixed_part_at_page_1900(self):
        """A region that fits only below $1F00: the code range ends at the code, so only the gap,
        `data` and `more` are free."""
        image = self.build('gap', 1400, LINES, code_hi=0x2C00)
        status, out, err, cycles = self.run_at(image, '1900')
        self.assertEqual((status, err), (0, b''))
        total, at = out.split()
        self.assertEqual(int(total, 16), expected_sum(1400))
        self.assertTrue(0x1900 <= int(at, 16) < 0x1F00, at)

    def test_a_region_too_large_for_main_ram_goes_to_the_first_sideways_ram(self):
        """In the lowest free slot (the B+128's slot 0; slot 8 of a Model B with RAM in 8 to 11),
        from its first page at the low byte it is linked at; with no sideways RAM it is refused."""
        image = self.build('large', 9000, LINES, code_hi=0x2C00)
        for page, model in (('1900', ()), ('1F00', ()),
                            ('1900', ('--bbc-model', 'b', '--bbc-sideways-ram', '8,9,10,11'))):
            with self.subTest(page=page, model=model):
                status, out, err, cycles = self.run_at(image, page, model)
                self.assertEqual((status, err), (0, b''))
                total, at = out.split()
                self.assertEqual(int(total, 16), expected_sum(9000))
                self.assertTrue(0x8000 <= int(at, 16) < 0x8100, at)
        status, out, said, cycles = self.run_at(image, '1900', ('--bbc-model', 'b', '--bbc-sideways-ram', 'none'))
        self.assertNotEqual(status, 0)
        self.assertIn(b'Too little sideways RAM', out + said)

    def test_a_region_with_a_capacity_takes_the_area_that_gives_the_most(self):
        """`region work WIN 32 dynamic dynreg.room`: a whole slot of sideways RAM where there is
        one, all of main RAM's largest area where there is none, and `room` the bytes from where
        the table is (its last variable) to the area's end; the table filled to its size as
        linked gives the same sum."""
        image = self.build('room', 300, ROOM_LINES, code_hi=0x2C00, program=ROOM_PROGRAM)
        work = os.path.join(self.dir, 'room')
        p, names = places.of_tool(os.path.join(work, 'DYN'), os.path.join(work, 'dynreg-rom.env'),
                                  os.path.join(work, 'work', 'dynreg.map'))
        for page, model in (('1900', ()), ('1F00', ()),
                            ('1900', ('--bbc-model', 'b', '--bbc-sideways-ram', '9'))):
            with self.subTest(page=page, model=model):
                status, out, err, cycles = self.run_at(image, page, model)
                self.assertEqual((status, err), (0, b''))
                total, at, room = (int(x, 16) for x in out.split())
                self.assertEqual(total, expected_sum(300))
                self.assertTrue(0x8000 <= at < 0x8100, hex(at))
                self.assertEqual(room, 0xBFE0 - at)
                model = places.plan(p, int(page, 16), 0x7C00, [9] if model else [0, 1, 12, 13])[0]
                self.assertEqual((model.where + p.regions[0].last, model.room), (at, room))   # the model of it
        status, out, err, cycles = self.run_at(image, '1900', ('--bbc-model', 'b', '--bbc-sideways-ram', 'none'))
        self.assertEqual((status, err), (0, b''))
        total, at, room = (int(x, 16) for x in out.split())
        self.assertEqual(total, expected_sum(300))
        self.assertLess(at, 0x7C00)
        self.assertGreater(room, 300)
        self.assertLessEqual(at + room, 0x7C00)
        model = places.plan(p, 0x1900, 0x7C00, [])[0]
        self.assertEqual((model.where + p.regions[0].last, model.slot, model.room), (at, None, room))
        print('\n  no sideways RAM: the table at &%04X, %d bytes' % (at, room))

    def test_page_above_the_fixed_part_is_refused(self):
        image = self.build('high', 300, LINES)
        status, out, said, cycles = self.run_at(image, '2100')
        self.assertNotEqual(status, 0)
        self.assertIn(b'PAGE too high', out + said)


if __name__ == '__main__':
    unittest.main()
