"""The new Michael ROM (firmware/boards/michael/michael_rom.s) on the emulator's Michael machine:
its format 2 loader (firmware/lib/serial/upload_v2.inc) receiving uploads over the serial line
(tests/michael/upload_check.s, uploaded with the data, shows what landed where), and its services
(firmware/boards/michael/michael_services.inc), driven by the small programs in tests/michael/.

Uses firmware/vasm with vasm6502_oldstyle from PATH, and builds the emulator with make (tests skip
if vasm, gcc or make is missing).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'upload'))
import upload_frame  # noqa: E402
from upload_frame import Block  # noqa: E402

FW_VASM = os.path.join(ROOT, 'firmware', 'vasm')
EMULATOR = os.path.join(ROOT, 'emulator', 'emulator.out')
ROM = os.path.join(ROOT, 'firmware', 'boards', 'michael', 'michael_rom.s')
TESTS = os.path.join(HERE, 'michael')
CHECK = os.path.join(TESTS, 'upload_check.s')
VECTORS = os.path.join(ROOT, 'firmware', 'boards', 'michael', 'michael_rom_vectors.inc')
ENVIRONMENT = os.path.join(ROOT, 'toolchain', 'asm2', '17', 'environment.asm')


NEEDS = unittest.skipUnless(shutil.which('vasm6502_oldstyle') and shutil.which('gcc') and shutil.which('make'),
                            'vasm6502_oldstyle, gcc and make are needed')


class RomTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        subprocess.run(['make', '-s', 'emulator/emulator.out'], cwd=ROOT, check=True, capture_output=True)
        cls.rom = cls.assemble(ROM)
        with open(cls.assemble(CHECK), 'rb') as f:
            cls.check = f.read()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def assemble(cls, source):
        binary = os.path.join(cls.tmp.name, os.path.basename(source) + '.bin')
        subprocess.run([FW_VASM, '-quiet', '-wdc02', '-wfail', '-Fbin', '-dotdir', '-ignore-mult-inc',
                        '-esc', '-I', TESTS, '-o', binary, source], check=True, capture_output=True)
        return binary

    def boot(self, wire, typed=None, stops=None):
        """The LCD's rows after the ROM boots and receives wire, and has had typed typed; the CPU
        must have stopped if stops (by default, when there is an upload)."""
        upload = os.path.join(self.tmp.name, 'upload')
        with open(upload, 'wb') as f:
            f.write(wire)
        options = []
        if typed is not None:
            keys = os.path.join(self.tmp.name, 'keys')
            with open(keys, 'wb') as f:
                f.write(typed)
            options = ['--keys', keys]
        report = subprocess.run([EMULATOR, self.rom, '--machine', 'michael', '--serial-input', upload,
                                 '--cycle-cap', '20000000', *options],
                                check=True, capture_output=True, text=True).stderr.splitlines()
        if bool(wire) if stops is None else stops:
            self.assertTrue(report[0].endswith('(STP)'), report[0])
        self.assertIn('michael: bus: lcd-undriven=0 portb-contention=0', report)
        lcd = report.index('michael: lcd:')
        return [line.strip()[1:-1].rstrip() for line in report[lcd + 1:lcd + 5]]



@NEEDS
class MichaelRomLoaderTest(RomTestCase):
    def expected_check(self, memory):
        """What upload_check shows for RAM as memory (address -> byte; absent = 0)."""
        byte = lambda address: memory.get(address, 0)
        total = lambda start, length: sum(byte(a) for a in range(start, start + length)) & 0xffff
        return ['%02X%02X%02X%02X%02X' % tuple(byte(a) for a in (0x0600, 0x06ff, 0x0800, 0x0fff, 0x3eff)),
                '%04X %04X' % (total(0x0600, 0x100), total(0x0800, 0x800))]

    @staticmethod
    def memory(blocks):
        memory = {}
        for block in blocks:
            data = block.data or bytes(block.fill)
            memory.update((block.address + i, b) for i, b in enumerate(data))
        return memory

    def upload(self, blocks, start=0x0200):
        return upload_frame.reverse_bits(upload_frame.build_upload(blocks, start))

    def test_ready_screen(self):
        self.assertEqual(self.boot(b'')[1], 'Ready.')

    def test_one_block_fills_all_of_ram(self):
        data = bytearray(self.check + bytes([0x11]) * (0x3f00 - 0x0200 - len(self.check)))
        data[-1] = 0x5a
        blocks = [Block(0x0200, bytes(data))]
        self.assertEqual(self.boot(self.upload(blocks))[:2], self.expected_check(self.memory(blocks)))

    def test_blocks_moved_up_and_zero_fill(self):
        # The zero-fill block's area first holds stream bytes of the block after it
        blocks = [Block(0x0200, self.check), Block(0x0600, fill=0x100),
                  Block(0x0800, bytes((i * 7 + 1) & 0xff for i in range(0x800))),
                  Block(0x3e00, bytes(0xff) + b'\xd1')]
        self.assertEqual(self.boot(self.upload(blocks))[:2], self.expected_check(self.memory(blocks)))

    def test_the_packer_upload_of_intel_hex_segments(self):
        segments = [(0x0200, self.check), (0x3eff, b'\x77')]
        self.assertEqual(self.boot(upload_frame.format_2(segments))[:2],
                         self.expected_check({0x3eff: 0x77}))

    def test_no_start_address_only_loads(self):
        self.assertEqual(self.boot(self.upload([Block(0x0200, self.check)], start=0xffff))[:2],
                         ['Loaded.', ''])

    def failure(self, wire):
        rows = self.boot(wire)
        self.assertEqual(rows[0], 'Upload failed')
        return rows[1]

    def test_unknown_version(self):
        upload = bytearray(upload_frame.build_upload([Block(0x0200, self.check)], 0x0200))
        upload[0] = 3
        self.assertEqual(self.failure(upload_frame.reverse_bits(upload)), 'Bad version 03')

    def test_reserved_flag(self):
        upload = bytearray(upload_frame.build_upload([Block(0x0200, self.check)], 0x0200))
        upload[9] |= 0x04
        self.assertEqual(self.failure(upload_frame.reverse_bits(upload)), 'Bad block 01')

    def test_below_ram(self):
        self.assertEqual(self.failure(self.upload([Block(0x01ff, b'x' * 20)])), 'Bad block 01')

    def test_past_the_interrupt_page(self):
        self.assertEqual(self.failure(self.upload([Block(0x3000, bytes(0xf01))])), 'Bad block 01')

    def test_data_that_would_move_down(self):
        # The second block's data would sit at $020E + len in the stream, past its load address
        self.assertEqual(self.failure(self.upload([Block(0x0200, self.check), Block(0x0210, b'x')])),
                         'Bad block 02')

    def test_blocks_out_of_order(self):
        self.assertEqual(self.failure(self.upload([Block(0x0200, self.check), Block(0x3000, b'x'),
                                                   Block(0x2000, b'y')])), 'Bad block 03')

    def test_bad_checksum(self):
        upload = bytearray(upload_frame.build_upload([Block(0x0200, self.check), Block(0x3000, b'xy')],
                                                     0x0200))
        upload[-1] ^= 1
        self.assertEqual(self.failure(upload_frame.reverse_bits(upload)), 'Bad checksum 02')

    def test_a_corrupt_header_field_is_caught_by_the_checksum(self):
        upload = bytearray(upload_frame.build_upload([Block(0x0200, self.check)], 0x0200))
        upload[1] ^= 0x10                        # the start address
        self.assertEqual(self.failure(upload_frame.reverse_bits(upload)), 'Bad checksum 01')


@NEEDS
class MichaelRomServicesTest(RomTestCase):
    def run_program(self, name, typed=None, stops=True):
        """The LCD's rows after uploading and running tests/michael/<name>.s."""
        with open(self.assemble(os.path.join(TESTS, name + '.s')), 'rb') as f:
            program = f.read()
        return self.boot(upload_frame.format_2([(0x0200, program)]), typed, stops)

    def test_the_vectors_are_the_environments(self):
        definition = re.compile(r'^([A-Za-z_]+) *= *(?:SVC|ENV)_BASE \+ \$([0-9A-F]{2})', re.M)
        with open(ENVIRONMENT) as f:
            environment = {name.upper(): offset for name, offset in definition.findall(f.read())}
        with open(VECTORS) as f:
            vectors = {name[4:]: offset for name, offset in definition.findall(f.read())}
        self.assertEqual({name: vectors[name] for name in environment}, environment)

    def test_every_vector_is_a_jmp(self):
        with open(self.rom, 'rb') as f:
            rom = f.read()
        with open(VECTORS) as f:
            offsets = [int(o, 16) for o in re.findall(r'^SVC_\w+ *= SVC_BASE \+ \$([0-9A-F]{2})', f.read(), re.M)]
        for offset in offsets[:-1]:              # all but SVC_END
            self.assertEqual(rom[0x7000 + offset], 0x4c, hex(offset))

    def test_screen_calls(self):
        self.assertEqual(self.run_program('screen_calls'), [
            'HelloXY world',
            '  abcdefghijklmnopqr',
            '~\\uvwxyz',
            'status        abcdef'])

    def test_scrolling(self):
        self.assertEqual(self.run_program('screen_scroll'), ['', 'row1', 'again', ''])

    def test_keys(self):
        typed = b'aA\x06\x1b[A\x1b[1;5C\x1b[3~\x1b\r\x08q'
        self.assertEqual(self.run_program('keys', typed)[0], '6141068089881B0D08')

    def test_exit_goes_back_to_the_loader(self):
        self.assertEqual(self.run_program('exit', stops=False)[:2], ['Michael ROM 3', 'Ready.'])
