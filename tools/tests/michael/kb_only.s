; The keyboard started alone (SVC_KEYBOARD_START) leaves the screen's RAM be. Marks that RAM,
; starts the keyboard, reads a key and shows it with the raw LCD calls, then 'Y' if the marks
; are all still there, else 'N'.
  .include rom_vectors.inc

MARK = $a5

  .org $0200
  ldx #$ff
  txs
  ldx #ROM_RAM_END - ROM_RAM_SCREEN - 1
.mark:
  lda #MARK
  sta ROM_RAM_SCREEN, X
  dex
  bpl .mark
  jsr SVC_KEYBOARD_START
  jsr con_read
  pha
  lda #CMD_SET_DDRAM_ADDRESS
  jsr SVC_LCD_COMMAND
  pla
  jsr SVC_LCD_CHARACTER
  ldx #ROM_RAM_END - ROM_RAM_SCREEN - 1
  lda #'Y'
.check:
  ldy ROM_RAM_SCREEN, X
  cpy #MARK
  beq .same
  lda #'N'
.same:
  dex
  bpl .check
  jsr SVC_LCD_CHARACTER
  stp

CMD_SET_DDRAM_ADDRESS = %10000000
