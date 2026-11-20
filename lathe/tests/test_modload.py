"""MODLOAD, the developer's loader of the tools' module, in Lathe (lathe/src/modload.lth;
lathe/docs/bbc.md, "The developer's cycle"), and bbcrom.py's whole layout, which it loads.

- bbcrom.layout(..., whole=True) on made-up programs: the home bank after every program's banks,
  its code at $8050, each resident part whole in a bank of its own after it, one copy entry of a
  whole bank each; region constants refused.
- On the emulated B+128 with ADFS (PAGE $1F00, ADFS's names) and the module's RAM form empty at
  power on: both tools in their eight-bank ROM forms (BBCFS 2, ADFS 1, what the developer's
  machine runs), their link outputs, the home bank (bbcrom.py --whole --home) and MODLOAD on the
  disc; `*RUN MODLOAD HOME ENV MAP IMAGE ENV MAP IMAGE` loads them, and then `*LATHE` compiles a
  module as the host's compiler does, and `*LLINK` gives the host linker's usage. What MODLOAD
  writes is the whole image bbcrom.py makes of the same files, bank for bank (the emulator's
  --bbc-module-dump). The whole cycle, every module of both tools compiled, linked and loaded on
  the BBC, waits for the owner's choice of discs (bbc.md, "The developer's cycle").
- MODLOAD's checks: a bank file of another size than its map gives, an image of another length,
  a home bank of another number, a missing file: each refused with its message and Exit 2, the
  module left byte for byte as the load before it left it.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402
import bbcfs  # noqa: E402
import bbcrom  # noqa: E402
import boards  # noqa: E402
import build  # noqa: E402

HAVE_TOOLS = os.path.isfile(support.EMULATOR) and os.path.isfile(build.COMPILER)
MODLOAD_ENV = os.path.join(support.SRC, 'modload-bbc.env')
TOOLS = (('LATHE', 'lathec'), ('LLINK', 'linker'))


def program(command, codes, resident, slots=()):
    """A made-up bbcrom.Program (test_bbc_rom128.program's)."""
    import test_bbc_rom128
    return test_bbc_rom128.program(command, codes, resident, slots)


class WholeLayout(unittest.TestCase):
    def test_the_home_bank_after_the_programs_and_each_resident_part_in_a_bank_of_its_own(self):
        a = program('A', {0: 14000, 1: 15000}, 9000)
        b = program('B', {2: 12000}, 7000)
        lay = bbcrom.layout([a, b], 16, whole=True)
        self.assertEqual((lay.home, lay.home_at), (3, bbcrom.FIRST))
        self.assertEqual([(e[0], e[1], e[2], len(e[3]), e[5]) for e in lay.placed],
                         [('A resident', 4, bbcrom.FIRST, 9000, 0x1900), ('B resident', 5, bbcrom.FIRST, 7000, 0x1900)])
        self.assertEqual(bbcrom.WHOLE, 0xBFEF - 0x8050 + 1)

    def test_the_home_bank_describes_the_layout_for_modload(self):
        """16 bytes at $BFE0 of the home bank: "LW", version 1, the home bank, the number of tools,
        whether the commands have a top, the command table's address and each tool's banks, a bit
        each, so that MODLOAD can load one tool into a module that is there."""
        a = program('A', {0: 14000, 1: 15000}, 9000)
        b = program('B', {2: 12000}, 7000)
        lay = bbcrom.layout([a, b], 16, whole=True)
        d = lay.descriptor
        self.assertEqual(len(d), 16)
        self.assertEqual(bbcrom.DESCRIPTOR_AT, 0xBFE0)
        self.assertEqual(d[:6], b'LW\x01\x03\x02\x00')
        table = d[6] + 256 * d[7]
        self.assertEqual(lay.code[table - lay.home_at:][:2], b'A\x00')
        self.assertEqual(list(d[8:]), [0x03, 0x00, 0x04, 0x00, 0, 0, 0, 0])
        end = max(at + len(part) for first, last, bank, at, part in lay.parts)
        self.assertLessEqual(end, bbcrom.DESCRIPTOR_AT)
        self.assertEqual(lay.areas[0], [3, end, bbcrom.DESCRIPTOR_AT - 1])

    def test_region_constants_and_too_many_banks_are_refused(self):
        with self.assertRaises(bbcrom.ImageError) as caught:
            bbcrom.layout([program('A', {0: 100}, 100, slots=[(13, 50)])], 16, whole=True)
        self.assertIn('region constants', str(caught.exception))
        with self.assertRaises(bbcrom.ImageError) as caught:
            bbcrom.layout([program('A', {n: 100 for n in range(15)}, 100)], 16, whole=True)
        self.assertIn('no bank left', str(caught.exception))


def build_modload(out_dir):
    """MODLOAD for the developer's machine: ADFS's PAGE and names. Returns its file (and .inf)."""
    import test_bbc_adfs as adfs
    os.makedirs(out_dir)
    env = adfs.adfs_env(MODLOAD_ENV, os.path.join(out_dir, 'modload.env'))
    image = os.path.join(out_dir, 'MODLOAD')
    build.build(os.path.join(support.SRC, 'modload.lth'), image, env=env, keep=os.path.join(out_dir, 'work'))
    return image


def build_tools(out_dir):
    """Both tools in their eight-bank ROM forms for ADFS (test_bbc_adfs.build_image), and the
    whole image of them in sixteen banks with its home bank: (the tools [(command, resident, ROM
    environment, map)], the whole image, the home bank's file)."""
    import test_bbc_adfs as adfs
    adfs.build_image(os.path.join(out_dir, 'eight'), banks=8)
    tools = []
    for command, _ in TOOLS:
        d = os.path.join(out_dir, 'eight', command.lower())
        source = 'lathec' if command == 'LATHE' else 'link'
        rom = [f for f in os.listdir(d) if f.endswith('.env') and f != 'dev.env'][0]
        tools.append((command, os.path.join(d, command), os.path.join(d, rom),
                      os.path.join(d, 'work', source + '.map')))
    image = os.path.join(out_dir, 'WHOLE')
    home = os.path.join(out_dir, 'HOME')
    bbcrom.image(tools, image, os.path.join(out_dir, 'listing'), banks=16, whole=True, home=home)
    return tools, image, home


def tool_files(tools):
    """{name as the tools give it on the disc: bytes} of each tool's ROM environment, map, image and
    bank files, and the arguments of MODLOAD for them."""
    files, args = {}, []
    for command, resident, rom, map_path in tools:
        stem = command.lower()
        names = (stem + '.env', stem + '.map', command)
        for name, path in zip(names, (rom, map_path, resident)):
            with open(path, 'rb') as f:
                files[name] = f.read()
        _, _, banks = bbcrom.read_env_banks(rom)
        for b in banks:
            if b.value & 0x80 and b.file:
                with open(os.path.join(os.path.dirname(resident), b.file), 'rb') as f:
                    files[b.file] = f.read()
        args += list(names)
    return files, args


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class OnTheBBC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-modload-')
        cls.modload = build_modload(os.path.join(cls.dir, 'modload'))
        cls.tools, cls.whole, cls.home = build_tools(os.path.join(cls.dir, 'tools'))
        cls.files, cls.args = tool_files(cls.tools)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def disc(self, files=None):
        """A disc with MODLOAD, the home bank and the tools' files (or `files` in their place)."""
        import test_bbc_adfs as adfs
        disk = tempfile.mkdtemp(dir=self.dir)
        with open(self.modload, 'rb') as f:
            adfs.put(disk, 'MODLOAD', f.read())
        with open(bbcfs.adfs_host_path(disk, 'MODLOAD') + '.inf', 'w') as f:
            f.write(boards.inf_text('$.MODLOAD', adfs.PAGE, os.path.getsize(self.modload)))
        with open(self.home, 'rb') as f:
            adfs.put(disk, 'HOME', f.read())
        for name, data in (files or self.files).items():
            adfs.put(disk, name, data)
        return disk

    def run_lines(self, disk, lines, dump=None, preload=None):
        """(status, output, what the MOS said, report) of the lines on an empty RAM form (or one
        that holds the image `preload` at power on); with dump, the module's banks are written to
        that file at the end."""
        import dataclasses
        import test_bbc_adfs as adfs
        board = adfs.board()
        if dump:
            board = dataclasses.replace(board, options=board.options + ('--bbc-module-dump', dump))
        if preload:
            board = dataclasses.replace(board, options=board.options + ('--bbc-module', preload))
        command, _, tail = lines[-1].partition(' ')
        code, out, err, cycles = boards.run_module(board, None, disk, command, tail=tail,
                                                   before=lines[:-1], raw=True, ram=True, cap=adfs.CAP)
        text = err.decode('latin-1')
        status, said, cycles = boards.bbc_status(code, text)
        return status, boards.bbc_output(out), said, text

    def load_line(self, args=None):
        return 'RUN MODLOAD HOME ' + ' '.join(args or self.args)

    def test_the_loaded_tools_compile_and_link_as_the_hosts(self):
        """*RUN MODLOAD on an empty RAM form, then a module compiled by *LATHE, every file the host
        compiler's, and *LLINK's usage, the host linker's."""
        import subprocess
        import test_bbc_adfs as adfs
        disk = self.disc()
        hello = b'module hello\nvar x: byte\npub func main()\n  x = 72\nend\n'
        adfs.put(disk, 'hello.lth', hello)
        host = tempfile.mkdtemp(dir=self.dir)
        with open(os.path.join(host, 'hello.lth'), 'wb') as f:
            f.write(hello)
        status, out, said, report = self.run_lines(disk, [self.load_line(), 'LATHE -c6502 hello.lth .'])
        self.assertEqual((status, out, said), (0, b'', b''), report)
        r = subprocess.run([sys.executable, build.COMPILER, '-c6502', 'hello.lth', '.'], cwd=host,
                           capture_output=True)
        self.assertEqual(r.returncode, 0)
        for name in ('hello.lo', 'hello.li'):
            with open(bbcfs.adfs_host_path(disk, name), 'rb') as f, open(os.path.join(host, name), 'rb') as g:
                self.assertEqual(f.read(), g.read(), name)
        self.assertIn('checks: mos-memory-writes=0  romsel-mismatches=0', report)
        # The linker: its usage, word for word the host's (its text from the module).
        status, out, said, report = self.run_lines(self.disc(), [self.load_line(), 'LLINK'])
        r = subprocess.run([sys.executable, build.LINKER], capture_output=True)
        self.assertEqual((status, out), (r.returncode, r.stdout + r.stderr))

    def assert_whole_image(self, dump):
        """The module's sixteen banks are bbcrom.py's whole image of the same files, but where the
        image has nothing (its $FF), which MODLOAD leaves as it was."""
        with open(self.whole, 'rb') as f:
            want = f.read()
        with open(dump, 'rb') as f:
            got = f.read()
        self.assertEqual(len(got), len(want))
        for i in range(len(want)):
            if want[i] != got[i] and (want[i] != 0xFF or i % 0x4000 < 0x50):
                self.fail('bank %d, $%04X: $%02X, the image $%02X' % (i // 0x4000, 0x8000 + i % 0x4000, got[i],
                                                                         want[i]))

    def test_home_is_the_home_bank_to_its_description(self):
        with open(self.home, 'rb') as f:
            home = f.read()
        with open(self.whole, 'rb') as f:
            whole = f.read()
        self.assertEqual(len(home), bbcrom.DESCRIPTOR_AT + 16 - 0x8000)
        self.assertEqual(home, whole[8 * 0x4000:8 * 0x4000 + len(home)])
        self.assertEqual(home[-16:-10], b'LW\x01\x08\x02\x01')
        self.assertEqual(list(home[-8:]), [0x1F, 0x00, 0xE0, 0x00, 0, 0, 0, 0])

    def test_what_it_writes_is_the_whole_image(self):
        disk = self.disc()
        dump = os.path.join(self.dir, 'dump')
        status, out, said, report = self.run_lines(disk, [self.load_line()], dump)
        self.assertEqual((status, out, said), (0, b'', b''), report)
        self.assert_whole_image(dump)

    def test_it_refuses_what_does_not_belong_together(self):
        """A bank file the size its map does not give, an image of another length than its map's,
        a home bank of another number, a file that is not there: refused with its message and
        Exit 2, and nothing written: after the tools are loaded, a refused load leaves the module
        as it was."""
        import test_bbc_adfs as adfs
        bank_file = sorted(n for n in self.files if n.endswith('.BIN'))[0]
        with open(self.home, 'rb') as f:
            home = f.read()
        other = bytearray(home)
        other[0x4F] += 1
        cases = [('not the size its map gives: ', {bank_file: self.files[bank_file] + b'\0'}),
                 ('not the size its map gives: ', {'LATHE': self.files['LATHE'][:-1]}),
                 ("not the module's own bank for this layout: ", {'HOME': bytes(other)}),
                 ('cannot open ', {bank_file: None})]
        for n, (message, changed) in enumerate(cases):
            with self.subTest(message=message, changed=sorted(changed)):
                disk = self.disc()
                # The same files, but one, on drive 1 (`1/NAME`).
                for name, data in dict(dict(self.files, HOME=home), **changed).items():
                    if data is not None:
                        adfs.put(disk, '1/' + name, data)
                bad = 'RUN MODLOAD 1/HOME ' + ' '.join('1/' + a for a in self.args)
                dump = os.path.join(self.dir, 'dump-%d' % n)
                status, out, said, report = self.run_lines(disk, [self.load_line(), bad], dump)
                self.assertEqual(status, 2, report)
                self.assertTrue(out.startswith(b'modload: ' + message.encode()), out)
                self.assert_whole_image(dump)

    # ---- One tool into the module that is there ------------------------------------------------

    def image_with(self, change):
        """A copy of the whole image changed by change(bytearray of it); its file."""
        with open(self.whole, 'rb') as f:
            data = bytearray(f.read())
        change(data)
        fd, path = tempfile.mkstemp(dir=self.dir)
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        return path

    @staticmethod
    def wipe(banks):
        """A change that clears the banks given from $8050 on, as a tool not loaded yet."""
        def change(data):
            for b in banks:
                data[b * 0x4000 + 0x50:(b + 1) * 0x4000] = bytes(0x4000 - 0x50)
        return change

    def tool_args(self, command):
        i = [c for c, _ in TOOLS].index(command)
        return self.args[3 * i:3 * i + 3]

    def test_one_tool_into_the_module_there(self):
        """Without HOME, MODLOAD writes the tool given into its own banks of the module there and
        leaves the rest: from a module whose compiler (banks 0 to 4, its resident part in 9) or
        linker (5 to 7, 10) is cleared, the whole image again; and the command then runs."""
        for command, banks in (('LATHE', (0, 1, 2, 3, 4, 9)), ('LLINK', (5, 6, 7, 10))):
            with self.subTest(command=command):
                before = self.image_with(self.wipe(banks))
                dump = os.path.join(self.dir, 'dump-' + command)
                line = 'RUN MODLOAD ' + ' '.join(self.tool_args(command))
                status, out, said, report = self.run_lines(self.disc(), [line], dump, preload=before)
                self.assertEqual((status, out, said), (0, b'', b''), report)
                self.assert_whole_image(dump)
        status, out, said, report = self.run_lines(self.disc(), ['RUN MODLOAD ' + ' '.join(self.tool_args('LLINK')),
                                                                  'LLINK'], preload=self.image_with(self.wipe((5, 6, 7, 10))))
        self.assertIn(b'usage', out.lower(), report)

    def test_it_refuses_a_module_it_does_not_know_or_that_does_not_fit_the_tool(self):
        """Without HOME: an empty slot, a home bank with no description, a module whose command
        copies the tool to another address, a module none of whose tools has the tool's banks:
        each refused with Exit 2 and the module as it was."""
        home = 8 * 0x4000
        with open(self.home, 'rb') as f:
            d = f.read()[-16:]
        table = d[6] + 256 * d[7] - 0x8000

        def no_description(data):
            data[home + 0x3FE0] = ord('X')

        def other_start(data):
            n = data.index(b'LATHE\0', home + table)
            data[n + 8] ^= 0x01                 # the low byte of its start address

        def other_banks(data):
            data[home + 0x3FE8] = 0x3F           # tool 0's banks: 0 to 5

        cases = [('no module MODLOAD knows in the slot', None),
                 ('no module MODLOAD knows in the slot', no_description),
                 ('its code or memory is not where the module', other_start),
                 ("its banks are none of the module's tools'", other_banks)]
        for n, (message, change) in enumerate(cases):
            with self.subTest(message=message):
                before = self.image_with(change) if change else None
                dump = os.path.join(self.dir, 'dump-refused-%d' % n)
                line = 'RUN MODLOAD ' + ' '.join(self.tool_args('LATHE'))
                status, out, said, report = self.run_lines(self.disc(), [line], dump, preload=before)
                self.assertEqual(status, 2, report)
                self.assertTrue(out.startswith(b'modload: ' + message.encode()), out)
                if before:
                    with open(before, 'rb') as f, open(dump, 'rb') as g:
                        self.assertEqual(f.read(), g.read())


if __name__ == '__main__':
    unittest.main()
