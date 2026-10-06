; Starting Michael's ILI9341 display, as its graphics driver (graphics_display.inc) and the ROM's graphic screen
; (michael_graphic_screen.inc) both do: ili9341_initialize sends the display's start-up commands
; (ili9341_init_commands.inc) through the includer's own routines, and, on the FPGA bus (fpga_bus.inc included
; first), ili9341_reset pulses the display's reset line.
;
; Requires: ILI_COMMAND (sends the display command in A), ILI_DATA (sends a parameter byte in A; may change A),
; both preserving X and Y; delay_hundredths (delay_routines.inc)

  .ifdef FB_DISP_RESET
; Resets the display through the bus's DISP_RESET: after 10 ms, holds it in reset for 10 ms, then waits
; 120 ms for it to wake.
; On exit A, X, Y are preserved
ili9341_reset:
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
  .endif


; Sends INIT_COMMANDS: each a command, a count of its parameters (bit 7: wait 150 ms after), the parameters;
; a 0 ends them.
; On exit A, X, Y are preserved
ili9341_initialize:
  pha
  phx
  phy
  ldy #0
.command:
  lda INIT_COMMANDS,Y
  beq .done
  iny
  jsr ILI_COMMAND
  lda INIT_COMMANDS,Y
  iny
  pha
  and #$7f
  tax
  beq .parameters_done
.parameter:
  lda INIT_COMMANDS,Y
  iny
  jsr ILI_DATA
  dex
  bne .parameter
.parameters_done:
  pla
  bpl .command
  lda #15
  jsr delay_hundredths           ; 150 ms
  bra .command
.done:
  ply
  plx
  pla
  rts

  .include ili9341_init_commands.inc
