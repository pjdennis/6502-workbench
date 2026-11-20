"""The developer's cycle (lathe/docs/bbc.md, "The developer's cycle"; opt-in, long:
LATHE_BBC_CYCLE=1): one tool at a time on a pair of ADFS discs of its own, with no host step and
no disc changed within a turn.

The B+128 with ADFS (PAGE $1F00) and the module's RAM form holding the host's first load from
power on: both tools in their eight-bank ROM forms in bbcrom.py's whole layout (what MODLOAD
writes from HOME and the tools' link outputs: test_modload.py). On the tool's pair, drive 0: its
sources (`lth`), its ROM environment (`env`), the link's command file LINKARG and MODLOAD; drive
1: its objects and interfaces (`lo`, `li`), its resident image, its bank files (`BIN`) and its map
(`map`). A turn, in one run of the emulator: `*LATHE` compiles each of the tool's modules from
drive 0 to drive 1, `*LLINK @LINKARG` links its ROM form, and `*RUN MODLOAD ENV MAP IMAGE`
writes it into its own banks of the module, the other tool and the home bank left as they are.
The second turn runs with what the first left in the module, so the tool it links is the one
the first made; then MODLOAD again.

The sources carry a change that shows which tool ran (made in copies only): for the compiler,
the version byte of its interface files, 2 to 3 (decl.lth and its twin decl.py), so that the
interfaces of the second turn, made by the compiler the first made, have 3; for the linker, the
mark after a read-only bank's file in its map, " rom" to " ROM" (lk_map.lth and lk_map.py), so
that the map of the second turn has " ROM". At each turn every file on both drives is the one
the host's tools leave from the same commands (the first turn's tools the host's, the second's
the host's twins with the change), and the module's sixteen banks are bbcrom.py's whole image
of the host's link outputs (the module dumped at the end of the run).

LATHE_BBC_CYCLE_TOOL=LATHE or LLINK runs one pair only. Prints each turn's cycles and minutes at
2 MHz and what each drive holds.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_bbc_adfs as adfs  # noqa: E402
import test_modload as modload  # noqa: E402
import bbcfs  # noqa: E402
import bbcrom  # noqa: E402
import boards  # noqa: E402
import build  # noqa: E402

CYCLE = os.environ.get('LATHE_BBC_CYCLE') == '1'
ONLY = os.environ.get('LATHE_BBC_CYCLE_TOOL')
LATHE = adfs.LATHE
CAP = 14_000_000_000
COMMAND_FILE = 'LINKARG'

# command: (its main source, the change: [(file of lathe/src or lathe/host, old, new)])
TOOLS = {
    'LATHE': ('lathec.lth', [('src/decl.lth', 'const LI_VERSION = 2', 'const LI_VERSION = 3'),
                             ('host/decl.py', 'LI_VERSION = 2', 'LI_VERSION = 3')]),
    'LLINK': ('link.lth', [('src/lk_map.lth', '= " rom"', '= " ROM"'),
                           ('host/lk_map.py', 'b" rom"', 'b" ROM"')]),
}


def changed_tree(work, command):
    """Copies of lathe/src and lathe/host in work with the tool's change: (src, host)."""
    src, host = os.path.join(work, 'src'), os.path.join(work, 'host')
    shutil.copytree(os.path.join(LATHE, 'src'), src)
    shutil.copytree(os.path.join(LATHE, 'host'), host, ignore=shutil.ignore_patterns('__pycache__'))
    for name, old, new in TOOLS[command][1]:
        path = os.path.join(work, name)
        with open(path) as f:
            text = f.read()
        assert text.count(old) == 1, (name, old)
        with open(path, 'w') as f:
            f.write(text.replace(old, new))
    return src, host


def lay_out_pair(work, source, rom_env, modload_image):
    """The pair's two drives in work/disc as the host's tools name them (`0/`, `1/` and the root
    for drive 0's root), from the host's build of source with rom_env: (the disc, each compile's
    arguments, the link's, MODLOAD's)."""
    import test_bbc_toolchain as toolchain
    steps = toolchain.recorded(source, rom_env, os.path.join(work, 'build'))
    flat = os.path.join(work, 'flat')
    os.makedirs(flat)
    compiles, link = toolchain.lay_out(steps, flat)
    disk = os.path.join(work, 'disc')
    for d in ('0', '1'):
        os.makedirs(os.path.join(disk, d))
    env = os.path.basename(rom_env)
    shutil.copy(os.path.join(flat, env), disk)
    moved = []
    for args in compiles:
        name = args[-2]
        shutil.copy(os.path.join(flat, name), os.path.join(disk, '0', name))
        moved.append(args[:-2] + ['0/' + name, '1'])
    link = link[:2] + ['1/' + link[2], '1/' + link[3]] + ['1/' + o for o in link[4:]]
    with open(os.path.join(disk, COMMAND_FILE), 'w') as f:
        f.write(''.join(a + '\n' for a in link))
    shutil.copy(modload_image, os.path.join(disk, 'MODLOAD'))
    return disk, moved, link, [env, link[3], link[2]]


def host_turn(disk, compiles, link, compiler, linker):
    """The compiles and the link run by the host's tools (compiler, linker) in disk."""
    for args in compiles:
        r = subprocess.run([sys.executable, compiler] + args, cwd=disk, capture_output=True)
        assert (r.returncode, r.stdout + r.stderr) == (0, b''), (args, r.stdout + r.stderr)
    r = subprocess.run([sys.executable, linker] + link, cwd=disk, capture_output=True)
    assert (r.returncode, r.stdout + r.stderr) == (0, b''), r.stdout + r.stderr


def on_the_bbc(files):
    """{file as --bbc-fs adfs keeps it: bytes} of {host name: bytes}."""
    return {bbcfs.adfs_host_file(bbcfs.adfs_name(f)): d for f, d in files.items()}


@unittest.skipUnless(adfs.HAVE_TOOLS and CYCLE, 'LATHE_BBC_CYCLE=1 runs it')
class Cycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-cycle-')
        cls.modload = modload.build_modload(os.path.join(cls.dir, 'modload'))
        cls.tools, cls.whole, cls.home = modload.build_tools(os.path.join(cls.dir, 'tools'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def whole_image(self, command, resident, out):
        """bbcrom.py's whole image of the host's first tools with `command` replaced by the link
        whose resident image is `resident` (its bank files beside it; its map, which only the
        listing reads and whose read-only mark the linker's change makes one mapenv does not take,
        left out)."""
        tools = [(c, resident, env) if c == command else (c, r, env, m) for c, r, env, m in self.tools]
        bbcrom.image(tools, out, os.path.join(self.dir, 'listing'), banks=16, whole=True)
        return out

    def assert_module(self, dump, want):
        with open(want, 'rb') as f:
            want = f.read()
        with open(dump, 'rb') as f:
            got = f.read()
        self.assertEqual(len(got), len(want))
        for i in range(len(want)):
            if want[i] != got[i] and (want[i] != 0xFF or i % 0x4000 < 0x50):
                self.fail('bank %d, $%04X: $%02X, the image $%02X' % (i // 0x4000, 0x8000 + i % 0x4000,
                                                                         got[i], want[i]))

    def cycle(self, command):
        work = os.path.join(self.dir, command.lower())
        os.makedirs(work)
        source, _ = TOOLS[command]
        src, host = changed_tree(work, command)
        rom_env = [env for c, r, env, m in self.tools if c == command][0]
        disk, compiles, link, load = lay_out_pair(work, os.path.join(src, source), rom_env, self.modload)
        compilers = [build.COMPILER, os.path.join(host, 'lathec.py') if command == 'LATHE' else build.COMPILER]
        linkers = [build.LINKER, os.path.join(host, 'link.py') if command == 'LLINK' else build.LINKER]
        # The BBC's discs, and the host's of each turn.
        bbc = os.path.join(work, 'bbc')
        os.makedirs(bbc)
        for f, d in adfs.files_of(disk).items():
            adfs.put(bbc, f, d)
        with open(bbcfs.adfs_host_path(bbc, 'MODLOAD') + '.inf', 'w') as f:
            f.write(boards.inf_text('$.MODLOAD', adfs.PAGE, os.path.getsize(self.modload)))
        hosts = []
        previous = disk
        for turn in range(2):
            h = os.path.join(work, 'host%d' % turn)
            shutil.copytree(previous, h)
            host_turn(h, compiles, link, compilers[turn], linkers[turn])
            hosts.append(h)
            previous = h
        lines = [boards.module_command('LATHE', args) for args in compiles]
        lines.append(boards.module_command('LLINK', ['@' + COMMAND_FILE]))
        lines.append(boards.module_command('RUN', ['MODLOAD'] + load))
        module = self.whole
        saved, adfs.CAP = adfs.CAP, CAP
        results = []
        try:
            for turn in range(2):
                dump = os.path.join(work, 'module%d' % turn)
                status, out, mos, written, cycles, report = adfs.run_adfs(
                    module, bbc, lines, ram=True, extra=('--bbc-module-dump', dump))
                with self.subTest(turn=turn + 1):
                    self.assertEqual((status, out, mos), (0, b'', b''))
                    want = on_the_bbc(adfs.files_of(hosts[turn]))
                    with open(self.modload, 'rb') as f:
                        want[bbcfs.adfs_host_file('MODLOAD')] = f.read()
                    got = adfs.files_of(bbc)
                    self.assertEqual(sorted(got), sorted(want))
                    for f in want:
                        self.assertTrue(got[f] == want[f], f + ' differs')
                    self.assert_module(dump, self.whole_image(command, os.path.join(hosts[turn], link[2]),
                                                              os.path.join(work, 'whole%d' % turn)))
                    self.assertEqual(report[:2], (2, 1))
                    cat = adfs.catalogue(bbc)
                    for d, (_, _, n, most) in cat.items():
                        self.assertEqual(report[3][d][0], n, d)
                        self.assertLessEqual(report[3][d][1], adfs.SECTORS)
                results.append((cycles, cat, report))
                module = dump
        finally:
            adfs.CAP = saved
        # The change shows: the second turn's files are the changed tool's.
        first, second = (adfs.files_of(h) for h in hosts)
        if command == 'LATHE':
            lis = [f for f in second if f.endswith('.li')]
            self.assertTrue(lis)
            for f in lis:
                self.assertEqual((first[f][2], second[f][2]), (2, 3), f)
        else:
            self.assertNotIn(b' ROM', first[link[3]])
            self.assertIn(b' ROM', second[link[3]])
        print('\n%s on its pair of discs:' % command)
        for turn, (cycles, cat, report) in enumerate(results):
            print('  turn %d: %d cycles, %.1f minutes at 2 MHz; most open %d, writing %d, most entries %d'
                  % ((turn + 1, cycles, cycles / 2e6 / 60) + report[:3]))
            for line in adfs.account(cat, report):
                print('    ' + line)

    @unittest.skipIf(ONLY and ONLY != 'LATHE', 'LATHE_BBC_CYCLE_TOOL')
    def test_the_compiler_on_its_pair(self):
        self.cycle('LATHE')

    @unittest.skipIf(ONLY and ONLY != 'LLINK', 'LATHE_BBC_CYCLE_TOOL')
    def test_the_linker_on_its_pair(self):
        self.cycle('LLINK')


if __name__ == '__main__':
    unittest.main()
