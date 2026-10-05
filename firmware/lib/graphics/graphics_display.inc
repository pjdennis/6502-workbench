CHAR_6x8   = 0
CHAR_12x16 = 1

CHAR_RESOLUTION=CHAR_12x16

  .if CHAR_RESOLUTION == CHAR_6x8

  .include character_patterns_6x8.inc
character_patterns = character_patterns_6x8
GD_CHAR_WIDTH  = 6
GD_CHAR_HEIGHT = 8
GD_CHAR_ROWS   = 40
GD_CHAR_COLS   = 40
GDC_CURSOR_HEIGHT = 1

  .endif

  .if CHAR_RESOLUTION == CHAR_12x16

  .include character_patterns_12x16.inc
character_patterns = character_patterns_12x16
GD_CHAR_WIDTH  = 12
GD_CHAR_HEIGHT = 16
GD_CHAR_ROWS   = 20
GD_CHAR_COLS   = 20
GDC_CURSOR_HEIGHT = 2
  .endif

  .include macros.inc
  .include graphics_macros.inc


; The display is reached through the FPGA bus (fpga_bus.inc): E (PA2) strobes each byte on port B, and RS (PA5)
; chooses between the bus's commands (low) and data (high). gd_select raises RS, so every byte strobed until
; gd_unselect is display data (the fast paths: gd_send_data, send_zero_data, gd_send_x2); gd_send_command
; sends the bus's DISP_COMMAND, then the display's command as its argument.
;
; With GD_PIN_INTERFACE defined, it drives the older interface instead (the spi-display FPGA design, before
; the bus), which has pins of its own for the display: E, CSB (select), RSTB (reset) and DC (data/command,
; on PA5). Only michael_fpga_input_check.s, which checks that interface's wiring, defines it.
;
; GD_E on GD_PORT is the strobe for whichever interface it is (the bus's E, or the pin interface's), for the
; code that serves both: gd_send_data, the fill loops and the macros. Code for one interface uses its own
; names: PORTA, RS and RW for the bus, as fpga_bus.inc does.
GD_PORT = PORTA
  .ifdef GD_PIN_INTERFACE
GD_E    = %00000001
GD_CSB  = %00000010
GD_RSTB = %00000100
GD_DC   = %00100000
  .else
  .include fpga_bus.inc
GD_E    = FB_E
  .endif

GD_CHAR_BYTES = GD_CHAR_WIDTH * GD_CHAR_HEIGHT / 8

BYTES_PER_PIXEL          = 2
BYTES_PER_SEND_ZERO_LOOP = 16

  .include ili9341.inc

GD_CMD_PTR           = GD_ZERO_PAGE_BASE + $00 ; 2 bytes
GD_COLOR             = GD_ZERO_PAGE_BASE + $02 ; 2 bytes
GD_ROW               = GD_ZERO_PAGE_BASE + $04 ; 1 byte
GD_COL               = GD_ZERO_PAGE_BASE + $05 ; 1 byte
GD_X                 = GD_ZERO_PAGE_BASE + $06 ; 2 bytes
GD_Y                 = GD_ZERO_PAGE_BASE + $08 ; 2 bytes
GD_TEMP              = GD_ZERO_PAGE_BASE + $0a ; 2 bytes
GD_CHAR_DATA_PTR     = GD_ZERO_PAGE_BASE + $0c ; 2 bytes
GD_STRING_PTR        = GD_ZERO_PAGE_BASE + $0e ; 2 bytes
GD_BYTE              = GD_ZERO_PAGE_BASE + $10 ; 1 byte
GD_SCROLL_ROWS       = GD_ZERO_PAGE_BASE + $11 ; 1 byte
GD_ZERO_PAGE_STOP    = GD_ZERO_PAGE_BASE + $12


gd_prepare_vertical:
  jsr gd_configure
  jsr gd_reset

  jsr gd_select
  jsr gd_initialize

; set screen orientation
  gd_send_command_immediate ILI9341_MADCTL
; Original value was ILI9341_MADCTL_MX | ILI9341_MADCTL_BGR
  gd_send_data_immediate ILI9341_MADCTL_MY | ILI9341_MADCTL_MV | ILI9341_MADCTL_BGR

  jsr gd_clear_screen
  jsr gd_unselect

  stz GD_ROW
  stz GD_COL
  rts


  .ifdef GD_PIN_INTERFACE

gd_configure:
  lda #GD_E
  trb PORTA
  lda #GD_RSTB | GD_CSB
  tsb PORTA
  lda #GD_E | GD_RSTB | GD_CSB
  tsb DDRA
  rts


gd_select:
  pha
  lda #GD_DC
  tsb GD_PORT
  tsb GD_PORT + DDR_OFFSET
  lda #GD_CSB
  trb GD_PORT
  pla
  rts


gd_unselect:
  pha
  lda #GD_CSB
  tsb GD_PORT
  lda #GD_DC
  trb GD_PORT
  pla
  rts


gd_reset:
  pha
  lda #1 ; could be 1 ms
  jsr delay_hundredths
  lda #GD_RSTB
  trb GD_PORT
  lda #1 ; 10 ms
  jsr delay_hundredths
  lda #GD_RSTB
  tsb GD_PORT
  lda #12 ; 120 ms
  jsr delay_hundredths
  pla
  rts


gd_send_command:
  pha
  lda #GD_DC
  trb GD_PORT
  pla
  jsr gd_send_data
  lda #GD_DC
  tsb GD_PORT
  rts

  .else

gd_configure = fb_initialize


; Sets RS high (data), so every byte strobed until gd_unselect is display data. RW is low (a write) between
; transfers already (fpga_bus.inc).
; On exit A, X, Y are preserved
gd_select:
  pha
  lda #RS
  tsb PORTA
  pla
  rts


; Sets RS low again, as the LCD routines expect between transfers.
; On exit A, X, Y are preserved
gd_unselect:
  pha
  lda #RS
  trb PORTA
  pla
  rts


; Resets the display through the bus's DISP_RESET: after 10 ms, holds it in reset for 10 ms, then waits
; 120 ms for it to wake.
; On exit A, X, Y are preserved
gd_reset:
  pha
  lda #1 ; could be 1 ms
  jsr delay_hundredths
  lda #FB_DISP_RESET
  jsr fb_command
  lda #0
  jsr fb_data                    ; RESET low
  lda #1 ; 10 ms
  jsr delay_hundredths
  lda #FB_DISP_RESET
  jsr fb_command
  lda #1
  jsr fb_data                    ; RESET high
  lda #12 ; 120 ms
  jsr delay_hundredths
  pla
  rts


; Between gd_select and gd_unselect.
; On entry A = the display command
gd_send_command:
  pha
  lda #RS
  trb PORTA                      ; RS low: the bus's command
  lda #FB_DISP_COMMAND
  jsr gd_send_data
  lda #RS
  tsb PORTA                      ; RS high: its argument, the display's command, then data
  pla
  jmp gd_send_data               ; tail call

  .endif


gd_send_data:
  sta PORTB
  lda #GD_E
  tsb GD_PORT
  trb GD_PORT
  rts


; On entry A = the amount to scroll - 0..19
gd_scroll_up:
  phx
  phy
  clc
  adc GD_SCROLL_ROWS
  cmp #GD_CHAR_ROWS
  bcc .row_ok1
  sec
  sbc #GD_CHAR_ROWS
.row_ok1:
  sta GD_SCROLL_ROWS
  beq .row_ok2
  sec
  lda #GD_CHAR_ROWS
  sbc GD_SCROLL_ROWS
.row_ok2:
  ldy #GD_CHAR_HEIGHT
  jsr multiply8x8
  sta GD_Y + 1
  lda MULTIPLY_8X8_RESULT_LOW
  sta GD_Y

; send command
  gd_send_command_immediate ILI9341_VSCRSADD
  gd_send_word GD_Y

  ply
  plx
  rts


; Input GD_ROW, GD_COL, GD_ROW2, GD_COL2
gd_clear_line:
  .ifdef gdc_clear_line
  jsr gdc_clear_line
  .endif

  stz GD_COL
  jsr x_y_from_row_col
  gd_send_command_immediate ILI9341_CASET
  gd_send_word GD_Y

  add16iTo16usingA GD_Y, GD_CHAR_HEIGHT-1

  gd_send_word GD_Y

  gd_send_command_immediate ILI9341_PASET
  gd_send_word GD_X

  add16iTo16usingA GD_X, ILI9341_TFTWIDTH-1

  gd_send_word GD_X

  gd_send_command_immediate ILI9341_RAMWR

CLEAR_LINE_LOOP_COUNT = -(ILI9341_TFTWIDTH * GD_CHAR_HEIGHT * BYTES_PER_PIXEL / BYTES_PER_SEND_ZERO_LOOP)

  sti16usingA GD_TEMP, CLEAR_LINE_LOOP_COUNT

  jmp send_zero_data ; tail call


gd_clear_screen:
  .ifdef gdc_char_buffer_clear
  jsr gdc_char_buffer_clear
  .endif

  gd_send_command_immediate ILI9341_DISPOFF

  gd_send_command_immediate ILI9341_CASET
  gd_send_word_immediate 0
  gd_send_word_immediate ILI9341_TFTHEIGHT-1

  gd_send_command_immediate ILI9341_PASET
  gd_send_word_immediate 0
  gd_send_word_immediate ILI9341_TFTWIDTH-1

  gd_send_command_immediate ILI9341_RAMWR

CLEAR_SCREEN_LOOP_COUNT = -(ILI9341_TFTWIDTH * ILI9341_TFTHEIGHT * BYTES_PER_PIXEL / BYTES_PER_SEND_ZERO_LOOP)

  sti16usingA GD_TEMP, CLEAR_SCREEN_LOOP_COUNT

  jsr send_zero_data

  gd_send_command_immediate ILI9341_DISPON

  rts


send_zero_data:
  lda #0
  sta PORTB

  lda GD_PORT
  and #~GD_E
  tax
  ldy #0
  ora #GD_E

  .macro .toggleX2
  sta PORTA,Y
  stx PORTA
  sta PORTA,Y
  stx PORTA
  .endm

.loop:
  .toggleX2 ;  2
  .toggleX2 ;  4
  .toggleX2 ;  6
  .toggleX2 ;  8
  .toggleX2 ; 10
  .toggleX2 ; 12
  .toggleX2 ; 14
  .toggleX2 ; 16

  inc GD_TEMP
  bne .loop
  inc GD_TEMP + 1
  bne .loop

  rts


gd_show_string:
  .loop:
  lda (GD_STRING_PTR)
  beq .done
  cmp #'\n'
  beq .newline
  jsr gd_show_character
  jsr gd_next_character
.continue:
  inc GD_STRING_PTR
  bne .loop
  inc GD_STRING_PTR + 1
  bne .loop
.done:
  rts
.newline
  stz GD_COL
  inc GD_ROW
  bra .continue


; On entry A contains the character to display (in ASCII)
; On exit X, Y are preserved
;         A is not preserved
gd_show_character:
  phx
  phy

  .ifdef gdc_char_store
  jsr gdc_char_store
  .endif

  jsr set_char_data_ptr
  jsr x_y_from_row_col

  gd_send_command_immediate ILI9341_CASET
  gd_send_word GD_Y
  add8iTo16usingA GD_Y, GD_CHAR_HEIGHT-1
  gd_send_word GD_Y

  gd_send_command_immediate ILI9341_PASET
  gd_send_word GD_X
  add8iTo16usingA GD_X, GD_CHAR_WIDTH-1
  gd_send_word GD_X

  gd_send_command_immediate ILI9341_RAMWR

  ldy #0
.col_loop:
  lda (GD_CHAR_DATA_PTR),Y
  sta GD_BYTE
  ldx #8
.row_loop:
  lsr GD_BYTE
  bcc .low_bit
  gd_send_x2 >ILI9341_WHITE ; relies on high and low bits being the same
  bra .color_done
.low_bit:
  gd_send_x2 >ILI9341_BLACK ; relies on high and low bits being the same
.color_done:
  dex
  bne .row_loop
  iny
  cpy #GD_CHAR_BYTES
  bne .col_loop
  ply
  plx
  rts


; On exit X, Y are preserved
;         A is not preserved
gd_next_character:
  lda GD_COL
  inc
  cmp #GD_CHAR_COLS
  beq .next_row
  sta GD_COL
  rts
.next_row:
  lda GD_ROW
  cmp #GD_CHAR_ROWS-1
  beq .at_bottom
  stz GD_COL
  inc GD_ROW
  rts
.at_bottom
  rts


gd_previous_character:
  lda GD_COL
  dec
  cmp #$ff
  beq .previous_row
  sta GD_COL
  rts
.previous_row:
  lda GD_ROW
  beq .at_top
  lda #GD_CHAR_COLS-1
  sta GD_COL
  dec GD_ROW
  rts
.at_top:
  rts

; On exit X, Y are preserved
;         A is not preserved
gd_next_line:
  lda GD_ROW
  cmp #GD_CHAR_ROWS-1
  beq .row_ready
  inc GD_ROW
.row_ready:
  stz GD_COL
  rts


set_char_data_ptr:
  ; calculate character offset
  sec
  sbc #' '

  ; GD_CHAR_DATA_PTR = character offset * 24
  ldy #GD_CHAR_BYTES
  jsr multiply8x8
  sta GD_CHAR_DATA_PTR + 1

  ; Add the table base address
  clc
  lda MULTIPLY_8X8_RESULT_LOW
  adc #<character_patterns
  sta GD_CHAR_DATA_PTR
  lda GD_CHAR_DATA_PTR + 1
  adc #>character_patterns
  sta GD_CHAR_DATA_PTR + 1
  rts


x_y_from_row_col:
  ; GD_Y = GD_ROW * GD_CHAR_HEIGHT
  clc
  lda GD_ROW
  adc GD_SCROLL_ROWS
  cmp #GD_CHAR_ROWS 
  bcc .row_ok
  sec
  sbc #GD_CHAR_ROWS
.row_ok:
  ldy #GD_CHAR_HEIGHT
  jsr multiply8x8
  sta GD_Y + 1
  lda MULTIPLY_8X8_RESULT_LOW
  sta GD_Y
  ; GD_X = GD_COL * GD_CHAR_WIDTH
  lda GD_COL
  ldy #GD_CHAR_WIDTH
  jsr multiply8x8
  sta GD_X + 1
  lda MULTIPLY_8X8_RESULT_LOW
  sta GD_X
  rts


gd_initialize:
  pha
  phx
  phy
  stz GD_SCROLL_ROWS ; TODO: maybe there's a better place to handle this kind of initialization
  lda #<INIT_COMMANDS
  sta GD_CMD_PTR
  lda #>INIT_COMMANDS
  sta GD_CMD_PTR + 1
.loop:
  jsr .next_byte
  cmp #0
  beq .done
  jsr gd_send_command
  jsr .next_byte
  tay
  and #$7f
  tax
  beq .param_done
.param_loop:
  jsr .next_byte
  jsr gd_send_data
  dex
  bne .param_loop
.param_done:
  tya
  and #$80
  beq .loop
  jsr .delay
  bra .loop
.done:
  ply
  plx
  pla
  rts
.next_byte:
  lda (GD_CMD_PTR)
  inc GD_CMD_PTR
  bne .next_byte_over
  inc GD_CMD_PTR + 1
.next_byte_over:
  rts
.delay:
  lda #15
  jsr delay_hundredths
  rts


  .include ili9341_init_commands.inc
