"""lathe/rt/disk.lth: files on Wendy 2 with --disk, with the interface of lathe/rt/host.lth.

The end-to-end cases in cases/e2e-wendy2disk/ use disk directly. Here:

- Interface: every function of host.lth that lathe/src/sys.lth calls is in disk.lth under the
  same name, with the same parameter and result types in the same order. host.lth binds them to
  registers; a Lathe function of disk.lth gets the same registers from the calling convention
  (lathe/docs/code-model.md, "Convention"), which the run below shows.
- sys over disk: lathe/src/sys.lth with `host` replaced by `disk` and nothing else changed,
  under lathe/src/copytest.lth, run on Wendy 2 with --disk: the cases of test_src_sys.py.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))

import boards  # noqa: E402
import build  # noqa: E402

RT = os.path.join(ROOT, 'lathe', 'rt')
SRC = os.path.join(ROOT, 'lathe', 'src')

FUNC_RE = re.compile(r'^pub\s+(?:extern\s+|asm\s+)?func\s+(\w+)\((.*?)\)\s*(?::\s*(.*?))?\s*(?:at\s+\$\w+)?\s*(?:;.*)?$')


def _read(path, mode='r'):
    with open(path, mode) as fh:
        return fh.read()


def signatures(path):
    """{name: ([parameter types], [result types])} of a module's exported functions."""
    def types(text):
        out = []
        for part in filter(None, (p.strip() for p in (text or '').split(','))):
            part = part.split(':', 1)[-1].strip()           # `name: type in r` -> `type in r`
            out.append(re.sub(r'\s+in\s+\w+$', '', part))   # -> `type`
        return out

    found = {}
    for line in _read(path).splitlines():
        m = FUNC_RE.match(line.strip())
        if m:
            found[m.group(1)] = (types(m.group(2)), types(m.group(3)))
    return found


class Interface(unittest.TestCase):
    def test_disk_has_what_sys_uses_of_host(self):
        code = '\n'.join(line.split(';', 1)[0] for line in _read(os.path.join(SRC, 'sys.lth')).splitlines())
        used = sorted(set(re.findall(r'\bhost\.(\w+)', code)))
        self.assertEqual(used, ['argc', 'argv', 'close', 'exit', 'open', 'open_out', 'put_byte',
                                'put_error', 'read', 'write'])
        host = signatures(os.path.join(RT, 'host.lth'))
        disk = signatures(os.path.join(RT, 'disk.lth'))
        for name in used:
            self.assertIn(name, disk)
            self.assertEqual(disk[name], host[name], name)

    def test_read_byte_is_the_one_left_out(self):
        host = signatures(os.path.join(RT, 'host.lth'))
        disk = signatures(os.path.join(RT, 'disk.lth'))
        self.assertEqual(sorted(set(host) - set(disk)), ['read_byte'])


def sys_over_disk(work):
    """lathe/src/sys.lth with the module host replaced by disk, and copytest.lth beside it."""
    text = _read(os.path.join(SRC, 'sys.lth'))
    changed = re.sub(r'\bhost\b(?=\.)', 'disk', text.replace('\nimport host\n', '\nimport disk\n'))
    with open(os.path.join(work, 'sys.lth'), 'w') as fh:
        fh.write(changed)
    shutil.copy(os.path.join(SRC, 'copytest.lth'), work)
    return os.path.join(work, 'copytest.lth'), text, changed


@unittest.skipUnless(os.path.isfile(boards.EMULATOR) and os.path.isfile(build.COMPILER),
                     'emulator or compiler missing')
class SysOverDisk(unittest.TestCase):
    """The cases of test_src_sys.py, on Wendy 2. The file names are relative: they are files of
    the directory the program runs on."""

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix='lathe-disk-')
        source, cls.before, cls.after = sys_over_disk(cls.work)
        cls.image = os.path.join(cls.work, 'copytest.bin')
        build.build(source, cls.image, 'wendy2disk', keep=os.path.join(cls.work, 'build'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        self.disk = tempfile.mkdtemp(prefix='lathe-disk-run-')
        self.addCleanup(shutil.rmtree, self.disk, True)

    def run_with(self, args):
        return build.run_program(self.image, 'wendy2disk', args, disk=self.disk)

    def test_only_the_module_name_changed(self):
        lines = [(a, b) for a, b in zip(self.before.splitlines(), self.after.splitlines()) if a != b]
        self.assertTrue(lines)
        for a, b in lines:
            self.assertEqual(a.replace('host', 'disk'), b)

    def test_a_file_is_copied_byte_for_byte(self):
        data = bytes(range(256)) * 5 + b'end'
        with open(os.path.join(self.disk, 'in.bin'), 'wb') as fh:
            fh.write(data)
        status, out, err = self.run_with(['in.bin', 'out.bin'])
        self.assertEqual((status, out, err), (0, b'2 6 7\n', b'!'))
        self.assertEqual(_read(os.path.join(self.disk, 'out.bin'), 'rb'), data)

    def test_an_empty_file_copies_to_an_empty_file(self):
        open(os.path.join(self.disk, 'e'), 'wb').close()
        self.assertEqual(self.run_with(['e', 'f'])[0], 0)
        self.assertEqual(os.path.getsize(os.path.join(self.disk, 'f')), 0)

    def test_arguments_are_counted_and_copied(self):
        status, out, _ = self.run_with(['a', 'bcd', 'ef'])
        self.assertEqual((status, out), (2, b'3 1 3 2\n'))     # no file called a

    def test_an_output_that_cannot_be_created_is_status_3(self):
        open(os.path.join(self.disk, 'g'), 'wb').close()
        self.assertEqual(self.run_with(['g', 'no/such'])[0], 3)


if __name__ == '__main__':
    unittest.main()
