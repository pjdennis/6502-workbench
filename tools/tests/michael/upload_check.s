; Shows what an upload left in RAM, for tests/test_michael_rom.py: on the first row the bytes at
; $0600, $06FF, $0800, $0FFF and $3EFF, on the second the 16-bit sums of $0600-$06FF and
; $0800-$0FFF. Loaded at $0200.
  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $00 ; 2 bytes
SUM_P                = $02 ; 2 bytes
SUM                  = $04 ; 2 bytes
SUM_COUNT            = $06 ; 2 bytes

  .org $0200
start:
  jmp check

  .include delay_routines.inc
  .include display_routines.inc
  .include display_hex.inc

  .macro show_byte,address
  lda \address
  jsr display_hex
  .endm

  .macro show_sum,address,length
  lda #<\address
  sta SUM_P
  lda #>\address
  sta SUM_P + 1
  lda #<\length
  sta SUM_COUNT
  lda #>\length
  sta SUM_COUNT + 1
  jsr show_sum
  .endm

check:
  ldx #$ff
  txs
  jsr reset_and_enable_display_no_cursor
  show_byte $0600
  show_byte $06ff
  show_byte $0800
  show_byte $0fff
  show_byte $3eff
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  show_sum $0600, $0100
  lda #' '
  jsr display_character
  show_sum $0800, $0800
  stp

show_sum:
  stz SUM
  stz SUM + 1
.loop:
  lda (SUM_P)
  clc
  adc SUM
  sta SUM
  bcc .added
  inc SUM + 1
.added:
  inc SUM_P
  bne .counted
  inc SUM_P + 1
.counted:
  lda SUM_COUNT
  bne .low
  dec SUM_COUNT + 1
.low:
  dec SUM_COUNT
  lda SUM_COUNT
  ora SUM_COUNT + 1
  bne .loop
  lda SUM + 1
  jsr display_hex
  lda SUM
  jmp display_hex
