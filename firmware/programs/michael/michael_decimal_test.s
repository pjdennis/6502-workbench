  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $00 ; 2 bytes

TO_DECIMAL_PARAM     = $02

  .org $2000                     ; Loader loads programs to this address
start:
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_decimal.inc

VALUE = $ffff


program_start:
  ; Initialize stack
  ldx #$ff
  txs

  lda #<VALUE
  ldx #>VALUE
  jsr display_decimal

  stp
