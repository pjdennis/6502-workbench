; Types on the FPGA's text mode (stage 3 of docs/michael-fpga-bus-plan.md): the FPGA keeps the 20 by 20 grid of
; characters and draws it, so each key is a few bytes on the bus, not a character's 400. Row 0 is a title;
; rows 1-19 are the scroll region. The keys try out the text mode's operations: inserting characters, and
; inserting, deleting and scrolling lines, the scrolls of the whole region by the display's hardware scroll.
;
; Keys: characters inserted at the cursor (the line's last drops off); past the bottom row's end the
;                  region scrolls up
;       Enter      a new line below (on the bottom row the region scrolls up)
;       Backspace  delete to the left    Delete  delete the line (the lines below move up)
;       arrows     move                  Tab     reverse video on/off      Esc  clear
;       Page Up, Page Down  the backlight brighter, dimmer: 0, 1, 3, 7 ... 127, 255 (halving down)
;       Alt and two hex digits  types that code, from $20 up: the font's glyphs, code page 437's (a control
;                  code is dropped, as is a first digit followed by anything else)
; Michael keeps the cursor's position itself, by the text mode's rules, and never reads it back.
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
ROW                      = $0c ; 1 byte: the cursor's, 1-19
COL                      = $0d ; 1 byte: the cursor's, 0-19, or 20 past the end of the bottom row
REVERSE                  = $0e ; 1 byte: 0 normal video, 1 reverse
BRIGHTNESS               = $0f ; 1 byte: the backlight's level
HEX_COUNT                = $10 ; 1 byte: Alt's hex digits so far, 0 or 1
HEX_HIGH                 = $11 ; 1 byte: the first of them, in the high nibble
GD_ZERO_PAGE_BASE        = $12 ; 18 bytes
KB_ZERO_PAGE_BASE        = GD_ZERO_PAGE_STOP

SIMPLE_BUFFER            = $0200 ; 256 bytes

TEXT_ROWS                = 20
TEXT_COLS                = 20
FIRST_ROW                = 1   ; of the region: row 0 is the title

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
callback_key_up      = cursor_up
callback_key_down    = cursor_down
callback_key_left    = cursor_left
callback_key_right   = cursor_right
callback_key_esc     = clear_region
callback_key_delete  = delete_line
callback_key_pageup  = brighter
callback_key_pagedown = dimmer
  .include keyboard_driver.inc
  .include multiply8x8.inc
  .include graphics_display.inc

program_start:
  ldx #$ff
  txs

  jsr reset_and_enable_display_no_cursor
  lda #<lcd_message
  ldx #>lcd_message
  jsr display_string

  jsr gd_prepare_vertical          ; Initialises the display, through the raw display commands
  lda #$ff                         ; Fully on, whatever ran before left
  sta BRIGHTNESS
  jsr send_brightness
  lda #FB_T_ON
  jsr fb_text
  lda #1
  jsr video
  ldx #0
.title:
  lda title,X
  beq .title_done
  jsr put
  inx
  bra .title
.title_done:
  lda #0
  jsr video
  lda #FB_T_REGION
  jsr fb_text
  lda #FIRST_ROW
  jsr fb_data
  lda #TEXT_ROWS - 1
  jsr fb_data
  lda #FB_T_CURSOR
  jsr fb_text
  lda #1
  jsr fb_data
  stz REVERSE
  lda #FIRST_ROW
  sta ROW
  stz COL
  jsr goto
  jsr keyboard_initialize          ; Enables interrupts

.keys:
  jsr keyboard_get_char            ; The arrows and Esc are handled on the way, by the callbacks above
  bcs .keys
  pha
  lda KEYBOARD_LATEST_META
  and #KB_META_ALT
  beq .not_alt
  pla
  jsr alt_hex
  bra .keys
.not_alt:
  stz HEX_COUNT                    ; Alt's code unfinished: dropped
  pla
  cmp #KEY_ENTER
  beq .enter
  cmp #KEY_BACKSPACE
  beq .backspace
  cmp #KEY_TAB
  beq .tab
  cmp #' '
  bcc .keys
  cmp #$7f
  bcs .keys
  jsr type_char
  bra .keys
.enter:
  lda ROW
  cmp #TEXT_ROWS - 1
  bcs .scroll
  inc ROW                          ; A new line below: the lines under it move down
  jsr goto
  lda #FB_T_INSERT_LINES
  jsr fb_text
  lda #1
  jsr fb_data
  stz COL                          ; (where INSERT_LINES leaves the cursor)
  bra .keys
.scroll:
  jsr new_bottom_line
  bra .keys
.backspace:
  lda COL
  beq .keys
  dec COL
  jsr goto
  lda #FB_T_DELETE
  jsr fb_text
  lda #1
  jsr fb_data
  bra .keys
.tab:
  lda REVERSE
  eor #1
  sta REVERSE
  jsr video
  bra .keys


title:        .asciiz " MICHAEL TEXT MODE  "
lcd_message:  .asciiz "TEXT MODE ON THE FPGA"


; Writes the character in A at the cursor.
; On exit X, Y are preserved
put:
  pha
  lda #FB_T_PUT
  jsr fb_text
  pla
  jmp fb_data                      ; tail call


; Normal (A = 0) or reverse (1) video from here on.
; On exit X, Y are preserved
video:
  pha
  lda #FB_T_VIDEO
  jsr fb_text
  pla
  jmp fb_data                      ; tail call


; Moves the text mode's cursor to ROW, COL.
; On exit X, Y are preserved
goto:
  lda #FB_T_GOTO
  jsr fb_text
  lda ROW
  jsr fb_data
  lda COL
  jmp fb_data                      ; tail call


; The arrows' callbacks: the cursor stays in the region.
; On exit X, Y are preserved
cursor_up:
  lda ROW
  cmp #FIRST_ROW + 1
  bcc cursor_stays
  dec ROW
  bra goto
cursor_down:
  lda ROW
  cmp #TEXT_ROWS - 1
  bcs cursor_stays
  inc ROW
  bra goto
cursor_left:
  lda COL
  beq cursor_stays
  dec COL
  bra goto
cursor_right:
  lda COL
  cmp #TEXT_COLS - 1
  bcs cursor_stays
  inc COL
  bra goto
cursor_stays:
  rts


; Scrolls the region up a row.
; On exit X, Y are preserved
scroll_up:
  lda #1
  ; fall through

; Scrolls the region up A rows.
; On exit X, Y are preserved
scroll_up_a:
  pha
  lda #FB_T_SCROLL_UP
  jsr fb_text
  pla
  jmp fb_data                      ; tail call


; Esc's callback: the region scrolled clear, and the cursor to its start.
; On exit X, Y are preserved
clear_region:
  lda #TEXT_ROWS - FIRST_ROW
  jsr scroll_up_a
  lda #FIRST_ROW
  sta ROW
  stz COL
  bra goto


; Inserts the character in A at the cursor (the rest of the line moves right, its last character dropping
; off), and moves on: to the next row after the last column, or past the bottom row's end, scrolling.
; On exit X, Y are preserved
type_char:
  pha
  lda #FB_T_INSERT                 ; Room for it
  jsr fb_text
  lda #1
  jsr fb_data
  pla
  jsr put
  inc COL                          ; The text mode's rule: to the next row after the last column, but not
  lda COL                          ; past the bottom one
  cmp #TEXT_COLS
  bne .done
  lda ROW
  cmp #TEXT_ROWS - 1
  bcs new_bottom_line              ; Past the bottom row's end: the region scrolls up
  inc ROW
  stz COL
.done:
  rts

; The region scrolled up a row, and the cursor to the start of the bottom row.
; On exit X, Y are preserved
new_bottom_line:
  jsr scroll_up
  stz COL
  jmp goto                         ; tail call

; A key with Alt held: two hex digits type the code they make, from $20 up (a control code is dropped);
; anything else drops a first digit.
; On entry A = the key's character
alt_hex:
  jsr hex_value
  bcs .drop
  ldy HEX_COUNT
  bne .second
  asl
  asl
  asl
  asl
  sta HEX_HIGH
  inc HEX_COUNT
  rts
.second:
  ora HEX_HIGH
  stz HEX_COUNT
  cmp #' '
  bcs type_char                    ; tail call
  rts
.drop:
  stz HEX_COUNT
  rts

; The hex digit in A ('0'-'9', 'a'-'f', 'A'-'F'): C clear and A its value, 0-15; else C set.
; On exit X, Y are preserved
hex_value:
  sec
  sbc #'0'
  cmp #10
  bcc .done                        ; '0'-'9'
  ora #$20                         ; 'A'-'F' as 'a'-'f' (less '0')
  sec
  sbc #'a' - '0'
  cmp #6
  bcs .done                        ; not a hex digit (C set)
  adc #10                          ; 'a'-'f' (C clear, and stays so)
.done:
  rts


; Page Up's callback: the backlight a step brighter (doubled, and 1 more), up to 255.
; On exit X, Y are preserved
brighter:
  lda BRIGHTNESS
  cmp #$ff
  beq brightness_stays
  sec
  rol
  bra brightness_to_a

; Page Down's callback: the backlight a step dimmer (halved), down to 0 (off).
; On exit X, Y are preserved
dimmer:
  lda BRIGHTNESS
  beq brightness_stays
  lsr
brightness_to_a:
  sta BRIGHTNESS
  ; fall through

; Sends BRIGHTNESS to the backlight.
; On exit X, Y are preserved
send_brightness:
  lda #FB_BACKLIGHT
  jsr fb_command
  lda BRIGHTNESS
  jmp fb_data                      ; tail call
brightness_stays:
  rts


; Delete's callback: the cursor's line deleted, the lines below moving up, and the cursor to its start.
; On exit X, Y are preserved
delete_line:
  lda #FB_T_DELETE_LINES
  jsr fb_text
  lda #1
  jsr fb_data
  stz COL                          ; (where DELETE_LINES leaves the cursor)
  rts
