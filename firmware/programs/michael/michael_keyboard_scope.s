; For looking at Michael's PS/2 keyboard on an oscilloscope. Sends Read ID ($F2) about every
; 100 ms, so the same exchange repeats on the screen: the host's frame, the ACK ($FA), then
; the ID (AB 83).
;
; Scope trigger: the LED output (VIA PA1, pin 3) rises just before the clock is pulled low to
; send $F2 and falls about 20 ms later, once the reply is over. Trigger on its rising edge and
; probe the PS/2 clock and data lines, and CA2 (VIA pin 39), the frame detector's output.
;
;   Scope: send $F2
;   Trigger: LED (PA1)
;   ACK AB 83            what the driver got: ACK, or --- if none came within about 25 ms,
;   Count 002A           then the other bytes; and how many times $F2 has been sent
;
; It doesn't hang when the ACK is lost (as with the MC-689, whose reply bytes the board merges).
; See docs/michael-keyboard-frame-detection.md.

  .include base_config_v2.inc

INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET

CP_M_DEST_P              = $00 ; 2 bytes
CP_M_SRC_P               = $02 ; 2 bytes
CP_M_LEN                 = $04 ; 2 bytes

SIMPLE_BUFFER_WRITE_PTR  = $06 ; 1 byte
SIMPLE_BUFFER_READ_PTR   = $07 ; 1 byte

DISPLAY_STRING_PARAM     = $08 ; 2 bytes

COUNT                    = $0A ; 2 bytes: times the command has been sent
ACK_WAIT                 = $0C ; 1 byte: steps left to wait for the ACK; 0 once given up

KB_ZERO_PAGE_BASE        = $0D ; up to KB_ZERO_PAGE_STOP

SIMPLE_BUFFER            = $0200 ; 256 bytes

COMMAND                  = KB_COMMAND_READ_ID
ACK_WAIT_STEPS           = 250   ; 0.1 ms each: more than the 20 ms IBM allows for a response
REPLY_TIME               = 2     ; Hundredths of a second for the reply, after the ACK
REPEAT_TIME              = 8     ; Hundredths of a second between sends, besides the above
REPLY_BYTES_SHOWN        = 4

  .org PROGRAM_LOAD_ADDRESS      ; Loader loads programs to this address
start:
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  ; The initialize_machine routine in this include will set up hardware registers and then
  ; jump to program_start. We do not call a subroutine because for some machine designs the
  ; stack is not usable until after the hardware registers have been initialized
  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_string.inc
  .include display_hex.inc
  .include simple_buffer.inc
  .include copy_memory.inc
  .include key_codes.inc
  .include keyboard_typematic.inc
KB_BUFFER_INITIALIZE = simple_buffer_initialize
KB_BUFFER_WRITE      = simple_buffer_write
KB_BUFFER_READ       = simple_buffer_read
callback_kb_trace    = scope_trace
  .include keyboard_driver.inc


program_start:
  ; Initialize stack
  ldx #$ff
  txs

  stz COUNT
  stz COUNT + 1

  jsr reset_and_enable_display_no_cursor
  jsr keyboard_initialize

  lda #DISPLAY_FIRST_LINE
  jsr move_cursor
  lda #<title
  ldx #>title
  jsr display_string
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda #<trigger_label
  ldx #>trigger_label
  jsr display_string

repeat:
  ; Drop any bytes left over, such as keys typed
.drop:
  jsr KB_BUFFER_READ
  bcc .drop

  lda #COMMAND
  jsr keyboard_send_command      ; scope_trace raises the LED first
  lda #REPLY_TIME
  jsr delay_hundredths
  lda #LED
  trb PORTA                      ; End of the capture window

  jsr show_reply
  inc COUNT
  bne .counted
  inc COUNT + 1
.counted:
  jsr show_count

  lda #REPEAT_TIME
  jsr delay_hundredths
  bra repeat


; Called by keyboard_send_command at each step. For COMMAND it raises the LED as it starts,
; and gives up waiting for the ACK after ACK_WAIT_STEPS
; On entry A = step, X = command byte
; On exit  X, Y are preserved
;          A is not preserved
scope_trace:
  cpx #COMMAND
  bne .done
  cmp #'a'
  beq .starting
  cmp #'w'
  bne .done
  lda #1
  jsr delay_10_thousandths
  dec ACK_WAIT
  bne .done
  lda #1
  sta ACK_RECEIVED               ; Give up waiting for the ACK
  rts
.starting:
  lda #ACK_WAIT_STEPS
  sta ACK_WAIT
  lda #LED
  tsb PORTA                      ; Scope trigger
.done:
  rts


; Shows on the third line "ACK" (or "---" if it didn't come) and up to REPLY_BYTES_SHOWN
; other bytes received
; On exit A, X, Y are not preserved
show_reply:
  lda #DISPLAY_THIRD_LINE
  jsr move_cursor
  lda #<ack_label
  ldx #>ack_label
  ldy ACK_WAIT
  bne .show_ack
  lda #<no_ack_label
  ldx #>no_ack_label
.show_ack:
  jsr display_string
  ldy #REPLY_BYTES_SHOWN
.next:
  jsr KB_BUFFER_READ
  bcs .clear
  jsr display_space
  jsr display_hex
  dey
  bne .next
  rts
.clear:                          ; Spaces over the rest of the last reply
  lda #<blank_byte
  ldx #>blank_byte
  jsr display_string
  dey
  bne .clear
  rts


; Shows COUNT on the fourth line
; On exit A, X, Y are not preserved
show_count:
  lda #DISPLAY_FOURTH_LINE
  jsr move_cursor
  lda #<count_label
  ldx #>count_label
  jsr display_string
  lda COUNT + 1
  jsr display_hex
  lda COUNT
  jmp display_hex                ; tail call


title:         .asciiz "Scope: send $F2"
trigger_label: .asciiz "Trigger: LED (PA1)"
ack_label:     .asciiz "ACK"
no_ack_label:  .asciiz "---"
blank_byte:    .asciiz "   "
count_label:   .asciiz "Count "
