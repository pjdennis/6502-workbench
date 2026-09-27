; The LCD routines with DISPLAY_INTERRUPTS_FLAG: with its bit 7 set they leave the interrupt
; disable bit alone, with it clear they disable interrupts around the strobe and enable them
; after. Starts with interrupts disabled, sends a command each way, and shows the I flag after
; each: "10" is right.
  .include base_config_v2.inc

DISPLAY_INTERRUPTS_FLAG = $fc
DISPLAY_STRING_PARAM    = $00 ; 2 bytes

  .org $0400
  jmp initialize_machine

  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc

program_start:
  ldx #$ff
  txs
  jsr reset_and_enable_display_no_cursor
  sei
  lda #$80
  sta DISPLAY_INTERRUPTS_FLAG     ; Leave interrupts alone
  lda #(CMD_DISPLAY_ON_OFF_CONTROL | CMD_PARAM_DISPLAY_ON) ; Moves nothing
  jsr display_command
  jsr show_i
  stz DISPLAY_INTERRUPTS_FLAG     ; Disable them around the strobe
  lda #(CMD_DISPLAY_ON_OFF_CONTROL | CMD_PARAM_DISPLAY_ON) ; Moves nothing
  jsr display_command
  jsr show_i
  stp

show_i:                           ; '1' if interrupts are disabled, else '0'
  php
  pla
  and #%00000100
  lsr
  lsr
  ora #'0'
  sei                             ; (keep the next command's starting state)
  jmp display_character
