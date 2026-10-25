; Reads the W5500 Ethernet module's VERSIONR register ($0039, always $04) again and again through the GAL20RA10
; SPI interface (hardware/michael/spi-interface/), with the FPGA board unplugged, and shows each round of 4096
; reads on the LCD:
;   W5500 VERSIONR
;   LAST 04 FIRST BAD --     the last value read, and the first wrong one seen (-- for none yet)
;   GOOD 1000 BAD 0000       this round's reads, in hex
;   ROUND 01
; Wiring: E on PA2 (GAL pin 7), the W5500's chip select on PA0, port B to the 74HC299's I/O pins, Phi2 to GAL
; CLK, /RES to GAL /RST and the W5500's reset, the '299's /OE1 to ground. Interrupts stay off, so the keyboard
; board never drives port B.
  .include base_config_v2.inc

GAL_E                = FPGA_E    ; PA2: a rising edge sends the byte on port B; held high past the 8 SCLK
                                 ; pulses, the '299 drives the byte received onto port B until E falls
W5500_CS             = %00000001 ; PA0, active low; the module pulls it up
VERSIONR             = $0039
VERSION              = $04
CONTROL_COMMON_READ  = $00       ; the common registers' block, read, variable length (until CS rises)

DISPLAY_STRING_PARAM = $00 ; 2 bytes
GOOD                 = $02 ; 2 bytes
BAD                  = $04 ; 2 bytes
COUNT                = $06 ; 2 bytes: reads left in the round
LAST                 = $08 ; 1 byte
FIRST_BAD            = $09 ; 1 byte
SEEN_BAD             = $0A ; 1 byte
ROUND                = $0B ; 1 byte

READS_HIGH           = $10       ; 4096 reads a round

  .org PROGRAM_LOAD_ADDRESS
start:
  jmp initialize_machine

  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_string.inc
  .include convert_to_hex.inc

program_start:
  ldx #$ff
  txs
  sei
  lda #W5500_CS
  tsb PORTA                      ; Deselected before PA0 becomes an output
  tsb DDRA
  jsr reset_and_enable_display_no_cursor
  stz ROUND
  stz SEEN_BAD
  lda #<title
  ldx #>title
  jsr display_string
.round:
  stz GOOD
  stz GOOD + 1
  stz BAD
  stz BAD + 1
  stz COUNT
  lda #READS_HIGH
  sta COUNT + 1
.read:
  jsr read_version
  sta LAST
  cmp #VERSION
  bne .bad
  inc GOOD
  bne .counted
  inc GOOD + 1
  bra .counted
.bad:
  inc BAD
  bne .first_bad
  inc BAD + 1
.first_bad:
  ldx SEEN_BAD
  bne .counted
  sta FIRST_BAD
  inc SEEN_BAD
.counted:
  lda COUNT
  bne .count_low
  dec COUNT + 1
.count_low:
  dec COUNT
  lda COUNT
  ora COUNT + 1
  bne .read
  inc ROUND
  jsr show
  bra .round


; Reads VERSIONR in one frame. On exit A = the value read; X, Y are preserved
read_version:
  lda #W5500_CS
  trb PORTA                      ; Select
  lda #>VERSIONR
  jsr spi_write
  lda #<VERSIONR
  jsr spi_write
  lda #CONTROL_COMMON_READ
  jsr spi_write
  lda #$00
  jsr spi_read
  pha
  lda #W5500_CS
  tsb PORTA                      ; Deselect: the frame ends
  pla
  rts


; Sends A. E is high for 6 cycles (tsb ... trb), well inside the 8 of the burst, so the '299 never drives
; port B; the burst ends long before the caller can start another (E must be low at its last edge).
; On exit A = GAL_E; X, Y are preserved
spi_write:
  sta PORTB
  lda #GAL_E
  tsb PORTA
  trb PORTA
  rts


; Sends A and returns the byte received in A. E stays high past the burst, so the '299 drives the byte
; received onto port B; port B turns to input within 8 cycles of E rising, before the '299 does, and back to
; output only after E has fallen and the '299 has let go. X, Y are preserved
spi_read:
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


show:
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda #<last_text
  ldx #>last_text
  jsr display_string
  lda LAST
  jsr display_hex
  lda #<first_bad_text
  ldx #>first_bad_text
  jsr display_string
  lda SEEN_BAD
  beq .none
  lda FIRST_BAD
  jsr display_hex
  bra .counts
.none:
  lda #<none_text
  ldx #>none_text
  jsr display_string
.counts:
  lda #DISPLAY_THIRD_LINE
  jsr move_cursor
  lda #<good_text
  ldx #>good_text
  jsr display_string
  lda GOOD + 1
  jsr display_hex
  lda GOOD
  jsr display_hex
  lda #<bad_text
  ldx #>bad_text
  jsr display_string
  lda BAD + 1
  jsr display_hex
  lda BAD
  jsr display_hex
  lda #DISPLAY_FOURTH_LINE
  jsr move_cursor
  lda #<round_text
  ldx #>round_text
  jsr display_string
  lda ROUND
  ; fall through

; On entry A = the byte to show in hex
display_hex:
  jsr convert_to_hex
  jsr display_character
  txa
  jmp display_character


title:          .asciiz "W5500 VERSIONR"
last_text:      .asciiz "LAST "
first_bad_text: .asciiz " FIRST BAD "
none_text:      .asciiz "--"
good_text:      .asciiz "GOOD "
bad_text:       .asciiz " BAD "
round_text:     .asciiz "ROUND "
