  .ifndef DISPLAY_DO_NOT_DISABLE_INTERRUPTS
DISPLAY_DO_NOT_DISABLE_INTERRUPTS = 0
  .endif

; Interrupts are disabled around each E strobe, so an interrupt handler that drives the ports
; (the keyboard's) can't cut in mid-transfer, unless:
;   DISPLAY_DO_NOT_DISABLE_INTERRUPTS = 1: never disabled;
;   DISPLAY_INTERRUPTS_FLAG = a zero-page byte: not disabled while its bit 7 is set (a serial
;     loader sets it while receiving, since its handler must not be delayed and leaves the
;     ports alone).
  .macro display_sei
  .ifeq DISPLAY_DO_NOT_DISABLE_INTERRUPTS
  .ifdef DISPLAY_INTERRUPTS_FLAG
  bit DISPLAY_INTERRUPTS_FLAG
  bmi * + 3                       ; Over the sei
  .endif
  sei
  .endif
  .endm

  .macro display_cli
  .ifeq DISPLAY_DO_NOT_DISABLE_INTERRUPTS
  .ifdef DISPLAY_INTERRUPTS_FLAG
  bit DISPLAY_INTERRUPTS_FLAG
  bmi * + 3                       ; Over the cli
  .endif
  cli
  .endif
  .endm

wait_for_not_busy:
  pha
  phx
  lda #%00000000 ; Set all pins on port B to input
  sta DDRB
  lda #RW
  tsb PORTA      ; Set RW for reading
busy:
  lda #E         ; Enable flag
  display_sei
  tsb PORTA
  ldx PORTB
  trb PORTA
  display_cli
  txa
  and #%10000000
  bne busy
  lda #RW
  trb PORTA
  lda #%11111111 ; Set all pins on port B to output
  sta DDRB
  plx
  pla
  rts


; On Entry A = Command to send
; On Exit  X, Y preserved
;          A not preserved
display_command:
  jsr wait_for_not_busy
  sta PORTB
  lda #E         ; Enable bit
  display_sei
  tsb PORTA
  trb PORTA
  display_cli
  rts


; On Entry A = Character to send
; On Exit  X, Y preserved
;          A not preserved
display_character:
  .ifdef EXTEND_CHARACTER_SET
  jsr extend_character_set_translate_for_display
  .endif

; Alternate entry point bypasses translation
display_data:
  jsr wait_for_not_busy
  sta PORTB
  lda #RS        ; Register select bit
  tsb PORTA      ; Select the data register
  lda #E         ; Enable bit
  display_sei
  tsb PORTA
  trb PORTA
  display_cli
  lda #RS        ; Register select bit
  trb PORTA      ; Select the instruction register
  rts


  .include display_update_helpers.inc 
