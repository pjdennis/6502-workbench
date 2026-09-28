  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $0000 ; 2 bytes

  .org PROGRAM_LOAD_ADDRESS
start:
  jmp initialize_machine

  .include initialize_machine_v2.inc
  .include display_routines_8bit.inc
  .include display_string.inc
  .include delay_routines.inc

program_start:
  ldx #$ff ; Initialize stack
  txs

  lda #<message
  ldx #>message
  jsr display_string
forever:
  lda PORTA
  eor #LED
  sta PORTA
  lda #50 
  jsr delay_hundredths
  bra forever


message: .asciiz "Hi I'm Michael!"
