;The serial receiver's interrupt handler (see serial_receive.inc). Its timing counts the
;cycles from the interrupt: run it where the interrupt vector points, not through a jmp.

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
