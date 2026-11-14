"""Programs on the emulated boards (lathe/docs/boards.md): Michael and Wendy 2.

Each board gets an object file, built with lo.Builder, whose main shows "HI" on the board's LCD:
the research programs of boards.md restructured as one function that calls its own subroutines
through labels, with the text as a constant. It is linked with lathe/env/BOARD.env, built again
by the assembler path (the files must be identical), and run through build.run_program, which is
what `build.py --env BOARD --run` uses. lathe/host/driver/boards.py is checked on its own too.
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_lk_support import link, ROOT  # noqa: E402
import boards  # noqa: E402  (test_lk_support puts the driver directory on the path)
import build  # noqa: E402
import cpu6502  # noqa: E402
import lo  # noqa: E402
import mapenv  # noqa: E402

ENVS = os.path.join(ROOT, 'lathe', 'env')
NEVER, EITHER = 2, 1


def env_text(name):
    with open(os.path.join(ENVS, name + '.env')) as fh:
        return fh.read()


def show_text(f, text, put):
    """The loop that sends constant `text` (ending with 0) to subroutine label `put`, with Y."""
    f.op('LDY', '#', 0)
    f.label('next').op('LDA', 'abs,y', text).op('BEQ', 'rel', 'shown')
    f.op('JSR', 'abs', put).op('INY').op('BNE', 'rel', 'next')
    f.label('shown')


def michael_hi():
    """Michael's 20x4 LCD in 8-bit mode: data on port B ($6000); E, RW, RS are PA7, PA6, PA5."""
    portb, porta, ddrb, ddra = 0x6000, 0x6001, 0x6002, 0x6003
    e, rw, rs = 0x80, 0x40, 0x20
    b = lo.Builder('hi', cpu6502.CPU_65C02)
    f = b.func('hi.main')
    f.op('LDA', '#', 0).op('STA', 'abs', porta)
    f.op('LDA', '#', 0xEE).op('STA', 'abs', ddra)       # the board's port A outputs
    f.op('LDA', '#', 0xFF).op('STA', 'abs', ddrb)
    for command in (0x38, 0x08, 0x01, 0x06, 0x0C):      # 8-bit 2 lines, off, clear, entry, on
        f.op('LDA', '#', command).op('JSR', 'abs', 'command')
    show_text(f, 'hi.$1', 'char')
    f.op('RTS')
    # wait while the busy flag (D7) is set; uses X
    f.label('wait').op('LDA', '#', 0).op('STA', 'abs', ddrb)
    f.op('LDA', '#', rw).op('STA', 'abs', porta)
    f.label('busy').op('LDA', '#', rw + e).op('STA', 'abs', porta).op('LDX', 'abs', portb)
    f.op('LDA', '#', rw).op('STA', 'abs', porta).op('TXA').op('AND', '#', 0x80)
    f.op('BNE', 'rel', 'busy')
    f.op('LDA', '#', 0).op('STA', 'abs', porta).op('LDA', '#', 0xFF).op('STA', 'abs', ddrb).op('RTS')
    for name, flag in (('command', 0), ('char', rs)):
        f.label(name).op('PHA').op('JSR', 'abs', 'wait').op('PLA').op('STA', 'abs', portb)
        f.op('LDA', '#', flag + e).op('STA', 'abs', porta)
        f.op('LDA', '#', flag).op('STA', 'abs', porta)
        f.op('LDA', '#', 0).op('STA', 'abs', porta).op('RTS')
    b.data('hi.$1', b'HI\0')
    return b


def wendy2_hi():
    """Wendy 2's 16x2 LCD in 4-bit mode: D4-D7 = PA4-PA7, RS = PA0 ($F001), E = PB5 ($F000).
    PB0-PB4 select the memory bank and stay $01. The byte being sent and its RS flag are kept
    in a two-byte variable."""
    portb, porta, ddrb, ddra = 0xF000, 0xF001, 0xF002, 0xF003
    bank, e = 0x01, 0x20
    b = lo.Builder('hi', cpu6502.CPU_65C02)
    b.var('hi.held', 2, EITHER, 4)
    f = b.func('hi.main')
    f.op('LDA', '#', bank).op('STA', 'abs', portb)
    f.op('LDA', '#', bank + e).op('STA', 'abs', ddrb)    # bank bits and E as outputs
    f.op('LDA', '#', 0).op('STA', 'abs', porta)
    f.op('LDA', '#', 0xF9).op('STA', 'abs', ddra)        # data, RW and RS as outputs
    for nibble in (0x30, 0x30, 0x30, 0x20):              # initialise by instruction, to 4-bit
        f.op('LDA', '#', nibble).op('JSR', 'abs', 'nibble')
    for command in (0x28, 0x08, 0x01, 0x06, 0x0C):       # 4-bit 2 lines, off, clear, entry, on
        f.op('LDA', '#', command).op('JSR', 'abs', 'command')
    show_text(f, 'hi.$1', 'char')
    f.op('RTS')
    f.label('nibble').op('STA', 'abs', porta)
    f.label('strobe').op('LDA', '#', bank + e).op('STA', 'abs', portb)
    f.op('LDA', '#', bank).op('STA', 'abs', portb)
    f.op('LDA', '#', 0).op('STA', 'abs', porta).op('RTS')
    f.label('command').op('LDX', '#', 0).op('BEQ', 'rel', 'send')
    f.label('char').op('LDX', '#', 1)
    f.label('send').op('STA', 'abs', 'hi.held').op('STX', 'abs', 'hi.held', 1)
    f.op('AND', '#', 0xF0).op('ORA', 'abs', 'hi.held', 1).op('STA', 'abs', porta)
    f.op('JSR', 'abs', 'strobe')
    f.op('LDA', 'abs', 'hi.held').op('ASL').op('ASL').op('ASL').op('ASL')
    f.op('ORA', 'abs', 'hi.held', 1).op('STA', 'abs', porta)
    f.op('JMP', 'abs', 'strobe')
    b.data('hi.$1', b'HI\0')
    return b


def spin():
    """A main that never returns."""
    b = lo.Builder('hi', cpu6502.CPU_65C02)
    b.func('hi.main').label('top').op('JMP', 'abs', 'top')
    return b


@unittest.skipUnless(os.path.isfile(boards.EMULATOR), 'emulator/emulator.out is not built (run make)')
class OnTheBoards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def built(self, board, program):
        r = link([program], env_text(board), asm=True)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual(r.image, r.asm_image, 'the linker and the assembler path differ\n' + r.asm_text)
        path = os.path.join(self.tmp.name, board + '.bin')
        with open(path, 'wb') as fh:
            fh.write(r.image)
        return r, path

    def test_michael_shows_hi(self):
        r, path = self.built('michael', michael_hi())
        self.assertEqual(r.image[:10], bytes.fromhex('A2FF9A D8 200820 DB A900'))
        self.assertEqual(len(r.image), r.addr('D', 'hi.$1') + 3 - 0x2000)
        self.assertEqual(build.run_program(path, 'michael'), (0, b'HI\n\n\n\n', b''))

    def test_wendy2_shows_hi(self):
        r, path = self.built('wendy2', wendy2_hi())
        self.assertEqual(r.addr('V', 'hi.held'), 0x0000)   # zero page: the ORAs shrink
        self.assertEqual(build.run_program(path, 'wendy2'), (0, b'HI\n\n', b''))

    def test_a_program_that_does_not_stop_is_an_error(self):
        for board in ('michael', 'wendy2'):
            _, path = self.built(board, spin())
            with self.assertRaisesRegex(boards.RunError, r'did not stop .*cycle cap at \$'):
                build.run_program(path, board)

    def test_build_py_runs_a_board(self):
        """build.py --env michael --run, with a stand-in compiler that writes michael_hi."""
        compiler = os.path.join(self.tmp.name, 'fake_lathec.py')
        with open(compiler, 'w') as fh:
            fh.write('import os, sys\nsys.path.insert(0, %r)\nsys.path.insert(0, %r)\n'
                     'import test_boards\n'
                     'test_boards.michael_hi().save(os.path.join(sys.argv[-1], "hi.lo"))\n'
                     % (os.path.dirname(build.__file__), HERE))
        source = os.path.join(self.tmp.name, 'hi.lth')
        with open(source, 'w') as fh:
            fh.write('; stand-in\n')
        out = os.path.join(self.tmp.name, 'hi.bin')
        saved = build.COMPILER
        build.COMPILER = compiler
        try:
            import io
            import contextlib
            buf = io.BytesIO()
            wrapper = io.TextIOWrapper(buf)
            with contextlib.redirect_stdout(wrapper):
                status = build.main([source, '-o', out, '--env', 'michael', '--run'])
            wrapper.flush()
        finally:
            build.COMPILER = saved
        self.assertEqual((status, buf.getvalue()), (0, b'HI\n\n\n\n'))


class Reports(unittest.TestCase):
    """boards.py reads the emulator's exit report."""
    MICHAEL = ('michael: exit  cpu_cycles=702  pc=$2036  (STP)\nmichael: lcd:\n'
               '  |HI                  |\n  |  two               |\n  |                    |\n'
               '  |                   x|\nmichael: lcd-hex:\n  |48 49 20|\n')

    def test_rows(self):
        self.assertEqual(boards.read_report(boards.BOARDS['michael'], self.MICHAEL),
                         ['HI', '  two', '', '                   x'])

    def test_cycle_cap(self):
        with self.assertRaisesRegex(boards.RunError, r'run ended by cycle cap at \$2067 after 2000000 CPU cycles'):
            boards.read_report(boards.BOARDS['michael'], self.MICHAEL.replace('$2036  (STP)', '$2067  (cycle cap)'))

    def test_no_report(self):
        with self.assertRaisesRegex(boards.RunError, 'no exit report'):
            boards.read_report(boards.BOARDS['michael'], 'something else\n')

    def test_wrong_number_of_rows(self):
        with self.assertRaisesRegex(boards.RunError, 'no 2-row LCD'):
            boards.read_report(boards.BOARDS['wendy2'], self.MICHAEL)

    def test_board_for(self):
        self.assertEqual(boards.board_for('michael').machine, 'michael')
        self.assertEqual(boards.board_for('/x/y/WENDY2.env').machine, 'wendy2c')
        self.assertIsNone(boards.board_for('host'))

    def test_commands(self):
        image = os.path.join(ROOT, 'x.bin')
        self.assertEqual(boards.command(boards.BOARDS['michael'], image, 0x2000)[1:],
                         [image, '--machine', 'michael', '--load', '2000', '--cycle-cap', '2000000',
                          '--exit-report'])
        self.assertEqual(boards.command(boards.BOARDS['wendy2'], image, 0x4000)[1:],
                         [image, '--machine', 'wendy2c', '--wendy2-prog', image, '--load', '4000',
                          '--cycle-cap', '4000000', '--exit-report'])

    def test_needs_raw_and_stop(self):
        env = mapenv.parse_env(env_text('michael').replace('output    raw', ''), 'michael.env')
        with self.assertRaisesRegex(boards.RunError, 'needs `output raw` and `exit stop`'):
            boards.run(boards.BOARDS['michael'], 'x.bin', env)


class Environments(unittest.TestCase):
    def test_board_environments(self):
        for name, code, data in (('michael', (0x2000, 0x3EFF), (0x0200, 0x1FFF)),
                                 ('wendy2', (0x4000, 0xEFFF), (0x0200, 0x3FFF))):
            env = mapenv.read_env(os.path.join(ENVS, name + '.env'))
            self.assertEqual((env.cpu, env.zeropage, env.code, env.data, env.stack, env.exit, env.output),
                             (1, (0, 0xFF), code, data, 0xFF, ('stop', None), 'raw'), name)

    def test_host_environment_is_unchanged(self):
        env = mapenv.read_env(os.path.join(ENVS, 'host.env'))
        self.assertEqual((env.exit, env.output), (('call', 0xF00F), 'image'))


if __name__ == '__main__':
    unittest.main()
