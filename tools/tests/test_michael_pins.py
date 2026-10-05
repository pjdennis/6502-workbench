"""Michael's port A as stage 4 of the FPGA bus plan wires it (docs/michael-fpga-bus-plan.md, "Stage 4 wiring
changes"), on the emulator: the LED on PA1, lit while it's high; the FPGA bus's E on PA2; PA0 free.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import michael_emulator  # noqa: E402

PROGRAM = """
  .org $2000
start:
  lda #{ddra}
  sta $6003                ; DDRA
  lda #{porta}
  sta $6001                ; PORTA
  lda #$ff
  sta $6002                ; DDRB
  lda #$2a
  sta $6000                ; PORTB
  lda #{porta} | {strobe}
  sta $6001
  lda #{porta}
  sta $6001
  stp
"""


def run(ddra, porta, strobe=0):
    log, report = michael_emulator.run(source=PROGRAM.format(ddra=ddra, porta=porta, strobe=strobe),
                                       cycle_cap=100_000)
    led = next(line for line in report.split('\n') if line.startswith('michael: led:'))
    return led.split()[-1], log


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class MichaelPinsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        michael_emulator.build_emulator()

    def test_the_led_is_on_pa1_and_lights_while_it_is_high(self):
        self.assertEqual(run(ddra=0x02, porta=0x02)[0], 'on')
        self.assertEqual(run(ddra=0x02, porta=0x00)[0], 'off')
        self.assertEqual(run(ddra=0x04, porta=0x00)[0], 'off')   # PA2 low: not the LED now

    def test_the_fpga_buss_e_is_on_pa2(self):
        self.assertEqual(run(ddra=0x64, porta=0x00, strobe=0x04)[1], 'C 2A\n')
        self.assertEqual(run(ddra=0x61, porta=0x00, strobe=0x01)[1], '')       # PA0 is free


if __name__ == '__main__':
    unittest.main()
