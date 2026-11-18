"""The 128 KB module: eight banks of 16 KB in one EPROM, scheme direct8 (a read of $BFF0+n selects
bank n, 0 to 7; $BFF8-$BFFF mirror them), on the emulated BBC Model B+128 (lathe/docs/bbc.md,
"The 128 KB module").

The machinery, which works today:

- bbcrom.layout() on made-up programs: the module's code and tables in the home bank after the
  code there, the resident parts and region constants in pieces in the ends of the banks, the
  bytes over when they do not fit;
- test_bbc_rom.py's three programs in an eight-bank image, their banks numbered from 0, so that
  bank 0 holds *FIRST's code and the module's own code is in another bank: each command from the
  ROM, in every power-on bank, through LOADMOD in the RAM form (whole and short), and the
  loader's refusal of an image larger than the module;
- the compiler alone in an eight-bank image (lathe/src/lathec-bbc.env, banks 0 to 4), which
  compiles a program from the ROM and through LOADMOD as the host compiler does.

The gate: both tools in the eight-bank image, the compiler in banks 0 to 4 and the linker in 5 to
7 (linker-bbc.env's `when ROM128` entries). Its message says by how many bytes they are over, in
all and bank by bank, if they do not fit; LATHE_BBC_ROM128_REPORT=1 prints the whole account. The
texts of the errors are in the image, after the module's code, and the module writes them
(lathe/docs/bbc.md, "The texts in the module"). The same image runs the tool chain on two small
programs, every text the module writes, and both tools' errors with nothing on the disc (and the
number alone when no ROM answers the call for the text); with LATHE_BBC_ROM128_SELFHOST=1 the compiler
compiles itself from it, with LATHE_BBC_ROM128_SELFLINK=1 the linker links the compiler, with
LATHE_BBC_ROM128_LOOP=1 the rebuild loop runs, and with LATHE_BBC_ROM128_ADFS=1 the rebuild loop
runs on two ADFS discs from the image built with ADFS's names and PAGE (BBCFS 2, ADFS 1): the
build the owner will use.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402
import bbcrom  # noqa: E402
import boards  # noqa: E402
import test_bbc_rom as tbr  # noqa: E402

BOARD = boards.BOARDS['bbc']
HAVE_TOOLS = tbr.HAVE_TOOLS


def program(command, codes, resident, slots=(), load=0x1900):
    """A made-up bbcrom.Program: code banks {n: bytes}, a resident part of `resident` bytes, and
    region constants [(slot, bytes)]."""
    p = bbcrom.Program(command, command, command + '.env', load=load, resident=bytes([0xEA]) * resident)
    for i, (n, size) in enumerate(sorted(codes.items())):
        b = bbcrom.Bank(i + 1, 0x80 + n, f'{command}{i + 1}.BIN', True)
        b.data = bytes([n]) * size
        p.banks.append(b)
    for slot, size in slots:
        b = bbcrom.Bank(32 + slot, slot, f'{command}S{slot}.BIN')
        b.data = bytes([0x55]) * size
        p.banks.append(b)
    return p


ROOM = bbcrom.ROOM                             # a bank's room for code, $8050-$BFDF
TAIL = bbcrom.TOP - bbcrom.FIRST + 1           # and for pieces, to $BFEF


class Layout(unittest.TestCase):
    def pieces(self, lay, what):
        return [e for e in lay.placed if e[0] == what]

    def test_the_home_bank_is_0_when_no_program_has_code_there(self):
        lay = bbcrom.layout([program('A', {1: 1000, 2: 2000}, 3000)], 8)
        self.assertEqual((lay.home, lay.home_at), (0, bbcrom.FIRST))
        lay = bbcrom.layout([program('A', {1: 1000, 2: 2000}, 3000)], 16)
        self.assertEqual((lay.home, lay.home_at), (0, bbcrom.FIRST))

    def test_with_a_program_in_bank_0_the_home_bank_has_the_most_room(self):
        lay = bbcrom.layout([program('A', {n: 11000 - 100 * n for n in range(8)}, 3000)], 8)
        self.assertEqual((lay.home, lay.home_at), (7, bbcrom.FIRST + 10300))

    def test_the_pieces_fill_the_ends_of_the_code_banks_to_bfef(self):
        codes = {n: 11000 for n in range(8)}
        lay = bbcrom.layout([program('A', codes, 9000, slots=[(13, 3000)])], 8)
        pieces = self.pieces(lay, 'A resident') + self.pieces(lay, 'A slot 13 (AS13.BIN)')
        self.assertEqual(sum(len(e[3]) for e in pieces), 12000)
        for what, bank, addr, data, unit, dest in pieces:
            self.assertGreaterEqual(addr, bbcrom.FIRST + 11000)
            self.assertLessEqual(addr + len(data) - 1, bbcrom.TOP)
            if bank == lay.home:
                self.assertGreaterEqual(addr, lay.home_at + len(lay.code))
        # Each piece goes where its part of the program goes, in order.
        resident = sorted(self.pieces(lay, 'A resident'), key=lambda e: e[5])
        self.assertEqual(resident[0][5], 0x1900)
        for a, b in zip(resident, resident[1:]):
            self.assertEqual(a[5] + len(a[3]), b[5])

    def test_the_sixteen_bank_image_keeps_its_layout_unless_asked(self):
        """Sixteen banks: the pieces in bank 0 to $BFDF, then in the banks no program uses, as
        before the eight-bank image; with tails, in the ends of the code banks first."""
        programs = [program('A', {n: 12000 for n in range(1, 6)}, 20000)]
        lay = bbcrom.layout(programs, 16)
        self.assertEqual(sorted({e[1] for e in lay.placed}), [0, 6])
        self.assertLessEqual(max(e[2] + len(e[3]) - 1 for e in lay.placed if e[1] == 0), bbcrom.LAST)
        lay = bbcrom.layout(programs, 16, tails=True)
        self.assertNotIn(6, {e[1] for e in lay.placed})
        self.assertTrue({1, 2, 3, 4, 5} & {e[1] for e in lay.placed})

    def test_the_texts_go_in_parts_where_no_bank_holds_them_whole(self):
        """With 13,000 bytes of code in each of the eight banks no bank has room for the texts of
        the errors whole (3.7 KB with their code): they go in two parts, each whole in a bank of
        its own, in the room after the code, together every text from 0 to 255. With room for
        them, one part, in the home bank."""
        lay = bbcrom.layout([program('A', {n: 13000 for n in range(8)}, 100)], 8)
        self.assertEqual(len(lay.parts), 2)
        self.assertEqual([(p[0], p[1]) for p in lay.parts], [(0, lay.parts[1][0] - 1), (lay.parts[1][0], 255)])
        self.assertNotEqual(lay.parts[0][2], lay.parts[1][2])
        for first, last, bank, addr, data in lay.parts:
            self.assertGreaterEqual(addr, bbcrom.FIRST + 13000)
            self.assertLessEqual(addr + len(data) - 1, bbcrom.TOP)
        lay = bbcrom.layout([program('A', {n: 11000 for n in range(8)}, 100)], 8)
        self.assertEqual([(p[0], p[1], p[2]) for p in lay.parts], [(0, 255, lay.home)])
        self.assertEqual(lay.parts[0][3], lay.home_at + len(lay.code))
        lay = bbcrom.layout([program('A', {n: 11000 for n in range(8)}, 100)], 8, parts=3)
        self.assertEqual(len(lay.parts), 3)

    def test_the_bytes_over(self):
        """Eight banks of code leave 8 * (TAIL - 11000) bytes; the module's code and tables, the
        texts of the errors (4 KB, in one part here) and its eight entries a piece take some of it;
        what does not fit is the error's .over."""
        codes = {n: 11000 for n in range(8)}
        room = 8 * (TAIL - 11000)
        lay = bbcrom.layout([program('A', codes, 100)], 8)
        code = len(lay.code) + sum(len(part[4]) for part in lay.parts)
        fits = room - code - 7 * bbcrom.ENTRY      # eight pieces: the first entry is in `code`
        lay = bbcrom.layout([program('A', codes, fits)], 8)
        self.assertEqual(sum(a[2] - a[1] + 1 for a in lay.areas), 0)
        with self.assertRaises(bbcrom.ImageError) as caught:
            bbcrom.layout([program('A', codes, fits + 50)], 8)
        self.assertEqual(caught.exception.over, 50)
        self.assertIn('50 bytes over', str(caught.exception))

    def test_a_bank_past_the_image_or_bank_0_of_sixteen_is_refused_by_rom_env(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'a.env')
            with open(src, 'w') as f:
                f.write('window WIN $8000 $BFDF\n' + ''.join(f'bank WIN {n} $8{n} A{n}.BIN\n' for n in range(1, 5)))
            self.assertEqual(bbcrom.rom_env(src, os.path.join(d, 'b.env'), 4, 8), 8)
            with self.assertRaises(bbcrom.ImageError) as caught:
                bbcrom.rom_env(src, os.path.join(d, 'b.env'), 5, 8)
            self.assertIn('no bank of the module is left for its bank 4 (an image has 8)', str(caught.exception))

    def test_rom_env_sets_rom128_and_numbers_conditional_banks(self):
        dev = ('define ROMFORM 0\ndefine ROM128 0\nwindow WIN $8000 $BFDF\n'
               'bank WIN 1 $81 A1.BIN\nunless ROM128 bank WIN 2 $82 A2.BIN\nwhen ROM128 bank WIN 3 $83 A3.BIN\n'
               'bank WIN 4 $84 A4.BIN\n')
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'a.env')
            with open(src, 'w') as f:
                f.write(dev)
            out = os.path.join(d, 'b.env')
            self.assertEqual(bbcrom.rom_env(src, out, 0, 8), 3)
            with open(out) as f:
                text = f.read()
            self.assertIn('define ROM128 1\n', text)
            self.assertIn('define ROMFORM 1\n', text)
            self.assertIn('unless ROM128 bank WIN 2 $82 A2.BIN\n', text)   # not an entry there: as it was
            self.assertIn('bank      WIN 3 $81 A3.BIN\n', text)
            self.assertIn('bank      WIN 4 $82 A4.BIN\n', text)
            self.assertEqual(re.findall(r'rom +WIN (\d+)', text), ['1', '3', '4'])
            self.assertEqual(bbcrom.rom_env(src, out, 1, 16), 4)
            with open(out) as f:
                text = f.read()
            self.assertIn('define ROM128 0\n', text)
            self.assertIn('bank      WIN 2 $82 A2.BIN\n', text)
            self.assertIn('when ROM128 bank WIN 3 $83 A3.BIN\n', text)


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class RomModule8(tbr.RomImage, unittest.TestCase):
    """test_bbc_rom.py's three programs in an image of eight banks, numbered from 0."""
    BANKS = 8
    FIRST_BANK = 0

    def test_the_image_has_eight_banks_and_bank_0_holds_code(self):
        self.assertEqual(os.path.getsize(self.image), 8 * 0x4000)
        self.assertIn('8 banks of 16 KB, scheme direct8', self.listing)
        self.assertEqual(re.findall(r'\*FIRST: .*; banks ([0-9, ]+);', self.listing), ['0, 1, 2'])
        self.assertEqual(re.findall(r'\*SECOND: .*; banks ([0-9, ]+);', self.listing), ['3, 4'])
        self.assertRegex(self.listing, r'bank  0: \$8050-\$[0-9A-F]{4} FIRST bank 1 code')
        home = re.search(r'bank  (\d): [^\n]*the module\'s code and tables', self.listing)
        self.assertNotEqual(home.group(1), '0')
        with open(self.image, 'rb') as f:
            data = f.read()
        for n in range(8):
            bank = data[n * 0x4000:(n + 1) * 0x4000]
            self.assertEqual(bank[:0x4F], data[:0x4F])
            self.assertEqual(bank[0x4F], n)
            self.assertEqual(bank[0x3FF0:], b'\xFF' * 16)

    def test_each_command_in_every_power_on_bank(self):
        for command, args in (('FIRST', tbr.FIRST_ARGS), ('SECOND', tbr.SECOND_ARGS), ('THIRD', [])):
            want = self.expected(command, args)
            for bank in range(8) if command == 'FIRST' else (0, 5):
                with self.subTest(command=command, bank=bank):
                    status, out, said, report = self.command(command, args, bank=bank)
                    self.assertEqual((status, out, said), want)
                    self.assertIn('direct8 ROM', report)
                    self.assertIn('checks: mos-memory-writes=0  romsel-mismatches=0', report)

    def test_through_the_loader_whole_and_short(self):
        bbcrom.loader(os.path.join(self.dir, 'LOADMOD'))
        for image, slot, bank in ((self.image, 4, 3), (self.short, 7, 7)):
            for command, args in (('FIRST', tbr.FIRST_ARGS), ('SECOND', tbr.SECOND_ARGS)):
                with self.subTest(image=os.path.basename(image), command=command):
                    disk = self.disk()
                    for name in ('LOADMOD', 'LOADMOD.inf'):
                        shutil.copy(os.path.join(self.dir, name), disk)
                    shutil.copy(image, os.path.join(disk, 'MODIMG'))
                    status, out, said, report = self.command(command, args, disk=disk, slot=slot, bank=bank,
                                                             ram=True, before=['RUN LOADMOD MODIMG %d' % slot])
                    self.assertEqual((status, out, said), self.expected(command, args))
                    self.assertIn('module: slot %d, direct8 RAM' % slot, report)

    def test_the_texts_in_three_parts(self):
        """The same programs' image with the texts in three parts (bbcrom.image(parts=3)), which
        the home bank enters in their banks: every text from banks 0 and 7, and through LOADMOD."""
        image = os.path.join(self.dir, 'MODPARTS')
        listing = bbcrom.image(self.specs, image, banks=self.BANKS, parts=3)
        self.assertEqual(len(re.findall(r'the texts \d+ to \d+ of the errors', listing)), 3)
        for bank in (0, 7):
            with self.subTest(bank=bank):
                self.assert_the_hosts_texts(bank=bank, image=image)
        bbcrom.loader(os.path.join(self.dir, 'LOADMOD'))
        disk = self.disk()
        for name in ('LOADMOD', 'LOADMOD.inf'):
            shutil.copy(os.path.join(self.dir, name), disk)
        shutil.copy(image, os.path.join(disk, 'MODIMG'))
        self.assert_the_hosts_texts(disk=disk, ram=True, slot=4, bank=2, before=['RUN LOADMOD MODIMG'])

    def test_the_module_writes_every_text_of_the_errors(self):
        """As test_bbc_rom.py's sixteen-bank image: from the home bank and another, and through
        LOADMOD whole and short."""
        for bank in (0, 7):
            with self.subTest(bank=bank):
                self.assert_the_hosts_texts(bank=bank)
        bbcrom.loader(os.path.join(self.dir, 'LOADMOD'))
        for image in (self.image, self.short):
            disk = self.disk()
            for name in ('LOADMOD', 'LOADMOD.inf'):
                shutil.copy(os.path.join(self.dir, name), disk)
            shutil.copy(image, os.path.join(disk, 'MODIMG'))
            self.assert_the_hosts_texts(disk=disk, ram=True, slot=4, bank=2, before=['RUN LOADMOD MODIMG'])

    def test_the_loader_refuses_an_image_larger_than_the_module(self):
        bbcrom.loader(os.path.join(self.dir, 'LOADMOD'))
        disk = self.disk()
        for name in ('LOADMOD', 'LOADMOD.inf'):
            shutil.copy(os.path.join(self.dir, name), disk)
        with open(self.image, 'rb') as f, open(os.path.join(disk, 'NINE'), 'wb') as g:
            g.write(f.read() + b'\xFF' * 0x4000)
        status, out, said, report = self.command('FIRST', disk=disk, ram=True, before=['RUN LOADMOD NINE'])
        self.assertEqual((status, said), (1, b'Image too large for the module\n'))

    def test_bank_8_is_past_the_image(self):
        with open(self.envs['FIRST']) as f:
            text = f.read()
        path = os.path.join(self.dir, 'eight.env')
        with open(path, 'w') as f:
            f.write(text.replace('$80 ', '$88 ', 1))
        with self.assertRaises(bbcrom.ImageError) as caught:
            bbcrom.image([('FIRST', self.specs[0][1], path)], os.path.join(self.dir, 'BAD'), banks=8)
        self.assertIn('a bank of the module is $80 to $87', str(caught.exception))


# ---- The tools in eight banks ---------------------------------------------------------------

REPORT = os.environ.get('LATHE_BBC_ROM128_REPORT') == '1'
SELFHOST = os.environ.get('LATHE_BBC_ROM128_SELFHOST') == '1'
SELFLINK = os.environ.get('LATHE_BBC_ROM128_SELFLINK') == '1'
LOOP = os.environ.get('LATHE_BBC_ROM128_LOOP') == '1'
ADFS = os.environ.get('LATHE_BBC_ROM128_ADFS') == '1'
BANKS = 8
JUDGED = os.path.join(HERE, 'lk_judged.py')
# The tools, the first bank of each, as test_bbc_toolchain.build_image has them.
TOOLS = (('LATHE', 'lathec.lth', 'lathec-bbc.env', 0), ('LLINK', 'link.lth', 'linker-bbc.env', 5))


class scheme:
    """boards.run_module's scheme, direct8, while it is in force."""
    def __enter__(self):
        self.saved = boards.MODULE_SCHEME
        boards.MODULE_SCHEME = bbcrom.SCHEMES[BANKS]

    def __exit__(self, *exc):
        boards.MODULE_SCHEME = self.saved


def read_judged(path):
    """lk_judged.py's notes of one link: ({bank index: (judged, placed, modules)}, fixed bytes)."""
    banks, fixed = {}, 0
    with open(path) as f:
        for line in f:
            m = re.match(r'bank (\d+): judged (\d+) placed (\d+)  (.*)$', line)
            if m:
                banks[int(m.group(1))] = (int(m.group(2)), int(m.group(3)), m.group(4))
            elif line.startswith('fixed '):
                fixed = sum(int(w.rsplit(' ', 1)[1]) for w in line[6:].strip().split(', ') if w)
    return banks, fixed


def build_tools(out_dir, tools=None):
    """Each tool linked for the eight-bank image (bbcrom.rom_env with eight banks, from its first
    bank), by lk_judged.py: [(command, resident, its ROM environment, its map, the link's error or
    None, the judged notes)]. A tool that does not link is still measured."""
    import build
    out = []
    for command, source, env, first in tools or TOOLS:
        d = os.path.join(out_dir, command.lower())
        os.makedirs(d)
        rom = os.path.join(d, env)
        bbcrom.rom_env(os.path.join(support.SRC, env), rom, first, BANKS)
        resident = os.path.join(d, command)
        notes = os.path.join(d, 'judged')
        saved, os.environ['LK_JUDGED_OUT'] = build.LINKER, notes
        build.LINKER = JUDGED
        error = None
        try:
            build.build(os.path.join(support.SRC, source), resident, env=rom, keep=os.path.join(d, 'work'))
        except build.BuildError as e:
            error = str(e).strip().splitlines()[-1]
        finally:
            build.LINKER = saved
            del os.environ['LK_JUDGED_OUT']
        out.append((command, resident, rom, os.path.join(d, 'work', os.path.splitext(source)[0] + '.map'),
                    error, read_judged(notes)))
    return out


class Account:
    """What the tools take of the eight-bank image, from their links' notes (so also for a tool
    that does not link yet): each bank's code as the linker judges it and as placed, the resident
    parts and region constants, and what bbcrom.layout() makes of them."""

    def __init__(self, tools):
        self.rows = {}              # image bank -> (command, judged, placed, modules)
        self.parts = []             # (what, bytes) of what is copied
        self.errors = [(t[0], t[4]) for t in tools if t[4]]
        programs = []
        for command, resident, rom, map_path, error, (notes, fixed) in tools:
            p = bbcrom.Program(command, resident, rom, load=0x1900, resident=bytes(fixed))
            p.top = bbcrom.memory_top(rom)      # every image checks HIMEM (bbcrom.image)
            _, _, banks = bbcrom.read_env_banks(rom)
            for i, b in enumerate(banks, 1):
                judged, placed, modules = notes.get(i, (0, 0, ''))
                b.data = bytes(placed)
                if b.value & 0x80:
                    self.rows[b.value & 0x7F] = (command, judged, placed, modules)
                    p.banks.append(b)
                elif b.file:
                    self.parts.append((f'{command} slot {b.value} constants', placed))
                    p.banks.append(b)
            self.parts.append((f'{command} resident part', fixed))
            programs.append(p)
        self.over_banks = {n: max(0, r[1] - bbcrom.ROOM) for n, r in self.rows.items()}
        self.in_use = sum(r[2] for r in self.rows.values()) + sum(n for _, n in self.parts)
        self.room = BANKS * (bbcrom.TOP - bbcrom.FIRST + 1)
        try:
            self.layout = bbcrom.layout(programs, BANKS)
            self.over_image = 0
            self.module = len(self.layout.code)
        except bbcrom.ImageError as e:
            self.layout = None
            self.over_image = e.over
            self.module = None

    def fits(self):
        return not self.errors and self.over_image == 0 and not any(self.over_banks.values())

    def summary(self):
        banks = ', '.join(f'bank {n} {o}' for n, o in sorted(self.over_banks.items()) if o)
        return (f'the tools are {self.over_image} bytes over the 128 KB image (in use {self.in_use} '
                f'of {self.room}, with the module\'s code and the copy entries on top); '
                f'banks over as the linker judges them: {banks or "none"} '
                f'({sum(self.over_banks.values())} bytes in all)')

    def text(self):
        lines = ['The 128 KB image: eight banks, $8050-$BFDF for code (16,272 bytes), to $BFEF for '
                 'what is copied (16,288)', '']
        lines.append('%-5s %-6s %7s %7s %6s %6s  %s' % ('bank', 'tool', 'judged', 'placed', 'over', 'end',
                                                        'modules (judged/placed)'))
        for n in range(BANKS):
            command, judged, placed, modules = self.rows.get(n, ('-', 0, 0, ''))
            lines.append('%-5d %-6s %7d %7d %6d %6d  %s' % (n, command, judged, placed, self.over_banks.get(n, 0),
                                                            bbcrom.TOP - bbcrom.FIRST + 1 - placed, modules))
        lines.append('')
        for what, n in self.parts:
            lines.append(f'{what}: {n} bytes')
        code = sum(r[2] for r in self.rows.values())
        lines.append(f'code banks as placed: {code}; copied: {sum(n for _, n in self.parts)}; '
                     f'in use: {self.in_use} of {self.room}')
        if self.layout:
            lines.append(f'the module\'s code and tables: {self.module} bytes, in bank {self.layout.home}; '
                         f'{len(self.layout.placed)} pieces; free: {sum(a[2] - a[1] + 1 for a in self.layout.areas)}')
        lines.append(self.summary())
        for command, error in self.errors:
            lines.append(f'{command} does not link: {error}')
        return '\n'.join(lines) + '\n'


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class Rom128(unittest.TestCase):
    """Both tools in the eight-bank image: the gate."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-rom128-')
        cls.tools = build_tools(cls.dir)
        cls.account = Account(cls.tools)
        cls.image = None
        if cls.account.fits():
            cls.image = os.path.join(cls.dir, 'MODULE')
            bbcrom.image([t[:4] for t in cls.tools], cls.image, os.path.join(cls.dir, 'listing'),
                         short=cls.image + '.short', banks=BANKS)
            bbcrom.loader(os.path.join(cls.dir, 'LOADMOD'))
        if REPORT:
            print('\n' + cls.account.text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_account_holds_every_byte(self):
        """The account's numbers are the links' own: the compiler's banks are 0 to 4, the
        linker's 5 to 7, and the parts copied are the resident parts (the compiler's messages,
        which were copied to slot 13, are the module's)."""
        self.assertEqual(sorted(self.account.rows), list(range(8)))
        self.assertEqual({r[0] for n, r in self.account.rows.items() if n < 5}, {'LATHE'})
        self.assertEqual({r[0] for n, r in self.account.rows.items() if n >= 5}, {'LLINK'})
        self.assertEqual([w for w, n in self.account.parts], ['LATHE resident part', 'LLINK resident part'])
        self.assertFalse([c for c, e in self.account.errors if c == 'LATHE'])

    def test_both_tools_fit_the_128k_image(self):
        """lathe/docs/bbc.md, "The 128 KB module": the message, if not, says by how much."""
        self.assertTrue(self.account.fits(), self.account.summary())

    def test_errors_from_the_128k_image(self):
        """Both tools' errors with nothing on the disc: the host's, their texts from the module;
        the number alone when no ROM claims the call (test_bbc_texts.py)."""
        self.need_image()
        import test_bbc_texts
        with scheme():
            test_bbc_texts.check_runs(self, self.image, self.dir)

    def test_errors_from_the_128k_image_with_the_texts_in_three_parts(self):
        """The same with the texts in three parts in other banks (bbcrom.image(parts=3)), which
        the home bank enters there: error 5, raised inside lex's `with STRING` (sideways slot 13),
        among them."""
        self.need_image()
        import test_bbc_texts
        image = os.path.join(self.dir, 'MODPARTS')
        listing = bbcrom.image([t[:4] for t in self.tools], image, banks=BANKS, parts=3)
        self.assertEqual(len(re.findall(r'the texts \d+ to \d+ of the errors', listing)), 3)
        work = tempfile.mkdtemp(dir=self.dir)
        with scheme():
            test_bbc_texts.check_runs(self, image, work)

    def need_image(self):
        if self.image is None:
            self.skipTest('the tools do not fit the 128 KB image yet: ' + self.account.summary())

    def test_the_tool_chain_from_the_128k_image(self):
        self.need_image()
        import test_bbc_toolchain as chain
        with scheme():
            for case in [c for c in chain.corpus() if c[0] in ('hello', 'farcall')]:
                name, source, _, _, banked = case
                with self.subTest(program=name):
                    disk, compiles, link, files, said, load = chain.prepare(case, os.path.join(self.dir, name))
                    lines = chain.bbc_lines(compiles, link, load, len(files[link[2]]))
                    status, out, mos, written, cycles, traffic = chain.bbc_run(self.image, disk, lines,
                                                                               ram=banked)
                    self.assertEqual((status, mos), (0, b''))
                    with open(os.path.splitext(source)[0] + '.expected.out', 'rb') as f:
                        self.assertEqual(out, f.read())
                    self.assertEqual(sorted(written), sorted(files))
                    for f in files:
                        self.assertTrue(written[f] == files[f], f + ' differs')

    @unittest.skipUnless(SELFHOST, 'LATHE_BBC_ROM128_SELFHOST=1 has the compiler compile itself from it')
    def test_the_compiler_compiles_itself_from_the_128k_image(self):
        self.need_image()
        cycles = compile_modules(self, self.image, ('rom', 'loader'), selfhost_modules())
        print('\nthe self-compile from the 128 KB image: %d cycles in the ROM form, %d through LOADMOD' % (
            sum(c['rom'] for c in cycles.values()), sum(c['loader'] for c in cycles.values())))

    @unittest.skipUnless(SELFLINK, 'LATHE_BBC_ROM128_SELFLINK=1 has the linker link the compiler from it')
    def test_the_linker_links_the_compiler_from_the_128k_image(self):
        self.need_image()
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as chain
        with scheme():
            name, source, env = selflink.TOOLS[0]
            work = os.path.join(self.dir, 'link-' + name)
            disk, compiles, link, files = selflink.prepare(name, source, env, work)
            for f in files:
                if f.endswith('.lo'):
                    shutil.copy(os.path.join(work, 'host', f), disk)
            lines = [boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE])]
            status, out, mos, written, cycles, traffic = chain.bbc_run(self.image, disk, lines)
            self.assertEqual((status, out, mos), (0, b'', b''))
            print('\nthe linker links the compiler from the 128 KB image: %d cycles' % cycles)
            expected = selflink.link_outputs(files)
            self.assertEqual(sorted(written), sorted(expected))
            for f in expected:
                self.assertTrue(written[f] == expected[f], f + ' differs')

    @unittest.skipUnless(LOOP, 'LATHE_BBC_ROM128_LOOP=1 has the compiler rebuild itself from it')
    def test_the_compiler_rebuilds_itself_from_the_128k_image(self):
        self.need_image()
        import test_bbc_selflink as selflink
        import test_bbc_toolchain as chain
        import mapenv
        with scheme():
            work = os.path.join(self.dir, 'loop')
            disk, compiles, link, files = selflink.prepare('lathec', 'lathec.lth', chain.COMPILER_ENV, work)
            image = link[2]
            again = [args for args in compiles if os.path.splitext(args[-2])[0] in selflink.LOOP_AGAIN]
            lines = [boards.module_command('LATHE', args) for args in compiles]
            lines.append(boards.module_command('LLINK', ['@' + selflink.COMMAND_FILE]))
            load = mapenv.read_env(chain.COMPILER_ENV).code[0]
            lines += ['LOAD %s %X' % (image, load), 'SAVE %s %X +%X %X' % (image, load, len(files[image]), load)]
            lines += [boards.module_command('RUN', [image] + args) for args in again]
            status, out, mos, written, cycles, traffic = selflink.run_long(self.image, disk, lines)
            self.assertEqual((status, mos, out), (0, b'', b''))
            print('\nthe rebuild loop from the 128 KB image: %d cycles' % cycles)
            self.assertEqual(sorted(written), sorted(files))
            for f in files:
                self.assertTrue(written[f] == files[f], f + ' differs')


@unittest.skipUnless(HAVE_TOOLS and ADFS, 'LATHE_BBC_ROM128_ADFS=1 runs the rebuild on two ADFS discs from it')
class Adfs128(unittest.TestCase):
    """The build the owner will use: the 128 KB image of both tools built with ADFS's names and
    PAGE (BBCFS 2, ADFS 1), the compiler in banks 0 to 4 and the linker in 5 to 7, its RAM form
    holding the image from power on (as a programmed EPROM does), doing the rebuild loop on two
    ADFS discs (test_bbc_adfs.Loop), the texts of the errors in the module."""

    def test_the_compiler_rebuilds_itself_on_two_adfs_discs_from_the_128k_image(self):
        import test_bbc_adfs as adfs
        work = tempfile.mkdtemp(prefix='lathe-bbc-rom128-adfs-loop-')
        self.addCleanup(shutil.rmtree, work, True)
        module, _ = adfs.build_image(os.path.join(work, 'image'), banks=BANKS)
        with open(os.path.join(work, 'image', 'listing')) as f:
            listing = f.read()
        self.assertEqual(re.findall(r'\*LATHE: .*; banks ([0-9, ]+);', listing), ['0, 1, 2, 3, 4'])
        self.assertEqual(re.findall(r'\*LLINK: .*; banks ([0-9, ]+);', listing), ['5, 6, 7'])
        saved, adfs.LOOP = adfs.LOOP, True          # its account is printed
        try:
            with scheme():
                cycles, report, cat = adfs.rebuild_on_two_discs(
                    self, module, work, 'the loop on two ADFS discs from the 128 KB image')
        finally:
            adfs.LOOP = saved


MAINRAM = os.path.join(HERE, 'lk_mainram.py')
ADFS_PAGE = 0x1F00
ADFS_ROOM = (0x7C00 - ADFS_PAGE) + (0x0700 - 0x0401)    # $1F00-$7BFF and $0401-$06FF: 24,575
MEASURE_DATA = 0xC000                                   # the measuring link's range for variables


def adfs_main_ram(out_dir, tools=None):
    """What each tool needs of main RAM in the eight-bank ROM form at ADFS's PAGE with BBCFS 2
    (test_bbc_adfs.adfs_env, then bbcrom.rom_env with eight banks): linked by lk_mainram.py, which
    lets a bank be over as judged, with the code from $1F00 to $7BFF and the variables in
    $C000-$FFFF (and `more data`), so that the map shows all of it wherever it would not fit.
    [(command, fixed code, constants and stubs, variables, free of the 24,575 bytes or, when
    negative, how far over, banks over as judged)]. The free figure is of the bytes, not of the
    split: a split is still to be chosen, and a large table cannot be broken across ranges."""
    import build
    import test_bbc_adfs as adfs
    import test_bbc_selfhost as selfhost
    found = []
    for command, source, env, first in tools or TOOLS:
        d = os.path.join(out_dir, 'adfs-' + command.lower())
        os.makedirs(d)
        dev = adfs.adfs_env(os.path.join(support.SRC, env), os.path.join(d, 'dev.env'))
        rom = os.path.join(d, env)
        bbcrom.rom_env(dev, rom, first, BANKS)
        with open(rom) as f:
            lines = [l for l in f if not re.match(r'(?i)^((when|unless)\s+\w+\s+)*(code|data)\s', l)]
        lines.insert(0, 'code      $%04X $7BFF\ndata      $%04X $FFFF\n' % (ADFS_PAGE, MEASURE_DATA))
        with open(rom, 'w') as f:
            f.write(''.join(lines))
        notes = os.path.join(d, 'over')
        open(notes, 'w').close()
        saved, os.environ['LK_MAINRAM_OUT'] = build.LINKER, notes
        build.LINKER = MAINRAM
        try:
            build.build(os.path.join(support.SRC, source), os.path.join(d, command), env=rom,
                        keep=os.path.join(d, 'work'))
        finally:
            build.LINKER = saved
            del os.environ['LK_MAINRAM_OUT']
        items = [i for i in selfhost.read_map(os.path.join(d, 'work', os.path.splitext(source)[0] + '.map'))
                 if i[4] is None]
        code = max(i[1] + i[2] for i in items if i[0] in 'FTD' and ADFS_PAGE <= i[1] < 0x8000) - ADFS_PAGE
        data = [i[1] + i[2] for i in items if i[0] in 'VS' and i[1] >= MEASURE_DATA]
        more = [i[1] + i[2] for i in items if i[0] in 'VS' and 0x0401 <= i[1] < 0x0800]
        variables = (max(data) - MEASURE_DATA if data else 0) + (max(more) - 0x0401 if more else 0)
        with open(notes) as f:
            over = [int(l.split()[2]) for l in f if l.startswith('bank over')]
        found.append((command, code, variables, ADFS_ROOM - code - variables, over))
    return found


def adfs_text(rows):
    lines = ['Main RAM at ADFS\'s PAGE ($1F00), the eight-bank ROM form, BBCFS 2 (of 24,575 bytes):']
    for command, code, variables, free, over in rows:
        lines.append('  %s: code, constants and stubs %d, variables %d: %s%s' % (
            command, code, variables, ('%d free' % free) if free >= 0 else ('%d bytes over' % -free),
            ('; banks over as judged: ' + ', '.join(str(o) for o in over)) if over else ''))
    return '\n'.join(lines) + '\n'


@unittest.skipUnless(HAVE_TOOLS and REPORT, 'LATHE_BBC_ROM128_REPORT=1 gives the ADFS account')
class AdfsMainRam(unittest.TestCase):
    """The build the owner will use, a 128 KB EPROM and ADFS discs: each tool's main RAM in the
    eight-bank ROM form at ADFS's PAGE, with BBCFS 2. A report: neither tool fits the eight banks
    yet (Rom128), so this says what main RAM they would need when they do."""

    def test_main_ram_at_adfs_page(self):
        d = tempfile.mkdtemp(prefix='lathe-bbc-rom128-adfs-')
        self.addCleanup(shutil.rmtree, d, True)
        rows = adfs_main_ram(d)
        self.assertEqual([r[0] for r in rows], ['LATHE', 'LLINK'])
        print('\n' + adfs_text(rows))


def selfhost_modules():
    import test_src_selfhost
    return test_src_selfhost.MODULES


def compile_modules(case, image, forms, modules):
    """The compiler from `image` (ROM, or the RAM form through LOADMOD) compiles each module as
    test_bbc_selfhost.py has it, and writes what the host compiler writes. Returns {module:
    {form: cycles}}."""
    import memory_report
    import test_bbc_selfhost as bbc_selfhost
    import test_src_selfhost
    cycles = {}
    with scheme():
        for form in forms:
            for name in modules:
                options = tuple(memory_report.options_of(os.path.join(support.SRC, name + '.lth')))
                disk, host = test_src_selfhost.prepare(
                    name, os.path.join(case.dir, 'work-%s-%s' % (form, name)), options)
                got = bbc_selfhost.report_run(form, image, disk, list(options) + [name + '.lth', '.'])
                cycles.setdefault(name, {})[form] = got[4]
                with case.subTest(form=form, module=name):
                    case.assertEqual(got[:3], (host[0], host[1] + host[2], b''))
                    case.assertEqual(sorted(got[3]), sorted(host[3]))
                    for f in host[3]:
                        case.assertTrue(got[3][f] == host[3][f], f + ' differs')
    return cycles


@unittest.skipUnless(HAVE_TOOLS, 'compiler or emulator missing')
class Compiler8(unittest.TestCase):
    """The compiler alone in an eight-bank image, its banks 0 to 4, so that bank 0 holds its
    code and the module's own code is in another bank: it compiles modules of lathe/src from the
    ROM and through LOADMOD as the host compiler does (all of them with
    LATHE_BBC_ROM128_SELFHOST=1)."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-rom128c-')
        cls.tools = build_tools(cls.dir, TOOLS[:1])
        cls.image = os.path.join(cls.dir, 'MODULE')
        cls.listing = bbcrom.image([t[:4] for t in cls.tools], cls.image, os.path.join(cls.dir, 'listing'),
                                   banks=BANKS)
        bbcrom.loader(os.path.join(cls.dir, 'LOADMOD'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_its_banks_are_0_to_4(self):
        self.assertEqual(re.findall(r'\*LATHE: .*; banks ([0-9, ]+);', self.listing), ['0, 1, 2, 3, 4'])
        self.assertRegex(self.listing, r'bank  0: \$8050-\$[0-9A-F]{4} LATHE bank 1 code')
        self.assertIn('8 banks of 16 KB, scheme direct8', self.listing)

    def test_it_compiles_as_the_host_does(self):
        import test_src_selfhost
        modules = selfhost_modules() if SELFHOST else test_src_selfhost.QUICK[:3]
        cycles = compile_modules(self, self.image, ('rom', 'loader'), modules)
        if REPORT:
            print('\nthe compiler alone, eight banks: cycles of each compile')
            for name, c in cycles.items():
                print('  %-9s rom %12d  loader %12d' % (name, c['rom'], c['loader']))

    def test_its_start_up(self):
        with scheme(), tempfile.TemporaryDirectory() as d:
            code, out, err, cycles = boards.run_module(BOARD, self.image, d, 'LATHE', raw=True)
        self.assertIn(b'usage: lathec', out)
        if REPORT:
            print('\n*LATHE with no arguments, the compiler alone in eight banks: %d cycles' % cycles)


if __name__ == '__main__':
    unittest.main()
