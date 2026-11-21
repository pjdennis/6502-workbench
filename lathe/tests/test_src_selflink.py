"""Stage 8's gate on Wendy 2: the Lathe-written linker (lathe/src/link.lth), banked at the full
capacities with its large tables in data banks (lathe/src/linker-full.env), links the
Lathe-written compiler (lathec.lth as test_src_selfhost.py builds it: compiler-bank.env through
src_support.banked_env) and links itself (link.lth as linker-full.env describes it), from the
object files the host compiler writes. The arguments are given by a command file (`link @cmd`:
disk.lth holds 256 bytes of arguments, and the compiler's link takes 244, the linker's 285). The
image, the bank files and the map must be what the host linker writes from the same objects, and
the status and error output the same.

By default the linker links hello by the command file at the full capacities (a few seconds);
LATHE_SELFLINK=1 also links lextest, the compiler and the linker (about five minutes); LATHE_SELFLINK_REPORT=1
also prints the cycles of each link.
"""
import dataclasses
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import src_support as support
from test_cases import _read
import lk_banked
import test_bbc_toolchain as chain

import boards
import build
import mapenv

ALL = os.environ.get('LATHE_SELFLINK') == '1'
REPORT = os.environ.get('LATHE_SELFLINK_REPORT') == '1'
ENV = os.path.join(support.SRC, 'linker-full.env')
CYCLE_CAP = 40_000_000_000      # oscillator ticks, 2 a CPU cycle
HAVE_TOOLS = os.path.isfile(support.EMULATOR) and os.path.isfile(build.COMPILER)


def recorded_link(source, env, work):
    """The host's build of source with env: ({file: bytes} the link reads, its arguments by base
    names)."""
    os.makedirs(work)
    steps = chain.recorded(source, env, work)
    _, env_path, main, objects = steps[-1]
    files = {os.path.basename(env_path): _read(env_path, 'rb')}
    for o in objects:
        files[os.path.basename(o)] = _read(o, 'rb')
    image = main.upper()[:7]
    return files, [os.path.basename(env_path), main, image, image + '.map'] + [os.path.basename(o) for o in objects]


def host_link(files, args, d):
    """The host linker in directory d: (status, error output, {file: bytes} it wrote)."""
    os.makedirs(d)
    for name, data in files.items():
        with open(os.path.join(d, name), 'wb') as f:
            f.write(data)
    r = subprocess.run([sys.executable, build.LINKER] + args, cwd=d, capture_output=True)
    return r.returncode, r.stderr, {f: _read(os.path.join(d, f), 'rb')
                                    for f in os.listdir(d) if f not in files}


def lathe_link(image, files, args):
    """The banked linker on Wendy 2, the arguments in the command file `cmd`: (status, error
    output, {file: bytes} of every file of the directory that is not an input, the board's or
    named `cmd`, CPU cycles). Unlike lk_banked.run, the linker's own bank files are not left out:
    linking itself, it writes files of those names."""
    env = mapenv.read_env(os.path.splitext(image)[0] + '.env')
    board = dataclasses.replace(boards.BOARDS['wendy2disk'], cycle_cap=CYCLE_CAP)
    with tempfile.TemporaryDirectory(prefix='lathe-selflink-') as disk:
        for name, data in files.items():
            with open(os.path.join(disk, name), 'wb') as f:
                f.write(data)
        with open(os.path.join(disk, 'cmd'), 'wb') as f:
            f.write(b''.join(a.encode() + b'\n' for a in args))
        build.window_files(env, os.path.dirname(os.path.abspath(image)), disk)
        own = {name: _read(os.path.join(disk, name), 'rb') for name in lk_banked.bank_names(env)}
        with open(os.path.join(disk, boards.ARGS_FILE), 'wb') as f:
            f.write(b'@cmd\n')
        report = boards.emulate(board, image, env, disk)
        boards.read_report(board, report)
        m = re.search(r'cpu_cycles=(\d+)', report)
        skip = set(lk_banked.HARNESS) | set(files) | {'cmd'}
        written = lk_banked.files_of(disk, skip)
        return (boards.read_status(disk), boards.read_file(disk, boards.ERRORS_FILE), written,
                int(m.group(1)) if m else 0, own)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class SelfLink(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-selflink-')
        os.makedirs(os.path.join(cls.dir, 'linker'))
        cls.image = lk_banked.build_linker(os.path.join(cls.dir, 'linker'), ENV)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def check(self, title, source, env):
        work = os.path.join(self.dir, title)
        files, args = recorded_link(source, env, work)
        status, err, written, cycles, own = lathe_link(self.image, files, args)
        host = host_link(files, args, os.path.join(work, 'host'))
        self.assertEqual((status, err), host[:2])
        # The linker's own bank files are in the directory: one it did not write is still its own.
        written = {f: d for f, d in written.items() if f in host[2] or f not in own or d != own[f]}
        self.assertEqual(sorted(written), sorted(host[2]))
        for f in host[2]:
            self.assertTrue(written[f] == host[2][f], f + ' differs')
        if REPORT:
            print('\n%s: %d cycles, %.1f minutes at 1 MHz, %d arguments, %d bytes of them'
                  % (title, cycles, cycles / 1e6 / 60, len(args), len(' '.join(args))))
        return args

    def test_a_link_by_the_command_file_at_full_capacities(self):
        self.check('hello', os.path.join(support.LATHE, 'tests', 'cases', 'e2e', 'hello.lth'), 'host')

    @unittest.skipUnless(ALL or REPORT, 'LATHE_SELFLINK=1 links lextest at full size')
    def test_lextest_at_full_capacities(self):
        self.check('lextest', os.path.join(support.SRC, 'lextest.lth'), os.path.join(support.SRC, 'compiler.env'))

    @unittest.skipUnless(ALL or REPORT, 'LATHE_SELFLINK=1 links the compiler and the linker')
    def test_the_linker_links_the_compiler(self):
        env = support.banked_env('lathec', os.path.join(self.dir, 'lathec.env'))
        # Its arguments were longer than a command line holds until `disk`, which `sys` imports only
        # for other machines, stopped being linked (build.py follows #if, 2026-11-21); the linker's
        # own link, below, still shows a link that needs the command file.
        self.check('lathec', os.path.join(support.SRC, 'lathec.lth'), env)

    @unittest.skipUnless(ALL or REPORT, 'LATHE_SELFLINK=1 links the compiler and the linker')
    def test_the_linker_links_itself(self):
        args = self.check('link', os.path.join(support.SRC, 'link.lth'), ENV)
        # More than a command line holds: this link is only possible by the command file.
        self.assertGreater(len(' '.join(args)), 256 - len(args))


if __name__ == '__main__':
    unittest.main()
