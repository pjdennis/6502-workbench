; Shows the installed ROM's 6502 vectors, to check which loader ROM a board has.
; The IRQ vector is the address the ROM expects a program's interrupt handler at
; (INTERRUPT_VECTOR_TARGET in base_config_v2.inc). The last line shows the first
; bytes at that address, where the ROM's loader copies its own serial handler.

  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $00 ; 2 bytes
WORD_P               = $02 ; 2 bytes

NMI_VECTOR           = $fffa
RESET_VECTOR         = $fffc
IRQ_VECTOR           = $fffe

  .org PROGRAM_LOAD_ADDRESS
  jmp initialize_machine

  .include initialize_machine_v2.inc
  .include display_routines_8bit.inc
  .include display_string.inc
  .include display_hex.inc

program_start:
  ldx #$ff ; Initialize stack
  txs

  jsr clear_display

  lda #DISPLAY_FIRST_LINE
  jsr move_cursor
  lda #<irq_label
  ldx #>irq_label
  jsr display_string
  lda #<IRQ_VECTOR
  ldx #>IRQ_VECTOR
  jsr display_word_at

  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda #<reset_label
  ldx #>reset_label
  jsr display_string
  lda #<RESET_VECTOR
  ldx #>RESET_VECTOR
  jsr display_word_at

  lda #DISPLAY_THIRD_LINE
  jsr move_cursor
  lda #<nmi_label
  ldx #>nmi_label
  jsr display_string
  lda #<NMI_VECTOR
  ldx #>NMI_VECTOR
  jsr display_word_at

  ; Show the first bytes at the address the IRQ vector points to
  lda #DISPLAY_FOURTH_LINE
  jsr move_cursor
  lda #<handler_label
  ldx #>handler_label
  jsr display_string
  lda IRQ_VECTOR
  sta WORD_P
  lda IRQ_VECTOR + 1
  sta WORD_P + 1
  ldy #0
show_handler_byte:
  lda #' '
  jsr display_character
  lda (WORD_P),Y
  jsr display_hex
  iny
  cpy #4
  bne show_handler_byte

forever:
  bra forever


; On entry A, X contain low and high bytes of the address of a word
; On exit  the word is displayed in hex, high byte first
;          A, X, Y are preserved
display_word_at:
  pha
  phy
  sta WORD_P
  stx WORD_P + 1
  ldy #1
  lda (WORD_P),Y
  jsr display_hex
  lda (WORD_P)
  jsr display_hex
  ply
  pla
  rts


irq_label:     .asciiz "IRQ   $FFFE: "
reset_label:   .asciiz "RESET $FFFC: "
nmi_label:     .asciiz "NMI   $FFFA: "
handler_label: .asciiz "At IRQ:"
