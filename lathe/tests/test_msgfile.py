"""The message file, LATHERR (lathe/host/driver/msgfile.py; lathe/docs/bbc.md, "The message
file"): the texts of the errors that the tools' ROM forms on the BBC do not hold.

- The file says what the host tools say: for every number 0 to 255 of each tool, what follows the
  number in its line read from the file as the tools read it is what the host's err.py and
  lk_err.py print, ": " and the text, or ": " alone for a number with no text; the layout is the
  documented one. The twins' own texts (lathe/src/err.lth, lk_err.lth, which every other build
  holds) are the host's tables too, so every form of a tool says the same.
- On the BBC (the tool chain's sixteen-bank image, both tools in their ROM forms: test_bbc_toolchain.
  build_image): with the file on the disc an error is what the host tools print, its position,
  its value and its names included; without it, the number alone with all the rest, for both
  tools. Every disc a test of the ROM forms needs the file on is given it by put_on(), from the
  tables: no test reads a file written by hand.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402
import msgfile  # noqa: E402
import err  # noqa: E402
import lk_err  # noqa: E402

LATHE = support.LATHE


def put_on(disk, fs=0):
    """The message file in the --disk directory disk, where the emulator keeps the file the tools
    open with BBCFS fs (0: names as given, 1: the DFS's, $.LATHERR, 2: ADFS's). Returns its path."""
    import bbcfs
    if fs == 1:
        path = bbcfs.host_path(disk, msgfile.NAME)
    elif fs == 2:
        path = bbcfs.adfs_host_path(disk, msgfile.NAME)
    else:
        path = os.path.join(disk, msgfile.NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    msgfile.write(path)
    return path


def twin_texts(name, first):
    """The texts of the twin lathe/src/NAME.lth's tables: the lines of its string constants from
    the one named `first` to the end of the run of them."""
    with open(os.path.join(support.SRC, name)) as f:
        text = f.read()
    start = text.index('const ' + first)
    lines = []
    for line in text[start:].split('\n'):
        m = re.match(r'\s*(?:const \w+(?: in \w+)? = )?"(.*)\\n"\s*$', line)
        if not m:
            if lines and line.startswith('const MESSAGES'):
                continue
            break
        lines.append(m.group(1).replace('\\"', '"').encode('latin-1'))
    return lines


class File(unittest.TestCase):
    def setUp(self):
        self.data = msgfile.contents()

    def test_the_compilers_numbers_read_as_the_host_prints_them(self):
        texts = msgfile.compiler_texts()
        for n in range(256):
            i = err.message_start(n)
            want = b': ' + (err.MESSAGES[i:err.MESSAGES.index(b'\n', i)] if i < len(err.MESSAGES) else b'')
            self.assertEqual(msgfile.text(self.data, msgfile.COMPILER, n), want, n)
            self.assertEqual(n in texts, i < len(err.MESSAGES), n)

    def test_the_linkers_numbers_read_as_the_host_prints_them(self):
        lines = lk_err.MESSAGES.split(b'\n')
        for n in range(256):
            want = b': ' + (lines[n - 1] if 1 <= n < len(lines) else b'')
            self.assertEqual(msgfile.text(self.data, msgfile.LINKER, n), want, n)

    def test_the_layout(self):
        data = self.data
        self.assertEqual(data[1024:1027], b': \0')         # where a number with no text points
        for part in (msgfile.COMPILER, msgfile.LINKER):
            for n in range(256):
                at = data[512 * part + n] | data[512 * part + 256 + n] << 8
                self.assertGreaterEqual(at, 1024)
                self.assertEqual(data[at:at + 2], b': ')
                self.assertIn(0, data[at:])
        self.assertEqual(data[-1], 0)
        self.assertEqual(len(data), 1024 + 3 + sum(len(t) + 3 for t in msgfile.compiler_texts().values())
                         + sum(len(t) + 3 for t in msgfile.linker_texts().values()))

    def test_the_tool_writes_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'm')
            r = subprocess.run([sys.executable, os.path.join(support.DRIVER, 'msgfile.py'), '-o', path])
            self.assertEqual(r.returncode, 0)
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), self.data)

    def test_the_twins_hold_the_hosts_texts(self):
        self.assertEqual(b''.join(t + b'\n' for t in twin_texts('err.lth', 'MESSAGES_1')), err.MESSAGES)
        self.assertEqual(b''.join(t + b'\n' for t in twin_texts('lk_err.lth', 'MESSAGES')), lk_err.MESSAGES)

    def test_its_name_is_the_same_under_every_filing_system(self):
        """No `.`: the mapping of names leaves it as it is, so the compiler, which opens it
        without the mapping, and the linker, which opens it with it, open the same file."""
        import bbcfs
        self.assertNotIn('.', msgfile.NAME)
        self.assertLessEqual(len(msgfile.NAME), bbcfs.LONGEST)
        self.assertEqual(bbcfs.dfs_name(msgfile.NAME), msgfile.NAME)
        self.assertEqual(bbcfs.host_file(msgfile.NAME), '$.' + msgfile.NAME)
        self.assertEqual(bbcfs.adfs_name(msgfile.NAME), msgfile.NAME)
        for name in ('err.lth', 'lk_err.lth'):
            with open(os.path.join(support.SRC, name)) as f:
                self.assertIn('const MESSAGE_FILE_NAME = "%s"' % msgfile.NAME, f.read())


# ---- On the BBC -----------------------------------------------------------------------------

def compiler_cases():
    """[(name, source text or None, arguments)]: an error with a position, one with a value after
    the text, #error's text after it, and the usage, which has no position."""
    def case(path):
        with open(os.path.join(LATHE, 'tests', 'cases', 'err', path)) as f:
            return f.read()
    return [('rows_record_size', case('rows_record_size.lth'), ['rows_record_size.lth', '.']),
            ('error_directive', case('error_directive.lth'), ['error_directive.lth', '.']),
            ('undefined', 'module undefined\nfunc main()\n  x = 1\nend\n', ['undefined.lth', '.']),
            ('usage', None, [])]


# The linker: the usage (link error 1), and a file it cannot open, whose name follows the text.
LINKER_CASES = [('usage', []), ('open', ['none.env', 'main', 'X', 'X.map', 'a.lo'])]

# Without the file: the number alone, and whatever follows the text.
WITHOUT = {'rows_record_size': b'rows_record_size.lth:7:8: error 136 3\n',
           'error_directive': b'error_directive.lth:4:1: error 181: this configuration is not supported\n',
           'undefined': b'undefined.lth:3:3: error 40\n',
           'usage': b'lathec: error 60\n',
           'link usage': b'link error 1\n',
           'link open': b'link error 2: none.env\n'}


def runs(module, work, with_file):
    """Each case of both tools on the BBC with the module image `module` (in the module scheme in
    force), on a disc of its own in work, with the message file on it or not: {case: ((status,
    output) on the BBC, (status, output) of the host tool)}."""
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
        if with_file:
            put_on(disk)
        tool = support.build.COMPILER if command == 'LATHE' else support.build.LINKER
        r = subprocess.run([sys.executable, tool] + args, cwd=host, capture_output=True)
        status, out, mos, written, cycles, traffic = chain.bbc_run(
            module, disk, [boards.module_command(command, args)])
        found[name] = ((status, out), (r.returncode, r.stdout + r.stderr))
    return found


def check_runs(case, module, work):
    """With the file, every case is the host's; without it, the number alone."""
    for name, (bbc, host) in runs(module, work, True).items():
        with case.subTest(case=name, file=True):
            case.assertEqual(bbc, host)
            case.assertNotEqual(bbc[0], 0)
    for name, (bbc, host) in runs(module, work, False).items():
        with case.subTest(case=name, file=False):
            case.assertEqual(bbc, (host[0], WITHOUT[name]))


@unittest.skipUnless(os.path.isfile(support.EMULATOR) and os.path.isfile(support.build.COMPILER),
                     'emulator or compiler missing')
class OnTheBBC(unittest.TestCase):
    """The tool chain's sixteen-bank image (test_bbc_rom128.py does the same from the eight-bank
    one, and test_bbc_dfs.py and test_bbc_adfs.py under the DFS's names and ADFS's)."""

    @classmethod
    def setUpClass(cls):
        import test_bbc_toolchain as chain
        cls.dir = tempfile.mkdtemp(prefix='lathe-msgfile-')
        cls.module = chain.build_image(os.path.join(cls.dir, 'image'))[0]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_with_the_file_the_hosts_errors_and_without_it_the_number_alone(self):
        check_runs(self, self.module, self.dir)


if __name__ == '__main__':
    unittest.main()
