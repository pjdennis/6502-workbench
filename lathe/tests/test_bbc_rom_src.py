"""The compiler's banked test programs (test_bbc_bank_src.py: outtest, regtest, condtest and
gentest) as programs of a ROM module on the emulated BBC Model B+128, in the small build: each
linked with the ROM form of its environment (lathe/src/compiler-bbc-bank.env with bbc_support's
lines, through bbcrom.rom_env: its five banks of the module `rom`, the window $8050-$BFDF), put
alone in a module image by lathe/host/driver/bbcrom.py and started by its * command (*OUTTEST,
...), with --bbc-strict. In a ROM bank nothing can be a variable, so the variables of the modules
placed in banks go to main RAM with the rest (lathe/docs/bbc.md, "Step 3, as built: the ROM
form", has the numbers). Each section of each script must give what the Python twin gives at the
small build's capacities, with the error output joined to the output as on the BBC; the files
written must be the same. All of it takes about 15 seconds."""
import concurrent.futures
import os
import shutil
import tempfile
import unittest

import src_support as support
import bbc_support as bbc
import script_host as script
import test_bbc_bank_src as banked

import bbcrom
import boards

HAVE_TOOLS = banked.HAVE_TOOLS
TOP = banked.TOP


class InTheRom:
    """One program, built for the ROM form and put in a module image in setUpClass (a mixin)."""
    NAME = None
    SCRIPT = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-rom-src-')
        run_env = bbc.bank_env(cls.NAME, os.path.join(cls.dir, cls.NAME + '-run.env'))
        cls.env = os.path.join(cls.dir, cls.NAME + '.env')
        bbcrom.rom_env(run_env, cls.env, 1)
        cls.command = cls.NAME.upper()
        resident = os.path.join(cls.dir, cls.command)
        support.build.build(os.path.join(support.SRC, cls.NAME + '.lth'), resident, env=cls.env,
                            keep=os.path.join(cls.dir, 'work'))
        map_path = os.path.join(cls.dir, 'work', cls.NAME + '.map')
        cls.map = banked.read_map(map_path)
        cls.image = os.path.join(cls.dir, 'MODULE')
        cls.listing = bbcrom.image([(cls.command, resident, cls.env, map_path)], cls.image)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def main(self):
        raise NotImplementedError

    def extra(self):
        return []

    def run_rom(self, args, paths):
        """bbc_support.run for the module's command: the arguments whose numbers are in paths are
        files, copied into the directory of the run and back."""
        with tempfile.TemporaryDirectory(prefix='lathe-bbc-rom-run-') as disk:
            names, inputs = [], set()
            for n, a in enumerate(map(str, args)):
                if n in paths:
                    base = os.path.basename(a)
                    if os.path.isfile(a):
                        shutil.copyfile(a, os.path.join(disk, base))
                        inputs.add(base)
                    a = base
                names.append(a)
            result = boards.run_module(bbc.BOARD, self.image, disk, self.command, names)
            for n, a in enumerate(map(str, args)):
                base = os.path.basename(a)
                if n in paths and base not in inputs and os.path.isfile(os.path.join(disk, base)):
                    shutil.copyfile(os.path.join(disk, base), a)
            return result

    def test_its_variables_are_in_main_ram_and_its_banks_read_only(self):
        """No variable in a bank of the module, every one of them `rom`; fixed code from $1900
        and fixed variables below HIMEM; the regions in sideways slots 12 and 13 as banked."""
        windows = [(name, bank) for kind, address, size, name, bank in self.map if kind == 'W']
        for kind, address, size, name, bank in self.map:
            if kind == 'V' and bank is not None:
                self.assertIn(bank, (32, 33), name)
            if kind in 'FDTVS' and bank is None and address >= 0x0800:
                self.assertLessEqual(address + size, TOP, name)
            if bank is not None and kind in 'FD' and bank < 16:
                self.assertTrue(0x8050 <= address and address + size <= 0xBFE0, name)
        self.assertTrue(windows)
        with open(os.path.join(self.dir, 'work', self.NAME + '.map')) as f:
            roms = [line.split()[3] for line in f if line.startswith('W ') and line.rstrip().endswith(' rom')]
        self.assertEqual(sorted(roms), ['1', '2', '3', '4', '5'][:len(roms)])
        self.assertGreaterEqual(len(roms), 2)
        tables = {name: bank for kind, address, size, name, bank in self.map if kind in 'VD'}
        for table, bank in (('kernel.names', 32), ('fbuf.buffer', 33), ('err.messages_1', 33)):
            self.assertEqual(tables.get(table), bank, table)

    def test_every_script(self):
        runs = []
        for n, (title, text) in enumerate(script.sections(self.SCRIPT) + list(self.extra())):
            path = os.path.join(self.dir, '%s-%d.txt' % (self.SCRIPT, n))
            with open(path, 'wb') as f:
                f.write(text)
            runs.append((title, text, path, os.path.join(self.dir, '%s-%d-0' % (self.SCRIPT, n))))
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            lathe = list(pool.map(lambda r: self.run_rom([r[2], r[3] + 'L'], paths=(0, 1)), runs))
        for (title, text, path, made), (status, out, said, _) in zip(runs, lathe):
            with self.subTest(section=title.decode()):
                host = bbc.host_run(self.main(), [os.path.basename(path), os.path.basename(made) + 'P'],
                                    self.dir)
                if out != host[1]:
                    self.fail(script.first_difference(text, out, host[1]))
                self.assertEqual((status, said), (host[0], b''))
                self.assertEqual(os.path.exists(made + 'L'), os.path.exists(made + 'P'))
                if os.path.exists(made + 'P'):
                    with open(made + 'L', 'rb') as a, open(made + 'P', 'rb') as b:
                        self.assertEqual(a.read(), b.read(), 'file %s' % made)
        self.assertGreater(len(runs), 2)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class OutRom(InTheRom, unittest.TestCase):
    NAME = 'outtest'
    SCRIPT = 'out'
    main = banked.OutBanked.main


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class RegRom(InTheRom, unittest.TestCase):
    NAME = 'regtest'
    SCRIPT = 'reg'
    main = banked.RegBanked.main


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class CondRom(InTheRom, unittest.TestCase):
    NAME = 'condtest'
    SCRIPT = 'cond'
    main = banked.CondBanked.main
    extra = banked.CondBanked.extra


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class GenRom(InTheRom, unittest.TestCase):
    NAME = 'gentest'
    SCRIPT = 'gen'
    main = banked.GenBanked.main


if __name__ == '__main__':
    unittest.main()
