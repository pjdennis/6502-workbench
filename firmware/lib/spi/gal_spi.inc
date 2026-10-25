; SPI through the GAL20RA10 interface (hardware/michael/spi-interface/), with Michael's FPGA board unplugged:
; port B to the 74HC299's I/O pins, E on PA2. A rising edge of E starts a burst of 8 SCLK pulses (2 MHz at a
; 2 MHz Phi2) sending the byte the '299 loaded from port B, MSB first, mode 0; held high past them, E has the
; '299 drive the byte received onto port B until E falls. A device's chip select is its own (e.g. w5500.inc).
;
; Requires (base_config_v2.inc): FPGA_E, PORTA, PORTB and DDRB, with E an output, low (michael_ports.inc), and
; port B an output between calls. The '299 drives port B only inside gal_spi_read, so call it with interrupts
; off: the keyboard handler would turn on the keyboard board's outputs onto port B at the same time.
;
; The timing is counted against the GAL's burst of 8 cycles from the first Phi2 edge with E high: a strobe
; that comes during a burst reads as "hold" and is lost, so successive calls must start 9 cycles apart (they
; do: a jsr and an rts alone take 12).

GAL_E = FPGA_E   ; PA2

; Sends A. E is high for 6 cycles (tsb ... trb), inside the 8 of the burst, so the '299 never drives port B.
; On exit A = GAL_E; X, Y are preserved
gal_spi_write:
  sta PORTB
  lda #GAL_E
  tsb PORTA
  trb PORTA
  rts


; Sends A and returns the byte received in A. E stays high past the burst, so the '299 drives the byte
; received onto port B; port B turns to input within 8 cycles of E rising, before the '299 does, and back to
; output only after E has fallen and the '299 has let go. The read comes 12 cycles later than it must: the
; emulator's CPU makes each access on an instruction's first cycle, so it can't check this margin.
; X, Y are preserved
gal_spi_read:
  sta PORTB
  lda #GAL_E
  tsb PORTA                      ; The burst starts
  stz DDRB                       ; Port B an input
  nop                            ; The burst's 8 cycles, and the '299's outputs settling
  nop
  nop
  nop
  nop
  nop
  lda PORTB                      ; The byte received
  pha
  lda #GAL_E
  trb PORTA                      ; The '299 lets go at the next edge
  lda #$ff
  sta DDRB                       ; Port B an output again
  pla
  rts
