; The graphic screen for the ROM's services (michael_services.inc): the screen calls on the FPGA's text mode
; (docs/michael-fpga-bus-plan.md, stage 3), which keeps a 20 by 20 grid of characters and draws it itself.
; Its rules are the LCD screen's (lcd_screen.inc), so each call is a translation: rows and columns 1-based
; here, 0-based on the bus. write_b keeps the bus's PUT command open between characters (ROM_PUTTING), so a
; character is one byte; every other command closes it.
;
; Requires: michael_rom.inc, base_config_v2.inc, delay_routines.inc

  .include fpga_bus.inc
  .include ili9341.inc

GRAPHIC_ROWS             = 20
GRAPHIC_COLS             = 20


; C clear if the FPGA answers ID with text mode (capabilities bit 1), else C set.
; On exit A is not preserved; X, Y are
graphic_present:
  jsr fb_initialize
  lda #FB_RESET                    ; Empties the reply queue
  jsr fb_command
  lda #FB_ID
  jsr fb_command
  jsr fb_read
  cmp #'M'
  bne .absent
  jsr fb_read
  cmp #'B'
  bne .absent
  jsr fb_read                      ; The protocol version
  jsr fb_read
  and #%00000010                   ; Text mode
  beq .absent
  clc
  rts
.absent:
  sec
  rts


; Starts the graphic screen: the display reset and initialised as Michael's graphic driver does it
; (ili9341_init_commands.inc), then text mode on (the orientation, the grid cleared and drawn).
; On exit A is not preserved; X, Y are
graphic_start:
  phx
  phy
  jsr fb_initialize
  lda #FB_DISP_RESET               ; (which ends text mode, if it's on)
  jsr fb_command
  lda #0
  jsr fb_data                      ; In reset...
  lda #1
  jsr delay_hundredths             ; ...10 ms...
  lda #FB_DISP_RESET
  jsr fb_command
  lda #1
  jsr fb_data                      ; ...out of it...
  lda #12
  jsr delay_hundredths             ; ...and 120 ms to wake
  ldy #0
.command:
  lda INIT_COMMANDS,Y              ; Each: the command, a count of its parameters (bit 7: a delay after),
  beq .commands_done               ; the parameters
  iny
  pha
  lda #FB_DISP_COMMAND
  jsr fb_command
  pla
  jsr fb_data
  lda INIT_COMMANDS,Y
  iny
  pha
  and #$7f
  tax
  beq .parameters_done
.parameter:
  lda INIT_COMMANDS,Y
  iny
  jsr fb_data
  dex
  bne .parameter
.parameters_done:
  pla
  bpl .command
  lda #15
  jsr delay_hundredths             ; 150 ms
  bra .command
.commands_done:
  lda #FB_T_ON
  jsr graphic_op
  ply
  plx
  rts

  .include ili9341_init_commands.inc


; Sends a text mode operation other than PUT (which it closes)
; On entry A = the operation (FB_T_*)
; On exit A, X, Y are preserved
graphic_op:
  stz ROM_PUTTING
  jmp fb_text                      ; tail call


; write_b: the character in A at the cursor
; On exit A, X, Y are preserved
graphic_write:
  pha
  bit ROM_PUTTING
  bmi .putting
  lda #FB_T_PUT
  jsr fb_text
  lda #$ff
  sta ROM_PUTTING
.putting:
  pla
  jmp fb_data                      ; tail call


; scr_goto: row A, column Y (1-based)
; On exit X is preserved
graphic_goto:
  pha
  lda #FB_T_GOTO
  bra graphic_row_and_column

; scr_region: rows A to Y (1-based)
; On exit X is preserved
graphic_region:
  pha
  lda #FB_T_REGION
graphic_row_and_column:
  jsr graphic_op
  pla
  dec
  jsr fb_data
  tya
  dec
  jmp fb_data                      ; tail call


; The calls with a count in A
; On exit X is preserved
graphic_insert:
  pha
  lda #FB_T_INSERT
  bra graphic_counted
graphic_delete:
  pha
  lda #FB_T_DELETE
  bra graphic_counted
graphic_scroll_up:
  pha
  lda #FB_T_SCROLL_UP
  bra graphic_counted
graphic_scroll_down:
  pha
  lda #FB_T_SCROLL_DOWN
  bra graphic_counted
graphic_insert_lines:
  pha
  lda #FB_T_INSERT_LINES
  bra graphic_counted
graphic_delete_lines:
  pha
  lda #FB_T_DELETE_LINES
graphic_counted:
  jsr graphic_op
  pla
  jmp fb_data                      ; tail call


; The calls without arguments
; On exit X is preserved
graphic_clear:
  lda #FB_T_CLEAR
  jmp graphic_op
graphic_clear_eol:
  lda #FB_T_CLEAR_EOL
  jmp graphic_op
graphic_region_reset:
  lda #FB_T_REGION_RESET
  jmp graphic_op
graphic_cursor_on:
  lda #FB_T_CURSOR
  ldy #1
  bra graphic_switch
graphic_cursor_off:
  lda #FB_T_CURSOR
  ldy #0
  bra graphic_switch
graphic_reverse:
  lda #FB_T_VIDEO
  ldy #1
  bra graphic_switch
graphic_normal:
  lda #FB_T_VIDEO
  ldy #0
graphic_switch:
  jsr graphic_op
  tya
  jmp fb_data                      ; tail call


; term_rows and term_cols
; On exit X, Y are preserved
graphic_rows:
  lda #GRAPHIC_ROWS
  rts
graphic_cols:
  lda #GRAPHIC_COLS
  rts
