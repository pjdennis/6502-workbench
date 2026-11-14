"""lathe/src/cond.lth against lathe/host/cond.py: lathe/src/condtest.lth runs each section of
lathe/tests/scripts/cond.txt, which compare operands of every type and make tests, values and
the carry flag of Conditions joined by `and`, `or` and `not`, and prints what each gives and
the function's code, fix-ups and frame; main() below does the same with cond.py (and the
commands of regcmd_host.py), and the outputs, error reports, exit statuses and object files
must be identical."""
import shutil
import tempfile
import unittest

import script_host as script
import regcmd_host
import env
import cond
import reg

COMMANDS = b"wanted compare left right invert value carry jumpfalse cpush iffalse "


def main():
    regcmd_host.init()
    script.open_script(env._args[0])
    while script.next_line():
        c = script.find(COMMANDS)
        if c == script.NOT_FOUND:
            regcmd_host.run(script.command(regcmd_host.WORDS))
        elif c == 0:
            cond.wanted_in_carry(script.flag())
        elif c == 1:
            cond.compare(script.small())
        elif c == 2:
            cond.left(script.flag())
        elif c == 3:
            cond.right()
        elif c == 4:
            cond.invert()
        elif c == 5:
            cond.value()
        elif c == 6:
            cond.carry(script.small())
        elif c == 7:
            script.show_word(cond.jump_false())
        elif c == 8:
            cond.push(script.small())
        elif c == 9:
            target = cond.jump_false()
            reg.implied(reg.OP_CLC)
            reg.label(target)
        script.end_line()
    env.exit(0)


# The grid: for each type, the constants at its edges (and one in between).
EDGES = {1: (0, 1, 0x7F, 0xFE, 0xFF), 2: (0, 1, 0x7F, 0xFFFF, 0xFF80),
         3: (0, 1, 0xFF, 0x100, 0x1234, 0xFFFE, 0xFFFF), 4: (0, 1, 0x7FFF, 0x8000, 0xFFFF, 0x100),
         9: (0,)}
OPERATORS = range(11, 17)
USES = (b'iffalse', b'value\npop', b'wanted 1\n@\nwanted 0\ncarry 0\npop')


def grid_sections():
    """One section for each type: every operator, between two variables, a variable and each
    constant (of the type, and as a number without a type where it is one), a constant and a
    variable, A and a variable, A and a constant; each used as a test, as a value and as the
    carry flag (compiled with the carry wanted)."""
    found = []
    for t, edges in EDGES.items():
        size = 2 if t in (3, 4, 9) else 1
        pairs = [(b'pslot %d 0' % t, b'pslot %d 1' % t), (b'preg %d' % t, b'pslot %d 1' % t)]
        for c in edges:
            pairs.append((b'pslot %d 0' % t, b'const %d %d' % (t, c)))
            pairs.append((b'const %d %d' % (t, c), b'pslot %d 0' % t))
            pairs.append((b'preg %d' % t, b'const %d %d' % (t, c)))
            if t != 9 and (t in (1, 3) or c < 0x8000):
                pairs.append((b'pslot %d 0' % t, b'const 6 %d' % c))
            if t in (2, 4) and c >= 0x8000:
                pairs.append((b'pslot %d 0' % t, b'const 7 %d' % c))
        if t == 9:
            pairs.append((b'pslot 9 0', b'const 8 0'))
        lines = [b'ptr 1'] if t == 9 else []
        for op in OPERATORS:
            for left, right in pairs:
                for use in USES:
                    body = b'%s\n%s\ncompare %d' % (left, right, op)
                    if use.startswith(b'wanted'):
                        body = use.replace(b'@', body)
                    else:
                        body = body + b'\n' + use
                    lines += [b'begin', b'slot %d 1 1 a' % size, b'slot %d 1 1 b' % size, body,
                              b'implied $60', b'finish']
        found.append((b'grid of type %d' % t, b'\n'.join(lines) + b'\n'))
    return found


class CondTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-cond-')
        cls.image = script.support.build_program('condtest', cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, main, 'cond',
                                               self.dir, outputs=1, extra=grid_sections()), 5)


if __name__ == '__main__':
    unittest.main()
