; Switches all of port B between $00 and $FF continuously, with E held low (no transfers), for measuring the
; switching noise that reaches the FPGA bus's E (hardware/michael/fpga/bus-check/noise.py).
  .include base_config_v2.inc

  .org PROGRAM_LOAD_ADDRESS
start:
  sei
  jsr fb_initialize
  lda #$ff
  sta DDRB
.switch:
  stz PORTB                      ; All 8 bits fall ...
  sta PORTB                      ; ... and rise: a pair every 11 cycles
  bra .switch

  .include fpga_bus.inc
