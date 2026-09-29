; Michael's VIA ports, set up for the LCD and the keyboard board: a macro, so it can open a
; program (initialize_machine_v2.inc) or a subroutine (the ROM's services).

  .macro initialize_michael_ports
  ; Disable input shift register; prepare to initialize output shift register; turn off LED.
  ; Set before port A becomes an output: SOEB low would have the input shift register drive
  ; port B at the same time as the 6522
  lda #(SOEB | SOLB | START | PARITY | LED)
  sta PORTA

  ; Initialize 6522 port A (display control and shift register output enable)
  lda #(E | RW | RS | SOEB | SOLB | START | PARITY | LED)
  sta DDRA

  ; Initialize 6522 port B (8 bit data lines)
  lda #%11111111 ; Set all pins on port B to output
  sta DDRB

  ; Initialize output shift register
  lda #%11111111
  sta PORTB
  ; Toggle SOLB low then high to load data to output shift register
  lda #SOLB
  trb PORTA
  tsb PORTA

  ; Default the display bits to 0
  lda #(RW | RS)
  trb PORTA
  .endm
