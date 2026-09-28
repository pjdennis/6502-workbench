; Keyboard diagnostic for Michael. Shows how far the keyboard start-up handshake gets, then
; shows the raw PS/2 bytes received. The last thing on the screen shows where it stopped.
;
; The screen shows "IRQ xxxx", the ROM's IRQ vector, where the interrupt handler is copied.
; Then, for each byte sent to the keyboard (F4 enable, F3 20 typematic, ED 02 LEDs):
;   the byte in hex - send started
;   b               - clock pulled low and CA2 saw the falling edge
;   c               - byte loaded into the output shift register and clock released
;   d               - keyboard clocked the byte in and the CA2 interrupt ran the handler
;   space           - keyboard replied with ACK ($FA)
; Bytes other than ACK received while waiting for the ACK are shown as [xx].
; After start-up it shows ">" and then each byte received from the keyboard in hex.

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

SIMPLE_BUFFER            = $0200 ; 256 bytes
CONSOLE_TEXT             = $0300 ; CONSOLE_LENGTH + 1 bytes

  .org PROGRAM_LOAD_ADDRESS      ; Loader loads programs to this address
start:
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  ; The initialize_machine routine in this include will set up hardware registers and then
  ; jump to program_start. We do not call a subroutine because for some machine designs the
  ; stack is not usable until after the hardware registers have been initialized
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
KB_BUFFER_WRITE         = simple_buffer_write
KB_BUFFER_READ          = simple_buffer_read
KB_NO_INTERRUPT_HANDLER = 1      ; diag_interrupt is copied to the ROM's IRQ vector instead
callback_kb_trace       = diag_trace
  .include keyboard_driver.inc
  .include convert_to_hex.inc


program_start:
  ; Initialize stack
  ldx #$ff
  txs

  jsr reset_and_enable_display_no_cursor
  jsr console_initialize

  ; Show the ROM's IRQ vector and copy the interrupt handler there
  ldx #0
.print_irq_message:
  lda irq_message, X
  beq .irq_message_done
  jsr console_print_character
  inx
  bra .print_irq_message
.irq_message_done:
  lda IRQ_VECTOR + 1
  sta CP_M_DEST_P + 1
  jsr console_print_hex
  lda IRQ_VECTOR
  sta CP_M_DEST_P
  jsr console_print_hex
  lda #' '
  jsr console_print_character
  jsr console_show

  lda #<diag_interrupt
  sta CP_M_SRC_P
  lda #>diag_interrupt
  sta CP_M_SRC_P + 1
  lda #<(diag_interrupt_end - diag_interrupt)
  sta CP_M_LEN
  lda #>(diag_interrupt_end - diag_interrupt)
  sta CP_M_LEN + 1
  jsr copy_memory

  jsr keyboard_initialize

  lda #'>'
  jsr console_print_character
  jsr console_show

  ; Show each byte received from the keyboard
show_bytes:
  jsr KB_BUFFER_READ
  bcs show_bytes
  jsr console_print_hex
  lda #' '
  jsr console_print_character
  jsr console_show
  bra show_bytes


; Called by keyboard_send_command at each step
; On entry A = step ('a' to 'e', or 'w' while waiting for the ACK), X = command byte
; On exit  X, Y are preserved
;          A is not preserved
diag_trace:
  cmp #'w'
  beq .waiting
  cmp #'a'
  beq .start
  cmp #'e'
  bne .print
  lda #' '
.print:
  jsr console_print_character
  jmp console_show
.start:
  txa
  jsr console_print_hex
  jmp console_show

  ; Show any byte other than ACK received while waiting for the ACK
.waiting:
  jsr KB_BUFFER_READ
  bcs .done
  pha
  lda #'['
  jsr console_print_character
  pla
  jsr console_print_hex
  lda #']'
  jsr console_print_character
  jsr console_show
.done:
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
diag_interrupt:
  pha
  jsr handle_keyboard_interrupt
  pla
  rti
diag_interrupt_end:


irq_message: .asciiz "IRQ "
