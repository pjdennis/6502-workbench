"""with_census.py: what it says of the functions a link keeps in fixed memory for `with` blocks,
on cases/e2e-config/kept.lth (lathe/docs/spikes.md, "One ROM for every BBC: a study
(measured)")."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'host', 'driver'))

import build  # noqa: E402
import with_census  # noqa: E402

CASES = os.path.join(HERE, 'cases', 'e2e-config')


class Source(unittest.TestCase):
    def test_blocks_and_loops_by_indentation(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'm.lth')
            with open(p, 'w') as f:
                f.write('module m\n'
                        'pub func a(n: byte)             ; a block with a loop\n'
                        '  with R do\n'
                        '    while n != 0 do             ; "with" in a comment: with X do\n'
                        '      n -= 1\n'
                        '    end\n'
                        '  end\n'
                        'end\n'
                        'func b(): byte\n'
                        '  loop                          ; a loop outside the block\n'
                        '    break\n'
                        '  end\n'
                        '  with R do\n'
                        '    return t[0]\n'
                        '  end\n'
                        'end\n')
            fs = with_census.functions_of(p)
        self.assertEqual(sorted(fs), ['a', 'b'])
        self.assertEqual([with_census.loops_in(b) for b in with_census.blocks_of(fs['a'])], [True])
        self.assertEqual([with_census.loops_in(b) for b in with_census.blocks_of(fs['b'])], [False])
        self.assertTrue(with_census.loops_in(fs['b']))


@unittest.skipUnless(os.path.isfile(build.COMPILER), 'compiler missing')
class Kept(unittest.TestCase):
    def test_kept_case(self):
        with tempfile.TemporaryDirectory(prefix='census_') as d:
            work = os.path.join(d, 'work')
            build.build(os.path.join(CASES, 'kept.lth'), os.path.join(d, 'x.bin'),
                        os.path.join(CASES, 'kept_banks.env'), keep=work)
            rows = {k.name: k for k in with_census.census(work, os.path.join(work, 'kept.map'),
                                                          source_dirs=[CASES])}
        got = {n: (k.why(), k.loop, sorted(k.regions)) for n, k in rows.items() if n.startswith('libk')}
        self.assertEqual(got['libkept.fill'], ('block', True, ['KWORK']))     # its block loops
        self.assertEqual(got['libkept.get'], ('block', False, ['KWORK']))     # one access
        self.assertEqual(got['libkept.next'], ('inside', False, ['KWORK']))   # called in fill's block
        self.assertEqual(got['libkept.step'], ('inside', False, ['KWORK']))   # called by next
        self.assertEqual(got['libkept.add8'], ('inside', True, ['KWORK']))    # loops, inside sum's
        self.assertEqual(got['libkrom.twice'][:2], ('inside', False))
        self.assertNotIn('libkept.begin', got)                                 # in the bank
        self.assertTrue(all(rows[n].kept for n in got))


if __name__ == '__main__':
    unittest.main()
