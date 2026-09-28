  .include base_config_v2.inc

LINE_CHARS_REMAINING     = $00 ; 1 byte
TEXT_PTR                 = $01 ; 2 bytes
MULTIPLY_8X8_RESULT_LOW  = $03 ; 1 byte
MULTIPLY_8X8_TEMP        = $04 ; 1 byte

GD_ZERO_PAGE_BASE        = $05 ; 18 bytes

  .org $2000                     ; Loader loads programs to this address
start:
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  ; The initialize_machine routine in this include will set up hardware registers and then
  ; jump to program_start. We do not call a subroutine because for some machine designs the
  ; stack is not usable until after the hardware registers have been initialized
  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include multiply8x8.inc
  .include graphics_display.inc

program_start:
  ; Initialize stack
  ldx #$ff
  txs

  jsr gd_prepare_vertical

  jsr gd_select
  jsr show_some_text
  jsr gd_unselect

  stp


show_some_text:
  lda #<message_text
  sta TEXT_PTR
  lda #>message_text
  sta TEXT_PTR + 1
  lda #GD_CHAR_COLS
  sta LINE_CHARS_REMAINING
.show_spaces_loop:
  lda LINE_CHARS_REMAINING
  beq .skip_remaining_spaces
  lda (TEXT_PTR)
  beq .done
  cmp #' '
  bne .show_text
  jsr gd_show_character
  jsr gd_next_character
  dec LINE_CHARS_REMAINING
  inc TEXT_PTR
  bne .show_spaces_loop
  inc TEXT_PTR + 1
  bra .show_spaces_loop
.show_text:
  lda (TEXT_PTR)
  beq .done
; look for end of word
  ldy #1
.word_search_loop:
  lda (TEXT_PTR),Y
  beq .found_word_end
  cmp #' '
  beq .found_word_end
  iny
  cpy #GD_CHAR_COLS
  bne .word_search_loop
.found_word_end:
; will word fit on line?
  cpy LINE_CHARS_REMAINING
  bcc .word_fits
  beq .word_fits
; word does not fit
.finish_line_loop:
  lda #' '
  jsr gd_show_character
  jsr gd_next_character
  dec LINE_CHARS_REMAINING
  bne .finish_line_loop
  lda #GD_CHAR_COLS
  sta LINE_CHARS_REMAINING
.word_fits:
.show_word_loop:
  lda (TEXT_PTR)
  jsr gd_show_character
  jsr gd_next_character
  dec LINE_CHARS_REMAINING
  inc TEXT_PTR
  bne .over
  inc TEXT_PTR + 1
.over:
  dey
  bne .show_word_loop
  bra .show_spaces_loop
.skip_remaining_spaces:
  lda #GD_CHAR_COLS
  sta LINE_CHARS_REMAINING
.skip_spaces_loop:
  lda (TEXT_PTR)
  beq .done
  cmp #' '
  bne .show_text
  inc TEXT_PTR
  bne .skip_spaces_loop
  inc TEXT_PTR + 1
  bra .skip_spaces_loop
.done:
  lda LINE_CHARS_REMAINING
  cmp #GD_CHAR_COLS
  beq .exit
.finish_last_line_loop:
  lda #' '
  jsr gd_show_character
  jsr gd_next_character
  dec LINE_CHARS_REMAINING
  bne .finish_last_line_loop
.exit:
  rts

message_text: .asciiz "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."

;message_text: .asciiz "  a 1234567890123456789 b 12345678901234567890 c 123456789012345678901 d e the quick brown fox. 123456789"
