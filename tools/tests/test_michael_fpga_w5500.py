"""Michael's W5500 driver on the FPGA bus (firmware/lib/fpga/fpga_w5500.inc), run on the emulator's Michael with
the W5500 on the FPGA's network device (--add w5500): a register read, the network settings written in one frame
and read back in another, a register written and read back and a 16-bit register; each step's error flag (carry)
is gathered (and a register read sets Z from the value), so the LCD shows OK, or ERR if a frame's header wasn't answered (with no W5500, MISO reads high),
then how many frames went wrong (W5500_FAULTS).

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import michael_emulator  # noqa: E402

PROGRAM = """
  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $00 ; 2 bytes
W5500_COUNT          = $02 ; 1 byte
W5500_ERRORS         = $03 ; 1 byte
W5500_WORD           = $04 ; 2 bytes
W5500_FAULTS         = $06 ; 2 bytes
FAILED               = $08 ; 1 byte

  .org PROGRAM_LOAD_ADDRESS
start:
  jmp initialize_machine

  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_hex.inc
  .include display_string.inc
  .include fpga_bus.inc
  .include fpga_w5500.inc

program_start:
  ldx #$ff
  txs
  sei
  jsr fb_initialize
;STALE
  jsr w5500_initialize
  jsr reset_and_enable_display_no_cursor
  stz FAILED
  stz W5500_FAULTS
  stz W5500_FAULTS + 1

  ldx #W5500_COMMON
  ldy #<W5500_VERSIONR
  jsr w5500_read_register
  jsr check
  jsr show
  ldx #W5500_S0_REGISTERS
  ldy #<W5500_SN_CR
  jsr w5500_read_register        ; Reads 0: Z and N from the value
  beq .zero
  inc FAILED
.zero:

  ldx #>W5500_GAR
  ldy #<W5500_GAR
  lda #W5500_COMMON
  jsr w5500_write
  ldy #0
.setting:
  lda network,Y
  jsr w5500_write_byte
  iny
  cpy #W5500_NETWORK_SIZE
  bne .setting
  jsr w5500_end
  jsr check

  lda #4
  sta W5500_COUNT
  ldx #>W5500_SIPR
  ldy #<W5500_SIPR
  lda #W5500_COMMON
  jsr w5500_read
  jsr check
  ldy #4
.ip:
  jsr w5500_read_byte
  jsr display_hex
  dey
  bne .ip
  lda #' '
  jsr display_character

  lda #$5A
  ldx #W5500_S0_REGISTERS
  ldy #<W5500_SN_PORT
  jsr w5500_write_register
  jsr check
  ldy #<W5500_SN_PORT
  jsr w5500_read_register
  jsr check
  jsr show

  ldx #W5500_S0_REGISTERS
  ldy #<W5500_SN_TX_FSR
  jsr w5500_read_register16
  jsr check
  lda W5500_WORD + 1
  jsr display_hex
  lda W5500_WORD
  jsr show

  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda #<ok
  ldx #>ok
  ldy FAILED
  beq .result
  lda #<failed
  ldx #>failed
.result:
  jsr display_string
  lda #' '
  jsr display_character
  lda W5500_FAULTS + 1
  jsr display_hex
  lda W5500_FAULTS
  jsr display_hex
  stp

; Notes a step's failure (carry set)
check:
  bcc .ok
  inc FAILED
.ok:
  rts

; Shows A in hex, then a space
show:
  jsr display_hex
  lda #' '
  jmp display_character

network:
  .byte 192, 168, 8, 1, 255, 255, 255, 0, $02, $65, $02, $00, $00, $01, 192, 168, 8, 50
ok:     .asciiz "OK"
failed: .asciiz "ERR"
"""


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class FpgaW5500Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        michael_emulator.build_emulator()

    def run_program(self, options=()):
        return michael_emulator.run(source=PROGRAM, cycle_cap=2_000_000, options=options)[1]

    def test_registers_and_frames(self):
        report = self.run_program(['--add', 'w5500'])
        self.assertIn('|04 C0A80832 5A 0800 |', report)
        self.assertIn('|OK 0000             |', report)
        self.assertIn('michael: w5500: ip 192.168.8.50 mask 255.255.255.0 gateway 192.168.8.1 '
                      'mac 02:65:02:00:00:01', report)

    def test_whatever_a_program_stopped_by_a_reset_left(self):
        """A reset stops a program part way: here a byte left in the reply queue, an error in the status and a
        NET_READ cut off in its arguments"""
        stale = '\n'.join(['  lda #FB_ECHO', '  jsr fb_command', '  lda #$55', '  jsr fb_data',
                           '  lda #$7F', '  jsr fb_command',
                           '  lda #FB_NET', '  jsr fb_command', '  lda #FB_NET_READ', '  jsr fb_data',
                           '  lda #$00', '  jsr fb_data'])
        report = michael_emulator.run(source=PROGRAM.replace(';STALE', stale), cycle_cap=2_000_000,
                                      options=['--add', 'w5500'])[1]
        self.assertIn('|04 C0A80832 5A 0800 |', report)
        self.assertIn('|OK 0000             |', report)

    def test_without_the_w5500_every_frame_is_an_error(self):
        report = self.run_program()
        self.assertIn('|FF FFFFFFFF FF FFFF |', report)
        self.assertIn('|ERR 0007            |', report)   # every frame


if __name__ == '__main__':
    unittest.main()
