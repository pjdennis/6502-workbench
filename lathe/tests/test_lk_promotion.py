"""Promotion judges most items from bounds instead of laying zero page out again
(lk_alloc.judge). Its choices must be those of the rule itself: lay out again after every item
taken, and take an item only if the program still fits. Each program here is linked twice, as
the linker is and with every item judged on a fresh layout, and the maps must be the same; the
number of layouts must come down.
"""
import os
import random
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lk_synthetic  # noqa: E402
import test_lk_random  # noqa: E402
from test_lk_support import HOST_ENV, LINK  # noqa: E402

# Run the linker in this process, counting layouts; with "exact", every item judged afresh.
RUNNER = '''import sys
sys.path.insert(0, sys.argv[1])
import env, lk_alloc, link
count = [0]
real = lk_alloc.layout_zp
def counting():
    count[0] += 1
    return real()
lk_alloc.layout_zp = counting
if sys.argv[2] == 'exact':
    lk_alloc.bound = lambda var_size: 0xFFFF
real_exit = env.exit
def leave(code):
    sys.stderr.write('layouts %d\\n' % count[0])
    real_exit(code)
env.exit = leave
env.start(sys.argv[3:])
link.main()
'''


def env_text(lo, hi):
    lines = [line for line in HOST_ENV.splitlines() if not line.startswith('zeropage')]
    return '\n'.join(lines + ['zeropage  $%02X $%02X' % (lo, hi)]) + '\n'


class Promotion(unittest.TestCase):
    def link_both(self, d, objects, main, lo, hi):
        """The map (or error) and the number of layouts, as linked and as linked exactly."""
        env_path = os.path.join(d, 'env')
        with open(env_path, 'w') as f:
            f.write(env_text(lo, hi))
        runner = os.path.join(d, 'runner.py')
        with open(runner, 'w') as f:
            f.write(RUNNER)
        out = []
        for mode in ('bounds', 'exact'):
            bin_path = os.path.join(d, mode + '.bin')
            map_path = os.path.join(d, mode + '.map')
            r = subprocess.run([sys.executable, runner, os.path.dirname(LINK), mode, env_path, main,
                                bin_path, map_path] + objects, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            text = r.stderr.decode()
            layouts = int(text.split('layouts ')[-1])
            result = text.split('layouts ')[0]
            if r.returncode == 0:
                with open(map_path) as f:
                    result = f.read()
            out.append((r.returncode, result, layouts))
        return out

    def test_the_synthetic_program(self):
        builders, calls = lk_synthetic.program(2)
        with tempfile.TemporaryDirectory() as d:
            paths = [b.save(os.path.join(d, b.module_.name + '.lo')) for b in builders]
            fewer = 0
            for size in (192,):
                (s1, m1, n1), (s2, m2, n2) = self.link_both(d, paths, 'p00', 0, size - 1)
                self.assertEqual((s1, m1), (s2, m2), size)
                self.assertLessEqual(n1, n2)
                fewer += n2 - n1
            self.assertGreater(fewer, 400)

    def test_random_programs(self):
        with tempfile.TemporaryDirectory() as d:
            for seed in range(25):
                rng = random.Random(seed)
                o, calls, roots, classes = test_lk_random.random_program(rng, rng.choice((0, 0, 2)))
                p = os.path.join(d, 't.lo')
                with open(p, 'wb') as f:
                    f.write(o.to_bytes())
                lo = rng.randint(0, 0xE0)
                hi = min(0xFF, lo + rng.randint(0, 24))
                (s1, m1, n1), (s2, m2, n2) = self.link_both(d, [p], 't', lo, hi)
                self.assertEqual((s1, m1), (s2, m2), seed)


if __name__ == '__main__':
    unittest.main()
