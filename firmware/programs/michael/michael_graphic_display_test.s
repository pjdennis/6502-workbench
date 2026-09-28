  .include base_config_v2.inc

DISPLAY_STRING_PARAM     = $00 ; 2 bytes
MULTIPLY_8X8_RESULT_LOW  = $02 ; 1 byte
MULTIPLY_8X8_TEMP        = $03 ; 1 byte
COUNTER                  = $04 ; 2 bytes

GD_ZERO_PAGE_BASE        = $06

  .org $2000
start:
  jmp initialize_machine

  ; Place code for delay_routines at start of page to ensure no page boundary crossings
  ; during timing loops
  .include delay_routines.inc

  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_string.inc
  .include multiply8x8.inc
  .include graphics_display.inc

program_start:
  ldx #$ff ; Initialize stack
  txs

  jsr gd_configure

  jsr clear_display
  lda #<start_message
  ldx #>start_message
  jsr display_string

  jsr gd_prepare_vertical

  jsr gd_select
  jsr show_stripes
  jsr gd_unselect

  lda #100
  jsr delay_hundredths

  jsr gd_select
  jsr gd_clear_screen

  lda #<hello_message
  sta GD_STRING_PTR
  lda #>hello_message
  sta GD_STRING_PTR + 1
  jsr gd_show_string  
  jsr gd_unselect

  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda #<done_message
  ldx #>done_message
  jsr display_string

  stp


start_message:  asciiz "Starting..."
done_message:   asciiz "Done."
hello_message:  asciiz "Hello, World! The\nquick brown fox\njumps over the lazy dog.\n\n\n   Phil\n        (\\/)\n         \\/\n             Angel"


show_stripes:
  lda #ILI9341_CASET
  jsr gd_send_command
  lda #0
  jsr gd_send_data
  lda #0
  jsr gd_send_data
  lda #>(ILI9341_TFTHEIGHT - 1)
  jsr gd_send_data
  lda #<(ILI9341_TFTHEIGHT - 1)
  jsr gd_send_data

  lda #ILI9341_PASET
  jsr gd_send_command
  lda #0
  jsr gd_send_data
  lda #0
  jsr gd_send_data
  lda #>(ILI9341_TFTWIDTH - 1)
  jsr gd_send_data
  lda #<(ILI9341_TFTWIDTH - 1)
  jsr gd_send_data

  lda #ILI9341_RAMWR
  jsr gd_send_command

STRIPE_WIDTH = 10

  ldy #ILI9341_TFTWIDTH / STRIPE_WIDTH / 4
.stripe_loop:
  lda #<ILI9341_RED
  sta GD_COLOR
  lda #>ILI9341_RED
  sta GD_COLOR + 1
  jsr send_stripe
  lda #<ILI9341_WHITE
  sta GD_COLOR
  lda #>ILI9341_WHITE
  sta GD_COLOR + 1
  jsr send_stripe
  lda #<ILI9341_ORANGE
  sta GD_COLOR
  lda #>ILI9341_ORANGE
  sta GD_COLOR + 1
  jsr send_stripe
  lda #<ILI9341_YELLOW
  sta GD_COLOR
  lda #>ILI9341_YELLOW
  sta GD_COLOR + 1
  jsr send_stripe
  dey
  bne .stripe_loop  
  rts


send_stripe:
  phy
  ldy #STRIPE_WIDTH
.width_loop:
  lda #<(-ILI9341_TFTHEIGHT)
  sta COUNTER
  lda #>(-ILI9341_TFTHEIGHT)
  sta COUNTER + 1
.height_loop:
  lda GD_COLOR + 1
;  jsr gd_send_data
  sta PORTB
  lda #GD_E
  tsb GD_PORT
  trb GD_PORT

  lda GD_COLOR
;  jsr gd_send_data
  sta PORTB
  lda #GD_E
  tsb GD_PORT
  trb GD_PORT

  inc COUNTER
  bne .height_loop
  inc COUNTER + 1
  bne .height_loop

  dey
  bne .width_loop
  ply
  rts
