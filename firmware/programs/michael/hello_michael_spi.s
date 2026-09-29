  .include base_config_v2.inc

; PORT A
SPI_E    = %00000001
SPI_RSTB = %00000100

DISPLAY_STRING_PARAM = $0000 ; 2 bytes

  .org $2000
start:
  jmp initialize_machine

  .include initialize_machine_v2.inc
  .include display_routines_8bit.inc
  .include display_string.inc
  .include delay_routines.inc

program_start:
  ldx #$ff ; Initialize stack
  txs

  lda #SPI_E
  trb PORTA
  lda #SPI_RSTB
  tsb PORTA
  lda #SPI_E | SPI_RSTB
  tsb DDRA

  lda #<message
  ldx #>message
  jsr display_string

  ; Reset the SPI interface
  lda #SPI_RSTB
  trb PORTA
  tsb PORTA

forever:
  lda #%11010101
  sta PORTB
  lda PORTA
  and #~SPI_E
  tax
  ldy #0
  ora #SPI_E
  sta PORTA,Y
  stx PORTA
;  nop
  sta PORTA,Y
  stx PORTA
  lda #100
  jsr delay_hundredths 
  bra forever


message: .asciiz "Hi I'm Michael!"
