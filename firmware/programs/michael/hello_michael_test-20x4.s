PORTB = $6000
PORTA = $6001
DDRB = $6002
DDRA = $6003

E  = %10000000
RW = %01000000
RS = %00100000

SET   = $FF
UNSET = $00

CMD_CLEAR_DISPLAY           = %00000001
CMD_RETURN_HOME             = %00000010
CMD_ENTRY_MODE_SET          = %00000100
CMD_DISPLAY_ON_OFF_CONTROL  = %00001000
CMD_CURSOR_OR_DISPLAY_SHIFT = %00010000
CMD_FUNCTION_SET            = %00100000
CMD_SET_CGRAM_ADDRESS       = %01000000
CMD_SET_DDRAM_ADDRESS       = %10000000

DISPLAY_FIRST_LINE  = $00
DISPLAY_SECOND_LINE = $40
DISPLAY_THIRD_LINE  = $14
DISPLAY_FOURTH_LINE = $54

DISPLAY_STRING_PARAM   = $0000
CREATE_CHARACTER_PARAM = $0002

CHARACTER_PD = 1

  .org $2000
start:

  jmp reset

CLOCK_FREQ_KHZ         = 1000
  .include delay_routines.inc

reset:
  ldx #$ff ; Initialize stack
  txs

  lda #(E | RW | RS) ; Set display control pins on port A to output
  sta DDRA
  lda #%11111111 ; Set all pins on port B to output
  sta DDRB

  lda #(CMD_FUNCTION_SET | %11000) ; Set 8-bit mode; 2-line display; 5x8 font
  jsr display_command

  lda #(CMD_DISPLAY_ON_OFF_CONTROL | %110) ; Display on; cursor on; blink off 
  jsr display_command

  lda #(CMD_ENTRY_MODE_SET | %10) ; Increment and shift cursor; don't shift display 
  jsr display_command

  lda #(CMD_CLEAR_DISPLAY) ; Clear display
  jsr display_command

  ; Create character
  lda #<character_pd
  ldx #>character_pd
  ldy #CHARACTER_PD
  jsr create_character

  lda #(CMD_SET_DDRAM_ADDRESS | DISPLAY_FIRST_LINE) ; Move to first line
  jsr display_command

  lda #<message1
  ldx #>message1
  jsr display_string

  lda #(CMD_SET_DDRAM_ADDRESS | DISPLAY_SECOND_LINE) ; Move to second line
  jsr display_command

  lda #<message2
  ldx #>message2
  jsr display_string

  lda #CHARACTER_PD ; Custom character 1
  jsr display_character 

  ;lda #%10111100
  ;jsr display_character

  lda #(CMD_SET_DDRAM_ADDRESS | DISPLAY_THIRD_LINE) ; Move to third line
  jsr display_command

  lda #<message3
  ldx #>message3
  jsr display_string

  lda #(CMD_SET_DDRAM_ADDRESS | DISPLAY_FOURTH_LINE) ; Move to fourth line
  jsr display_command

  lda #<message4
  ldx #>message4
  jsr display_string

forever:
  lda #(CMD_CURSOR_OR_DISPLAY_SHIFT | %00001000)
  jsr display_command

  lda #50
  jsr delay_hundredths
  bra forever

loop:
  jmp loop

message1:
  .asciiz "Hello, World!......."
message2:
  .asciiz "Custom character: "
message3:
  .asciiz "Additional writings."
message4:
  .asciiz "X           Goodbye!"

wait_for_not_busy:
  pha
  lda #%00000000 ; Set all pins on port B to input
  sta DDRB
  lda #RW
  sta PORTA
  lda #(RW | E)  ; Set RW and E to enable reading
  sta PORTA
busy:
  lda PORTB
  and #%10000000
  bne busy

  lda #RW
  sta PORTA
  lda #%11111111 ; Set all pins on port B to output
  sta DDRB
  pla
  rts

display_command:
  jsr wait_for_not_busy
  sta PORTB
  lda #0         ; Clear RS/RW/E bits
  sta PORTA
  lda #E         ; Set E bit to send instruction
  sta PORTA
  lda #0         ; Clear RS/RW/E bits
  sta PORTA
  rts

display_character:
  jsr wait_for_not_busy
  sta PORTB
  lda #RS        ; Set RS bit
  sta PORTA
  lda #(RS | E)  ; Set RS and E bit to send instruction
  sta PORTA
  lda #RS        ; Set RS bit
  sta PORTA
  rts

display_string:
  sta DISPLAY_STRING_PARAM
  stx DISPLAY_STRING_PARAM + 1
  ldy #0
print_loop:
  lda (DISPLAY_STRING_PARAM),Y
  beq done_printing
  jsr display_character
  iny
  jmp print_loop
done_printing:
  rts

;On entry A = low source address
;         X = high byte source address
;         Y = character number
create_character:
  sta CREATE_CHARACTER_PARAM
  stx CREATE_CHARACTER_PARAM + 1

  tya
  asl
  asl
  asl
  ora #CMD_SET_CGRAM_ADDRESS
  jsr display_command

  ldy #0
create_loop:
  lda (CREATE_CHARACTER_PARAM),Y
  jsr display_character

  iny
  cpy #8
  bne create_loop

  rts

character_pd:
  .byte %11000
  .byte %10100
  .byte %11001
  .byte %10001
  .byte %10011
  .byte %00101
  .byte %00011
  .byte %00000
