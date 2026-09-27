; Receives an upload in format 2 (tools/upload/upload_frame.py) and runs it: a header (version,
; start address) then blocks (length, load address, checksum, flags, data), every byte already
; bit-reversed by the sender.
;
; The whole stream is stored in order from UPLOAD_RAM_START - 10, so the header and the first
; block's header sit just below UPLOAD_RAM_START and the first block's data lands at
; UPLOAD_RAM_START. Each block's header is checked as soon as it arrives, and its checksum once its
; data has: blocks ascend without overlapping, within UPLOAD_RAM_START to INTERRUPT_ROUTINE, and
; their data never moves down. After the last block the blocks move up to their load addresses,
; last first, and the zero-fill blocks are cleared. Then the upload runs from its start address,
; or with none ($ffff) "Loaded." shows. A bad upload shows "Upload failed" and why, lights the LED
; and stops the CPU.
;
; The LCD is only written while nothing is being received: its routines briefly disable
; interrupts, which would lose bits.
;
; Requires:
;   serial_receive_timing.inc, serial_receive_interrupt.inc (copied to INTERRUPT_ROUTINE), 6522.inc
;   clear_display, move_cursor, display_string, display_hex (and their parameters)
;   UPLOAD_RAM_START, INTERRUPT_ROUTINE, LED (PORTA)
;   Zero page: UPLOAD_P (2), WAITING_FOR_SHIFT (1), UPLOAD_POS (2), UPLOAD_TARGET (2),
;     UPLOAD_CHECK_FROM (2), UPLOAD_END (2), UPLOAD_START (2), UPLOAD_FLAGS (1),
;     UPLOAD_BLOCK (1), CHECKSUM_VALUE (2), TEMP_P (2), UPLOAD_LENGTH (2), UPLOAD_ADDRESS (2),
;     UPLOAD_FROM (2)

UPLOAD_VERSION     = 2
UPLOAD_MORE        = %00000001
UPLOAD_ZERO_FILL   = %00000010
UPLOAD_NO_START    = $ffff
UPLOAD_STREAM      = UPLOAD_RAM_START - 10 ; Header (3) and the first block's header (7)
UPLOAD_MAX_BLOCKS  = 100                   ; Each block's stream position goes on the stack

; Offsets in a block header
UPLOAD_H_LENGTH    = 0
UPLOAD_H_ADDRESS   = 2
UPLOAD_H_CHECKSUM  = 4
UPLOAD_H_FLAGS     = 6
UPLOAD_H_SIZE      = 7

upload_loaded_message:  .asciiz 'Loaded.'
upload_failed_message:  .asciiz 'Upload failed'
upload_version_message: .asciiz 'Bad version '
upload_block_message:   .asciiz 'Bad block '
upload_checksum_message: .asciiz 'Bad checksum '


; Receive and run an upload. Does not return
upload_v2:
  ldx #<(UPLOAD_STREAM - 1)       ; Stack below the stream
  txs

  ldx #0                          ; The receive handler goes where the interrupt vector points
.copy_handler:
  lda interrupt, X
  sta INTERRUPT_ROUTINE, X
  inx
  cpx #<(interrupt_end - interrupt)
  bne .copy_handler

  stz WAITING_FOR_SHIFT
  lda #<UPLOAD_STREAM
  sta UPLOAD_P
  sta UPLOAD_POS
  sta UPLOAD_CHECK_FROM
  lda #>UPLOAD_STREAM
  sta UPLOAD_P + 1
  sta UPLOAD_POS + 1
  sta UPLOAD_CHECK_FROM + 1

  lda #PCR_CB2_IND_NEG_E          ; CB2 independent interrupt negative edge
  sta PCR
  lda #ICB2                       ; Clear any pending CB2 interrupt
  sta IFR
  lda #(IERSETCLEAR | ICB2 | ISR) ; Enable interrupts for SR and CB2
  sta IER
  lda #INITIAL_INTERVAL
  sta T2CL
  cli

  ; The header: version, start address
  lda #3
  jsr upload_wait_past_pos
  lda (UPLOAD_POS)
  cmp #UPLOAD_VERSION
  beq .version_ok
  jmp upload_bad_version
.version_ok:
  ldy #1
  lda (UPLOAD_POS), Y
  sta UPLOAD_START
  iny
  lda (UPLOAD_POS), Y
  sta UPLOAD_START + 1
  lda #3
  jsr upload_advance_pos
  lda #<UPLOAD_RAM_START          ; Blocks start at or above the end of the one before
  sta UPLOAD_END
  lda #>UPLOAD_RAM_START
  sta UPLOAD_END + 1
  stz UPLOAD_BLOCK

.block:
  jsr upload_check_block
  bcs .bad_block

  ; The data, if any, follows the header in the stream
  lda UPLOAD_FLAGS
  and #UPLOAD_ZERO_FILL
  bne .have_data
  clc
  lda UPLOAD_TARGET
  adc UPLOAD_LENGTH
  sta UPLOAD_TARGET
  lda UPLOAD_TARGET + 1
  adc UPLOAD_LENGTH + 1
  sta UPLOAD_TARGET + 1
  jsr upload_wait_for_target
.have_data:

  ; Checksum: from the end of the previous block to here, less the checksum bytes
  stz CHECKSUM_VALUE
  stz CHECKSUM_VALUE + 1
  lda #UPLOAD_H_CHECKSUM
  jsr upload_checksum_to_pos_plus
  clc
  lda UPLOAD_POS
  adc #UPLOAD_H_FLAGS
  sta UPLOAD_CHECK_FROM
  lda UPLOAD_POS + 1
  adc #0
  sta UPLOAD_CHECK_FROM + 1
  jsr upload_checksum_to_target
  ldy #UPLOAD_H_CHECKSUM
  lda (UPLOAD_POS), Y
  cmp CHECKSUM_VALUE
  bne .bad_checksum
  iny
  lda (UPLOAD_POS), Y
  cmp CHECKSUM_VALUE + 1
  bne .bad_checksum

  lda UPLOAD_POS + 1              ; Remember where the block is, for moving it later
  pha
  lda UPLOAD_POS
  pha
  lda UPLOAD_TARGET               ; The next block starts where this one's data ends
  sta UPLOAD_POS
  sta UPLOAD_CHECK_FROM
  lda UPLOAD_TARGET + 1
  sta UPLOAD_POS + 1
  sta UPLOAD_CHECK_FROM + 1
  lda UPLOAD_FLAGS
  and #UPLOAD_MORE
  beq .received
  jmp .block

.bad_block:
  jmp upload_bad_block
.bad_checksum:
  jmp upload_bad_checksum

.received:
  jsr upload_stop_receiving
.place:                           ; Last block first
  pla
  sta UPLOAD_POS
  pla
  sta UPLOAD_POS + 1
  jsr upload_read_header
  jsr upload_place_block
  dec UPLOAD_BLOCK
  bne .place

  lda UPLOAD_START
  and UPLOAD_START + 1
  cmp #$ff
  beq .no_start
  ldx #$ff
  txs
  jmp (UPLOAD_START)

.no_start:
  jsr clear_display
  lda #<upload_loaded_message
  ldx #>upload_loaded_message
  jsr display_string
  stp


; Wait for the next block's header, at UPLOAD_POS, then read and check it. UPLOAD_TARGET is then
; where its data starts, and UPLOAD_END where it ends up.
; On exit C set if the block is bad
upload_check_block:
  inc UPLOAD_BLOCK
  lda UPLOAD_BLOCK
  cmp #UPLOAD_MAX_BLOCKS + 1
  bcs .bad
  lda #UPLOAD_H_SIZE              ; The header must end below the receive handler...
  jsr upload_target_past_pos
  bcs .bad
  lda UPLOAD_TARGET + 1
  cmp #>INTERRUPT_ROUTINE
  bcs .bad
  jsr upload_wait_for_target      ; ...and then be here
  jsr upload_read_header
  lda UPLOAD_FLAGS
  and #(~(UPLOAD_MORE | UPLOAD_ZERO_FILL)) & $ff
  bne .bad

  ; Load address >= the previous block's end (and UPLOAD_RAM_START), and >= where the data sits
  lda UPLOAD_ADDRESS
  cmp UPLOAD_END
  lda UPLOAD_ADDRESS + 1
  sbc UPLOAD_END + 1
  bcc .bad
  lda UPLOAD_ADDRESS
  cmp UPLOAD_TARGET
  lda UPLOAD_ADDRESS + 1
  sbc UPLOAD_TARGET + 1
  bcc .bad
  ; End = load address + length, at most INTERRUPT_ROUTINE
  clc
  lda UPLOAD_ADDRESS
  adc UPLOAD_LENGTH
  sta UPLOAD_END
  lda UPLOAD_ADDRESS + 1
  adc UPLOAD_LENGTH + 1
  sta UPLOAD_END + 1
  bcs .bad
  lda #<INTERRUPT_ROUTINE
  cmp UPLOAD_END
  lda #>INTERRUPT_ROUTINE
  sbc UPLOAD_END + 1
  bcc .bad
  clc
  rts
.bad:
  sec
  rts

; UPLOAD_TARGET = UPLOAD_POS + A; C set if that passes $ffff
upload_target_past_pos:
  clc
  adc UPLOAD_POS
  sta UPLOAD_TARGET
  lda UPLOAD_POS + 1
  adc #0
  sta UPLOAD_TARGET + 1
  rts

; UPLOAD_POS += A
upload_advance_pos:
  jsr upload_target_past_pos
  lda UPLOAD_TARGET
  sta UPLOAD_POS
  lda UPLOAD_TARGET + 1
  sta UPLOAD_POS + 1
  rts

; Wait until A bytes past UPLOAD_POS have arrived
upload_wait_past_pos:
  jsr upload_target_past_pos
  ; fall through

; Wait until the stream has reached UPLOAD_TARGET. UPLOAD_P only grows, so comparing the high
; bytes first can only ever wait too long, never too short
upload_wait_for_target:
  lda UPLOAD_P + 1
  cmp UPLOAD_TARGET + 1
  bcc upload_wait_for_target
  bne .done
  lda UPLOAD_P
  cmp UPLOAD_TARGET
  bcc upload_wait_for_target
.done:
  rts

; The block header at UPLOAD_POS into UPLOAD_LENGTH, UPLOAD_ADDRESS and UPLOAD_FLAGS
upload_read_header:
  ldy #UPLOAD_H_LENGTH
  lda (UPLOAD_POS), Y
  sta UPLOAD_LENGTH
  iny
  lda (UPLOAD_POS), Y
  sta UPLOAD_LENGTH + 1
  iny
  lda (UPLOAD_POS), Y
  sta UPLOAD_ADDRESS
  iny
  lda (UPLOAD_POS), Y
  sta UPLOAD_ADDRESS + 1
  ldy #UPLOAD_H_FLAGS
  lda (UPLOAD_POS), Y
  sta UPLOAD_FLAGS
  rts

; Add the bytes from UPLOAD_CHECK_FROM up to UPLOAD_POS + A to the checksum
upload_checksum_to_pos_plus:
  jsr upload_target_past_pos
  jsr upload_checksum_to_target
  ; Leave UPLOAD_TARGET at the end of the block's data again
  lda #UPLOAD_H_SIZE
  jsr upload_target_past_pos
  lda UPLOAD_FLAGS
  and #UPLOAD_ZERO_FILL
  bne .done
  clc
  lda UPLOAD_TARGET
  adc UPLOAD_LENGTH
  sta UPLOAD_TARGET
  lda UPLOAD_TARGET + 1
  adc UPLOAD_LENGTH + 1
  sta UPLOAD_TARGET + 1
.done:
  rts

; Add the bytes from UPLOAD_CHECK_FROM up to UPLOAD_TARGET to the checksum, as
; calculate_checksum does
upload_checksum_to_target:
  lda UPLOAD_CHECK_FROM
  sta TEMP_P
  lda UPLOAD_CHECK_FROM + 1
  sta TEMP_P + 1
.loop:
  lda TEMP_P
  cmp UPLOAD_TARGET
  bne .add
  lda TEMP_P + 1
  cmp UPLOAD_TARGET + 1
  beq .done
.add:
  lda CHECKSUM_VALUE + 1          ; Rotate right...
  ror
  ror CHECKSUM_VALUE
  ror CHECKSUM_VALUE + 1
  clc                             ; ...and add the byte
  lda (TEMP_P)
  adc CHECKSUM_VALUE
  sta CHECKSUM_VALUE
  bcc .next
  inc CHECKSUM_VALUE + 1
.next:
  inc TEMP_P
  bne .loop
  inc TEMP_P + 1
  bra .loop
.done:
  rts

upload_stop_receiving:
  sei
  stz ACR                         ; Disable shifting
  stz PCR                         ; Turn off CB2 interrupts
  lda #(ICB2 | ISR)               ; Disable and reset interrupt flags
  sta IER
  sta IFR
  rts

; Move the block whose header is at UPLOAD_POS up to its load address, or clear it
upload_place_block:
  lda UPLOAD_FLAGS
  and #UPLOAD_ZERO_FILL
  bne .clear
  clc                             ; From: its data in the stream
  lda UPLOAD_POS
  adc #UPLOAD_H_SIZE
  sta UPLOAD_FROM
  lda UPLOAD_POS + 1
  adc #0
  sta UPLOAD_FROM + 1
  cmp UPLOAD_ADDRESS + 1
  bne .move
  lda UPLOAD_FROM
  cmp UPLOAD_ADDRESS
  beq .done                       ; Already in place
.move:                            ; Copy from the top down: the areas may overlap
  clc                             ; Point both at one past the last byte
  lda UPLOAD_FROM
  adc UPLOAD_LENGTH
  sta UPLOAD_FROM
  lda UPLOAD_FROM + 1
  adc UPLOAD_LENGTH + 1
  sta UPLOAD_FROM + 1
  clc
  lda UPLOAD_ADDRESS
  adc UPLOAD_LENGTH
  sta UPLOAD_ADDRESS
  lda UPLOAD_ADDRESS + 1
  adc UPLOAD_LENGTH + 1
  sta UPLOAD_ADDRESS + 1
.move_loop:
  jsr upload_count_down
  beq .done
  lda UPLOAD_FROM
  bne .from_low
  dec UPLOAD_FROM + 1
.from_low:
  dec UPLOAD_FROM
  lda UPLOAD_ADDRESS
  bne .to_low
  dec UPLOAD_ADDRESS + 1
.to_low:
  dec UPLOAD_ADDRESS
  lda (UPLOAD_FROM)
  sta (UPLOAD_ADDRESS)
  bra .move_loop
.clear:
  jsr upload_count_down
  beq .done
  lda #0
  sta (UPLOAD_ADDRESS)
  inc UPLOAD_ADDRESS
  bne .clear
  inc UPLOAD_ADDRESS + 1
  bra .clear
.done:
  rts

; Z set if UPLOAD_LENGTH is 0, else decrement it
upload_count_down:
  lda UPLOAD_LENGTH
  ora UPLOAD_LENGTH + 1
  beq .done
  lda UPLOAD_LENGTH
  bne .low
  dec UPLOAD_LENGTH + 1
.low:
  dec UPLOAD_LENGTH
  lda #1                          ; Z clear
.done:
  rts


upload_bad_version:
  lda (UPLOAD_POS)
  ldx #<upload_version_message
  ldy #>upload_version_message
  bra upload_failed
upload_bad_block:
  lda UPLOAD_BLOCK
  ldx #<upload_block_message
  ldy #>upload_block_message
  bra upload_failed
upload_bad_checksum:
  lda UPLOAD_BLOCK
  ldx #<upload_checksum_message
  ldy #>upload_checksum_message
  ; fall through

; Show "Upload failed" and the message at X, Y with A in hex; light the LED and stop
upload_failed:
  pha
  phx
  phy
  jsr upload_stop_receiving
  jsr clear_display
  lda #<upload_failed_message
  ldx #>upload_failed_message
  jsr display_string
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  ply
  plx
  txa
  phy
  plx
  jsr display_string
  pla
  jsr display_hex
  lda #LED
  tsb PORTA
  stp
