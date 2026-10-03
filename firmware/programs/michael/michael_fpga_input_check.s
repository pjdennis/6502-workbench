; Bring-up check for the FPGA SPI display interface's inputs (hardware/michael/fpga/input-check/).
; Steps each signal the interface reads one at a time, holding each state for 20 ms, then sends bytes
; through the display driver. The FPGA's input-check design reports what it sees, and
; hardware/michael/fpga/input-check/check.py compares that with the sequence this program produces.
;
; Sequence (states are port B; E, CSB, RSTB, DC):
;   start marker  $C3, $3C, $00 (E low, CSB high, RSTB high, DC low throughout)
;   port B        $01, $02, ... $80, then $FF, $55, $AA, $00
;   control       E high then low; CSB low then high; RSTB low then high; DC high then low
;   bytes         gd_select; command $2A; data $00-$FF; command $2C; 64 zero bytes at the fill loop's
;                 full speed (send_zero_data); gd_unselect
;   end marker    $E7, $7E, $00
  .include base_config_v2.inc

DISPLAY_STRING_PARAM     = $00 ; 2 bytes
MULTIPLY_8X8_RESULT_LOW  = $02 ; 1 byte
MULTIPLY_8X8_TEMP        = $03 ; 1 byte
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
  sei      ; No keyboard interrupts: the keyboard driver also uses PA5 (DC)

  jsr gd_configure ; E low, CSB and RSTB high, all outputs
  lda #GD_DC
  trb GD_PORT      ; DC low (PA5 is already an output)
  stz PORTB
  lda #5
  jsr delay_hundredths

  ; Start marker
  lda #$c3
  jsr show
  lda #$3c
  jsr show
  lda #$00
  jsr show

  ; Port B: a walking one, then all ones, alternating bits and zero
  lda #$01
.walk:
  jsr show
  asl
  bne .walk
  lda #$ff
  jsr show
  lda #$55
  jsr show
  lda #$aa
  jsr show
  lda #$00
  jsr show

  ; Control lines one at a time, each away from its idle level and back
  lda #GD_E
  jsr pulse_high
  lda #GD_CSB
  jsr pulse_low
  lda #GD_RSTB
  jsr pulse_low
  lda #GD_DC
  jsr pulse_high

  ; Bytes through the display driver
  jsr gd_select
  jsr pause
  lda #$2a
  jsr gd_send_command
  ldx #0
.bytes:
  txa
  jsr gd_send_data
  inx
  bne .bytes
  lda #$2c
  jsr gd_send_command
  lda #$fc         ; send_zero_data sends 16 bytes per count up to $10000: 4 counts, 64 bytes
  sta GD_TEMP
  lda #$ff
  sta GD_TEMP + 1
  jsr send_zero_data
  jsr pause
  jsr gd_unselect
  jsr pause

  ; End marker
  lda #$e7
  jsr show
  lda #$7e
  jsr show
  lda #$00
  jsr show

.done:
  bra .done


; Puts A on port B and holds it
show:
  sta PORTB
; Holds the current state for 20 ms, well over the input-check design's 1 ms settle time
pause:
  pha
  lda #2
  jsr delay_hundredths
  pla
  rts


; Raises the port A bits in A, holds, lowers them and holds
pulse_high:
  tsb GD_PORT
  jsr pause
  trb GD_PORT
  jmp pause ; tail call


; Lowers the port A bits in A, holds, raises them and holds
pulse_low:
  trb GD_PORT
  jsr pause
  tsb GD_PORT
  jmp pause ; tail call
