"""Michael's FPGA bus driver (firmware/lib/fpga/fpga_bus.inc), run on the emulator's Michael: each routine must
make the transfer it names, as the emulator's FPGA bus logs it (--fpga-log), however another program left RS
and RW. fb_initialize puts them in their quiet state (low), and the routines rely on finding them there.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import michael_emulator  # noqa: E402

PROGRAM = """
  .include base_config_v2.inc
  .org PROGRAM_LOAD_ADDRESS
start:
  ldx #$ff
  txs
  lda #(RS | RW)
  tsb DDRA
  tsb PORTA                      ; RS and RW high, as another program might leave them
  jsr fb_initialize
  lda #$01
  jsr fb_command
  lda #$AA
  jsr fb_data
  jsr fb_read
  jsr fb_status
  jsr fb_read
  lda #$04
  jsr fb_command
  stp
  .include fpga_bus.inc
"""


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class FpgaBusDriverTest(unittest.TestCase):
    def test_each_routine_makes_its_transfer(self):
        michael_emulator.build_emulator()
        log, report = michael_emulator.run(source=PROGRAM)
        self.assertEqual(log.split(), ['C', '01', 'D', 'AA', 'R', 'S', 'R', 'C', '04'], report)


if __name__ == '__main__':
    unittest.main()
