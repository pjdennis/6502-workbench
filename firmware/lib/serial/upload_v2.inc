; Receives an upload in format 2 (tools/upload/upload_frame.py) and runs it: a header (version,
; start address) then blocks (length, load address, checksum, flags, data), every byte already
; bit-reversed by the sender.
;
; The whole stream is stored in order from UPLOAD_RAM_START - 10, so the header and the first
; block's header sit just below UPLOAD_RAM_START and the first block's data lands at
; UPLOAD_RAM_START. While the receive handler stores bytes, the main loop takes turns at two
; tasks: checking (each block's header once it has arrived, then its checksum, a few bytes at a
; time as they come in) and showing progress on the first two rows of the LCD (16 columns, so a
; 2x16 panel will do):
;
;   Block 02 $0A40      the block arriving, and where its next byte will end up ($---- while
;   Received $1A40      its header is arriving); every byte received so far
;
; redrawn when the count changes, but at most every UPLOAD_REDRAW_TICKS runs of timer 1 (~0.2 s)
; since redrawing nonstop dims the LCD; a stalled upload still shows exactly how far it got. Blocks
; must ascend without overlapping, within UPLOAD_RAM_START to INTERRUPT_ROUTINE, and their data
; must never move down. After the last block they move up to their load addresses, last first,
; and the zero-fill blocks are cleared; then the LCD is cleared and the upload runs from its start
; address (after UPLOAD_BEFORE_RUN, if defined), or with none ($ffff) "Loaded." shows. A bad
; upload shows "Upload failed" and why, lights the LED and stops the CPU.
;
; The LCD routines must leave interrupts on while receiving, which would otherwise lose bits:
; DISPLAY_INTERRUPTS_FLAG (bit 7 is set while receiving) or DISPLAY_DO_NOT_DISABLE_INTERRUPTS.
;
; Requires:
;   serial_receive_timing.inc, serial_receive_interrupt.inc (copied to INTERRUPT_ROUTINE), 6522.inc
;   clear_display, display_command, display_string, display_hex (and their parameters)
;   UPLOAD_RAM_START, INTERRUPT_ROUTINE, LED (PORTA)
;   Zero page: UPLOAD_P (2), WAITING_FOR_SHIFT (1), UPLOAD_POS (2), UPLOAD_TARGET (2),
;     UPLOAD_CHECK_FROM (2), UPLOAD_END (2), UPLOAD_START (2), UPLOAD_FLAGS (1),
;     UPLOAD_BLOCK (1), CHECKSUM_VALUE (2), TEMP_P (2), UPLOAD_LENGTH (2), UPLOAD_ADDRESS (2),
;     UPLOAD_FROM (2), UPLOAD_STATE (1), UPLOAD_SEEN (2), UPLOAD_SHOWN (2), UPLOAD_DATA (2),
;     UPLOAD_SHOWN_BLOCK (1), TEMP (1), UPLOAD_TICKS (1)
;   Timer 1, while receiving
; Optional: UPLOAD_BEFORE_RUN - called just before running an upload

  .ifndef DISPLAY_INTERRUPTS_FLAG
  .if DISPLAY_DO_NOT_DISABLE_INTERRUPTS == 0
  fail "The loader's LCD routines would disable interrupts while receiving"
  .endif
  .endif

UPLOAD_VERSION     = 2
UPLOAD_MORE        = %00000001
UPLOAD_ZERO_FILL   = %00000010
UPLOAD_STREAM      = UPLOAD_RAM_START - 10 ; Header (3) and the first block's header (7)
UPLOAD_MAX_BLOCKS  = 100                   ; Each block's stream position goes on the stack
UPLOAD_SUM_STEP    = 32                    ; Most bytes summed before the display's turn
UPLOAD_REDRAW_TICKS = 6                    ; Runs of timer 1 (65538 cycles) between redraws

; Offsets in a block header
UPLOAD_H_LENGTH    = 0
UPLOAD_H_ADDRESS   = 2
UPLOAD_H_CHECKSUM  = 4
UPLOAD_H_FLAGS     = 6
UPLOAD_H_SIZE      = 7

; UPLOAD_STATE: what the checking task is waiting for
UPLOAD_S_HEADER    = 0                     ; The upload's header
UPLOAD_S_BLOCK     = 1                     ; A block's header
UPLOAD_S_DATA      = 2                     ; A block's data, being summed as it arrives

; Where the progress fields go
UPLOAD_ROW_BLOCK   = CMD_SET_DDRAM_ADDRESS | DISPLAY_FIRST_LINE
UPLOAD_ROW_COUNT   = CMD_SET_DDRAM_ADDRESS | DISPLAY_SECOND_LINE
UPLOAD_FIELD       = 10                    ; The column of both rows' hex

upload_block_label:     .asciiz 'Block '
upload_address_mark:    .asciiz ' $'
upload_received_label:  .asciiz 'Received $'
upload_no_address:      .asciiz '----'
upload_loaded_message:  .asciiz 'Loaded.         '
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
  lda #<UPLOAD_RAM_START          ; Blocks start at or above the end of the one before
  sta UPLOAD_END
  lda #>UPLOAD_RAM_START
  sta UPLOAD_END + 1
  lda #UPLOAD_S_HEADER
  sta UPLOAD_STATE
  lda #1
  sta UPLOAD_BLOCK
  stz UPLOAD_TICKS                ; Free to redraw
  stz UPLOAD_SHOWN_BLOCK          ; Nothing shown yet...
  lda #$ff
  sta UPLOAD_SHOWN
  sta UPLOAD_SHOWN + 1            ; ...not even the count

  .ifdef DISPLAY_INTERRUPTS_FLAG
  lda #%10000000                  ; The LCD routines leave interrupts on from here
  tsb DISPLAY_INTERRUPTS_FLAG
  .endif
  lda #UPLOAD_ROW_COUNT
  jsr display_command
  lda #<upload_received_label
  ldx #>upload_received_label
  jsr display_string

  lda #PCR_CB2_IND_NEG_E          ; CB2 independent interrupt negative edge
  sta PCR
  lda #ICB2                       ; Clear any pending CB2 interrupt
  sta IFR
  lda #(IERSETCLEAR | ICB2 | ISR) ; Enable interrupts for SR and CB2
  sta IER
  lda #INITIAL_INTERVAL
  sta T2CL
  cli

.loop:                            ; Take turns: show progress, then check a little
  jsr upload_read_seen
  jsr upload_pace_progress
  jsr upload_check_step
  bcc .loop

  jsr upload_read_seen            ; The final count
  jsr upload_show_progress
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
  jsr clear_display
  .ifdef UPLOAD_BEFORE_RUN
  jsr UPLOAD_BEFORE_RUN
  .endif
  ldx #$ff
  txs
  jmp (UPLOAD_START)

.no_start:
  lda #UPLOAD_ROW_BLOCK
  jsr display_command
  lda #<upload_loaded_message
  ldx #>upload_loaded_message
  jsr display_string
  stp


; UPLOAD_SEEN = UPLOAD_P, the next byte's address, read so the receive handler can't change it
; between its two halves
upload_read_seen:
  lda UPLOAD_P + 1
  sta UPLOAD_SEEN + 1
  lda UPLOAD_P
  sta UPLOAD_SEEN
  lda UPLOAD_P + 1
  cmp UPLOAD_SEEN + 1
  bne upload_read_seen
  rts


; Make the display task redraw next time (after a change it can't see in the count)
upload_redraw:
  lda #$ff
  sta UPLOAD_SHOWN + 1
  rts

; The display task: redraw what has changed since last time, once UPLOAD_TICKS has counted
; down; each run of timer 1 (one-shot, polled) counts it down, and a redraw restarts it
upload_pace_progress:
  lda UPLOAD_TICKS
  beq upload_show_progress
  lda #IT1
  bit IFR
  beq .wait
  dec UPLOAD_TICKS
  jsr upload_start_tick
.wait:
  rts

upload_show_progress:
  lda UPLOAD_SEEN
  cmp UPLOAD_SHOWN
  bne .changed
  lda UPLOAD_SEEN + 1
  cmp UPLOAD_SHOWN + 1
  bne .changed
  lda UPLOAD_BLOCK
  cmp UPLOAD_SHOWN_BLOCK
  bne .changed
  rts
.changed:
  lda #UPLOAD_REDRAW_TICKS
  sta UPLOAD_TICKS
  jsr upload_start_tick
  lda UPLOAD_SEEN
  sta UPLOAD_SHOWN
  lda UPLOAD_SEEN + 1
  sta UPLOAD_SHOWN + 1

  lda #UPLOAD_ROW_COUNT + UPLOAD_FIELD
  jsr display_command
  sec                             ; Received = UPLOAD_SHOWN - UPLOAD_STREAM
  lda UPLOAD_SHOWN
  sbc #<UPLOAD_STREAM
  tax
  lda UPLOAD_SHOWN + 1
  sbc #>UPLOAD_STREAM
  jsr display_hex
  txa
  jsr display_hex
  lda UPLOAD_SHOWN                ; Nothing yet: leave the first row as it is
  cmp #<UPLOAD_STREAM
  bne .block_row
  lda UPLOAD_SHOWN + 1
  cmp #>UPLOAD_STREAM
  beq .done

.block_row:
  lda UPLOAD_BLOCK
  cmp UPLOAD_SHOWN_BLOCK
  beq .address
  sta UPLOAD_SHOWN_BLOCK
  lda #UPLOAD_ROW_BLOCK
  jsr display_command
  lda #<upload_block_label
  ldx #>upload_block_label
  jsr display_string
  lda UPLOAD_BLOCK
  jsr display_hex
  lda #<upload_address_mark
  ldx #>upload_address_mark
  jsr display_string
.address:
  lda #UPLOAD_ROW_BLOCK + UPLOAD_FIELD
  jsr display_command
  lda UPLOAD_STATE
  cmp #UPLOAD_S_DATA
  beq .show_address
  lda #<upload_no_address
  ldx #>upload_no_address
  jmp display_string
.show_address:                    ; Load address + data received, at most to the data's end
  lda UPLOAD_SHOWN
  ldx UPLOAD_SHOWN + 1
  cmp UPLOAD_TARGET
  txa
  sbc UPLOAD_TARGET + 1
  bcc .within
  lda UPLOAD_TARGET
  ldx UPLOAD_TARGET + 1
  bra .offset
.within:
  lda UPLOAD_SHOWN
.offset:
  sec
  sbc UPLOAD_DATA
  sta TEMP
  txa
  sbc UPLOAD_DATA + 1
  tax
  clc
  lda TEMP
  adc UPLOAD_ADDRESS
  sta TEMP
  txa
  adc UPLOAD_ADDRESS + 1
  jsr display_hex
  lda TEMP
  jmp display_hex
.done:
  rts


; Start a run of timer 1 (clearing its flag)
upload_start_tick:
  lda #$ff
  sta T1CL
  sta T1CH
  rts


; The checking task: one step
; On exit C set once the last block has checked out
upload_check_step:
  lda UPLOAD_STATE
  cmp #UPLOAD_S_BLOCK
  beq upload_check_block_header
  bcc upload_check_upload_header
  jmp upload_check_data

; The upload's header: version, start address
upload_check_upload_header:
  lda #3
  jsr upload_seen_past_pos
  bcc .wait
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
  clc
  lda UPLOAD_POS
  adc #3
  sta UPLOAD_POS
  bcc .advanced
  inc UPLOAD_POS + 1
.advanced:
  lda #UPLOAD_S_BLOCK
  sta UPLOAD_STATE
.wait:
  clc
  rts

; A block's header: check it once it has arrived, and start summing
upload_check_block_header:
  lda UPLOAD_BLOCK
  cmp #UPLOAD_MAX_BLOCKS + 1
  bcs .bad_block
  lda #UPLOAD_H_SIZE              ; The header must end below the receive handler
  jsr upload_seen_past_pos
  php
  lda UPLOAD_TARGET + 1
  cmp #>INTERRUPT_ROUTINE
  bcs .bad_block_pull
  plp
  bcc .wait
  jsr upload_read_header
  jsr upload_valid_block
  bcs .bad_block
  lda UPLOAD_TARGET               ; Its data starts after the header...
  sta UPLOAD_DATA
  lda UPLOAD_TARGET + 1
  sta UPLOAD_DATA + 1
  lda UPLOAD_FLAGS                ; ...and ends after its length (a zero-fill block has none)
  and #UPLOAD_ZERO_FILL
  bne .no_data
  clc
  lda UPLOAD_TARGET
  adc UPLOAD_LENGTH
  sta UPLOAD_TARGET
  lda UPLOAD_TARGET + 1
  adc UPLOAD_LENGTH + 1
  sta UPLOAD_TARGET + 1
.no_data:
  ; Sum from the end of the previous block to the checksum field, then from the flags on
  stz CHECKSUM_VALUE
  stz CHECKSUM_VALUE + 1
  lda UPLOAD_CHECK_FROM
  sta TEMP_P
  lda UPLOAD_CHECK_FROM + 1
  sta TEMP_P + 1
  clc
  lda UPLOAD_POS
  adc #UPLOAD_H_CHECKSUM
  tax
  lda UPLOAD_POS + 1
  adc #0
  jsr upload_sum_to
  clc
  lda UPLOAD_POS
  adc #UPLOAD_H_FLAGS
  sta TEMP_P
  lda UPLOAD_POS + 1
  adc #0
  sta TEMP_P + 1
  lda #UPLOAD_S_DATA
  sta UPLOAD_STATE
  jsr upload_redraw               ; Now there's an address to show
.wait:
  clc
  rts
.bad_block_pull:
  plp
.bad_block:
  jmp upload_bad_block

; A block's data: sum what has arrived, a few bytes at a time; check the sum at its end
upload_check_data:
  ldy #UPLOAD_SUM_STEP
.sum:
  lda TEMP_P                      ; At the data's end?
  cmp UPLOAD_TARGET
  bne .not_end
  lda TEMP_P + 1
  cmp UPLOAD_TARGET + 1
  beq .end
.not_end:
  lda TEMP_P                      ; Caught up with the stream?
  cmp UPLOAD_SEEN
  bne .add
  lda TEMP_P + 1
  cmp UPLOAD_SEEN + 1
  beq .wait
.add:
  jsr upload_sum_byte
  dey
  bne .sum
.wait:
  clc
  rts
.end:
  ldy #UPLOAD_H_CHECKSUM
  lda (UPLOAD_POS), Y
  cmp CHECKSUM_VALUE
  bne .bad_checksum
  iny
  lda (UPLOAD_POS), Y
  cmp CHECKSUM_VALUE + 1
  bne .bad_checksum
  pla                             ; The block's stream position goes under the return address,
  tax                             ; for moving it later
  pla
  tay
  lda UPLOAD_POS + 1
  pha
  lda UPLOAD_POS
  pha
  tya
  pha
  txa
  pha
  lda UPLOAD_TARGET               ; The next block starts where this one's data ends
  sta UPLOAD_POS
  sta UPLOAD_CHECK_FROM
  lda UPLOAD_TARGET + 1
  sta UPLOAD_POS + 1
  sta UPLOAD_CHECK_FROM + 1
  lda UPLOAD_FLAGS
  and #UPLOAD_MORE
  sec
  beq .last                       ; C set: all checked
  inc UPLOAD_BLOCK
  lda #UPLOAD_S_BLOCK
  sta UPLOAD_STATE
  jsr upload_redraw
  clc
.last:
  rts
.bad_checksum:
  jmp upload_bad_checksum


; C set if UPLOAD_SEEN has reached UPLOAD_POS + A, which goes in UPLOAD_TARGET
upload_seen_past_pos:
  clc
  adc UPLOAD_POS
  sta UPLOAD_TARGET
  lda UPLOAD_POS + 1
  adc #0
  sta UPLOAD_TARGET + 1
  lda UPLOAD_SEEN
  cmp UPLOAD_TARGET
  lda UPLOAD_SEEN + 1
  sbc UPLOAD_TARGET + 1
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

; Check the block just read (its data would start at UPLOAD_TARGET): reserved flags clear,
; load address at or above the previous block's end (and UPLOAD_RAM_START) and where its data
; sits, and its end (into UPLOAD_END) at most INTERRUPT_ROUTINE
; On exit C set if the block is bad
upload_valid_block:
  lda UPLOAD_FLAGS
  and #(~(UPLOAD_MORE | UPLOAD_ZERO_FILL)) & $ff
  bne .bad
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

; Add the bytes from TEMP_P up to A (high), X (low) to the checksum
upload_sum_to:
  stx UPLOAD_FROM
  sta UPLOAD_FROM + 1
.loop:
  lda TEMP_P
  cmp UPLOAD_FROM
  bne .add
  lda TEMP_P + 1
  cmp UPLOAD_FROM + 1
  beq .done
.add:
  jsr upload_sum_byte
  bra .loop
.done:
  rts

; Add the byte at TEMP_P to the checksum, as calculate_checksum does, and move TEMP_P on
upload_sum_byte:
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
  bne .done
  inc TEMP_P + 1
.done:
  rts

upload_stop_receiving:
  sei
  stz ACR                         ; Disable shifting
  stz PCR                         ; Turn off CB2 interrupts
  lda #(ICB2 | ISR)               ; Disable and reset interrupt flags
  sta IER
  sta IFR
  .ifdef DISPLAY_INTERRUPTS_FLAG
  lda #%10000000                  ; The LCD routines disable interrupts again
  trb DISPLAY_INTERRUPTS_FLAG
  .endif
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
