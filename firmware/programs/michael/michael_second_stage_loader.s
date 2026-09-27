; Second-stage loader for programs too big for the ROM's loader, which receives uploads at
; PROGRAM_LOAD_ADDRESS and so can't take more than will fit from there to the interrupt page.
; Upload this first (it runs from PROGRAM_LOAD_ADDRESS), then the program, without a reset:
; it receives the program the same way (tools/upload/upload_frame.py), straight into RAM
; at PROGRAM_TO and up to the interrupt page, and runs it from PROGRAM_TO.
;
; While it waits, from the interrupt page, the LCD says so. A bad checksum, or a program too
; long, lights the LED and stops the CPU.

  .include base_config_v2.inc

BPS_HUNDREDS      = 576                   ; 57600 bps, as the ROM's loader
PROGRAM_TO        = $0400
FRAME_AT          = PROGRAM_TO - 2        ; The frame's length lands just below the program

; Zero page and RAM, free until the program starts
UPLOAD_P          = $00 ; 2 bytes
UPLOAD_STOP_AT    = $02 ; 2 bytes
TEMP_P            = $04 ; 2 bytes
CHECKSUM_VALUE    = $06 ; 2 bytes
CP_M_SRC_P        = $08 ; 2 bytes
CP_M_LEN          = $0a ; 2 bytes
WAITING_FOR_SHIFT = $0c ; 1 byte
TEMP              = $0d ; 1 byte
DISPLAY_STRING_PARAM = $0e ; 2 bytes
TRANSLATE         = $0200 ; 256 bytes
INTERRUPT_ROUTINE = INTERRUPT_VECTOR_TARGET

  .include serial_receive_timing.inc

  .org PROGRAM_LOAD_ADDRESS
  jmp initialize_machine

  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_string.inc

waiting_message:  .asciiz 'Waiting for the'
waiting_message2: .asciiz 'program...'

program_start:
  ldx #$ff
  txs

  jsr reset_and_enable_display_no_cursor
  lda #<waiting_message
  ldx #>waiting_message
  jsr display_string
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda #<waiting_message2
  ldx #>waiting_message2
  jsr display_string

  ; Move the receiver to the interrupt page: the program overwrites this one
  ldx #0
.copy:
  lda receiver_image, X
  sta INTERRUPT_ROUTINE, X
  inx
  cpx #<(receiver_end - INTERRUPT_ROUTINE)
  bne .copy

  jsr build_translate
  stz WAITING_FOR_SHIFT
  lda #<FRAME_AT
  sta UPLOAD_P
  lda #>FRAME_AT
  sta UPLOAD_P + 1

  lda #PCR_CB2_IND_NEG_E          ; CB2 independent interrupt negative edge
  sta PCR
  lda #ICB2                       ; Clear any pending CB2 interrupt
  sta IFR
  lda #(IERSETCLEAR | ICB2 | ISR) ; Enable interrupts for SR and CB2
  sta IER
  lda #INITIAL_INTERVAL
  sta T2CL
  cli
  jmp receive                     ; Bytes reach this page long after we've left it

  .include serial_receive.inc     ; build_translate


receiver_image:
  .rorg INTERRUPT_ROUTINE

  .include serial_receive_interrupt.inc   ; First: the interrupt vector points here

receive:
.wait_for_length:                 ; Until UPLOAD_P reaches PROGRAM_TO
  lda UPLOAD_P + 1
  cmp #>PROGRAM_TO
  bcc .wait_for_length
  bne .length_available
  lda UPLOAD_P
  cmp #<PROGRAM_TO
  bcc .wait_for_length

.length_available:                ; The program ends at PROGRAM_TO + length...
  ldx FRAME_AT
  lda TRANSLATE, X
  clc
  adc #<PROGRAM_TO
  sta CP_M_LEN
  ldx FRAME_AT + 1
  lda TRANSLATE, X
  adc #>PROGRAM_TO
  sta CP_M_LEN + 1
  bcs failed
  lda CP_M_LEN                    ; ...and the frame 2 bytes later, after the checksum
  adc #2
  sta UPLOAD_STOP_AT
  lda CP_M_LEN + 1
  adc #0
  sta UPLOAD_STOP_AT + 1
  cmp #>INTERRUPT_ROUTINE         ; It must end below this page
  bcs failed

.wait_for_done:                   ; Until UPLOAD_P reaches UPLOAD_STOP_AT
  lda UPLOAD_P + 1
  cmp UPLOAD_STOP_AT + 1
  bcc .wait_for_done
  bne .done
  lda UPLOAD_P
  cmp UPLOAD_STOP_AT
  bcc .wait_for_done

.done:
  sei
  stz ACR                         ; Disable shifting
  stz PCR                         ; Turn off CB2 interrupts
  lda #(ICB2 | ISR)               ; Disable and reset interrupt flags
  sta IER
  sta IFR

  ; Restore each byte's bit order and add it to the checksum (as calculate_checksum),
  ; up to the end of the program (CP_M_LEN)
  lda #<PROGRAM_TO
  sta TEMP_P
  lda #>PROGRAM_TO
  sta TEMP_P + 1
  stz CHECKSUM_VALUE
  stz CHECKSUM_VALUE + 1
.byte:
  lda TEMP_P
  cmp CP_M_LEN
  bne .add
  lda TEMP_P + 1
  cmp CP_M_LEN + 1
  beq .check
.add:
  jsr translate_byte
  pha
  lda CHECKSUM_VALUE + 1          ; Rotate the checksum right...
  ror
  ror CHECKSUM_VALUE
  ror CHECKSUM_VALUE + 1
  pla                             ; ...and add the byte
  clc
  adc CHECKSUM_VALUE
  sta CHECKSUM_VALUE
  bcc .next
  inc CHECKSUM_VALUE + 1
.next:
  inc TEMP_P
  bne .byte
  inc TEMP_P + 1
  bra .byte

.check:                           ; TEMP_P is at the uploaded checksum
  jsr translate_byte
  cmp CHECKSUM_VALUE
  bne failed
  inc TEMP_P                      ; (the checksum is below the page end: no carry)
  jsr translate_byte
  cmp CHECKSUM_VALUE + 1
  bne failed
  jmp PROGRAM_TO                  ; Run it (interrupts disabled, as after a reset)

failed:
  sei
  lda #LED
  tsb PORTA
  stp

; On exit A = the byte at TEMP_P with its bit order restored, and stored back
translate_byte:
  lda (TEMP_P)
  tax
  lda TRANSLATE, X
  sta (TEMP_P)
  rts

receiver_end:
  .rend

  .if receiver_end - INTERRUPT_ROUTINE > $100
  fail "The receiver doesn't fit in the interrupt page"
  .endif
