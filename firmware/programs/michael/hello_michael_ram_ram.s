  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $0000 ; 2 bytes

  .org $3000
start:
  jmp initialize_machine

  .include initialize_machine_v2.inc
  .include display_routines_8bit.inc
  .include display_string.inc

program_start:
  ldx #$ff ; Initialize stack
  txs

  lda #<message
  ldx #>message
  jsr display_string
forever:
  bra forever


message: .asciiz "Michael Ram!"
