  .include base_config_v2.inc
  .include macros.inc

INTERRUPT_ROUTINE        = $3f00

TAB_WIDTH                = 4
CURSOR_FLASH_DELAY       = 25  ; hundredths of a second

CP_M_DEST_P              = $00 ; 2 bytes
CP_M_SRC_P               = $02 ; 2 bytes
CP_M_LEN                 = $04 ; 2 bytes

CREATE_CHARACTER_PARAM   = $06 ; 2 bytes

SIMPLE_BUFFER_WRITE_PTR  = $08 ; 1 byte
SIMPLE_BUFFER_READ_PTR   = $09 ; 1 byte

DISPLAY_STRING_PARAM     = $0A ; 2 bytes
TEXT_PTR                 = $0C ; 2 bytes
TEXT_PTR_NEXT            = $0E ; 2 bytes
SCROLL_OFFSET            = $10 ; 2 bytes
LINE_CHARS_REMAINING     = $12 ; 1 byte
MULTIPLY_8X8_RESULT_LOW  = $13 ; 1 byte
MULTIPLY_8X8_TEMP        = $14 ; 1 byte
FLASH_COUNTER            = $15 ; 1 byte
MAX_ROW                  = $16 ; 1 byte

GD_ZERO_PAGE_BASE        = $17
GDC_ZERO_PAGE_BASE       = GD_ZERO_PAGE_STOP
KB_ZERO_PAGE_BASE        = GDC_ZERO_PAGE_STOP
TO_DECIMAL_PARAM         = KB_ZERO_PAGE_STOP

SIMPLE_BUFFER            = $0200 ; 256 bytes
LINE_LENGTHS             = $0300 ; GD_CHAR_COLS bytes 
GDC_CHAR_BUFFER          = $0400 ; GD_CHAR_ROWS * GD_CHAR_COLS bytes

  .org $2000                     ; Loader loads programs to this address
start:
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  ; The initialize_machine routine in this include will set up hardware registers and then
  ; jump to program_start. We do not call a subroutine because for some machine designs the
  ; stack is not usable until after the hardware registers have been initialized
  .include delay_routines.inc
  .include initialize_machine_v2.inc
EXTEND_CHARACTER_SET = 1
  .include display_routines.inc
  .include display_string.inc
  .include simple_buffer.inc
  .include copy_memory.inc
  .include key_codes.inc
  .include keyboard_typematic.inc
KB_BUFFER_INITIALIZE = simple_buffer_initialize
KB_BUFFER_WRITE      = simple_buffer_write
KB_BUFFER_READ       = simple_buffer_read
callback_key_left    = handle_left
callback_key_right   = handle_right
callback_key_up      = handle_up
callback_key_down    = handle_down
callback_key_f1      = handle_f1
;KEYBOARD_RATE_AND_DELAY = KEYBOARD_RATE_4_3_CPS | KEYBOARD_DELAY_0_50_S
  .include keyboard_driver.inc
  .include display_hex.inc
  .include multiply8x8.inc
  .include graphics_display_cursor.inc
  .include graphics_display.inc
  .include display_decimal.inc
 
program_start:
  ; Initialize stack
  ldx #$ff
  txs

  jsr gd_prepare_vertical
  jsr set_line_length

  jsr cursor_on
  stz FLASH_COUNTER
  stz MAX_ROW

  jsr reset_and_enable_display_no_cursor

  ldaxi last_key_message
  jsr display_string
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  ldaxi line_length_message
  jsr display_string

  jsr display_line_length

  jsr keyboard_initialize

  ; Read and display translated characters from the keyboard

get_char_loop:
  lda FLASH_COUNTER
  cmp #CURSOR_FLASH_DELAY
  bne .not_invert
  jsr gd_select
  jsr cursor_invert
  jsr gd_unselect
  stz FLASH_COUNTER
.not_invert:
  inc FLASH_COUNTER
  lda #1
  jsr delay_hundredths
  jsr keyboard_get_char
  bcs get_char_loop
get_char_loop_2:
  jsr callback_char_received
  jsr keyboard_get_char
  bcc get_char_loop_2
  bra get_char_loop


last_key_message:    .asciiz "Last key:"
line_length_message: .asciiz "Line len:"


callback_char_received:
  jsr display_received_character
  jsr gd_select
  jsr cursor_off
  jsr write_character_to_screen
  jsr cursor_on
  jsr gd_unselect
  jsr display_line_length
  stz FLASH_COUNTER
  rts


write_character_to_screen:
  jsr move_to_end
  cmp #ASCII_BACKSPACE
  beq .backspace
  cmp #ASCII_TAB
  beq .tab
  cmp #ASCII_LF
  beq .newline
; Normal character
  jsr gd_show_character
  inc GD_COL
  jsr set_line_length
  lda GD_COL
  cmp #GD_CHAR_COLS
  bne .not_last_char
  lda GD_ROW
  cmp #GD_CHAR_ROWS - 1
  bne .not_last_char
  jsr do_scroll
  jsr set_line_length
  bra .done
.not_last_char:
  lda GD_COL
  cmp #GD_CHAR_COLS
  bne .done
; at last character on line
  stz GD_COL
  inc GD_ROW
  jsr set_line_length
  bra .done
.backspace:
  lda GD_ROW
  bne .not_first_char
  lda GD_COL
  beq .done
.not_first_char:
  jsr move_position_back
  jsr set_line_length
  lda #' '
  jsr gd_show_character
  bra .done
.tab:
  jsr do_tab
  bra .done
.newline:
  jsr set_line_length
  lda GD_ROW
  cmp #GD_CHAR_ROWS - 1
  bne .not_last_line
  jsr do_scroll
  jsr set_line_length
  bra .done
.not_last_line:
  jsr gd_next_line
  jsr set_line_length
.done:
; Set max row
  lda GD_ROW
  cmp MAX_ROW
  bcc .return
  sta MAX_ROW
.return
  rts


do_tab:
  lda #TAB_WIDTH
.loop:
  cmp #GD_CHAR_COLS
  bcs .next_line
  cmp GD_COL
  beq .over1
  bcs .move_cursor ; A > GD_COL
.over1
  clc
  adc #TAB_WIDTH
  bra .loop
.next_line
  lda #GD_CHAR_COLS
  sta GD_COL
  jsr set_line_length
  lda GD_ROW
  cmp #GD_CHAR_ROWS - 1
  bne .not_last_line
  jsr do_scroll
  jsr set_line_length
  rts
.not_last_line:
  jsr gd_next_line
  jsr set_line_length
  rts
.move_cursor:
  sta GD_COL
  jsr set_line_length
  rts


do_scroll:
  phx
  phy

  stz GD_ROW
  jsr gd_clear_line
  lda #1
  jsr gd_scroll_up
  lda #GD_CHAR_ROWS - 1
  sta GD_ROW
  stz GD_COL
  jsr scroll_line_lengths

  ply
  plx
  rts


move_position_back:
  pha
  lda GD_COL
  beq .previous_line
  dec
  sta GD_COL
  bra .done
.previous_line:
  dec MAX_ROW
  phx
  lda GD_ROW
  dec
  sta GD_ROW
  tax
  lda LINE_LENGTHS,X
  cmp #GD_CHAR_COLS
  bne .non_full_line
  dec
.non_full_line:
  sta GD_COL
  plx
.done:
  pla
  rts


scroll_line_lengths:
  pha
  phx

  ldx #0
.loop
  lda LINE_LENGTHS + 1,X
  sta LINE_LENGTHS,X
  inx
  cpx #GD_CHAR_ROWS - 1
  bne .loop

  plx
  pla
  rts


set_line_length:
  pha
  phx

  ldx GD_ROW
  lda GD_COL
  sta LINE_LENGTHS,X

  plx
  pla
  rts


move_to_end:
  pha
  phx

  lda MAX_ROW
  sta GD_ROW
  tax
  lda LINE_LENGTHS,X
  sta GD_COL

  plx
  pla
  rts


; On entry A = character received
; On exit A, X, Y are preserved
display_received_character:
  phx
  tax
  lda #(DISPLAY_FIRST_LINE + 10)
  jsr move_cursor
  txa
  jsr display_character
  lda #' '
  jsr display_character
  txa
  jsr display_hex
  txa
  plx
  rts


display_line_length:
  pha
  phx

  lda #(DISPLAY_SECOND_LINE + 10)
  jsr move_cursor
  ldaxi .spaces
  jsr display_string
  lda #(DISPLAY_SECOND_LINE + 10)
  jsr move_cursor

  ldx GD_ROW
  lda LINE_LENGTHS,X ; low byte of value to display
  ldx #0             ; high byte of value to display
  jsr display_decimal

  plx
  pla
  rts

.spaces: .asciiz "   "


cursor_on:
  pha
  lda #$ff
  sta GDC_INVERT
  jsr gdc_show_cursor
  pla
  rts


cursor_off:
  pha
  stz GDC_INVERT
  jsr gdc_show_cursor
  pla
  rts


cursor_invert:
  pha
  lda GDC_INVERT
  eor #$ff
  sta GDC_INVERT
  jsr gdc_show_cursor
  pla
  rts


handle_left:
  pha
  jsr gd_select
  jsr cursor_off
  jsr gd_previous_character
  jsr force_col_to_length
  jsr cursor_on
  jsr gd_unselect
  jsr display_line_length
  stz FLASH_COUNTER
  pla
  rts


handle_right:
  pha
  jsr gd_select
  jsr cursor_off
  jsr gd_next_character

  phx
  ldx GD_ROW
  lda LINE_LENGTHS,X
  cmp GD_COL
  bcs .done
  lda GD_ROW
  cmp MAX_ROW
  beq .at_end
  inc GD_ROW
  stz GD_COL
  bra .done
.at_end:
  jsr force_col_to_length
.done:
  plx

  jsr cursor_on
  jsr gd_unselect
  jsr display_line_length
  stz FLASH_COUNTER
  pla
  rts


handle_up:
  pha
  jsr gd_select
  jsr cursor_off

  lda GD_ROW
  beq .skip
  dec GD_ROW
  jsr force_col_to_length
.skip:

  jsr cursor_on
  jsr gd_unselect
  jsr display_line_length
  stz FLASH_COUNTER
  pla
  rts


handle_down:
  pha
  jsr gd_select
  jsr cursor_off

  lda GD_ROW
  cmp MAX_ROW
  beq .skip
  inc GD_ROW
  jsr force_col_to_length
.skip:

  jsr cursor_on
  jsr gd_unselect
  jsr display_line_length
  stz FLASH_COUNTER
  pla
  rts


; Limit cursor column to the length of the current line
; Adjusts GD_COL based on the length of line at GD_ROW
; On exit X, Y are preserved
;         A is not preserved
force_col_to_length:
  phx

  ldx GD_ROW
  lda LINE_LENGTHS,X
  cmp GD_COL
  bcs .done
  sta GD_COL
.done

  plx
  rts




handle_f1:
  pha
  phx
  phy

  jsr gd_select

  ldy #0
.loop:
  lda .f1_text, Y
  beq .done
  jsr write_character_to_screen
  iny
  bra .loop
.done:
  jsr gd_unselect

  ply
  plx
  pla
  rts

.f1_text: .asciiz "The quick brown fox jumps over the lazy dog. "
