"""The texts of the errors from the module, on the emulated BBC (lathe/docs/bbc.md, "The texts in
the module"): the tools' ROM forms hold no texts; an error asks the module for its text with the
service call $4C, and the module writes it from the packed tables every image holds
(lathe/host/driver/msgpack.py; test_msgpack.py tests the tables, test_bbc_rom.py every text the
module writes).

- With nothing on the disc, each tool's errors are the host's: a position, a value after the
  text, `#error`'s text after it, the usage (which has no position), an error raised inside a
  `with` block of a region in a sideways RAM slot (error 5, inside lex's `with STRING`), the
  longest text (182), a link error's name after its text.
- When no ROM claims the call (here an image whose reserved bytes answer another call in its
  place), an error is its number alone, with everything else of its line and the same status.

From the tool chain's sixteen-bank image (test_bbc_toolchain.build_image); test_bbc_rom128.py runs
the same from the eight-bank one, and test_bbc_dfs.py and test_bbc_adfs.py under the DFS's names
and ADFS's.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402

LATHE = support.LATHE


def compiler_cases():
    """[(name, source text or None, arguments)]."""
    def case(path):
        with open(os.path.join(LATHE, 'tests', 'cases', 'err', path)) as f:
            return f.read()
    return [('rows_record_size', case('rows_record_size.lth'), ['rows_record_size.lth', '.']),
            ('error_directive', case('error_directive.lth'), ['error_directive.lth', '.']),
            ('undefined', 'module undefined\nfunc main()\n  x = 1\nend\n', ['undefined.lth', '.']),
            ('usage', None, []),
            ('open_string', 'module s\nconst T = "abc\n', ['s.lth', '.']),
            ('region_init', 'module m\nvar x: byte in R = 1\n', ['m.lth', '.'])]


# The linker: the usage (link error 1), and a file it cannot open, whose name follows the text.
LINKER_CASES = [('usage', []), ('open', ['none.env', 'main', 'X', 'X.map', 'a.lo'])]

# When no ROM claims the call: the number alone, and whatever follows the text.
NUMBER_ALONE = {'rows_record_size': b'rows_record_size.lth:7:8: error 136 3\n',
                'error_directive': b'error_directive.lth:4:1: error 181: this configuration is not supported\n',
                'undefined': b'undefined.lth:3:3: error 40\n',
                'usage': b'lathec: error 60\n',
                'open_string': b's.lth:2:11: error 5\n',
                'region_init': b'm.lth:2:13: error 182\n',
                'link usage': b'link error 1\n',
                'link open': b'link error 2: none.env\n'}


def unclaimed(module, path):
    """A copy of the image `module` at `path` whose service code answers call $4D, not $4C, in
    every bank: no ROM claims a tool's call for a text."""
    with open(module, 'rb') as f:
        data = bytearray(f.read())
    at = data[:0x4F].index(bytes([0xC9, 0x4C, 0xF0]))     # CMP #text_call, BEQ
    for bank in range(len(data) // 0x4000):
        assert data[bank * 0x4000 + at + 1] == 0x4C
        data[bank * 0x4000 + at + 1] = 0x4D
    with open(path, 'wb') as f:
        f.write(data)
    return path


def runs(module, work):
    """Each case of both tools on the BBC with the module image `module` (in the module scheme in
    force), on a disc of its own in work: {case: ((status, output) on the BBC, (status, output)
    of the host tool)}."""
    import boards
    import test_bbc_toolchain as chain
    found = {}
    cases = [('LATHE', name, text, args) for name, text, args in compiler_cases()]
    cases += [('LLINK', 'link ' + name, None, args) for name, args in LINKER_CASES]
    for command, name, text, args in cases:
        disk = tempfile.mkdtemp(dir=work)
        if text is not None:
            with open(os.path.join(disk, args[0]), 'w') as f:
                f.write(text)
        host = tempfile.mkdtemp(dir=work)
        for f in os.listdir(disk):
            shutil.copy(os.path.join(disk, f), host)
        tool = support.build.COMPILER if command == 'LATHE' else support.build.LINKER
        r = subprocess.run([sys.executable, tool] + args, cwd=host, capture_output=True)
        status, out, mos, written, cycles, traffic = chain.bbc_run(
            module, disk, [boards.module_command(command, args)])
        found[name] = ((status, out), (r.returncode, r.stdout + r.stderr))
    return found


def check_runs(case, module, work):
    """From the image, every case is the host's; when no ROM claims the call, the number alone."""
    for name, (bbc, host) in runs(module, work).items():
        with case.subTest(case=name):
            case.assertEqual(bbc, host)
            case.assertNotEqual(bbc[0], 0)
    for name, (bbc, host) in runs(unclaimed(module, os.path.join(work, 'UNCLAIMED')), work).items():
        with case.subTest(case=name, claimed=False):
            case.assertEqual(bbc, (host[0], NUMBER_ALONE[name]))


@unittest.skipUnless(os.path.isfile(support.EMULATOR) and os.path.isfile(support.build.COMPILER),
                     'emulator or compiler missing')
class OnTheBBC(unittest.TestCase):
    """The tool chain's sixteen-bank image."""

    @classmethod
    def setUpClass(cls):
        import test_bbc_toolchain as chain
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-texts-')
        cls.module = chain.build_image(os.path.join(cls.dir, 'image'))[0]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_hosts_errors_with_nothing_on_the_disc_and_the_number_alone_if_unclaimed(self):
        check_runs(self, self.module, self.dir)


if __name__ == '__main__':
    unittest.main()
