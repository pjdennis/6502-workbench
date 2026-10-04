; Bring-up check for the Michael FPGA bus's reads (stage 1 of docs/michael-fpga-bus-plan.md), with the
; bus-check design loaded in the FPGA (hardware/michael/fpga/bus-check/). Reports each result on the LCD and,
; through SERIAL_SEND, to the PC, where hardware/michael/fpga/bus-check/check.py reads it:
;   FPGA BUS CHECK        the start
;   ID OK                 ID replies 'M', 'B', version 1, and the status is clear
;   ECHO BAD nnnn         32 passes of 256 bytes echoed and read back; nnnn mismatches (hex)
;   UNDERFLOW OK          an empty queue reads $00 and sets UNDERFLOW, which one status read clears
;   HOLD A KEY            the keyboard is now on: hold a key down until DONE
;   KEYBOARD BAD nnnn     more passes, with the keyboard interrupting at random points, until 128 keys
;                         have arrived (or about 15 s)
;   KEYS nnnn             characters the keyboard driver received meanwhile
; Status checks ignore BUSY: it's set while SERIAL_SEND's output is still going to the PC.
;   DONE
  .include base_config_v2.inc

INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET

DISPLAY_STRING_PARAM     = $00 ; 2 bytes
CP_M_DEST_P              = $02 ; 2 bytes
CP_M_SRC_P               = $04 ; 2 bytes
CP_M_LEN                 = $06 ; 2 bytes
SIMPLE_BUFFER_WRITE_PTR  = $08 ; 1 byte
SIMPLE_BUFFER_READ_PTR   = $09 ; 1 byte
ERRORS                   = $0A ; 2 bytes
KEYS                     = $0C ; 2 bytes
SEED                     = $0E ; 1 byte
PASSES                   = $0F ; 1 byte
GOT                      = $10 ; 1 byte
LINE                     = $11 ; 1 byte: the LCD line being written (DISPLAY_HEIGHT: the screen is full)
ROUNDS                   = $14 ; 1 byte
SAY_PTR                  = $12 ; 2 bytes
KB_ZERO_PAGE_BASE        = $20 ; 10 bytes

SIMPLE_BUFFER            = $0200 ; 256 bytes

ECHO_PASSES              = 32
KEYBOARD_KEYS            = 128   ; keys to wait for with the keyboard on, a round of passes at a time
KEYBOARD_ROUND_PASSES    = 16    ; about 0.25 s
KEYBOARD_ROUNDS          = 64    ; at most: about 15 s

  .org PROGRAM_LOAD_ADDRESS
start:
  jmp initialize_machine

  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_string.inc
  .include convert_to_hex.inc
  .include simple_buffer.inc
  .include copy_memory.inc
  .include key_codes.inc
  .include keyboard_typematic.inc
KB_BUFFER_INITIALIZE = simple_buffer_initialize
KB_BUFFER_WRITE      = simple_buffer_write
KB_BUFFER_READ       = simple_buffer_read
  .include keyboard_driver.inc
  .include fpga_bus.inc

program_start:
  ldx #$ff
  txs
  sei                            ; No keyboard until the last part

  jsr reset_and_enable_display_no_cursor
  stz LINE
  jsr simple_buffer_initialize   ; Empty, so echo_passes finds no keys until the keyboard is on
  jsr fb_initialize
  lda #<title
  ldx #>title
  jsr say_line

  ; ID, and a clear status
  lda #FB_RESET
  jsr fb_command
  lda #FB_ID
  jsr fb_command
  jsr fb_read
  cmp #'M'
  bne .id_bad
  jsr fb_read
  cmp #'B'
  bne .id_bad
  jsr fb_read
  cmp #1
  bne .id_bad
  jsr fb_read                    ; Capabilities: none in the check design
  jsr fb_status
  and #FB_ERRORS
  bne .id_bad
  lda #<id_ok
  ldx #>id_ok
  bra .id_done
.id_bad:
  lda #<id_bad
  ldx #>id_bad
.id_done:
  jsr say_line

  ; Echoed bytes read back
  stz ERRORS
  stz ERRORS + 1
  lda #ECHO_PASSES
  jsr echo_passes
  lda #<echo_bad
  ldx #>echo_bad
  jsr say_errors

  ; An empty reply queue
  jsr fb_read
  bne .underflow_bad
  jsr fb_status
  and #FB_ERRORS
  cmp #FB_UNDERFLOW
  bne .underflow_bad
  jsr fb_status
  and #FB_ERRORS
  bne .underflow_bad
  lda #<underflow_ok
  ldx #>underflow_ok
  bra .underflow_done
.underflow_bad:
  lda #<underflow_bad
  ldx #>underflow_bad
.underflow_done:
  jsr say_line

  ; The same with the keyboard interrupting
  lda #<hold_a_key
  ldx #>hold_a_key
  jsr say_line
  jsr keyboard_initialize        ; Enables interrupts
  lda #200
  jsr delay_hundredths           ; Time to hold a key down
  stz KEYS
  stz KEYS + 1
  stz ERRORS
  stz ERRORS + 1
  lda #KEYBOARD_ROUNDS
  sta ROUNDS
.round:
  lda #KEYBOARD_ROUND_PASSES
  jsr echo_passes
  lda KEYS + 1
  bne .enough_keys
  lda KEYS
  cmp #KEYBOARD_KEYS
  bcs .enough_keys
  dec ROUNDS
  bne .round
.enough_keys:
  sei
  lda #%00000001                 ; CA2 interrupt off
  sta IER
  lda #<keyboard_bad
  ldx #>keyboard_bad
  jsr say_errors
  lda #<keys
  ldx #>keys
  jsr say_string
  lda KEYS + 1
  jsr say_hex
  lda KEYS
  jsr say_hex
  jsr say_newline

  lda #<done
  ldx #>done
  jsr say_line
.forever:
  bra .forever


title:         .asciiz "FPGA BUS CHECK"
id_ok:         .asciiz "ID OK"
id_bad:        .asciiz "ID BAD"
echo_bad:      .asciiz "ECHO BAD "
underflow_ok:  .asciiz "UNDERFLOW OK"
underflow_bad: .asciiz "UNDERFLOW BAD"
hold_a_key:    .asciiz "HOLD A KEY"
keyboard_bad:  .asciiz "KEYBOARD BAD "
keys:          .asciiz "KEYS "
done:          .asciiz "DONE"


; Passes of ECHO with 256 bytes, read back and compared, with no errors in the status after each.
; Mismatches and status errors are added to ERRORS. Characters from the keyboard, if it's on, are added
; to KEYS.
; On entry A = passes (0 for 256)
echo_passes:
  sta PASSES
.pass:
  lda #FB_ECHO
  jsr fb_command
  ldx #0
.send:
  txa
  clc
  adc SEED
  jsr fb_data
  inx
  bne .send
.receive:
  jsr fb_read
  sta GOT
  txa
  clc
  adc SEED
  cmp GOT
  beq .matched
  jsr count_error
.matched:
  inx
  bne .receive
  jsr fb_status
  and #FB_ERRORS
  beq .status_clear
  jsr count_error
.status_clear:
  lda SEED
  clc
  adc #37                        ; A different pattern each pass
  sta SEED
.keys:
  jsr keyboard_get_char
  bcs .no_more_keys
  inc KEYS
  bne .keys
  inc KEYS + 1
  bra .keys
.no_more_keys:
  dec PASSES
  bne .pass
  rts


count_error:
  inc ERRORS
  bne .done
  inc ERRORS + 1
.done:
  rts


; Says the string at A (low), X (high), then ERRORS in hex, and ends the line
say_errors:
  jsr say_string
  lda ERRORS + 1
  jsr say_hex
  lda ERRORS
  jsr say_hex
  jmp say_newline


; Says the string at A (low), X (high) and ends the line
say_line:
  jsr say_string
  jmp say_newline


; Says the string at A (low), X (high): on the LCD and, through SERIAL_SEND, to the PC
say_string:
  sta SAY_PTR
  stx SAY_PTR + 1
  lda LINE
  cmp #DISPLAY_HEIGHT
  bne .room
  stz LINE
  jsr clear_display              ; A new screen, from the top
.room:
  lda #FB_SERIAL_SEND
  jsr fb_command
  ldy #0
.next:
  lda (SAY_PTR),Y
  beq .end
  jsr say_character
  iny
  bra .next
.end:
  rts


; On entry A = byte to say in hex (SERIAL_SEND already sent)
say_hex:
  jsr convert_to_hex
  jsr say_character
  txa
  ; fall through

; On entry A = character (SERIAL_SEND already sent)
say_character:
  jsr fb_data
  jmp display_character


; Ends the line: CR LF to the PC, and the next LCD line (after the last one, the next say_string clears
; the screen)
say_newline:
  lda #FB_SERIAL_SEND
  jsr fb_command
  lda #$0d
  jsr fb_data
  lda #$0a
  jsr fb_data
  inc LINE
  ldx LINE
  cpx #DISPLAY_HEIGHT
  beq .full
  lda lcd_lines,X
  jmp move_cursor
.full:
  rts

lcd_lines: .byte DISPLAY_FIRST_LINE, DISPLAY_SECOND_LINE, DISPLAY_THIRD_LINE, DISPLAY_FOURTH_LINE
