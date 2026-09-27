;Serial receiving through the 6522: the interrupt handler that shifts each byte in (a start
;bit's CB2 edge starts the shift register, timed by T2) and stores it at UPLOAD_P, and the
;routines that undo the bit reversal and check the upload frame's checksum
;(tools/upload/upload_frame.py). Shared by upload_and_run.inc and the loaders built on it.
;
;Requires serial_receive_timing.inc, 6522.inc, and:
;  TRANSLATE          - 256 bytes: the bit-reversal table build_translate fills
;  UPLOAD_P           - 2 bytes in zero page: where the next byte goes
;  WAITING_FOR_SHIFT  - 1 byte
;  TEMP_P             - 2 bytes in zero page
;  TEMP               - 1 byte
;  CHECKSUM_VALUE     - 2 bytes
;  CP_M_SRC_P, CP_M_LEN - start and length of the data (translate_data, calculate_checksum)

translate_data:
  lda CP_M_SRC_P
  sta TEMP_P
  lda CP_M_SRC_P + 1
  sta TEMP_P + 1

  ; Translate count + 2 bytes, to include checksum
  clc
  lda CP_M_LEN
  adc #2
  tax                             ; Low byte of count
  lda CP_M_LEN + 1
  adc #0
  tay                             ; High byte of count

translate_loop:
  cpy #0
  bne translate_not_done
  cpx #0
  beq translate_done
translate_not_done:
  phx
  lda (TEMP_P)
  tax
  lda TRANSLATE,X
  sta (TEMP_P)
  plx

  inc TEMP_P
  bne translate_p_increment_done
  inc TEMP_P + 1
translate_p_increment_done:

  dex
  cpx #$ff
  bne translate_loop
  dey
  bra translate_loop

translate_done:
  rts


; On exit A, X, Y are not preserved
calculate_checksum:
  stz CHECKSUM_VALUE
  stz CHECKSUM_VALUE + 1

  lda CP_M_SRC_P
  sta TEMP_P
  lda CP_M_SRC_P + 1
  sta TEMP_P + 1

  ldx CP_M_LEN                    ; Low byte of count
  ldy CP_M_LEN + 1                ; High byte of count

checksum_loop:
  cpy #0
  bne checksum_not_done
  cpx #0
  beq checksum_done
checksum_not_done:

  lda CHECKSUM_VALUE + 1
  ror
  ror CHECKSUM_VALUE
  ror CHECKSUM_VALUE + 1

  clc
  lda (TEMP_P)
  adc CHECKSUM_VALUE
  sta CHECKSUM_VALUE
  lda #0
  adc CHECKSUM_VALUE + 1
  sta CHECKSUM_VALUE + 1

  inc TEMP_P
  bne checksum_p_increment_done
  inc TEMP_P + 1
checksum_p_increment_done:

  dex
  cpx #$ff
  bne checksum_loop
  dey
  bra checksum_loop

checksum_done:
  rts


; On exit A, X, Y are not preserved
build_translate:
  ldx #0
build_translate_loop:
  txa
  ldy #8
build_translate_shift_loop: 
  asl
  ror TEMP
  dey
  bne build_translate_shift_loop
  
  lda TEMP
  sta TRANSLATE,X

  inx
  bne build_translate_loop

  rts


; Interrupt handler - Read in serial data
interrupt:                        ; 7 + 2 (avg) cycles to get into the handler
  pha                             ; 3

  lda WAITING_FOR_SHIFT           ; 3
  bne interrupt_shift_done        ; 2 (not taken) 3 (taken)

interrupt_serial_in_start:        ;                  - 17 cycles to get here
  lda #ACR_SR_IN_T2               ; 2 Reenable the shift register
  sta ACR                         ; 4

  stz T2CH                        ; 4 Start timer for the initial interval before shift starts

  lda SR                          ; 4 Start shifting - 31 cycles to get to here

  lda #SUBSEQUENT_INTERVAL        ; 2
  sta T2CL                        ; 4 Interval set   - 37 cycles to get here

  lda #ICB2                       ; Disable CB2 interrupts while shift is in progress
  sta IER

  inc WAITING_FOR_SHIFT           ; Indicate we're waiting for completed shift

  pla
  rti

interrupt_shift_done:             ;                  - 18 cycles to get here
  stz ACR                         ; 4 Disable the timer temporarily

  lda #ICB2                       ; 2 Clear pending ICB2 interrupt
  sta IFR                         ; 4
  lda #(IERSETCLEAR | ICB2)       ; 2 Reenable CB2 interrupts
  sta IER                         ; 4

  lda #INITIAL_INTERVAL           ; 2 Pre-load initial interval to T2
  sta T2CL                        ; 4

  lda SR                          ; 4 Load value; clears SR interrupt as a side effect

  stz WAITING_FOR_SHIFT           ; 3 Indicate we're no longer waiting for completed shift

  cli                             ; 2 Renable interrupts so that start of shift can occur
                                  ;                  - 49 cycles to get here

  nop                             ; Noops provide a window for low-latency response
  nop                             ; To the CB2 interrupt indicating shift start
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop

  sta (UPLOAD_P)                  ; Now store the value that was received...
  inc UPLOAD_P                    ; ...and increment the data pointer
  bne interrupt_upload_incremented
  inc UPLOAD_P + 1
interrupt_upload_incremented:

  pla
  rti

interrupt_end:
