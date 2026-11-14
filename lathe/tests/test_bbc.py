"""lathe/rt/bbc.lth and lathe/env/bbc.env: a Lathe program on the emulated BBC Model B+128,
run with *RUN through the MOS (lathe/docs/boards.md, "The BBC Micro").

- Interface: bbc.lth has every function of host.lth, with the same parameter and result types.
- The environment: what bbc.env must hold, and that it agrees with bbc.lth.
- The driver: the command line it gives the MOS, and what it makes of the run.
- Each call on the emulator, with --bbc-strict (boards.py always passes it): output and the line
  end, arguments, files byte for byte, the end of a file, a missing file, an error the filing
  system raises, standard input, exit with 0 from any depth and with another status.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))
sys.path.insert(0, HERE)

import boards  # noqa: E402
import build  # noqa: E402
import mapenv  # noqa: E402
from test_disk import signatures, code_of  # noqa: E402

RT = os.path.join(ROOT, 'lathe', 'rt')
BBC_ENV = os.path.join(ROOT, 'lathe', 'env', 'bbc.env')
HAVE_TOOLS = os.path.isfile(boards.EMULATOR) and os.path.isfile(build.COMPILER)


def _read(path, mode='r'):
    with open(path, mode) as fh:
        return fh.read()


class Interface(unittest.TestCase):
    def test_bbc_has_every_function_of_host(self):
        host = signatures(os.path.join(RT, 'host.lth'))
        bbc = signatures(os.path.join(RT, 'bbc.lth'))
        self.assertEqual(sorted(host), ['argc', 'argv', 'close', 'exit', 'open', 'open_out', 'put_byte',
                                        'put_error', 'read', 'read_byte', 'write'])
        for name in host:
            self.assertIn(name, bbc)
            self.assertEqual(bbc[name], host[name], name)

    def test_only_nmos_instructions(self):
        """No 65C02 mnemonic in its asm (STZ, BRA, PHX, PHY, PLX, PLY, TRB, TSB, STP, WAI)."""
        import re
        code = code_of(os.path.join(RT, 'bbc.lth'))
        self.assertEqual(re.findall(r'^\s*(STZ|BRA|PHX|PHY|PLX|PLY|TRB|TSB|STP|WAI)\b', code, re.M), [])


class Environment(unittest.TestCase):
    def setUp(self):
        self.env = mapenv.read_env(BBC_ENV)

    def test_the_machine(self):
        e = self.env
        self.assertEqual((e.cpu, e.zeropage, e.stack, e.output), (0, (0x00, 0x8F), None, 'raw'))
        self.assertEqual(e.code[0], 0x1900)            # PAGE with the DFS: the load address
        self.assertLessEqual(max(e.code[1], e.data[1]), 0x7BFF)     # HIMEM in mode 7
        self.assertGreaterEqual(min(e.code[0], e.data[0]), 0x1900)
        self.assertEqual(dict(e.defines)['PORTS'], 2)
        self.assertIs(boards.board_for(BBC_ENV), boards.BOARDS['bbc'])

    def test_the_stack_pointer_is_kept_where_bbc_looks(self):
        text = _read(os.path.join(RT, 'bbc.lth'))
        self.assertIn('pub const KEEP = $0400', text)
        self.assertEqual(self.env.exit, ('return', 0x0400))

    def test_more_data_is_the_language_workspace_but_the_kept_byte_and_the_command_line(self):
        text = _read(BBC_ENV)
        self.assertIn('\nmore      data $0401 $06FF\n', text)


class Command(unittest.TestCase):
    def test_arguments_are_quoted_only_when_they_must_be(self):
        self.assertEqual(boards.bbc_command('PROG', []), 'RUN PROG')
        self.assertEqual(boards.bbc_command('PROG', ['a', 'b.lth']), 'RUN PROG a b.lth')
        self.assertEqual(boards.bbc_command('PROG', ['', 'a b', 'say "hi"']),
                         'RUN PROG "" "a b" "say ""hi"""')

    def test_what_the_mos_cannot_take(self):
        with self.assertRaises(boards.RunError):
            boards.bbc_command('PROG', ['a\rb'])
        with self.assertRaises(boards.RunError):
            boards.bbc_command('PROG', ['x' * 260])

    def test_the_line_end_is_given_back_as_a_line_feed(self):
        self.assertEqual(boards.bbc_output(b'a\n\rb\n\r\n\r'), b'a\nb\n\n')
        self.assertEqual(boards.bbc_output(b'\r\n\n'), b'\r\n\n')

    def test_the_status_of_an_exit(self):
        report = 'bbcbplus: exit  cpu_cycles=10  pc=$C136  (error)\n'
        self.assertEqual(boards.bbc_status(1, 'Exit 20\n' + report), (20, b'', 10))
        self.assertEqual(boards.bbc_status(1, 'File not found\n' + report), (1, b'File not found\n', 10))
        self.assertEqual(boards.bbc_status(0, report.replace('error', 'returned')), (0, b'', 10))
        with self.assertRaises(boards.RunError):
            boards.bbc_status(1, report.replace('error', 'strict'))
        with self.assertRaises(boards.RunError):
            boards.bbc_status(2, report.replace('error', 'cycle cap'))


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class Calls(unittest.TestCase):
    """Small programs over bbc.lth, each built once."""

    PROGRAMS = {
        # Every argument in brackets, then the count; with three arguments exit(7) from inside
        # a function call; with two, exit(0) from there.
        'args': '''
module args
import bbc
func text(p: ^byte)
  var i: byte = 0
  while p[i] != 0 do
    bbc.put_byte(p[i])
    i += 1
  end
end
func deeper(n: byte)
  if n == 3 then
    bbc.exit(7)
  end
  if n == 2 then
    bbc.exit(0)
  end
end
pub func main()
  var i: byte
  for i = 0 until bbc.argc() do
    text("[")
    text(bbc.argv(i))
    text("]")
  end
  text(bbc.argv(bbc.argc()))
  bbc.put_byte('0' + bbc.argc())
  bbc.put_byte(10)
  deeper(bbc.argc())
  text("end\\n")
end
''',
        # copy IN OUT: byte for byte; the count of bytes in hex; then read once more at the end.
        'copy': '''
module copy
import bbc
const DIGITS: [16]byte = "0123456789ABCDEF"
func hex(b: byte)
  bbc.put_byte(DIGITS[b >> 4])
  bbc.put_byte(DIGITS[b & 15])
end
pub func main()
  var i: byte
  var o: byte
  var b: byte
  var n: word = 0
  i = bbc.open(bbc.argv(0))
  if i == 0 then
    bbc.put_error('?')
    bbc.exit(2)
  end
  o = bbc.open_out(bbc.argv(1))
  if o == 0 then
    bbc.exit(3)
  end
  while not bbc.read(i) -> b do
    bbc.write(b, o)
    n += 1
  end
  hex(hi(n))
  hex(lo(n))
  if bbc.read(i) -> b then
    bbc.put_byte('.')
  end
  if bbc.read(i) -> b then
    bbc.put_byte('.')
  end
  bbc.close(o)
  bbc.close(i)
  bbc.put_byte(10)
end
''',
        # standard input to standard output, '<' at its end
        'echo': '''
module echo
import bbc
pub func main()
  var c: byte
  while not bbc.read_byte() -> c do
    bbc.put_byte(c)
  end
  bbc.put_byte('<')
end
''',
        # files left open are closed by exit: a file written and not closed is complete
        'unclosed': '''
module unclosed
import bbc
pub func main()
  var o: byte
  o = bbc.open_out("left")
  bbc.write('o', o)
  bbc.write('k', o)
  bbc.exit(bbc.argc())
end
''',
    }

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix='lathe-bbc-')
        cls.images = {}
        for name, text in cls.PROGRAMS.items():
            source = os.path.join(cls.work, name + '.lth')
            with open(source, 'w') as fh:
                fh.write(text.lstrip())
            cls.images[name] = os.path.join(cls.work, name + '.bin')
            build.build(source, cls.images[name], 'bbc', keep=os.path.join(cls.work, name))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        self.disk = tempfile.mkdtemp(prefix='lathe-bbc-disk-')
        self.addCleanup(shutil.rmtree, self.disk, True)

    def run_with(self, name, args=(), stdin=None):
        return build.run_program(self.images[name], 'bbc', args, stdin=stdin, disk=self.disk)

    def file(self, name, data=None):
        path = os.path.join(self.disk, name)
        if data is not None:
            with open(path, 'wb') as fh:
                fh.write(data)
        return path

    def test_the_build_writes_the_inf_file(self):
        inf = _read(self.images['args'] + '.inf').split()
        size = os.path.getsize(self.images['args'])
        self.assertEqual(inf, ['args', '00001900', '00001900', '%08X' % size])

    def test_the_start_up_code_keeps_the_stack_pointer(self):
        self.assertEqual(_read(self.images['args'], 'rb')[:4], bytes.fromhex('BA8E0004'))

    def test_no_arguments(self):
        self.assertEqual(self.run_with('args'), (0, b'0\nend\n', b''))

    def test_arguments(self):
        self.assertEqual(self.run_with('args', ['a']), (0, b'[a]1\nend\n', b''))

    def test_quoted_and_empty_arguments(self):
        status, out, _ = self.run_with('args', ['x y', '', '"q"', 'z'])
        self.assertEqual((status, out), (0, b'[x y][]["q"][z]4\nend\n'))

    def test_spaces_between_arguments_do_not_count(self):
        """The command line as typed, with more spaces than the driver writes."""
        status, out, _, _ = boards.run_mos(boards.BOARDS['bbc'], self.images['args'], self.disk,
                                           command_tail='   a    b   ')
        self.assertEqual((status, out), (0, b'[a][b]2\n'))

    def test_exit_0_returns_to_the_mos_from_inside_a_call(self):
        status, out, err = self.run_with('args', ['a', 'b'])
        self.assertEqual((status, out, err), (0, b'[a][b]2\n', b''))

    def test_exit_with_a_status_raises_a_mos_error(self):
        status, out, err = self.run_with('args', ['a', 'b', 'c'])
        self.assertEqual((status, out, err), (7, b'[a][b][c]3\n', b''))
        # what the emulator itself shows: the MOS's error, and status 1
        status, _, err, _ = boards.run_mos(boards.BOARDS['bbc'], self.images['args'], self.disk,
                                           ['a', 'b', 'c'], raw=True)
        self.assertEqual(status, 1)
        self.assertTrue(err.startswith(b'Exit 7\n'), err)

    def test_a_file_is_copied_byte_for_byte(self):
        data = bytes(range(256)) * 3 + b'\r\n\n\r'
        self.file('in', data)
        self.assertEqual(self.run_with('copy', ['in', 'out']), (0, b'0304..\n', b''))
        self.assertEqual(_read(self.file('out'), 'rb'), data)

    def test_an_empty_file(self):
        self.file('e', b'')
        self.assertEqual(self.run_with('copy', ['e', 'f']), (0, b'0000..\n', b''))
        self.assertEqual(_read(self.file('f'), 'rb'), b'')

    def test_a_missing_file_is_0(self):
        status, out, err = self.run_with('copy', ['none', 'f'])
        self.assertEqual((status, out, err), (2, b'?', b''))     # the error output is the output

    def test_a_name_the_filing_system_refuses_is_0_and_not_an_error(self):
        self.file('e', b'')
        self.assertEqual(self.run_with('copy', ['e', 'no/such'])[0], 3)       # Bad name
        self.assertEqual(self.run_with('copy', ['no/such', 'f'])[0], 2)

    def test_standard_input(self):
        self.assertEqual(self.run_with('echo', stdin=b'ab\rc\n'), (0, b'ab\nc\n<', b''))
        self.assertEqual(self.run_with('echo', stdin=b''), (0, b'<', b''))

    def test_exit_closes_the_files(self):
        self.assertEqual(self.run_with('unclosed', ['x'])[0], 1)
        self.assertEqual(_read(self.file('left'), 'rb'), b'ok')
        self.assertEqual(self.run_with('unclosed')[0], 0)
        self.assertEqual(_read(self.file('left'), 'rb'), b'ok')

    def test_the_program_is_not_left_in_the_directory(self):
        self.run_with('args')
        self.assertEqual(os.listdir(self.disk), [])


if __name__ == '__main__':
    unittest.main()
