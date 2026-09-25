"""Firmware must assemble identically on vasm 1.9f and 2.0+.

Three differences between vasm releases matter here:
- 2.0d+ no longer NUL-terminates .ascii strings (1.9f did), so firmware uses
  .asciiz (or explicit .byte data) instead.
- 2.0+ rejects a byte selector inside parentheses, e.g. `lda #(>X)`, so macros
  must not wrap an immediate argument as `#(\\value)`: callers pass `>X` / `<X`.
- 2.0+ does not split macro arguments after a quoted string: in `m "s", x` the
  first parameter receives `"s", x`. A quoted string must be the last argument.

Uses firmware/vasm with vasm6502_oldstyle from PATH (tests skip if missing).
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FW_VASM = os.path.join(ROOT, 'firmware', 'vasm')
SOURCE_DIRS = ['firmware', 'hardware']

# Symbols the macros reference, so a test program can use them standalone.
PRELUDE = """
CT_ZERO_PAGE_BASE = $80
CT_COMMANDS = $2000
PORTB = $6000
GD_PORT = $6001
GD_E = $01
  .org $1000
gd_send_data:
gd_send_command:
  rts
"""


def firmware_sources():
    for top in SOURCE_DIRS:
        for dirpath, _, files in os.walk(os.path.join(ROOT, top)):
            for name in files:
                if name.endswith(('.s', '.inc', '.asm')):
                    yield os.path.join(dirpath, name)


class NoAsciiDirectiveTest(unittest.TestCase):
    def test_firmware_uses_asciiz_not_ascii(self):
        pattern = re.compile(r'^\s*\.ascii\s', re.M)
        offenders = []
        for path in firmware_sources():
            with open(path, errors='replace') as f:
                text = f.read()
            for m in pattern.finditer(text):
                line = text.count('\n', 0, m.start()) + 1
                offenders.append(f'{os.path.relpath(path, ROOT)}:{line}')
        self.assertEqual(offenders, [], '.ascii termination differs between vasm versions; use .asciiz')


class QuotedMacroArgumentTest(unittest.TestCase):
    def test_quoted_string_is_the_last_macro_argument(self):
        macros = set()
        sources = list(firmware_sources())
        for path in sources:
            with open(path, errors='replace') as f:
                macros.update(re.findall(r'^\s*\.macro\s+(\w+)', f.read(), re.M))
        call = re.compile(r'^\s*(%s)\b[^;\n]*["\'][^"\'\n]*["\']\s*,' % '|'.join(sorted(macros)), re.M)
        offenders = []
        for path in sources:
            with open(path, errors='replace') as f:
                text = f.read()
            for m in call.finditer(text):
                offenders.append(f'{os.path.relpath(path, ROOT)}:{text.count(chr(10), 0, m.start()) + 1}')
        self.assertEqual(offenders, [], 'vasm 2.0+ swallows the arguments after a quoted string')


@unittest.skipUnless(shutil.which('vasm6502_oldstyle'), 'vasm6502_oldstyle not on PATH')
class ImmediateMacrosTest(unittest.TestCase):
    def assemble(self, include, body):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = os.path.join(tmp, 't.s'), os.path.join(tmp, 't.bin')
            with open(src, 'w') as f:
                f.write(PRELUDE + f'  .include {include}\nstart:\n{body}\n')
            result = subprocess.run([FW_VASM, '-quiet', '-wdc02', '-wfail', '-Fbin', '-dotdir',
                                     '-o', out, src], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with open(out, 'rb') as f:
                return f.read()

    def assert_emits(self, include, call, opcode, byte):
        code = self.assemble(include, '  ' + call)
        self.assertIn(bytes([opcode, byte]), code, f'{call} should emit {opcode:02X} {byte:02X}')

    def test_graphics_immediate_macros_accept_byte_selectors(self):
        for macro in ('gd_send_command_immediate', 'gd_send_data_immediate', 'gd_send_x2'):
            with self.subTest(macro=macro):
                self.assert_emits('graphics_macros.inc', f'{macro} >$1234', 0xA9, 0x12)
                self.assert_emits('graphics_macros.inc', f'{macro} <$1234', 0xA9, 0x34)

    def test_ct_entry_emits_name_then_address(self):
        code = self.assemble('command_table.inc', '  ct_entry $1234, "hi"')
        self.assertIn(b'hi\x00\x34\x12', code)

    def test_add8_macro_accepts_byte_selectors(self):
        self.assert_emits('macros.inc', 'add8iTo16usingA $10, >$1234', 0x69, 0x12)
        self.assert_emits('macros.inc', 'add8iTo16usingA $10, <$1234', 0x69, 0x34)


if __name__ == '__main__':
    unittest.main()
