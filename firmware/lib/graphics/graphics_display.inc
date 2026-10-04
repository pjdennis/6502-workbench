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


; The display is reached through the FPGA bus (fpga_bus.inc): E (PA0) strobes each byte on port B, and RS (PA5)
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

ILI9341_TFTWIDTH  = 240 ; ILI9341 max TFT width
ILI9341_TFTHEIGHT = 320 ; ILI9341 max TFT height

ILI9341_NOP     = $00 ; No-op register
ILI9341_SWRESET = $01 ; Software reset register
ILI9341_RDDID   = $04 ; Read display identification information
ILI9341_RDDST   = $09 ; Read Display Status

ILI9341_SLPIN  = $10 ; Enter Sleep Mode
ILI9341_SLPOUT = $11 ; Sleep Out
ILI9341_PTLON  = $12 ; Partial Mode ON
ILI9341_NORON  = $13 ; Normal Display Mode ON

ILI9341_RDMODE     = $0a ; Read Display Power Mode
ILI9341_RDMADCTL   = $0b ; Read Display MADCTL
ILI9341_RDPIXFMT   = $0c ; Read Display Pixel Format
ILI9341_RDIMGFMT   = $0d ; Read Display Image Format
ILI9341_RDSELFDIAG = $0f ; Read Display Self-Diagnostic Result

ILI9341_INVOFF   = $20 ; Display Inversion OFF
ILI9341_INVON    = $21 ; Display Inversion ON
ILI9341_GAMMASET = $26 ; Gamma Set
ILI9341_DISPOFF  = $28 ; Display OFF
ILI9341_DISPON   = $29 ; Display ON

ILI9341_CASET = $2a ; Column Address Set
ILI9341_PASET = $2b ; Page Address Set
ILI9341_RAMWR = $2c ; Memory Write
ILI9341_RAMRD = $2e ; Memory Read

ILI9341_PTLAR    = $30 ; Partial Area
ILI9341_VSCRDEF  = $33 ; Vertical Scrolling Definition
ILI9341_MADCTL   = $36 ; Memory Access Control
ILI9341_VSCRSADD = $37 ; Vertical Scrolling Start Address
ILI9341_PIXFMT   = $3a ; COLMOD: Pixel Format Set

ILI9341_FRMCTR1 = $b1 ; Frame Rate Control (In Normal Mode/Full Colors)
ILI9341_FRMCTR2 = $b2 ; Frame Rate Control (In Idle Mode/8 colors)
ILI9341_FRMCTR3 = $b3 ; Frame Rate control (In Partial Mode/Full Colors)
ILI9341_INVCTR  = $b4 ; Display Inversion Control
ILI9341_DFUNCTR = $b6 ; Display Function Control

ILI9341_PWCTR1 = $c0 ; Power Control 1
ILI9341_PWCTR2 = $c1 ; Power Control 2
ILI9341_PWCTR3 = $c2 ; Power Control 3
ILI9341_PWCTR4 = $c3 ; Power Control 4
ILI9341_PWCTR5 = $c4 ; Power Control 5
ILI9341_VMCTR1 = $c5 ; VCOM Control 1
ILI9341_VMCTR2 = $c7 ; VCOM Control 2

ILI9341_RDID1 = $da ; Read ID 1
ILI9341_RDID2 = $db ; Read ID 2
ILI9341_RDID3 = $dc ; Read ID 3
ILI9341_RDID4 = $dd ; Read ID 4

ILI9341_GMCTRP1 = $e0 ; Positive Gamma Correction
ILI9341_GMCTRN1 = $e1 ; Negative Gamma Correction
;ILI9341_PWCTR6 = $fc

; Parameter definitions for the ILI9341_MADCTL command
ILI9341_MADCTL_MY  = %10000000 ; Starts from bottom when set, top otherwise
ILI9341_MADCTL_MX  = %01000000 ; Starts from right of screen when set, left otherwise
ILI9341_MADCTL_MV  = %00100000 ; Orientation vertical when set, horizontal otherwise
ILI9341_MADCTL_ML  = %00010000 ; Affects vertical scrolling orientation
ILI9341_MADCTL_BGR = %00001000 ; LCD pixel color order is BGR when set, RGB otherwise
ILI9341_MADCTL_MH  = %00000100 ; Affects horizontal refresh direction

; Second parameter of the ILI9341_DFUNCTR command
ILI9341_DFUNCTR_REV = %10000000 ; Normally white panel
ILI9341_DFUNCTR_GS  = %01000000 ; Gate scan reversed: the picture is upside down
ILI9341_DFUNCTR_SS  = %00100000 ; Source scan reversed: the picture is mirrored left to right
ILI9341_DFUNCTR_ISC = %00000010 ; Gate scan cycle in the non-display area

; Michael's display, as mounted on the FPGA interface (hardware/michael/fpga/spi-display), needs the picture
; rotated 180 degrees: both scans reversed. Reversing the panel's scan, rather than the memory access order
; (MADCTL), keeps hardware scrolling (VSCRSADD) moving the right way.
GD_PANEL_SCAN = ILI9341_DFUNCTR_REV | ILI9341_DFUNCTR_GS | ILI9341_DFUNCTR_SS | ILI9341_DFUNCTR_ISC

; Color definitions
ILI9341_BLACK       = $0000 ;   0,   0,   0
ILI9341_NAVY        = $000f ;   0,   0, 123
ILI9341_DARKGREEN   = $03e0 ;   0, 125,   0
ILI9341_DARKCYAN    = $03ef ;   0, 125, 123
ILI9341_MAROON      = $7800 ; 123,   0,   0
ILI9341_PURPLE      = $780f ; 123,   0, 123
ILI9341_OLIVE       = $7be0 ; 123, 125,   0
ILI9341_LIGHTGREY   = $c618 ; 198, 195, 198
ILI9341_DARKGREY    = $7bef ; 123, 125, 123
ILI9341_BLUE        = $001f ;   0,   0, 255
ILI9341_GREEN       = $07e0 ;   0, 255,   0
ILI9341_CYAN        = $07ff ;   0, 255, 255
ILI9341_RED         = $f800 ; 255,   0,   0
ILI9341_MAGENTA     = $f81f ; 255,   0, 255
ILI9341_YELLOW      = $ffe0 ; 255, 255,   0
ILI9341_WHITE       = $ffff ; 255, 255, 255
ILI9341_ORANGE      = $fd20 ; 255, 165,   0
ILI9341_GREENYELLOW = $afe5 ; 173, 255,  41
ILI9341_PINK        = $fc18 ; 255, 130, 198

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


; Sets RS high (data) and RW low (a write), so every byte strobed until gd_unselect is display data.
; On exit A, X, Y are preserved
gd_select:
  pha
  lda #RS
  tsb PORTA
  lda #RW
  trb PORTA
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


INIT_COMMANDS:
  .byte $ef,              3, $03, $80, $02
  .byte $cf,              3, $00, $c1, $30
  .byte $ed,              4, $64, $03, $12, $81
  .byte $e8,              3, $85, $00, $78
  .byte $cb,              5, $39, $2c, $00, $34, $02
  .byte $f7,              1, $20
  .byte $ea,              2, $00, $00
  .byte ILI9341_PWCTR1,   1, $23                     ; Power control VRH[5:0]
  .byte ILI9341_PWCTR2,   1, $10                     ; Power control SAP[2:0];BT[3:0]
  .byte ILI9341_VMCTR1,   2, $3e, $28                ; VCM control
  .byte ILI9341_VMCTR2,   1, $86                     ; VCM control2
  .byte ILI9341_MADCTL,   1, $48                     ; Memory Access Control
  .byte ILI9341_VSCRSADD, 1, $00                     ; Vertical scroll zero
  .byte ILI9341_PIXFMT,   1, $55
  .byte ILI9341_FRMCTR1,  2, $00, $18
  .byte ILI9341_DFUNCTR,  3, $08, GD_PANEL_SCAN, $27 ; Display Function Control
  .byte $f2,              1, $00                     ; 3Gamma Function Disable
  .byte ILI9341_GAMMASET, 1, $01                     ; Gamma curve selected
  .byte ILI9341_GMCTRP1, 15, $0f, $31, $2b, $0c, $0e ; Set Gamma
  .byte                      $08, $4e, $f1, $37, $07
  .byte                      $10, $03, $0e, $09, $00
  .byte ILI9341_GMCTRN1, 15, $00, $0e, $14, $03, $11 ; Set Gamma
  .byte                      $07, $31, $c1, $48, $08
  .byte                      $0f, $0c, $31, $36, $0f
  .byte ILI9341_SLPOUT, $80                          ; Exit Sleep
  .byte ILI9341_DISPON,   0                          ; Display on
  .byte $00                                          ; End of list
