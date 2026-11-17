"""Lathe programs as a ROM module on the emulated BBC Model B+128 (lathe/docs/bbc.md, "Step 3, as
built: the ROM form"): one image of sixteen 16 KB banks (lathe/host/driver/bbcrom.py, scheme
direct16) in one sideways slot, holding three programs, each linked on its own with an
environment of its own (lathe/env/bbc-rom.env and its lines, bbcrom.rom_env) and started by its
* command, with its arguments; their code banks read only, their regions in sideways RAM, the rest
in main RAM. Every run is under --bbc-strict (boards.run_module).

- *FIRST: e2e-config's farcall.lth (far calls between banks 1 and 2), bankdata.lth (constants of
  libbkd in bank 3, its variable in main RAM, as a ROM bank holds no variable) and regions.lth
  (variables in sideways slot 12, constants in slot 13, which the module copies there).
- *SECOND: test_bbc_bank.py's program (far calls between banks 4 and 5, recursion across them,
  regions in slots 12 and 13 at the same addresses, a far call inside a block, MOS file calls from
  a bank and inside a block).
- *THIRD: all in one, no bank; `*THIRD fail` ends with exit(9).

Each gives what it gives run with *RUN, banked (the developer's form, lathe/env/bbc-bank.env) and
all in one (lathe/env/bbc.env), from the same objects; in every power-on bank of the latch; in a
slot other than 4; and from the same image loaded by LOADMOD into the module's RAM form. The ends:
re-entering a language ROM (one made here) with OSBYTE 142, or returning from the service call
where there is none; an error for a status other than 0. A command the module does not know is
left unclaimed, *HELP lists the commands, and other service calls change nothing (the latch
stays where it was). And the image tool's checks.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
CASES = os.path.join(HERE, 'cases', 'e2e-config')
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))
sys.path.insert(0, HERE)

import bbcrom  # noqa: E402
import boards  # noqa: E402
import build  # noqa: E402
import mapenv  # noqa: E402
import test_bbc_bank as tbb  # noqa: E402

BOARD = boards.BOARDS['bbc']
ROM_ENV = os.path.join(ROOT, 'lathe', 'env', 'bbc-rom.env')
BANK_ENV = tbb.BANK_ENV
FLAT_ENV = tbb.FLAT_ENV
HAVE_TOOLS = tbb.HAVE_TOOLS

ARGS = '''  i = 0
  while i < host.argc() do
    libfco.text(" [")
    libfco.text(host.argv(i))
    libfco.put(']')
    i += 1
  end
  libfco.put(10)
'''
MAINS = {
    'rfirst': '''module rfirst
import host
import libfco
import farcall
import bankdata
import regions

pub func main()
  var i: byte
  libfco.text("first")
''' + ARGS + '''  farcall.main()
  bankdata.main()
  regions.main()
end
''',
    'rsecond': '''module rsecond
import host
import libfco
import bkmain

pub func main()
  var i: byte
  libfco.text("second")
''' + ARGS + '''  bkmain.main()
end
''',
    'rthird': '''module rthird
import host
import libfco

pub func main()
  libfco.text("third")
  libfco.put(10)
  if host.argc() > 0 then
    host.exit(9)
  end
end
''',
}
FIRST_BANKS = tbb.FARCALL + tbb.BANKDATA + tbb.REGIONS
SECOND_BANKS = tbb.PROGRAM_BANKS
# command, main module, its lines for bbc-bank.env (None: all in one)
PROGRAMS = (('FIRST', 'rfirst', FIRST_BANKS), ('SECOND', 'rsecond', SECOND_BANKS),
            ('THIRD', 'rthird', None))
FIRST_ARGS = ['a', 'b c', '']
SECOND_ARGS = ['x']


def language_rom(path):
    """A language ROM of 16 KB: its language entry prints LANG and a new line and returns (which
    ends the emulator's run); its service entry returns."""
    rom = bytearray([0xFF]) * 0x4000
    rom[0:9] = bytes([0x4C, 0x20, 0x80, 0x4C, 0x30, 0x80, 0xC2, 0x0D, 0x01])
    rom[9:0x12] = b'Lang\x00(C)\x00'
    rom[0x20:0x2D] = bytes([0xA2, 0x00, 0xBD, 0x40, 0x80, 0xF0, 0x06, 0x20, 0xE3, 0xFF, 0xE8,
                            0xD0, 0xF5])
    rom[0x2D] = 0x60                     # RTS
    rom[0x30] = 0x60
    rom[0x40:0x46] = b'LANG\r\x00'
    with open(path, 'wb') as f:
        f.write(rom)
    return path


class RomImage:
    """The image of the three programs, of BANKS banks, their banks numbered from FIRST_BANK, and
    the helpers that run them (test_bbc_rom128.py's eight-bank form uses them too)."""
    BANKS = 16
    FIRST_BANK = 1

    @classmethod
    def setUpClass(cls):
        d = cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-rom-')
        src = os.path.join(d, 'src')
        os.makedirs(src)
        for f in glob.glob(os.path.join(CASES, '*.lth')):
            shutil.copy(f, src)
        tbb.write_program(src, tbb.PROGRAM)
        for name, text in MAINS.items():
            with open(os.path.join(src, name + '.lth'), 'w') as f:
                f.write(text)
        cls.specs, cls.runs, cls.flats, cls.maps, cls.envs = [], {}, {}, {}, {}
        first = cls.FIRST_BANK
        for command, main, lines in PROGRAMS:
            source = os.path.join(src, main + '.lth')
            rom = os.path.join(d, 'rom-' + command)
            os.makedirs(rom)
            env = os.path.join(d, command.lower() + '-rom.env')
            if lines is None:
                shutil.copy(ROM_ENV, env)
            else:
                run_env = tbb.bank_env(os.path.join(d, command.lower() + '-run.env'), lines, ports=0)
                first = bbcrom.rom_env(run_env, env, first, cls.BANKS)
                run_dir = os.path.join(d, 'run-' + command)
                os.makedirs(run_dir)
                build.build(source, os.path.join(run_dir, command), run_env,
                            keep=os.path.join(run_dir, 'work'))
                cls.runs[command] = (os.path.join(run_dir, command), run_env)
            with open(env) as f:
                text = f.read()
            text, n = re.subn(r'(?m)^define\s+PORTS\s+\d+', 'define    PORTS 0', text)
            assert n == 1
            with open(env, 'w') as f:
                f.write(text)
            cls.envs[command] = env
            build.build(source, os.path.join(rom, command), env, keep=os.path.join(rom, 'work'))
            cls.maps[command] = os.path.join(rom, 'work', main + '.map')
            cls.specs.append((command, os.path.join(rom, command), env, cls.maps[command]))
            flat_dir = os.path.join(d, 'flat-' + command)
            os.makedirs(flat_dir)
            flat_env = tbb.bank_env(os.path.join(d, command.lower() + '-flat.env'), [], base=FLAT_ENV,
                                    ports=0)
            build.build(source, os.path.join(flat_dir, command), flat_env,
                        keep=os.path.join(flat_dir, 'work'))
            cls.flats[command] = (os.path.join(flat_dir, command), flat_env)
        cls.image = os.path.join(d, 'MODULE')
        cls.short = os.path.join(d, 'MODSHORT')
        cls.listing = bbcrom.image(cls.specs, cls.image, os.path.join(d, 'MODULE.txt'), short=cls.short,
                                   banks=cls.BANKS)
        cls.language = language_rom(os.path.join(d, 'LANG.rom'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def disk(self):
        d = tempfile.mkdtemp(prefix='disk-', dir=self.dir)
        with open(os.path.join(d, 'INPUT'), 'wb') as f:
            f.write(tbb.INPUT)
        return d

    def command(self, command, args=(), **options):
        """(status, output, error output, the emulator's report) of *COMMAND ARGS."""
        disk = options.pop('disk', None) or self.disk()
        options.setdefault('scheme', bbcrom.SCHEMES[self.BANKS])
        status, out, err, _ = boards.run_module(BOARD, self.image, disk, command, args, raw=True,
                                                **options)
        report = err.decode('latin-1')
        said = ''.join(line for line in report.splitlines(True) if not line.startswith('bbcbplus: '))
        try:
            status, said, _ = boards.bbc_status(status, report)
        except boards.RunError:
            self.fail(report)
        return status, boards.bbc_output(out), said, report

    def expected(self, command, args):
        """What *RUN gives for the program, banked (the developer's form) and all in one: the
        two must be the same, and are what the ROM form must give."""
        found = []
        for image, env in [self.runs[command], self.flats[command]] if command in self.runs \
                else [self.flats[command]]:
            disk = self.disk()
            found.append(build.run_program(image, env, args, disk=disk))
            if command == 'SECOND':
                with open(os.path.join(disk, 'OUTPUT'), 'rb') as f:
                    self.assertEqual(f.read(), tbb.INPUT)
        self.assertEqual(len(set(found)), 1, found)
        return found[0]


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class RomModule(RomImage, unittest.TestCase):

    # ---- The programs ------------------------------------------------------------------------

    def test_two_programs_of_one_image_each_by_its_command(self):
        for command, args in (('FIRST', FIRST_ARGS), ('SECOND', SECOND_ARGS), ('THIRD', [])):
            with self.subTest(command=command):
                want = self.expected(command, args)
                disk = self.disk()
                status, out, said, report = self.command(command, args, disk=disk)
                self.assertEqual((status, out, said), want)
                self.assertIn('checks: mos-memory-writes=0  romsel-mismatches=0', report)
                if command == 'SECOND':
                    with open(os.path.join(disk, 'OUTPUT'), 'rb') as f:
                        self.assertEqual(f.read(), tbb.INPUT)
        first = self.expected('FIRST', FIRST_ARGS)[1]
        self.assertTrue(first.startswith(b'first [a] [b c] []\nnest '), first)
        for case in ('farcall', 'bankdata', 'regions'):
            with open(os.path.join(CASES, case + '.expected.out'), 'rb') as f:
                self.assertIn(f.read(), first)
        self.assertTrue(self.expected('SECOND', SECOND_ARGS)[1].endswith(tbb.PROGRAM_OUT))

    def test_the_same_objects_link_for_run_and_for_the_rom(self):
        for command in ('FIRST', 'SECOND'):
            rom = os.path.join(self.dir, 'rom-' + command, 'work')
            run = os.path.join(self.dir, 'run-' + command, 'work')
            objects = sorted(os.path.basename(p) for p in glob.glob(os.path.join(rom, '*.lo')))
            self.assertEqual(objects, sorted(os.path.basename(p) for p in glob.glob(os.path.join(run, '*.lo'))))
            self.assertIn('rt_bbc.lo', objects)
            for name in objects:
                with open(os.path.join(rom, name), 'rb') as a, open(os.path.join(run, name), 'rb') as b:
                    self.assertEqual(a.read(), b.read(), name)

    def test_every_power_on_bank(self):
        want = self.expected('FIRST', FIRST_ARGS)
        second = self.expected('SECOND', SECOND_ARGS)
        for bank in range(16):
            with self.subTest(bank=bank):
                self.assertEqual(self.command('FIRST', FIRST_ARGS, bank=bank)[:3], want)
                if bank in (3, 15):
                    self.assertEqual(self.command('SECOND', SECOND_ARGS, bank=bank)[:3], second)

    def test_a_slot_other_than_4(self):
        for slot in (7, 2):
            with self.subTest(slot=slot):
                for command, args in (('FIRST', FIRST_ARGS), ('SECOND', SECOND_ARGS)):
                    status, out, said, report = self.command(command, args, slot=slot, bank=6)
                    self.assertEqual((status, out, said), self.expected(command, args))
                    self.assertIn('module: slot %d, direct16 ROM' % slot, report)

    def test_the_same_image_through_the_loader_in_the_ram_form(self):
        loader = os.path.join(self.dir, 'LOADMOD')
        bbcrom.loader(loader)
        for slot, bank, line in ((4, 0, 'RUN LOADMOD MODIMG'), (4, 9, 'RUN LOADMOD MODIMG 4'),
                                 (7, 13, '*RUN LOADMOD MODIMG 7')):
            for command, args in (('FIRST', FIRST_ARGS), ('SECOND', SECOND_ARGS), ('THIRD', [])):
                with self.subTest(slot=slot, bank=bank, command=command):
                    disk = self.disk()
                    for name in ('LOADMOD', 'LOADMOD.inf'):
                        shutil.copy(os.path.join(self.dir, name), disk)
                    shutil.copy(self.image, os.path.join(disk, 'MODIMG'))
                    status, out, said, report = self.command(command, args, disk=disk, slot=slot,
                                                             bank=bank, ram=True, before=[line])
                    self.assertEqual((status, out, said), self.expected(command, args))
                    self.assertIn('module: slot %d, direct16 RAM' % slot, report)
        # Without it the RAM form is empty: the command is no one's.
        status, out, said, report = self.command('FIRST', ram=True)
        self.assertEqual((status, said), (1, b'Bad command\n'))

    def test_the_short_image_holds_the_banks_in_use(self):
        """bbcrom --short: banks 0 to the last one in use (here 5: the programs' banks are 1 to
        5, and the resident parts and region constants fit bank 0), the full image's first ones;
        the listing says how many."""
        with open(self.image, 'rb') as f:
            full = f.read()
        with open(self.short, 'rb') as f:
            short = f.read()
        used = int(re.search(r'banks in use: 0 to (\d+), (\d+) bytes', self.listing).group(1))
        self.assertEqual(len(short), (used + 1) * 0x4000)
        self.assertEqual(short, full[:len(short)])
        self.assertLess(used, 15)
        self.assertNotIn('bank %2d: empty' % used, self.listing)
        self.assertIn('bank %2d: empty' % (used + 1), self.listing)

    def test_the_short_image_through_the_loader(self):
        """LOADMOD takes the short image: each command gives what it gives from the ROM, with the
        latch at a bank past the file's at power on; and a bank past the file has the reserved
        bytes: a program latches bank 14 and makes service call 6 (OSBYTE 143), which the
        header there passes to bank 0 and back."""
        loader = os.path.join(self.dir, 'LOADMOD')
        bbcrom.loader(loader)
        svc = bytes([0xA5, 0xF4, 0x48, 0xA9, 0x04, 0x85, 0xF4, 0x8D, 0x30, 0xFE, 0xAD, 0xFE, 0xBF,
                     0x68, 0x85, 0xF4, 0x8D, 0x30, 0xFE,
                     0xA9, 0x8F, 0xA2, 0x06, 0xA0, 0x00, 0x20, 0xF4, 0xFF, 0x60])
        for command, args in (('FIRST', FIRST_ARGS), ('SECOND', SECOND_ARGS), ('THIRD', []),
                              ('RUN', ['SVC'])):
            with self.subTest(command=command):
                disk = self.disk()
                for name in ('LOADMOD', 'LOADMOD.inf'):
                    shutil.copy(os.path.join(self.dir, name), disk)
                shutil.copy(self.short, os.path.join(disk, 'MODIMG'))
                with open(os.path.join(disk, 'SVC'), 'wb') as f:
                    f.write(svc)
                with open(os.path.join(disk, 'SVC.inf'), 'w') as f:
                    f.write(boards.inf_text('SVC', 0x1900, len(svc)))
                status, out, said, report = self.command(command, args, disk=disk, bank=13, ram=True,
                                                         before=['RUN LOADMOD MODIMG'])
                if command == 'RUN':
                    self.assertEqual((status, out, said), (0, b'', b''))
                    self.assertIn('direct16 RAM, bank 14', report)
                else:
                    self.assertEqual((status, out, said), self.expected(command, args))

    def test_the_loader_refuses_a_missing_or_short_image(self):
        loader = os.path.join(self.dir, 'LOADMOD')
        bbcrom.loader(loader)
        disk = self.disk()
        for name in ('LOADMOD', 'LOADMOD.inf'):
            shutil.copy(os.path.join(self.dir, name), disk)
        with open(os.path.join(disk, 'SHORT'), 'wb') as f:
            f.write(b'\xFF' * 0x5000)                   # a bank and a part of one
        with open(os.path.join(disk, 'EMPTY'), 'wb') as f:
            pass
        for line, said in (('RUN LOADMOD NONE', b'File not found\n'),
                           ('RUN LOADMOD SHORT', b'Not a module image (too short)\n'),
                           ('RUN LOADMOD EMPTY', b'Not a module image (too short)\n'),
                           ('RUN LOADMOD SHORT 16', b'Bad slot\n'), ('RUN LOADMOD', b'Syntax: LOADMOD IMAGE [SLOT]\n')):
            with self.subTest(line=line):
                self.assertEqual(self.command('THIRD', disk=disk, ram=True, before=[line])[0::2],
                                 (1, said))

    def test_a_modules_variables_land_in_main_ram_not_in_its_rom_bank(self):
        rom = {(e.kind, e.name): e for e in mapenv.read_map(self.maps['FIRST'])}
        calls, squares = rom['V', 'libbkd.calls'], rom['D', 'libbkd.squares']
        self.assertIsNone(calls.bank)
        self.assertLess(calls.addr, 0x8000)
        self.assertEqual((squares.bank, squares.addr), (3, 0x8050))
        windows = {e.number: e for e in rom.values() if e.kind == 'W'}
        self.assertTrue(windows[1].rom and windows[2].rom and windows[3].rom)
        self.assertFalse(windows[33].rom)
        run = {(e.kind, e.name): e for e in mapenv.read_map(os.path.join(self.dir, 'run-FIRST', 'work',
                                                                         'rfirst.map'))}
        self.assertEqual((run['V', 'libbkd.calls'].bank, run['V', 'libbkd.calls'].addr), (3, 0xBFDF))
        self.assertIn('bank  3: $8050-', self.listing)

    def test_a_status_other_than_0_is_the_mos_error(self):
        status, out, said, report = self.command('THIRD', ['fail'])
        self.assertEqual((status, out, said), (9, b'third\n', b''))
        self.assertEqual(self.expected('THIRD', ['fail']), (9, b'third\n', b''))

    def test_the_end_enters_a_language_rom_again_and_returns_where_there_is_none(self):
        for command, args in (('FIRST', FIRST_ARGS), ('SECOND', SECOND_ARGS), ('THIRD', [])):
            with self.subTest(command=command):
                want = self.expected(command, args)
                status, out, said, report = self.command(command, args, roms=[(15, self.language)])
                self.assertEqual((status, out, said), (0, want[1] + b'LANG\n', b''))
                self.assertIn('(returned)', report)
                # With none, the service call returns, claimed: no Bad command.
                self.assertEqual(self.command(command, args)[:3], want)
        # *HELP is not a tool: it returns, with or without a language.
        self.assertNotIn(b'LANG', self.command('HELP', roms=[(15, self.language)])[1])

    def test_a_command_the_module_does_not_know_is_left_unclaimed(self):
        for line in ('NOSUCH', 'FIRSTX', 'FIRS', 'SECOND.'):
            with self.subTest(line=line):
                status, out, said, report = self.command(line, bank=7)
                self.assertEqual((status, out, said), (1, b'', b'Bad command\n'))
                self.assertIn('direct16 ROM, bank 7, bank switches 2', report)
        status, out, said, report = self.command('first', FIRST_ARGS)
        self.assertEqual((status, out, said), self.expected('FIRST', FIRST_ARGS))

    def test_help(self):
        status, out, said, report = self.command('HELP', bank=11)
        self.assertEqual((status, out, said), (0, b'\nLathe\n  FIRST\n  SECOND\n  THIRD\n', b''))
        self.assertIn('direct16 ROM, bank 11, bank switches 2', report)
        self.assertEqual(self.command('HELP', ['BASIC'])[:3], (0, b'', b''))
        # Spaces after it are no argument (the emulator's MOS skips them; the module does too).
        self.assertEqual(self.command('HELP', tail='  ')[1], b'\nLathe\n  FIRST\n  SECOND\n  THIRD\n')

    def test_other_service_calls_change_nothing(self):
        """A program run with *RUN issues service calls 50 and 6 (OSBYTE 143) with the latch at
        bank 9: the module's header code returns them unclaimed, with A, X and Y as given, and the
        latch is not moved."""
        disk = self.disk()
        code = bytes([0xA9, 0x8F, 0xA2, 0x32, 0xA0, 0x5A, 0x20, 0xF4, 0xFF, 0x86, 0x70, 0x84, 0x71,
                      0xA9, 0x8F, 0xA2, 0x06, 0xA0, 0x00, 0x20, 0xF4, 0xFF, 0x60])
        with open(os.path.join(disk, 'SVC'), 'wb') as f:
            f.write(code)
        with open(os.path.join(disk, 'SVC.inf'), 'w') as f:
            f.write(boards.inf_text('SVC', 0x1900, len(code)))
        status, out, said, report = self.command('RUN', ['SVC'], disk=disk, bank=9)
        self.assertEqual((status, said), (0, b''))
        self.assertIn('direct16 ROM, bank 9, bank switches 0', report)

    # ---- The image tool ---------------------------------------------------------------------

    def test_the_listing_and_the_command_line(self):
        self.assertIn('*FIRST: FIRST, ', self.listing)
        self.assertIn('banks 1, 2, 3; regions in slot 12, slot 13 (REGTEXT.BIN)', self.listing)
        self.assertIn('banks 4, 5; regions in slot 12, slot 13', self.listing)
        self.assertRegex(self.listing, r'bank  0: \$8050-\$[0-9A-F]{4} the module\'s code and tables')
        self.assertEqual(os.path.getsize(self.image), 262144)
        out = os.path.join(self.dir, 'CLI')
        done = subprocess.run([sys.executable, bbcrom.__file__, '-o', out, '--loader',
                               os.path.join(self.dir, 'LOADCLI')]
                              + ['%s=%s,%s,%s' % s for s in self.specs], capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stderr), (0, ''))
        self.assertEqual(done.stdout, self.listing.replace('MODULE:', 'CLI:', 1))
        with open(out, 'rb') as a, open(self.image, 'rb') as b:
            self.assertEqual(a.read(), b.read())
        self.assertTrue(os.path.isfile(os.path.join(self.dir, 'LOADCLI.inf')))

    def test_every_bank_begins_with_the_same_reserved_bytes(self):
        with open(self.image, 'rb') as f:
            data = f.read()
        banks = [data[n * 0x4000:(n + 1) * 0x4000] for n in range(16)]
        for n, bank in enumerate(banks):
            self.assertEqual(bank[:0x4F], banks[0][:0x4F], n)
            self.assertEqual(bank[0x4F], n)
            self.assertEqual(bank[0x07], 0x0E)
            self.assertEqual(bank[0x0E:0x12], b'\x00(C)')
            self.assertEqual(bank[0x3FE0:], b'\xFF' * 32)

    def errors(self, specs):
        with self.assertRaises(bbcrom.ImageError) as caught:
            bbcrom.image(specs, os.path.join(self.dir, 'BAD'))
        return str(caught.exception)

    def edited(self, command, change, name):
        """A copy of COMMAND's ROM environment with change(text) applied."""
        with open(self.envs[command]) as f:
            text = change(f.read())
        path = os.path.join(self.dir, name)
        with open(path, 'w') as f:
            f.write(text)
        return path

    def test_the_tools_checks(self):
        first, second, third = self.specs
        self.assertIn('bank 1 of the module is FIRST (its bank 1, FCBANK1.BIN)\'s and OTHER\'s too',
                      self.errors([first, ('OTHER',) + first[1:]]))
        self.assertIn('the command FIRST is given twice', self.errors([first, ('first',) + third[1:]]))
        env = self.edited('FIRST', lambda t: t.replace('rom       WIN 2\n', ''), 'norom.env')
        self.assertIn('bank 2 ($82) is not `rom`', self.errors([('FIRST', first[1], env)]))
        env = self.edited('FIRST', lambda t: t.replace('$8050 $BFDF', '$8000 $BFDF'), 'window.env')
        self.assertIn('the window must be $8050-$BFDF', self.errors([('FIRST', first[1], env)]))
        env = self.edited('FIRST', lambda t: t.replace('$81 FCBANK1.BIN', '$80 FCBANK1.BIN'), 'zero.env')
        self.assertIn('is bank 0 of the module ($80)', self.errors([('FIRST', first[1], env)]))
        env = self.edited('FIRST', lambda t: t.replace('bank      WIN 32 $0C', 'bank      WIN 32 $04'),
                          'slot.env')
        self.assertIn('bank 32 is slot 4, which is not sideways RAM', self.errors([('FIRST', first[1], env)]))
        env = self.edited('THIRD', lambda t: t.replace('more      data $0401 $06FF', 'more      data $0401 $07FF'),
                          'tail.env')
        self.assertIn('takes $0700-$07FF', self.errors([('THIRD', third[1], env)]))
        self.assertIn('a command is a capital letter', self.errors([('2ND',) + third[1:]]))
        # Too much: thirteen programs of 21,248 bytes each, no bank of their own.
        big = os.path.join(self.dir, 'BIG')
        with open(big, 'wb') as f:
            f.write(b'\xEA' * (0x6C00 - 0x1900))
        text = self.errors([('T%d' % n, big, third[2]) for n in range(13)])
        self.assertIn('do not fit in the banks the programs leave free', text)


class RomEnv(unittest.TestCase):
    """bbcrom.rom_env: the ROM form's environment defines ROMFORM as 1, and its `when ROMFORM`
    and `unless ROMFORM` entries choose what differs between the forms."""
    DEV = ('cpu       6502\nzeropage  $00 $8F\ndefine    ROMFORM 0     ; bbcrom.rom_env makes it 1\n'
           'unless    ROMFORM code $1900 $519F\nunless    ROMFORM data $51A0 $7BFF\n'
           'when      ROMFORM code $1900 $4FFF\nwhen      ROMFORM data $5000 $7BFF\n'
           'exit      return $0400\noutput    raw\n; a comment\nwindow    WIN $8000 $BFDF\n'
           'switch    WIN bank farcall\nbank      WIN 1 $81 X1.BIN\nbank      WIN 32 $0C\n'
           'place     m WIN 1\nwhen      ROMFORM place bbcfs WIN 1   ; fixed in the developer\'s form\n'
           'place     n WIN 1\nfarcall   rt_bbc\n')

    def test_the_forms(self):
        with tempfile.TemporaryDirectory() as d:
            dev, rom = os.path.join(d, 'dev.env'), os.path.join(d, 'rom.env')
            with open(dev, 'w') as f:
                f.write(self.DEV)
            self.assertEqual(bbcrom.rom_env(dev, rom, 6), 7)
            with open(rom) as f:
                text = f.read()
            self.assertEqual(text, self.DEV.replace('ROMFORM 0     ;', 'ROMFORM 1     ;')
                             .replace('$8000 $BFDF', '$8050 $BFDF').replace('$81 X1.BIN', '$86 X1.BIN')
                             + 'rom       WIN 1\n')
            a, b = mapenv.read_env(dev), mapenv.read_env(rom)
        self.assertEqual((a.code, a.data, a.places, a.defines[0]),
                         ((0x1900, 0x519F), (0x51A0, 0x7BFF), ['m', 'n'], ('ROMFORM', 0)))
        self.assertEqual((b.code, b.data, b.places, b.defines[0]),
                         ((0x1900, 0x4FFF), (0x5000, 0x7BFF), ['m', 'bbcfs', 'n'], ('ROMFORM', 1)))

    def test_the_tools_environments(self):
        # The compiler's and the linker's: bbcfs is placed in the ROM form only, and the
        # compiler's split differs.
        for name, dev_split, rom_split in (('lathec-bbc.env', 0x57A0, 0x4F00), ('linker-bbc.env', 0x4000, 0x4000)):
            with self.subTest(env=name), tempfile.TemporaryDirectory() as d:
                rom = os.path.join(d, name)
                bbcrom.rom_env(os.path.join(ROOT, 'lathe', 'src', name), rom)
                a, b = mapenv.read_env(os.path.join(ROOT, 'lathe', 'src', name)), mapenv.read_env(rom)
                self.assertEqual((a.data[0], b.data[0]), (dev_split, rom_split))
                self.assertNotIn('bbcfs', a.places)
                self.assertEqual(set(b.places) - set(a.places), {'bbcfs'})
                self.assertEqual((dict(a.defines)['ROMFORM'], dict(b.defines)['ROMFORM']), (0, 1))


if __name__ == '__main__':
    unittest.main()
