"""The placer on the emulated BBC (lathe/rt/rt_place.lth; lathe/docs/bbc.md, "One image for every
machine with sideways RAM"): a program whose region is `dynamic` (lathe/host/lk_dyn.py), its code
linked from $1F00, run with *RUN at PAGE $1900 and $1F00, in the developer's form (the module's
RAM, as test_bbc_bank.py runs banked programs), every run --bbc-strict on filled memory, so that
a write below PAGE or into the screen is a fault.

The program fills a table of its region, sums it, and writes the sum and where the table is; the
same program linked with the region in its sideways slot as before is what it is compared with:
the same sum (its blocks still map a slot: the module's own; lk_dyn.py). A region too large for the main RAM there is stays in its slot.
"""
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
import build  # noqa: E402
import mapenv  # noqa: E402

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

LINES = ['bank      WIN 32 $0C', 'region    work WIN 32 dynamic', 'placer    rt_place']
STATIC = ['bank      WIN 32 $0C', 'region    work WIN 32']


def expected_sum(size):
    return (sum(i & 0xFF for i in range(size)) + 7) & 0xFFFF


@unittest.skipUnless(bank.HAVE_TOOLS, 'compiler or emulator missing')
class Placed(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lathe-bbc-place-')
        self.addCleanup(shutil.rmtree, self.dir, True)

    def build(self, name, size, lines, code_hi=None):
        work = os.path.join(self.dir, name)
        os.makedirs(work)
        source = os.path.join(work, 'dynreg.lth')
        with open(source, 'w') as f:
            f.write(PROGRAM.replace('SIZE', str(size)))
        env = bank.bank_env(os.path.join(work, 'dynreg.env'), lines)
        with open(env) as f:
            text = f.read()
        text = re.sub(r'(?m)^define\s+ADFS\s+0', 'define    ADFS 1', text)
        if code_hi:
            text = text.replace('when      ADFS code $1F00 $6BFF', 'when      ADFS code $1F00 $%04X' % code_hi)
        with open(env, 'w') as f:
            f.write(text)
        image = os.path.join(work, 'dynreg.bin')
        build.build(source, image, env, keep=os.path.join(work, 'work'))
        return image, env

    def run_at(self, image, env, page):
        described = mapenv.read_env(env)
        disk = tempfile.mkdtemp(dir=self.dir)
        build.window_files(described, os.path.dirname(image), disk)
        module = boards.module_options(described) + ('--bbc-page', page)
        status, out, err, cycles = boards.run_mos(boards.BOARDS['bbc'], image, disk, module=module)
        return status, out, err, cycles

    def test_a_small_region_goes_to_main_ram_at_either_page(self):
        image, env = self.build('small', 300, LINES)
        static, senv = self.build('static', 300, STATIC)
        s_status, s_out, s_err, s_cycles = self.run_at(static, senv, '1F00')
        self.assertEqual((s_status, s_err), (0, b''))
        total, at = s_out.split()
        self.assertEqual(int(total, 16), expected_sum(300))
        self.assertGreaterEqual(int(at, 16), 0x8000)                            # in its slot
        for page in ('1900', '1F00'):
            with self.subTest(page=page):
                status, out, err, cycles = self.run_at(image, env, page)
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
        image, env = self.build('gap', 1400, LINES, code_hi=0x2C00)
        status, out, err, cycles = self.run_at(image, env, '1900')
        self.assertEqual((status, err), (0, b''))
        total, at = out.split()
        self.assertEqual(int(total, 16), expected_sum(1400))
        self.assertTrue(0x1900 <= int(at, 16) < 0x1F00, at)

    def test_a_region_too_large_for_main_ram_stays_in_its_slot(self):
        image, env = self.build('large', 9000, LINES, code_hi=0x2C00)
        for page in ('1900', '1F00'):
            with self.subTest(page=page):
                status, out, err, cycles = self.run_at(image, env, page)
                self.assertEqual((status, err), (0, b''))
                total, at = out.split()
                self.assertEqual(int(total, 16), expected_sum(9000))
                self.assertGreaterEqual(int(at, 16), 0x8000)

    def test_page_above_the_fixed_part_is_refused(self):
        image, env = self.build('high', 300, LINES)
        status, out, err, cycles = self.run_at(image, env, '2100')
        self.assertNotEqual(status, 0)
        self.assertIn(b'PAGE too high', out + err)


if __name__ == '__main__':
    unittest.main()
