  .include base_config_v1.inc

; PORTA assignments
MORSE_LED         = %00010000
CONTROL_BUTTON    = %00100000
CONTROL_LED       = %01000000

PORTA_OUT_MASK    = BANK_MASK | CONTROL_LED | MORSE_LED | SD_CSB

SD_DATA           = %00001000
SD_CLK            = %00010000
SD_DC             = %00100000
SD_CS_PORT        = PORTA
SD_DATA_PORT      = PORTB

; PORTB assignments
T1_SQWAVE_OUT     = %10000000

PORTB_OUT_MASK    = DISPLAY_BITS_MASK | E | T1_SQWAVE_OUT

; Variables
DISPLAY_STRING_PARAM = $0000 ; 2 bytes

  .org $2000
  jmp program_entry

  ; Place delay_routines at start of page to ensure no page boundary crossings during timing loops
  .include delay_routines.inc

  .include display_routines.inc
  .include display_string.inc

program_entry:
  ldx #$ff                                 ; Initialize stack
  txs

  lda #0                                   ; Initialize status flags
  pha
  plp

  ; Initialize 6522 port A (memory banking control)
  lda #(BANK_START | SD_CSB)
  sta PORTA
  lda #PORTA_OUT_MASK                      ; Set pin direction on port A
  sta DDRA

  ; Initialize 6522 port B (display control)
  lda #0
  sta PORTB
  lda #PORTB_OUT_MASK                      ; Set pin direction on port B
  sta DDRB

  ; Set up the RAM vector pull location
  lda #<interrupt
  sta $3ffe
  lda #>interrupt
  sta $3fff

  ; Initialize display
  jsr reset_and_enable_display_no_cursor

  ; Show a message
  lda #<message
  ldx #>message
  jsr display_string

busy_loop:
  bra busy_loop


message:
  .asciiz "Hello from ram!"


; Interrupt handler - switch memory banks and routines
interrupt:
  rti
