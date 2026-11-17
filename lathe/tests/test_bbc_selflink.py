"""The Lathe-written linker links the Lathe-written compiler and itself on the emulated BBC Model
B+128, and the compiler rebuilds itself there (lathe/docs/bbc.md, "The linker links the
compiler").

One module image of both tools (test_bbc_toolchain.build_image), every run --bbc-strict, on
memory that starts filled with bytes that are not 0 (the emulator's --fill-ram, which
boards.run_module passes):

- Links: the compiler as lathe/src/lathec-bbc.env describes it (the developer's form, the one
  `*RUN` loads), and the linker as lathe/src/linker-bbc.env does, each from its object files on
  the disc, compiled by the host as build.py compiles them: `*LLINK @LINKARG`, the arguments in
  the command file LINKARG (the compiler's command line is 247 bytes, the linker's 283, and the
  module copies at most 239). Every file the link writes (the image, its bank files, the map)
  must be what the host linker writes from the same objects (LATHE_BBC_SELFLINK=1; by default,
  only a small program linked by a command file and by its command line, the same both ways).
- The loop (LATHE_BBC_LOOP=1): in one run of the emulator, `*LATHE` compiles the compiler's
  modules from their sources, `*LLINK @LINKARG` links them, and the compiler just linked is run
  by `*RUN LATHEC`, its banks loaded into the module's RAM form (`*RUN LOADMOD MODULE` first,
  as for a banked program of test_bbc_toolchain.py), and compiles modules again (LOOP_AGAIN).
  Every object file, interface, the image, its bank files and the map must be the host tools'.

LATHE_BBC_SELFLINK_REPORT=1 prints, for each link, the cycles in the ROM form, the far calls and
`with` blocks (the counting copy), and the file traffic.
"""
import os
import shutil
import tempfile
import unittest

import src_support as support
import test_bbc_toolchain as chain
from test_cases import _read

import boards
import mapenv

LINK_ALL = os.environ.get('LATHE_BBC_SELFLINK') == '1'
LOOP = os.environ.get('LATHE_BBC_LOOP') == '1'
REPORT = os.environ.get('LATHE_BBC_SELFLINK_REPORT') == '1'
TOOLS = (('lathec', 'lathec.lth', chain.COMPILER_ENV), ('link', 'link.lth', chain.LINKER_ENV))
COMMAND_FILE = 'LINKARG'
LOOP_AGAIN = ('err', 'kernel')      # modules the compiler just linked compiles again
CAP = 12_000_000_000


def prepare(name, source, env, work):
    """The BBC's disc and the host's for the build of lathe/src/SOURCE with env, the host's run on
    its own: (bbc disc with the sources and the environment, the compiles' arguments, the link's,
    {file: bytes} the host wrote)."""
    os.makedirs(work)
    steps = chain.recorded(os.path.join(support.SRC, source), env, work)
    disk = os.path.join(work, 'bbc')
    os.makedirs(disk)
    compiles, link = chain.lay_out(steps, disk)
    host = os.path.join(work, 'host')
    shutil.copytree(disk, host)
    files, said = chain.host_files(compiles, link, host)
    assert said == [(0, b'')] * len(said), said
    with open(os.path.join(disk, COMMAND_FILE), 'w') as f:
        f.write(''.join(a + '\n' for a in link))
    return disk, compiles, link, files


def link_outputs(files):
    return {f: d for f, d in files.items() if not f.endswith(('.lo', '.li'))}


@unittest.skipUnless(chain.HAVE_TOOLS, 'emulator or compiler missing')
class SelfLink(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-selflink-')
        cls.module, cls.linker_env, cls.linker_map = chain.build_image(os.path.join(cls.dir, 'image'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_a_command_file_gives_what_the_command_line_gives(self):
        case = [c for c in chain.corpus() if c[0] == 'calls'][0]
        disk, compiles, link, files, said, load = chain.prepare(case, os.path.join(self.dir, 'calls'))
        for f in files:
            if f.endswith('.lo'):
                shutil.copy(os.path.join(os.path.dirname(disk), 'host', f), disk)
        with open(os.path.join(disk, COMMAND_FILE), 'w') as f:
            f.write(' '.join(link) + '\r\n')
        expected = link_outputs(files)
        for n, args in enumerate((['@' + COMMAND_FILE], link)):
            with self.subTest(args=args[0]):
                here = os.path.join(self.dir, 'calls-%d' % n)
                shutil.copytree(disk, here)
                lines = [boards.module_command('LLINK', args)]
                status, out, mos, written, cycles, traffic = chain.bbc_run(self.module, here, lines)
                self.assertEqual((status, out, mos), (0, b'', b''))
                self.assertEqual(sorted(written), sorted(expected))
                for f in expected:
                    self.assertTrue(written[f] == expected[f], f + ' differs')

    @unittest.skipUnless(LINK_ALL or REPORT, 'LATHE_BBC_SELFLINK=1 links the compiler and the linker')
    def test_the_linker_links_the_compiler_and_itself(self):
        for name, source, env in TOOLS:
            with self.subTest(tool=name):
                work = os.path.join(self.dir, 'link-' + name)
                disk, compiles, link, files = prepare(name, source, env, work)
                self.assertGreater(len(' '.join(link)), boards.ROM_TAIL)
                for f in files:
                    if f.endswith('.lo'):
                        shutil.copy(os.path.join(work, 'host', f), disk)
                lines = [boards.module_command('LLINK', ['@' + COMMAND_FILE])]
                status, out, mos, written, cycles, traffic = chain.bbc_run(self.module, disk, lines)
                self.assertEqual((status, out, mos), (0, b'', b''))
                expected = link_outputs(files)
                self.assertEqual(sorted(written), sorted(expected))
                for f in expected:
                    self.assertTrue(written[f] == expected[f], f + ' differs')
                if REPORT:
                    self.report(name, disk, link, cycles, traffic)

    @unittest.skipUnless(LOOP, 'LATHE_BBC_LOOP=1 has the compiler rebuild itself on the BBC')
    def test_the_compiler_rebuilds_itself_on_the_bbc(self):
        work = os.path.join(self.dir, 'loop')
        disk, compiles, link, files = prepare('lathec', 'lathec.lth', chain.COMPILER_ENV, work)
        image = link[2]
        again = [args for args in compiles if os.path.splitext(args[-2])[0] in LOOP_AGAIN]
        self.assertEqual(len(again), len(LOOP_AGAIN))
        lines = [boards.module_command('LATHE', args) for args in compiles]
        lines.append(boards.module_command('LLINK', ['@' + COMMAND_FILE]))
        # The linker writes the image's bytes; *LOAD and *SAVE give it the load and execution
        # addresses that *RUN needs (test_bbc_toolchain.bbc_lines).
        load = mapenv.read_env(chain.COMPILER_ENV).code[0]
        lines += ['LOAD %s %X' % (image, load), 'SAVE %s %X +%X %X' % (image, load, len(files[image]), load)]
        lines += [boards.module_command('RUN', [image] + args) for args in again]
        status, out, mos, written, cycles, traffic = run_long(self.module, disk, lines)
        self.assertEqual((status, mos), (0, b''))
        self.assertEqual(out, b'')
        self.assertEqual(sorted(written), sorted(files))
        for f in files:
            self.assertTrue(written[f] == files[f], f + ' differs')
        if REPORT:
            print('\nthe loop: %d cycles, %.1f minutes at 2 MHz; files opened %d, read %d, written %d'
                  % ((cycles, cycles / 2e6 / 60) + traffic))

    def report(self, name, disk, link, cycles, traffic):
        if not hasattr(type(self), 'counting'):
            type(self).counting = chain.build_counting(os.path.join(self.dir, 'counting'))
        status, out, mos, written, cycles, traffic = chain.bbc_run(
            self.module, disk, [boards.module_command('LLINK', ['@' + COMMAND_FILE])])
        far, withs = chain.counted_link(self.counting, disk, ['@' + COMMAND_FILE])
        print('\n%-8s %12d cycles %7.2f min at 2 MHz, %d far calls, %d blocks, files opened %d, '
              'read %d, written %d' % ((name, cycles, cycles / 2e6 / 60, far, withs) + traffic))


def run_long(module, disk, lines):
    """chain.bbc_run with the module's RAM form and a cycle cap for the whole loop."""
    saved = chain.CAP
    chain.CAP = CAP
    try:
        return chain.bbc_run(module, disk, lines, ram=True)
    finally:
        chain.CAP = saved


if __name__ == '__main__':
    unittest.main()
