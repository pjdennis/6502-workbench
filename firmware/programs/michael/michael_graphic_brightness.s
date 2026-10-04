; Explores the display's backlight brightness: the FPGA bus's BACKLIGHT command ($13), 0 (off) to 255 (fully
; on), which the FPGA turns into PWM. The display shows the level, the PWM duty and a bar; the LCD shows the
; level too, so it can still be read with the backlight off.
;
; Keys: up/down   +1/-1          + and -   +1/-1
;       right/left +16/-16        0-9       presets, from off (0) to full (9)
; The level never goes past 0 or 255. Each key sends its level at once, but the screens are redrawn only
; when no keys are waiting, so a held key's repeats don't pile up behind the drawing.
  .include base_config_v2.inc

INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET

CP_M_DEST_P              = $00 ; 2 bytes
CP_M_SRC_P               = $02 ; 2 bytes
CP_M_LEN                 = $04 ; 2 bytes
SIMPLE_BUFFER_WRITE_PTR  = $06 ; 1 byte
SIMPLE_BUFFER_READ_PTR   = $07 ; 1 byte
DISPLAY_STRING_PARAM     = $08 ; 2 bytes
MULTIPLY_8X8_RESULT_LOW  = $0a ; 1 byte
MULTIPLY_8X8_TEMP        = $0b ; 1 byte
LEVEL                    = $0c ; 1 byte: the brightness
DIGITS                   = $0d ; 3 bytes: a number in decimal, as characters
BAR                      = $10 ; 1 byte: the bar's length
CHANGED                  = $11 ; 1 byte: non-zero when LEVEL hasn't been shown yet
GD_ZERO_PAGE_BASE        = $12 ; 18 bytes
KB_ZERO_PAGE_BASE        = GD_ZERO_PAGE_STOP

SIMPLE_BUFFER            = $0200 ; 256 bytes

BAR_ROW                  = 7

  .org PROGRAM_LOAD_ADDRESS
start:
  jmp initialize_machine

  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_string.inc
  .include simple_buffer.inc
  .include copy_memory.inc
  .include key_codes.inc
  .include keyboard_typematic.inc
KB_BUFFER_INITIALIZE = simple_buffer_initialize
KB_BUFFER_WRITE      = simple_buffer_write
KB_BUFFER_READ       = simple_buffer_read
callback_key_up      = brighter_by_1
callback_key_down    = dimmer_by_1
callback_key_right   = brighter_by_16
callback_key_left    = dimmer_by_16
  .include keyboard_driver.inc
  .include multiply8x8.inc
  .include graphics_display.inc

program_start:
  ldx #$ff
  txs

  jsr reset_and_enable_display_no_cursor
  jsr gd_prepare_vertical
  jsr gd_select
  lda #<screen
  sta GD_STRING_PTR
  lda #>screen
  sta GD_STRING_PTR + 1
  stz GD_ROW
  stz GD_COL
  jsr gd_show_string
  jsr gd_unselect

  lda #255
  jsr set_level
  jsr keyboard_initialize        ; Enables interrupts

.keys:
  jsr keyboard_get_char          ; The arrow keys are handled on the way, by the callbacks above
  bcc .key
  lda CHANGED                    ; No keys waiting: catch the screens up
  beq .keys
  stz CHANGED
  jsr show_level
  bra .keys
.key:
  cmp #'+'
  beq .brighter
  cmp #'='                       ; + without shift
  beq .brighter
  cmp #'-'
  beq .dimmer
  cmp #'0'
  bcc .keys
  cmp #'9' + 1
  bcs .keys
  sec
  sbc #'0'
  tax
  lda presets,X
  jsr set_level
  bra .keys
.brighter:
  jsr brighter_by_1
  bra .keys
.dimmer:
  jsr dimmer_by_1
  bra .keys


presets: .byte 0, 28, 57, 85, 113, 142, 170, 198, 227, 255

screen:
  .byte " BACKLIGHT TEST\n\n\n"
  .byte "LEVEL     /255\n"
  .byte "DUTY      %\n\n\n\n\n\n"
  .byte "UP/DOWN      +1/-1\n"
  .byte "RIGHT/LEFT +16/-16\n"
  .byte "+ AND -      +1/-1\n"
  .byte "0-9 PRESETS\n"
  .byte "  0 OFF ... 9 FULL\n\n"
  .byte "THE QUICK BROWN FOX\n"
  .byte "JUMPS OVER THE LAZY\n"
  .asciiz "DOG 0123456789"

lcd_label: .asciiz "BACKLIGHT "


; Changes LEVEL by a signed amount, staying within 0-255, and sends it.
; On exit X, Y are preserved
brighter_by_1:
  lda #1
  bra change_level
dimmer_by_1:
  lda #$ff
  bra change_level
brighter_by_16:
  lda #16
  bra change_level
dimmer_by_16:
  lda #$f0
change_level:
  cmp #0
  bmi .down
  clc
  adc LEVEL
  bcc .set
  lda #255                       ; Past 255
  bra .set
.down:
  clc
  adc LEVEL
  bcs .set
  lda #0                         ; Past 0
.set:
  ; fall through


; LEVEL = A, sent to the FPGA; shown later, by show_level.
; On exit X, Y are preserved
set_level:
  sta LEVEL
  lda #FB_BACKLIGHT              ; Outside gd_select: fb_data leaves RS low
  jsr fb_command
  lda LEVEL
  jsr fb_data
  lda #1                         ; LEVEL may be 0
  sta CHANGED
  rts


; Shows LEVEL on the display and the LCD.
show_level:

  ; The LCD
  lda #DISPLAY_FIRST_LINE
  jsr move_cursor
  lda #<lcd_label
  ldx #>lcd_label
  jsr display_string
  lda LEVEL
  jsr to_digits
  ldx #0
.lcd_digit:
  lda DIGITS,X
  jsr display_character
  inx
  cpx #3
  bne .lcd_digit

  ; The display: level, duty and bar
  jsr gd_select
  lda #3
  ldx #6
  ldy LEVEL
  jsr show_number_at
  lda LEVEL                      ; Duty: LEVEL * 100 / 256, and 255 is fully on
  cmp #255
  beq .full
  ldy #100
  jsr multiply8x8
  bra .duty
.full:
  lda #100
.duty:
  tay
  lda #4
  ldx #6
  jsr show_number_at

  lda LEVEL                      ; Bar: LEVEL * 20 / 256, and 255 is all of it
  cmp #255
  beq .bar_full
  ldy #GD_CHAR_COLS
  jsr multiply8x8
  bra .bar_length
.bar_full:
  lda #GD_CHAR_COLS
.bar_length:
  sta BAR
  lda #BAR_ROW
  sta GD_ROW
  stz GD_COL
  ldx #0
.bar:
  lda #'#'
  cpx BAR
  bcc .bar_char
  lda #'-'
.bar_char:
  jsr gd_show_character
  jsr gd_next_character
  inx
  cpx #GD_CHAR_COLS
  bne .bar
  jsr gd_unselect
  rts


; Shows a number (0-255), right aligned in 3 characters, on the display.
; On entry A = row, X = column, Y = the number
show_number_at:
  sta GD_ROW
  stx GD_COL
  tya
  jsr to_digits
  ldx #0
.digit:
  lda DIGITS,X
  jsr gd_show_character
  jsr gd_next_character
  inx
  cpx #3
  bne .digit
  rts


; DIGITS = A in decimal: three characters, with leading spaces.
; On exit X, Y are preserved
to_digits:
  phx
  ldx #'0' - 1
.hundreds:
  inx
  sec
  sbc #100
  bcs .hundreds
  adc #100
  stx DIGITS
  ldx #'0' - 1
.tens:
  inx
  sec
  sbc #10
  bcs .tens
  adc #10 + '0'
  sta DIGITS + 2
  stx DIGITS + 1
  lda DIGITS                     ; Leading zeros as spaces
  cmp #'0'
  bne .done
  lda #' '
  sta DIGITS
  lda DIGITS + 1
  cmp #'0'
  bne .done
  lda #' '
  sta DIGITS + 1
.done:
  plx
  rts
