; The Michael FPGA bus (docs/michael-fpga-bus-plan.md): one byte at a time to and from the FPGA on the Cmod
; A7, over port B. E (FB_E) strobes each transfer; RS and RW, shared with the LCD and sampled as E rises,
; choose it, with the same meanings as for the LCD:
;   RW 0, RS 0  write a command          RW 1, RS 0  read the status byte
;   RW 0, RS 1  write a data byte        RW 1, RS 1  read the next byte of the reply queue
;
; Requires (base_config_v2.inc): RS and RW (PORTA bits), and the VIA's PORTA, DDRA, PORTB and DDRB.
; Interrupts may arrive at any point, including in the middle of a read: the keyboard driver's interrupt
; saves and restores the ports, and the FPGA stops driving port B while the keyboard board does (SOEB low).
; Every routine leaves RS and RW low, as the LCD routines do and expect: with RS high, the LCD's busy check
; would read its data instead of the busy flag.

FB_E               = %00000001 ; PA0: the bus's strobe (moves to PA2 in stage 4 of the plan)

; Commands
FB_NOP             = $00
FB_ID              = $01 ; replies 'M', 'B', the protocol version, a capabilities byte
FB_RESET           = $03 ; empties the queues and clears the status
FB_ECHO            = $04 ; streams: each data byte joins the reply queue
FB_SERIAL_SEND     = $50 ; streams: each data byte goes to the PC (provisional)

; Status bits (sticky ones are cleared by reading the status)
FB_ABANDONED       = %00000001 ; a command arrived before the previous one's arguments were complete
FB_UNKNOWN         = %00000010 ; an unknown command
FB_EXTRA           = %00000100 ; data after a command's arguments, for one that doesn't stream
FB_UNDERFLOW       = %00001000 ; a read with the reply queue empty
FB_OVERFLOW        = %00010000 ; a queue overflowed
FB_BUSY            = %10000000 ; (not sticky) the FPGA is still working through what it was sent


; Makes E an output, low, and RS and RW outputs. Call before the first transfer.
; On exit A, X, Y are preserved
fb_initialize:
  pha
  lda #FB_E
  trb PORTA
  lda #(FB_E | RS | RW)
  tsb DDRA
  pla
  rts


; Sends a command byte.
; On entry A = the command
; On exit  A, X, Y are preserved
fb_command:
  pha
  lda #(RS | RW)
  trb PORTA                      ; RS 0, RW 0
  bra fb_write


; Sends a data byte.
; On entry A = the byte
; On exit  A, X, Y are preserved
fb_data:
  pha
  lda #RW
  trb PORTA                      ; RW 0
  lda #RS
  tsb PORTA                      ; RS 1
fb_write:
  lda #$ff
  sta DDRB                       ; Port B an output
  pla
  sta PORTB
  pha
  lda #FB_E
  tsb PORTA                      ; E rises: the FPGA takes the byte
  trb PORTA
  lda #RS
  trb PORTA                      ; RS low again
  pla
  rts


; Reads the next byte of the reply queue ($00, and FB_UNDERFLOW set, if it's empty).
; On exit A = the byte, with Z and N set from it
;         X, Y are preserved
fb_read:
  phx
  lda #RS
  tsb PORTA                      ; RS 1
  bra fb_read_byte


; Reads the status byte, which clears its sticky bits.
; On exit A = the status, with Z and N set from it
;         X, Y are preserved
fb_status:
  phx
  lda #RS
  trb PORTA                      ; RS 0
fb_read_byte:
  stz DDRB                       ; Port B an input
  lda #RW
  tsb PORTA                      ; RW 1: a read
  lda #FB_E
  tsb PORTA                      ; E rises: the FPGA turns the bus around and drives the byte
  ldx PORTB                      ; 2 us after E rose
  trb PORTA                      ; E falls: the FPGA releases the bus
  lda #(RS | RW)
  trb PORTA                      ; RS and RW low again
  txa
  plx
  cmp #0                         ; Z and N from the byte, not from X
  rts
