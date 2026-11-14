"""The stand-in for linking the compiler: a synthetic program of about 700 functions, 3,500
slots and 3,000 calls in 30 modules (lk_synthetic.py), linked and checked against the
assembler path. `python3 lathe/tests/lk_memory_report.py --synthetic` prints the peak use of
every table for it and the host linker's time.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lk_synthetic  # noqa: E402
from test_lk_support import HOST_ENV, link  # noqa: E402


class Synthetic(unittest.TestCase):
    def test_links_as_the_assembler_does(self):
        builders, calls = lk_synthetic.program(1)
        self.assertGreater(calls, 2900)
        r = link(builders, HOST_ENV, main='p00', asm=True)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual(r.image, r.asm_image)
        functions = [m for m in r.map if m[0] == 'F']
        self.assertGreater(len(functions), 650)
        self.assertTrue(any('@' in m[3] for m in functions))        # copies for the interrupt
        self.assertTrue(any(m[0] == 'C' for m in r.map))            # a live pointer class


if __name__ == '__main__':
    unittest.main()
