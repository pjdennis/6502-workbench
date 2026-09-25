PORTB = $6000
PORTA = $6001
DDRB = $6002
DDRA = $6003

; PORTA assignments
BANK              = %00001111

BANK_START        = %00000100
BANK_STOP         = %00010000

; PORTB assignments
DISPLAY_DATA_MASK = %11110000
E                 = %00001000
RW                = %00000100
RS                = %00000010
BF                = %10000000
DISPLAY_BITS_MASK = (DISPLAY_DATA_MASK | E | RW | RS)

  .include display_parameters.inc

; Memory locations
BANK_TEST_CHAR         = $0000
STACK_POINTER_SAVE     = $0001
BUSY_COUNTER           = $0002 ; 2 bytes
STRING_POINTER         = $0004 ; 2 bytes
BANK_SWITCH_SCRATCH    = $0006
BANK_TEST_CHAR_FIXED   = $2000


  .org $8000

  ;Place code for delay_routines at start of page to ensure no page boundary crossings during timing loops
  .include delay_routines.inc

  .include display_routines.inc
  .include convert_to_hex.inc


test_message:
  .asciiz "Ambidextrous"


reset:
  ldx #$ff ; Initialize stack
  txs

  lda #0   ; Initialize status flags
  pha
  plp

  ; Initialize 6522 port A (memory banking control)
  lda #BANK_START
  sta PORTA
  lda #BANK ; Set pin direction  on port A
  sta DDRA

  ; Initialize 6522 port B (display control)
  lda #0
  sta PORTB
  lda #DISPLAY_BITS_MASK ; Set display control pins and data pins on port B to output
  sta DDRB


  ; Initialize display
  jsr reset_display

  lda #(CMD_ENTRY_MODE_SET | %10)          ; Increment and shift cursor; don't shift display 
  jsr display_command

  lda #(CMD_DISPLAY_ON_OFF_CONTROL | %100) ; Display on; cursor off; blink off 
  jsr display_command


  ; Test results for storing on private area of each bank shown on line 1
  lda #(CMD_SET_DDRAM_ADDRESS | DISPLAY_FIRST_LINE) ; Move to first line
  jsr display_command

  ; Store 'Ambidextrous' across the banks
  lda #<test_message
  sta STRING_POINTER
  lda #>test_message
  sta STRING_POINTER + 1
  ldy #0
  ldx #BANK_START
store_in_banks_loop:
  lda (STRING_POINTER),Y
  jsr store_in_bank
  iny
  inx
  cpx #BANK_STOP
  bne store_in_banks_loop

  ; Retrieve and print from the banks
  ldx #BANK_START
bank_print_loop:
  jsr retrieve_from_bank
  jsr display_character
  inx
  cpx #BANK_STOP
  bne bank_print_loop


  ; Test results for updating shared area from each bank shown on line 2
  lda #(CMD_SET_DDRAM_ADDRESS | DISPLAY_SECOND_LINE) ; Move to second line
  jsr display_command

  ; Increment same memory location from each bank and print, starting with 'A'
  lda #'A'
  sta BANK_TEST_CHAR_FIXED
  ldx #BANK_START
bank_fixed_loop:
  jsr bank_fixed_test
  jsr display_character
  inx
  cpx #BANK_STOP
  bne bank_fixed_loop


  ; Show incrementing counter to prove the compuer is running
  jmp run_counter


; On entry X = bank to test
; On exit  A = value retrieved from bank
;          X is preserved
;          Y is not preserved
bank_fixed_test
  stx BANK_SWITCH_SCRATCH

  sei
  lda PORTA
  tax
  and #(~BANK & $ff)
  ora BANK_SWITCH_SCRATCH
  ; new bank in A; old bank in X; value in Y
  sta PORTA
  ;nop ; might not need these
  ;nop
  ;nop
  ;nop
  ldy BANK_TEST_CHAR_FIXED
  tya
  iny
  sty BANK_TEST_CHAR_FIXED
  stx PORTA
  ;nop ; might not need these
  ;nop
  ;nop
  ;nop
  cli
  ldx BANK_SWITCH_SCRATCH

  rts


; On entry A = value to store
;          X = bank to store in
; On exit  X, Y are preserved
;          A is not preserved
store_in_bank:
  stx BANK_SWITCH_SCRATCH

  ; Push 'Y' while preserving A
  tax
  tya
  pha
  txa

  tay

  sei
  lda PORTA
  tax
  and #(~BANK & $ff)
  ora BANK_SWITCH_SCRATCH
  ; new bank in A; old bank in X; value in Y
  sta PORTA
  ;nop ; might not need these
  ;nop
  ;nop
  ;nop
  sty BANK_TEST_CHAR
  stx PORTA
  ;nop ; might not need these
  ;nop
  ;nop
  ;nop
  cli

  ldx BANK_SWITCH_SCRATCH
  pla
  tay

  rts


; On entry X = bank to retrieve from
; On exit  A = value retrieved
;          X is preserved
;          Y is not preserved
retrieve_from_bank:
  stx BANK_SWITCH_SCRATCH

  sei
  lda PORTA
  tax
  and #(~BANK & $ff)
  ora BANK_SWITCH_SCRATCH
  ; new bank in A; old bank in X; load value to Y
  sta PORTA
  ;nop ; might not need these
  ;nop
  ;nop
  ;nop
  ldy BANK_TEST_CHAR
  stx PORTA
  ;nop ; might not need these
  ;nop
  ;nop
  ;nop
  cli

  ldx BANK_SWITCH_SCRATCH
  tya
  
  rts


; Busy loop incrementing and displaying counter
run_counter:
  lda #0
  sta BUSY_COUNTER
  sta BUSY_COUNTER + 1
run_counter_repeat:
  lda #(CMD_SET_DDRAM_ADDRESS | (DISPLAY_SECOND_LINE + 13))
  jsr display_command

  ; Display first 3 of 4 hex characters from the counter
  lda BUSY_COUNTER + 1
  jsr convert_to_hex
  jsr display_character
  txa
  jsr display_character

  lda BUSY_COUNTER
  jsr convert_to_hex
  jsr display_character

  ; Increment counter
  inc BUSY_COUNTER
  bne run_counter_repeat
  inc BUSY_COUNTER + 1
  jmp run_counter_repeat


; Vectors
  .org $fffc
  .word reset
  .word $0000
