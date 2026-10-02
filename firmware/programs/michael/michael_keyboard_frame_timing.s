; Times the frames of a Read ID ($F2) exchange with Michael's PS/2 keyboard. After the usual
; start-up it sends $F2 and logs each CA2 interrupt with T1 (free-running, 0.5 us ticks at
; 2 MHz) for 100 ms, then shows up to 10 entries: type, byte, and the time since the previous
; entry as 4 hex digits:
;   b  clock pulled low to send $F2 (the first entry, 0000)
;   c  clock released, plus 300 us
;   s  frame start: CA2 fell as the keyboard began clocking
;   h  end of the host's frame (the $F2)
;   a  end of a frame that was an ACK ($FA)
;   r  end of a frame with any other byte
; Then it logs the next key typed (a press and release that send 3 bytes, such as 'a') and shows
; its entries instead, to time single frames from the same keyboard.
; A frame's end comes the detector's idle time after its last clock. If the keyboard sends
; the next byte sooner than that, the two frames show as one long one. The driver then reads
; only the second byte and never sees the ACK: after about a second this program stops waiting
; for it. See docs/michael-keyboard-frame-detection.md.

  .include base_config_v2.inc

IRQ_VECTOR               = $fffe
CP_M_DEST_P              = $00 ; 2 bytes
CP_M_SRC_P               = $02 ; 2 bytes
CP_M_LEN                 = $04 ; 2 bytes
CREATE_CHARACTER_PARAM   = $06 ; 2 bytes
SIMPLE_BUFFER_WRITE_PTR  = $08 ; 1 byte
SIMPLE_BUFFER_READ_PTR   = $09 ; 1 byte
CONSOLE_CURSOR_POSITION  = $0A ; 1 byte
KB_ZERO_PAGE_BASE        = $0B ; up to KB_ZERO_PAGE_STOP
LOGGING                  = $20 ; 1 byte: non-zero while interrupts are logged
LOG_INDEX                = $21 ; 1 byte
WAIT_COUNT               = $22 ; 2 bytes: times round the wait for the ACK
T_HI                     = $24 ; 1 byte
T_LO                     = $25 ; 1 byte
EVT_TYPE                 = $26 ; 1 byte
LAST_BYTE                = $27 ; 1 byte: the last byte the driver wrote to the buffer
ACK_BEFORE               = $28 ; 1 byte
PREV_HI                  = $29 ; 1 byte
PREV_LO                  = $2A ; 1 byte

SIMPLE_BUFFER            = $0200 ; 256 bytes
CONSOLE_TEXT             = $0300 ; CONSOLE_LENGTH + 1 bytes
LOG                      = $0400 ; 4 bytes per entry: type, byte, T1 high, T1 low
LOG_ENTRIES              = 10    ; 8 characters each fill the screen
KEY_ENTRIES              = 6     ; A start and an end for each of a key's 3 bytes

  .org PROGRAM_LOAD_ADDRESS      ; Loader loads programs to this address
start:
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  .include delay_routines.inc
  .include initialize_machine_v2.inc
EXTEND_CHARACTER_SET = 1
  .include display_routines.inc
CONSOLE_WIDTH = DISPLAY_WIDTH
CONSOLE_HEIGHT = DISPLAY_HEIGHT
  .include full_screen_console_flexible_line_based.inc
  .include simple_buffer.inc
  .include copy_memory.inc
  .include key_codes.inc
  .include keyboard_typematic.inc
KB_BUFFER_INITIALIZE    = simple_buffer_initialize
KB_BUFFER_WRITE         = probe_buffer_write
KB_BUFFER_READ          = simple_buffer_read
KB_NO_INTERRUPT_HANDLER = 1      ; probe_isr is copied to the ROM's IRQ vector instead
callback_kb_trace       = probe_trace
  .include keyboard_driver.inc
  .include convert_to_hex.inc

program_start:
  ; Initialize stack
  ldx #$ff
  txs
  stz LOGGING
  stz LOG_INDEX
  stz WAIT_COUNT
  stz WAIT_COUNT + 1

  lda #ACR_T1_CONT               ; T1 free-running from $FFFF
  sta ACR
  lda #$ff
  sta T1CL
  sta T1CH

  jsr reset_and_enable_display_no_cursor
  jsr console_initialize

  ; Copy the interrupt handler to the ROM's IRQ vector
  lda IRQ_VECTOR
  sta CP_M_DEST_P
  lda IRQ_VECTOR + 1
  sta CP_M_DEST_P + 1
  lda #<probe_isr
  sta CP_M_SRC_P
  lda #>probe_isr
  sta CP_M_SRC_P + 1
  lda #<(probe_isr_end - probe_isr)
  sta CP_M_LEN
  lda #>(probe_isr_end - probe_isr)
  sta CP_M_LEN + 1
  jsr copy_memory

  jsr keyboard_initialize
  lda #'I'
  jsr console_print_character
  jsr console_show

  lda #KB_COMMAND_READ_ID
  jsr keyboard_send_command
  lda #10
  jsr delay_hundredths           ; 100 ms for the rest of the reply
  sei
  stz LOGGING
  cli

  jsr show_log

  ; Log a key's frames
  stz LOG_INDEX
  lda #1
  sta LOGGING
.wait_for_key:
  lda LOG_INDEX
  cmp #KEY_ENTRIES * 4
  bcc .wait_for_key
  stz LOGGING
  jsr show_log

forever:
  bra forever


; Shows the log: each entry's time is from the previous one
; On exit A, X, Y are not preserved
show_log:
  jsr console_clear
  ldx #0
.entry:
  cpx LOG_INDEX
  beq .done
  cpx #0
  beq .first
  lda #' '
  jsr console_print_character
.first:
  lda LOG, X
  jsr console_print_character
  lda LOG + 1, X
  jsr console_print_hex
  cpx #0
  bne .delta
  lda LOG + 2, X
  sta PREV_HI
  lda LOG + 3, X
  sta PREV_LO
.delta:
  lda PREV_LO
  sec
  sbc LOG + 3, X
  sta T_LO
  lda PREV_HI
  sbc LOG + 2, X
  jsr console_print_hex
  lda T_LO
  jsr console_print_hex
  lda LOG + 2, X
  sta PREV_HI
  lda LOG + 3, X
  sta PREV_LO
  inx
  inx
  inx
  inx
  bra .entry
.done:
  jmp console_show               ; tail call


; The driver's KB_BUFFER_WRITE: notes each byte for the log
probe_buffer_write:
  sta LAST_BYTE
  jmp simple_buffer_write


; Called by keyboard_send_command at each step: logs the steps of sending $F2, starts logging
; interrupts, and gives up waiting for the ACK after 65536 times round
; On entry A = step, X = command byte
; On exit  X, Y are preserved
;          A is not preserved
probe_trace:
  cpx #KB_COMMAND_READ_ID
  bne .done
  cmp #'w'
  beq .wait
  cmp #'b'
  beq .marker
  cmp #'c'
  bne .done
.marker:
  sei
  sta EVT_TYPE
  stz LAST_BYTE
  lda T1CL
  sta T_LO
  lda T1CH
  sta T_HI
  phx
  jsr log_event
  plx
  lda #1
  sta LOGGING
  cli
  rts
.wait:
  inc WAIT_COUNT
  bne .done
  inc WAIT_COUNT + 1
  bne .done
  lda #1                         ; Give up waiting for the ACK
  sta ACK_RECEIVED
.done:
  rts


; Called by probe_isr: while logging, logs each CA2 interrupt around the driver's handler
; On exit X, Y are preserved
;         A is not preserved
probe_interrupt:
  lda LOGGING
  bne .log
  jmp handle_keyboard_interrupt
.log:
  lda #ICA2
  bit IFR
  bne .ca2
  rts
.ca2:
  phx
  lda T1CL
  sta T_LO
  lda T1CH
  sta T_HI
  lda #'s'
  ldx KEYBOARD_RECEIVING
  beq .type
  lda #'h'
  ldx SENDING_TO_KEYBOARD
  bne .type
  lda #'r'
.type:
  sta EVT_TYPE
  stz LAST_BYTE
  lda ACK_RECEIVED
  sta ACK_BEFORE
  jsr handle_keyboard_interrupt
  lda EVT_TYPE
  cmp #'r'
  bne .record
  lda ACK_RECEIVED
  cmp ACK_BEFORE
  beq .record
  lda #$fa
  sta LAST_BYTE
  lda #'a'
  sta EVT_TYPE
.record:
  jsr log_event
  plx
  rts


; Adds EVT_TYPE, LAST_BYTE, T_HI and T_LO to the log, unless it is full
; On exit A, X are not preserved
;         Y is preserved
log_event:
  ldx LOG_INDEX
  cpx #LOG_ENTRIES * 4
  beq .full
  lda EVT_TYPE
  sta LOG, X
  lda LAST_BYTE
  sta LOG + 1, X
  lda T_HI
  sta LOG + 2, X
  lda T_LO
  sta LOG + 3, X
  inx
  inx
  inx
  inx
  stx LOG_INDEX
.full:
  rts


; On entry A = byte to print in hex
; On exit  X, Y are preserved
;          A is not preserved
console_print_hex:
  phx
  jsr convert_to_hex
  jsr console_print_character
  txa
  jsr console_print_character
  plx
  rts


; Copied to the address in the ROM's IRQ vector
probe_isr:
  pha
  jsr probe_interrupt
  pla
  rti
probe_isr_end:
