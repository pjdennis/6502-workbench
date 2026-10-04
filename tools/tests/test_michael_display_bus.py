"""Michael's graphic display driver (firmware/lib/graphics/graphics_display.inc) on the FPGA bus (stage 2 of
docs/michael-fpga-bus-plan.md): gd_prepare_vertical, run on the emulator's Michael, must send the display,
through the bus's raw display commands, exactly what it sent the spi-display interface: a reset, the
driver's INIT_COMMANDS, the orientation and a cleared screen. The emulator logs each bus transfer
(--fpga-log), and the test decodes them into display operations.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
Uses firmware/vasm with vasm6502_oldstyle from PATH, and builds the emulator with make.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import michael_emulator  # noqa: E402
sys.path.insert(0, os.path.join(michael_emulator.ROOT, 'hardware', 'michael', 'fpga', 'display-probe'))
import probe  # noqa: E402  (its parsers of graphics_display.inc)

PROGRAM = """
  .include base_config_v2.inc
DISPLAY_STRING_PARAM     = $00 ; 2 bytes
MULTIPLY_8X8_RESULT_LOW  = $02 ; 1 byte
MULTIPLY_8X8_TEMP        = $03 ; 1 byte
GD_ZERO_PAGE_BASE        = $06

  .org PROGRAM_LOAD_ADDRESS
start:
  jmp initialize_machine
  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include multiply8x8.inc
  .include graphics_display.inc

program_start:
  ldx #$ff
  txs
  jsr gd_prepare_vertical
  stp
"""

DISP_RESET, DISP_COMMAND, DISP_DATA = 0x10, 0x11, 0x12


def display_operations(log):
    """The bus transfers ("C hh", "D hh") as display operations: ("reset", level), or ("command", c,
    [bytes]) for DISP_COMMAND with its data. Other transfers are kept as ("other", line)."""
    ops, current = [], None
    lines = [line.split() for line in log.splitlines() if line.strip()]
    i = 0
    while i < len(lines):
        kind, value = lines[i][0], int(lines[i][1], 16)
        if kind == 'C' and value == DISP_RESET and i + 1 < len(lines) and lines[i + 1][0] == 'D':
            ops.append(('reset', int(lines[i + 1][1], 16)))
            current, i = None, i + 2
        elif kind == 'C' and value == DISP_COMMAND and i + 1 < len(lines) and lines[i + 1][0] == 'D':
            current = ['command', int(lines[i + 1][1], 16), []]
            ops.append(current)
            i += 2
        elif kind == 'D' and current is not None:
            current[2].append(value)
            i += 1
        else:
            ops.append(('other', ' '.join(lines[i])))
            current, i = None, i + 1
    return [tuple(op) for op in ops]


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class DisplayDriverOnTheBusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        michael_emulator.build_emulator()
        cls.ops = display_operations(michael_emulator.run(source=PROGRAM)[0])

    def test_resets_the_display(self):
        self.assertEqual(self.ops[:2], [('reset', 0), ('reset', 1)])

    def test_sends_the_init_table(self):
        table = [('command', cmd, params) for cmd, params, _ in probe.michael_init_commands()]
        self.assertEqual(self.ops[2:2 + len(table)], table)

    def test_then_the_orientation_and_a_cleared_screen(self):
        names = probe.driver_constants()
        madctl = names['ILI9341_MADCTL_MY'] | names['ILI9341_MADCTL_MV'] | names['ILI9341_MADCTL_BGR']
        rest = self.ops[2 + len(probe.michael_init_commands()):]
        self.assertEqual(rest[0], ('command', 0x36, [madctl]))
        self.assertEqual(rest[1], ('command', 0x28, []))                     # DISPOFF
        self.assertEqual(rest[2], ('command', 0x2A, [0x00, 0x00, 0x01, 0x3F]))  # 320 columns
        self.assertEqual(rest[3], ('command', 0x2B, [0x00, 0x00, 0x00, 0xEF]))  # 240 rows
        self.assertEqual(rest[4][:2], ('command', 0x2C))                      # RAMWR
        self.assertEqual(len(rest[4][2]), 320 * 240 * 2)
        self.assertEqual(set(rest[4][2]), {0})
        self.assertEqual(rest[5:], [('command', 0x29, [])])                  # DISPON, and nothing else


if __name__ == '__main__':
    unittest.main()
