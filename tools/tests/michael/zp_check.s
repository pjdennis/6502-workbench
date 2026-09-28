; Shows the zero page an upload left, for tests/test_michael_rom.py: saves it first, then shows
; on the first row the bytes at $00, $01, $24, $25, $FB, $FC, $FD and $FF, on the second the
; 16-bit sum of all 256. Loaded at $0200.
  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $00 ; 2 bytes (once zero page is saved)
SAVED                = $0800 ; 256 bytes
SUM                  = $0900 ; 2 bytes

  .macro show_saved,address
  lda SAVED + \address
  jsr display_hex
  .endm

  .org $0200
start:
  ldx #0
.save:
  lda $00, X
  sta SAVED, X
  inx
  bne .save
  ldx #$ff
  txs
  jsr reset_and_enable_display_no_cursor
  show_saved $00
  show_saved $01
  show_saved $24
  show_saved $25
  show_saved $fb
  show_saved $fc
  show_saved $fd
  show_saved $ff
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  stz SUM
  stz SUM + 1
  ldx #0
.sum:
  clc
  lda SAVED, X
  adc SUM
  sta SUM
  bcc .added
  inc SUM + 1
.added:
  inx
  bne .sum
  lda SUM + 1
  jsr display_hex
  lda SUM
  jsr display_hex
  stp

  .include delay_routines.inc
  .include display_routines.inc
  .include display_hex.inc

  .if * > SAVED
  fail "The program runs into SAVED"
  .endif
