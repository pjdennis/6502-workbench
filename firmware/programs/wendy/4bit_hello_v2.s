CLOCK_FREQ_KHZ    = 5000

  .include 6522.inc

; PORTB assignments
DISPLAY_DATA_MASK = %01111000
E                 = %00000100
RW                = %00000010
RS                = %00000001

BF                = %01000000
DISPLAY_BITS_MASK = (DISPLAY_DATA_MASK | E | RW | RS)

DISPLAY_BITS      = 4

; Variables
DISPLAY_STRING_PARAM = $0000 ; 2 bytes

  .org $2000
  jmp program_entry

  .include display_update_routines.inc
  .include display_string.inc

program_entry:
  ; Show a message
  lda #<message
  ldx #>message
  jsr display_string

busy_loop:
  bra busy_loop


message:
  .asciiz "Hello from ram!"
