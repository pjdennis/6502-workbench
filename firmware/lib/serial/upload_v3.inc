; Receives an upload in format 3 (tools/upload/upload_frame.py, docs/michael-upload-format-3-plan.md)
; and runs it: a header (version, start address, count, header and data checksums) and a table of
; entries (address, length, flags), then the entries' data, every byte already bit-reversed by
; the sender.
;
; The whole stream is stored in order from UPLOAD_STREAM, so that with one entry the header ends
; just below UPLOAD_RAM_START and the data lands there; each further entry puts the data
; UPLOAD_ENTRY_SIZE bytes higher. While the receive handler stores bytes, the main loop takes
; turns at two tasks: checking (the header once it has arrived, copying the entries into the
; table, then the data's checksum, a few bytes at a time as they come in) and showing progress on
; the first two rows of the LCD (16 columns, so a 2x16 panel will do):
;
;   Block 02 $0A40      the entry arriving, and where its next byte will end up ($---- while
;   Received $1A40      the header arrives); every byte received so far ("Ready" until the
;                       first arrives)
;
; redrawn when the count changes, but at most every UPLOAD_REDRAW_TICKS runs of timer 1 (~0.2 s)
; since redrawing nonstop dims the LCD; a stalled upload still shows exactly how far it got.
;
; Entries must ascend without overlapping, each within zero page or UPLOAD_RAM_START to
; INTERRUPT_ROUTINE, and the stream must end by INTERRUPT_ROUTINE. Nothing moves until all has
; arrived. Then, in the order that keeps each move clear of data still to be moved (destinations
; ascend without overlapping): zero page (its loader-owned bytes into the stash), the entries
; moving down, lowest first, and those moving up, highest first; then the zero-fill entries are
; cleared. The LCD is cleared, the stash copied into zero page, and the upload runs from its start
; address (after UPLOAD_BEFORE_RUN, if defined); with none ($ffff), "Loaded." shows instead. A bad
; upload shows "Upload failed" and why, lights the LED and stops the CPU.
;
; The LCD routines must leave interrupts on while receiving, which would otherwise lose bits:
; DISPLAY_INTERRUPTS_FLAG (bit 7 is set while receiving) or DISPLAY_DO_NOT_DISABLE_INTERRUPTS.
;
; Requires:
;   serial_receive_timing.inc, 6522.inc
;   clear_display, display_command, display_string, display_hex, move_cursor
;   UPLOAD_RAM_START, INTERRUPT_ROUTINE (where the receive handler, serial_receive_interrupt.inc,
;     is copied; the zero-page stash follows it), LED (PORTA)
;   Zero page, one block from UPLOAD_ZP_START to UPLOAD_ZP_END, checked below: DISPLAY_STRING_PARAM
;     (2), UPLOAD_P (2), WAITING_FOR_SHIFT (1), UPLOAD_STATE (1), UPLOAD_COUNT (1), UPLOAD_SEEN (2),
;     UPLOAD_SHOWN (2), UPLOAD_SHOWN_ENTRY (1), UPLOAD_TICKS (1), UPLOAD_ENTRY (1),
;     UPLOAD_ENTRY_DATA (2), UPLOAD_ENTRY_NEXT (2), UPLOAD_DATA (2), UPLOAD_END (2),
;     UPLOAD_SOURCE (2), UPLOAD_FROM (2), UPLOAD_TO (2), UPLOAD_LENGTH (2), UPLOAD_LIMIT (2),
;     UPLOAD_FLAGS (1), CHECKSUM_VALUE (2), TEMP (1)
;   Page 1 from UPLOAD_TABLE for the entry table; the stack runs down from UPLOAD_STREAM - 1
;   Timer 1, while receiving
; Optional:
;   UPLOAD_BEFORE_RUN       - called just before running an upload
;   DISPLAY_INTERRUPTS_FLAG - a zero-page byte stashed like the loader's own, so an upload's wins

  .ifndef DISPLAY_INTERRUPTS_FLAG
  .if DISPLAY_DO_NOT_DISABLE_INTERRUPTS == 0
  fail "The loader's LCD routines would disable interrupts while receiving"
  .endif
  .endif

  .ifndef UPLOAD_MAX_ENTRIES
UPLOAD_MAX_ENTRIES = 32
  .endif
  .ifndef UPLOAD_TABLE
UPLOAD_TABLE       = $0100
  .endif

UPLOAD_VERSION     = 3
UPLOAD_ZERO_FILL   = %00000001             ; Entry flags; the others are reserved (0)
UPLOAD_FIXED_SIZE  = 8                     ; The header before the entries
UPLOAD_ENTRY_SIZE  = 5
UPLOAD_STREAM      = UPLOAD_RAM_START - UPLOAD_FIXED_SIZE - UPLOAD_ENTRY_SIZE
UPLOAD_SUM_STEP    = 32                    ; Most bytes summed before the display's turn
UPLOAD_REDRAW_TICKS = 6                    ; Runs of timer 1 (65538 cycles) between redraws
UPLOAD_STACK_ROOM  = 64                    ; Between the entry table and the stream

; The header's fields, where they arrive
UPLOAD_H_VERSION   = UPLOAD_STREAM
UPLOAD_H_START     = UPLOAD_STREAM + 1
UPLOAD_H_COUNT     = UPLOAD_STREAM + 3
UPLOAD_H_HEADER_SUM = UPLOAD_STREAM + 4
UPLOAD_H_DATA_SUM  = UPLOAD_STREAM + 6
UPLOAD_H_ENTRIES   = UPLOAD_STREAM + 8

; The entry table: an array per field, indexed by entry
UPLOAD_T_ADDRESS_L = UPLOAD_TABLE
UPLOAD_T_ADDRESS_H = UPLOAD_T_ADDRESS_L + UPLOAD_MAX_ENTRIES
UPLOAD_T_LENGTH_L  = UPLOAD_T_ADDRESS_H + UPLOAD_MAX_ENTRIES
UPLOAD_T_LENGTH_H  = UPLOAD_T_LENGTH_L + UPLOAD_MAX_ENTRIES
UPLOAD_T_FLAGS     = UPLOAD_T_LENGTH_H + UPLOAD_MAX_ENTRIES
UPLOAD_TABLE_END   = UPLOAD_T_FLAGS + UPLOAD_MAX_ENTRIES

; The zero-page stash: the loader's block, then DISPLAY_INTERRUPTS_FLAG
UPLOAD_ZP_SIZE     = UPLOAD_ZP_END - UPLOAD_ZP_START
UPLOAD_STASH       = INTERRUPT_ROUTINE + (interrupt_end - interrupt)
  .ifdef DISPLAY_INTERRUPTS_FLAG
UPLOAD_STASH_SIZE  = UPLOAD_ZP_SIZE + 1
  .else
UPLOAD_STASH_SIZE  = UPLOAD_ZP_SIZE
  .endif

; UPLOAD_STATE: what the checking task is waiting for
UPLOAD_S_FIXED     = 0                     ; The header's fixed fields
UPLOAD_S_HEADER    = 1                     ; The rest of the header: the entries
UPLOAD_S_DATA      = 2                     ; The data, being summed as it arrives

; Where the progress fields go
UPLOAD_ROW_BLOCK   = CMD_SET_DDRAM_ADDRESS | DISPLAY_FIRST_LINE
UPLOAD_ROW_COUNT   = CMD_SET_DDRAM_ADDRESS | DISPLAY_SECOND_LINE
UPLOAD_FIELD       = 10                    ; The column of both rows' hex

upload_block_label:     .asciiz 'Block '
upload_address_mark:    .asciiz ' $'
upload_received_label:  .asciiz 'Received $'
upload_ready_message:   .asciiz 'Ready'
upload_no_address:      .asciiz '----'
upload_loaded_message:  .asciiz 'Loaded.         '
upload_failed_message:  .asciiz 'Upload failed'
upload_version_message: .asciiz 'Bad version '
upload_header_message:  .asciiz 'Bad header'
upload_block_message:   .asciiz 'Bad block '
upload_checksum_message: .asciiz 'Bad checksum'


; Receive and run an upload. Does not return
upload_v3:
  ldx #<(UPLOAD_STREAM - 1)       ; Stack below the stream
  txs

  ldx #0                          ; The receive handler goes where the interrupt vector points
.copy_handler:
  lda interrupt, X
  sta INTERRUPT_ROUTINE, X
  inx
  cpx #<(interrupt_end - interrupt)
  bne .copy_handler

  ldx #UPLOAD_STASH_SIZE - 1      ; Zero page the upload doesn't give ends up 0
.clear_stash:
  stz UPLOAD_STASH, X
  dex
  bpl .clear_stash

  stz WAITING_FOR_SHIFT
  lda #<UPLOAD_STREAM
  sta UPLOAD_P
  lda #>UPLOAD_STREAM
  sta UPLOAD_P + 1
  stz UPLOAD_STATE                ; UPLOAD_S_FIXED
  stz UPLOAD_ENTRY
  stz UPLOAD_TICKS                ; Free to redraw
  lda #$ff
  sta UPLOAD_SHOWN_ENTRY          ; Nothing shown yet...
  sta UPLOAD_SHOWN
  sta UPLOAD_SHOWN + 1            ; ...not even the count

  .ifdef DISPLAY_INTERRUPTS_FLAG
  lda #%10000000                  ; The LCD routines leave interrupts on from here
  tsb DISPLAY_INTERRUPTS_FLAG
  .endif
  lda #UPLOAD_ROW_COUNT
  jsr display_command
  lda #<upload_ready_message
  ldx #>upload_ready_message
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
  jsr upload_place

  lda UPLOAD_H_START
  and UPLOAD_H_START + 1
  cmp #$ff
  beq .no_start
  jsr clear_display
  .ifdef UPLOAD_BEFORE_RUN
  jsr UPLOAD_BEFORE_RUN
  .endif
  jsr upload_unstash              ; Zero page is the upload's from here...
  ldx #$ff
  txs
  jmp (UPLOAD_H_START)            ; ...so its start address is read from page 1

.no_start:
  lda #UPLOAD_ROW_BLOCK
  jsr display_command
  lda #<upload_loaded_message
  ldx #>upload_loaded_message
  jsr display_string
  jsr upload_unstash
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
  rts
.changed:
  lda #UPLOAD_REDRAW_TICKS
  sta UPLOAD_TICKS
  jsr upload_start_tick
  lda UPLOAD_SEEN
  sta UPLOAD_SHOWN
  lda UPLOAD_SEEN + 1
  sta UPLOAD_SHOWN + 1
  lda UPLOAD_SHOWN                ; Nothing yet: "Ready" stays
  cmp #<UPLOAD_STREAM
  bne .count_row
  lda UPLOAD_SHOWN + 1
  cmp #>UPLOAD_STREAM
  bne .count_row
  rts

.count_row:
  lda UPLOAD_SHOWN_ENTRY          ; The first time, over "Ready", the label too
  cmp #$ff
  bne .count_field
  lda #UPLOAD_ROW_COUNT
  jsr display_command
  lda #<upload_received_label
  ldx #>upload_received_label
  jsr display_string
  bra .count
.count_field:
  lda #UPLOAD_ROW_COUNT + UPLOAD_FIELD
  jsr display_command
.count:
  sec                             ; Received = UPLOAD_SHOWN - UPLOAD_STREAM
  lda UPLOAD_SHOWN
  sbc #<UPLOAD_STREAM
  tax
  lda UPLOAD_SHOWN + 1
  sbc #>UPLOAD_STREAM
  jsr display_hex
  txa
  jsr display_hex

  lda UPLOAD_STATE
  cmp #UPLOAD_S_DATA
  bne .block_row
.advance:                         ; On to the entry the count has reached (past any zero-fill)
  lda UPLOAD_ENTRY
  inc
  cmp UPLOAD_COUNT
  bcs .block_row                  ; The last
  lda UPLOAD_ENTRY_NEXT
  cmp UPLOAD_SHOWN
  lda UPLOAD_ENTRY_NEXT + 1
  sbc UPLOAD_SHOWN + 1
  bcs .block_row                  ; Its data isn't all in yet
  inc UPLOAD_ENTRY
  ldx UPLOAD_ENTRY
  jsr upload_entry_data
  bra .advance

.block_row:
  lda UPLOAD_ENTRY
  cmp UPLOAD_SHOWN_ENTRY
  beq .address
  sta UPLOAD_SHOWN_ENTRY
  lda #UPLOAD_ROW_BLOCK
  jsr display_command
  lda #<upload_block_label
  ldx #>upload_block_label
  jsr display_string
  lda UPLOAD_ENTRY
  inc
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
.show_address:                    ; Its address + its data received, at most to the data's end
  lda UPLOAD_SHOWN
  ldx UPLOAD_SHOWN + 1
  cmp UPLOAD_ENTRY_NEXT
  txa
  sbc UPLOAD_ENTRY_NEXT + 1
  bcc .within
  lda UPLOAD_ENTRY_NEXT
  ldx UPLOAD_ENTRY_NEXT + 1
  bra .offset
.within:
  lda UPLOAD_SHOWN
.offset:
  sec
  sbc UPLOAD_ENTRY_DATA
  sta TEMP
  txa
  sbc UPLOAD_ENTRY_DATA + 1
  ldx UPLOAD_ENTRY
  clc
  adc UPLOAD_T_ADDRESS_H, X
  pha
  lda TEMP
  clc
  adc UPLOAD_T_ADDRESS_L, X
  sta TEMP
  pla
  adc #0
  jsr display_hex
  lda TEMP
  jmp display_hex

; Entry X's data follows the data before it: UPLOAD_ENTRY_DATA = UPLOAD_ENTRY_NEXT, which moves
; on by its length, unless it's zero-fill
; On exit X is preserved
upload_entry_data:
  lda UPLOAD_ENTRY_NEXT
  sta UPLOAD_ENTRY_DATA
  lda UPLOAD_ENTRY_NEXT + 1
  sta UPLOAD_ENTRY_DATA + 1
  lda UPLOAD_T_FLAGS, X
  and #UPLOAD_ZERO_FILL
  bne .done
  clc
  lda UPLOAD_ENTRY_NEXT
  adc UPLOAD_T_LENGTH_L, X
  sta UPLOAD_ENTRY_NEXT
  lda UPLOAD_ENTRY_NEXT + 1
  adc UPLOAD_T_LENGTH_H, X
  sta UPLOAD_ENTRY_NEXT + 1
.done:
  rts


; Start a run of timer 1 (clearing its flag)
upload_start_tick:
  lda #$ff
  sta T1CL
  sta T1CH
  rts


; The checking task: one step
; On exit C set once all has arrived and checked out
upload_check_step:
  lda UPLOAD_STATE
  beq upload_check_fixed
  cmp #UPLOAD_S_HEADER
  beq upload_check_header
  jmp upload_check_data

; The header's fixed fields: the version and the count
upload_check_fixed:
  lda UPLOAD_SEEN
  cmp #<UPLOAD_H_ENTRIES
  lda UPLOAD_SEEN + 1
  sbc #>UPLOAD_H_ENTRIES
  bcc .wait
  lda UPLOAD_H_VERSION
  cmp #UPLOAD_VERSION
  beq .version_ok
  jmp upload_bad_version
.version_ok:
  lda UPLOAD_H_COUNT
  beq .bad_header
  cmp #UPLOAD_MAX_ENTRIES + 1
  bcs .bad_header
  sta UPLOAD_COUNT
  asl                             ; The data starts after the entries: count x 5 (at most 160)
  asl
  adc UPLOAD_COUNT
  adc #<UPLOAD_H_ENTRIES
  sta UPLOAD_DATA
  lda #>UPLOAD_H_ENTRIES
  adc #0
  sta UPLOAD_DATA + 1
  lda #UPLOAD_S_HEADER
  sta UPLOAD_STATE
.wait:
  clc
  rts
.bad_header:
  jmp upload_bad_header

; The rest of the header: once it has arrived, check its checksum and its entries, copied into
; the table, and start summing the data
upload_check_header:
  lda UPLOAD_SEEN
  cmp UPLOAD_DATA
  lda UPLOAD_SEEN + 1
  sbc UPLOAD_DATA + 1
  bcc .wait
  stz CHECKSUM_VALUE              ; The header's bytes but its checksum's
  stz CHECKSUM_VALUE + 1
  lda #<UPLOAD_STREAM
  sta UPLOAD_SOURCE
  lda #>UPLOAD_STREAM
  sta UPLOAD_SOURCE + 1
  ldx #<UPLOAD_H_HEADER_SUM
  lda #>UPLOAD_H_HEADER_SUM
  jsr upload_sum_to
  lda #<UPLOAD_H_DATA_SUM
  sta UPLOAD_SOURCE
  lda #>UPLOAD_H_DATA_SUM
  sta UPLOAD_SOURCE + 1
  ldx UPLOAD_DATA
  lda UPLOAD_DATA + 1
  jsr upload_sum_to
  lda CHECKSUM_VALUE
  cmp UPLOAD_H_HEADER_SUM
  bne .bad_header
  lda CHECKSUM_VALUE + 1
  cmp UPLOAD_H_HEADER_SUM + 1
  bne .bad_header
  jsr upload_read_entries
  bcc .entries_ok
  jmp upload_bad_block
.entries_ok:
  lda #<INTERRUPT_ROUTINE         ; The stream must end by the receive handler
  cmp UPLOAD_END
  lda #>INTERRUPT_ROUTINE
  sbc UPLOAD_END + 1
  bcc .bad_header
  stz CHECKSUM_VALUE              ; Sum the data from its start
  stz CHECKSUM_VALUE + 1
  lda UPLOAD_DATA
  sta UPLOAD_SOURCE
  sta UPLOAD_ENTRY_NEXT
  lda UPLOAD_DATA + 1
  sta UPLOAD_SOURCE + 1
  sta UPLOAD_ENTRY_NEXT + 1
  ldx #0                          ; The display starts at the first entry
  jsr upload_entry_data
  lda #UPLOAD_S_DATA
  sta UPLOAD_STATE
  jsr upload_redraw               ; Now there's an address to show
.wait:
  clc
  rts
.bad_header:
  jmp upload_bad_header

; The data: sum what has arrived, a few bytes at a time; check the sum at its end
upload_check_data:
  ldy #UPLOAD_SUM_STEP
.sum:
  lda UPLOAD_SOURCE               ; At the data's end?
  cmp UPLOAD_END
  bne .not_end
  lda UPLOAD_SOURCE + 1
  cmp UPLOAD_END + 1
  beq .end
.not_end:
  lda UPLOAD_SOURCE               ; Caught up with the stream?
  cmp UPLOAD_SEEN
  bne .add
  lda UPLOAD_SOURCE + 1
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
  lda CHECKSUM_VALUE
  cmp UPLOAD_H_DATA_SUM
  bne .bad_checksum
  lda CHECKSUM_VALUE + 1
  cmp UPLOAD_H_DATA_SUM + 1
  bne .bad_checksum
  sec                             ; All checked
  rts
.bad_checksum:
  jmp upload_bad_checksum


; Copy the header's entries into the table, checking each (upload_table_entry). UPLOAD_END =
; where the data ends in the stream
; On exit C set if an entry is bad, with its number (from 1) in A
upload_read_entries:
  lda #<UPLOAD_H_ENTRIES
  sta UPLOAD_FROM
  lda #>UPLOAD_H_ENTRIES
  sta UPLOAD_FROM + 1
  stz UPLOAD_LIMIT
  stz UPLOAD_LIMIT + 1
  lda UPLOAD_DATA
  sta UPLOAD_END
  lda UPLOAD_DATA + 1
  sta UPLOAD_END + 1
  ldx #0
.entry:
  jsr upload_table_entry
  bcs .bad
  clc
  lda UPLOAD_FROM
  adc #UPLOAD_ENTRY_SIZE
  sta UPLOAD_FROM
  bcc .advanced
  inc UPLOAD_FROM + 1
.advanced:
  inx
  cpx UPLOAD_COUNT
  bne .entry
  clc
  rts
.bad:
  txa
  inc
  rts

; Copy the entry at UPLOAD_FROM into the table as entry X and check it: reserved flags clear, not
; empty, at or above UPLOAD_LIMIT (the end of the one before, which becomes its end), and within
; zero page or UPLOAD_RAM_START to INTERRUPT_ROUTINE. Its data (if not zero-fill) moves UPLOAD_END
; on
; On exit C set if it's bad; X is preserved
upload_table_entry:
  ldy #0
  lda (UPLOAD_FROM), Y
  sta UPLOAD_T_ADDRESS_L, X
  iny
  lda (UPLOAD_FROM), Y
  sta UPLOAD_T_ADDRESS_H, X
  iny
  lda (UPLOAD_FROM), Y
  sta UPLOAD_T_LENGTH_L, X
  iny
  lda (UPLOAD_FROM), Y
  sta UPLOAD_T_LENGTH_H, X
  iny
  lda (UPLOAD_FROM), Y
  sta UPLOAD_T_FLAGS, X
  and #~UPLOAD_ZERO_FILL & $ff
  bne .bad
  lda UPLOAD_T_LENGTH_L, X
  ora UPLOAD_T_LENGTH_H, X
  beq .bad
  lda UPLOAD_T_ADDRESS_L, X       ; At or above the end of the one before
  cmp UPLOAD_LIMIT
  lda UPLOAD_T_ADDRESS_H, X
  sbc UPLOAD_LIMIT + 1
  bcc .bad
  clc                             ; Its end, the next one's limit
  lda UPLOAD_T_ADDRESS_L, X
  adc UPLOAD_T_LENGTH_L, X
  sta UPLOAD_LIMIT
  lda UPLOAD_T_ADDRESS_H, X
  adc UPLOAD_T_LENGTH_H, X
  sta UPLOAD_LIMIT + 1
  bcs .bad
  beq .area_ok                    ; Ends by $00FF: in zero page
  cmp #1
  bne .ram
  lda UPLOAD_LIMIT
  beq .area_ok                    ; Ends at $00FF
.ram:
  lda UPLOAD_T_ADDRESS_L, X       ; At or above UPLOAD_RAM_START...
  cmp #<UPLOAD_RAM_START
  lda UPLOAD_T_ADDRESS_H, X
  sbc #>UPLOAD_RAM_START
  bcc .bad
  lda #<INTERRUPT_ROUTINE         ; ...and ending by INTERRUPT_ROUTINE
  cmp UPLOAD_LIMIT
  lda #>INTERRUPT_ROUTINE
  sbc UPLOAD_LIMIT + 1
  bcc .bad
.area_ok:
  lda UPLOAD_T_FLAGS, X           ; Its data (none if zero-fill) is in the stream
  and #UPLOAD_ZERO_FILL
  bne .good
  clc
  lda UPLOAD_END
  adc UPLOAD_T_LENGTH_L, X
  sta UPLOAD_END
  lda UPLOAD_END + 1
  adc UPLOAD_T_LENGTH_H, X
  sta UPLOAD_END + 1
  bcs .bad
.good:
  clc
  rts
.bad:
  sec
  rts


; Add the bytes from UPLOAD_SOURCE up to A (high), X (low) to the checksum
upload_sum_to:
  stx UPLOAD_TO
  sta UPLOAD_TO + 1
.loop:
  lda UPLOAD_SOURCE
  cmp UPLOAD_TO
  bne .add
  lda UPLOAD_SOURCE + 1
  cmp UPLOAD_TO + 1
  beq .done
.add:
  jsr upload_sum_byte
  bra .loop
.done:
  rts

; Add the byte at UPLOAD_SOURCE to the checksum, as calculate_checksum does, and move on
upload_sum_byte:
  lda CHECKSUM_VALUE + 1          ; Rotate right...
  ror
  ror CHECKSUM_VALUE
  ror CHECKSUM_VALUE + 1
  clc                             ; ...and add the byte
  lda (UPLOAD_SOURCE)
  adc CHECKSUM_VALUE
  sta CHECKSUM_VALUE
  bcc .next
  inc CHECKSUM_VALUE + 1
.next:
  inc UPLOAD_SOURCE
  bne .done
  inc UPLOAD_SOURCE + 1
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


; Move every entry's data into place from the stream, then clear the zero-fill entries. The
; stream holds each entry's data in order from UPLOAD_DATA to UPLOAD_END
upload_place:
  lda UPLOAD_DATA                 ; Moving down (zero page always does): lowest first
  sta UPLOAD_SOURCE
  lda UPLOAD_DATA + 1
  sta UPLOAD_SOURCE + 1
  ldx #0
.down:
  jsr upload_read_entry
  bne .down_next                  ; Zero-fill
  lda UPLOAD_TO + 1
  bne .down_ram
  jsr upload_place_zero_page
  bra .down_on
.down_ram:
  lda UPLOAD_TO
  cmp UPLOAD_SOURCE
  lda UPLOAD_TO + 1
  sbc UPLOAD_SOURCE + 1
  bcs .down_on                    ; Not moving down
  jsr upload_move_down
.down_on:
  clc
  lda UPLOAD_SOURCE
  adc UPLOAD_T_LENGTH_L, X
  sta UPLOAD_SOURCE
  lda UPLOAD_SOURCE + 1
  adc UPLOAD_T_LENGTH_H, X
  sta UPLOAD_SOURCE + 1
.down_next:
  inx
  cpx UPLOAD_COUNT
  bne .down

  lda UPLOAD_END                  ; Moving up: highest first
  sta UPLOAD_SOURCE
  lda UPLOAD_END + 1
  sta UPLOAD_SOURCE + 1
  ldx UPLOAD_COUNT
.up:
  dex
  lda UPLOAD_T_FLAGS, X
  and #UPLOAD_ZERO_FILL
  bne .up_next
  sec                             ; Back to its data
  lda UPLOAD_SOURCE
  sbc UPLOAD_T_LENGTH_L, X
  sta UPLOAD_SOURCE
  lda UPLOAD_SOURCE + 1
  sbc UPLOAD_T_LENGTH_H, X
  sta UPLOAD_SOURCE + 1
  jsr upload_read_entry
  lda UPLOAD_SOURCE               ; Moving up?
  cmp UPLOAD_TO
  lda UPLOAD_SOURCE + 1
  sbc UPLOAD_TO + 1
  bcs .up_next
  jsr upload_move_up
.up_next:
  cpx #0
  bne .up

  ldx #0                          ; Zero-fill
.fill:
  jsr upload_read_entry
  beq .fill_next
  lda UPLOAD_TO + 1
  bne .fill_ram
  jsr upload_place_zero_page
  bra .fill_next
.fill_ram:
  jsr upload_count_down
  beq .fill_next
  lda #0
  sta (UPLOAD_TO)
  inc UPLOAD_TO
  bne .fill_ram
  inc UPLOAD_TO + 1
  bra .fill_ram
.fill_next:
  inx
  cpx UPLOAD_COUNT
  bne .fill
  rts

; Entry X into UPLOAD_TO (its address), UPLOAD_LENGTH, UPLOAD_FLAGS; UPLOAD_FROM = UPLOAD_SOURCE,
; where the pass placing it has its data
; On exit Z clear if it's zero-fill; X is preserved
upload_read_entry:
  lda UPLOAD_T_ADDRESS_L, X
  sta UPLOAD_TO
  lda UPLOAD_T_ADDRESS_H, X
  sta UPLOAD_TO + 1
  lda UPLOAD_T_LENGTH_L, X
  sta UPLOAD_LENGTH
  lda UPLOAD_T_LENGTH_H, X
  sta UPLOAD_LENGTH + 1
  lda UPLOAD_SOURCE
  sta UPLOAD_FROM
  lda UPLOAD_SOURCE + 1
  sta UPLOAD_FROM + 1
  lda UPLOAD_T_FLAGS, X
  sta UPLOAD_FLAGS
  and #UPLOAD_ZERO_FILL
  rts

; Copy UPLOAD_LENGTH bytes from UPLOAD_FROM down to UPLOAD_TO, from the bottom up: the areas may
; overlap
; On exit X is preserved
upload_move_down:
  jsr upload_count_down
  beq .done
  lda (UPLOAD_FROM)
  sta (UPLOAD_TO)
  inc UPLOAD_FROM
  bne .from_high
  inc UPLOAD_FROM + 1
.from_high:
  inc UPLOAD_TO
  bne upload_move_down
  inc UPLOAD_TO + 1
  bra upload_move_down
.done:
  rts

; Copy UPLOAD_LENGTH bytes from UPLOAD_FROM up to UPLOAD_TO, from the top down: the areas may
; overlap
; On exit X is preserved
upload_move_up:
  clc                             ; Point both at one past the last byte
  lda UPLOAD_FROM
  adc UPLOAD_LENGTH
  sta UPLOAD_FROM
  lda UPLOAD_FROM + 1
  adc UPLOAD_LENGTH + 1
  sta UPLOAD_FROM + 1
  clc
  lda UPLOAD_TO
  adc UPLOAD_LENGTH
  sta UPLOAD_TO
  lda UPLOAD_TO + 1
  adc UPLOAD_LENGTH + 1
  sta UPLOAD_TO + 1
.loop:
  jsr upload_count_down
  beq .done
  lda UPLOAD_FROM
  bne .from_low
  dec UPLOAD_FROM + 1
.from_low:
  dec UPLOAD_FROM
  lda UPLOAD_TO
  bne .to_low
  dec UPLOAD_TO + 1
.to_low:
  dec UPLOAD_TO
  lda (UPLOAD_FROM)
  sta (UPLOAD_TO)
  bra .loop
.done:
  rts

; Put the zero-page entry just read into place from UPLOAD_FROM (zeros if it's zero-fill): the
; loader's own bytes and DISPLAY_INTERRUPTS_FLAG into the stash
; On exit X is preserved
upload_place_zero_page:
  phx
  ldx UPLOAD_TO
  ldy #0
.loop:
  jsr upload_count_down
  beq .done
  lda UPLOAD_FLAGS
  and #UPLOAD_ZERO_FILL
  beq .data
  lda #0
  bra .store
.data:
  lda (UPLOAD_FROM), Y
.store:
  jsr upload_store_zero_page
  inx
  iny
  bra .loop
.done:
  plx
  rts

; Store A at zero page X, or in its place in the stash
; On exit A, X, Y are preserved
upload_store_zero_page:
  cpx #UPLOAD_ZP_END
  bcs .outside
  .if UPLOAD_ZP_START > 0
  cpx #UPLOAD_ZP_START
  bcc .outside
  .endif
  sta UPLOAD_STASH - UPLOAD_ZP_START, X
  rts
.outside:
  .ifdef DISPLAY_INTERRUPTS_FLAG
  cpx #DISPLAY_INTERRUPTS_FLAG
  bne .direct
  sta UPLOAD_STASH + UPLOAD_ZP_SIZE
  rts
.direct:
  .endif
  sta $00, X
  rts

; Copy the stash into zero page (the loader's own, then DISPLAY_INTERRUPTS_FLAG), using none
upload_unstash:
  ldx #0
.loop:
  lda UPLOAD_STASH, X
  sta UPLOAD_ZP_START, X
  inx
  cpx #UPLOAD_ZP_SIZE
  bne .loop
  .ifdef DISPLAY_INTERRUPTS_FLAG
  lda UPLOAD_STASH + UPLOAD_ZP_SIZE
  sta DISPLAY_INTERRUPTS_FLAG
  .endif
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
  lda UPLOAD_H_VERSION
  ldx #<upload_version_message
  ldy #>upload_version_message
  sec
  bra upload_failed
upload_bad_header:
  ldx #<upload_header_message
  ldy #>upload_header_message
  clc
  bra upload_failed
upload_bad_block:
  ldx #<upload_block_message
  ldy #>upload_block_message
  sec
  bra upload_failed
upload_bad_checksum:
  ldx #<upload_checksum_message
  ldy #>upload_checksum_message
  clc
  ; fall through

; Show "Upload failed" and the message at X, Y, then A in hex if C is set; light the LED and stop
upload_failed:
  php
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
  plp
  bcc .no_value
  jsr display_hex
.no_value:
  lda #LED                       ; The LED is wired from +5V: low lights it
  trb PORTA
  stp


  .include serial_receive_interrupt.inc   ; Copied to INTERRUPT_ROUTINE


; Where everything goes, checked
  .macro upload_zp,name,size
  .if (\name < UPLOAD_ZP_START) | (\name + \size > UPLOAD_ZP_END)
  fail "A loader variable is outside UPLOAD_ZP_START to UPLOAD_ZP_END"
  .endif
  .endm

  upload_zp DISPLAY_STRING_PARAM, 2
  upload_zp UPLOAD_P, 2
  upload_zp WAITING_FOR_SHIFT, 1
  upload_zp UPLOAD_STATE, 1
  upload_zp UPLOAD_COUNT, 1
  upload_zp UPLOAD_SEEN, 2
  upload_zp UPLOAD_SHOWN, 2
  upload_zp UPLOAD_SHOWN_ENTRY, 1
  upload_zp UPLOAD_TICKS, 1
  upload_zp UPLOAD_ENTRY, 1
  upload_zp UPLOAD_ENTRY_DATA, 2
  upload_zp UPLOAD_ENTRY_NEXT, 2
  upload_zp UPLOAD_DATA, 2
  upload_zp UPLOAD_END, 2
  upload_zp UPLOAD_SOURCE, 2
  upload_zp UPLOAD_FROM, 2
  upload_zp UPLOAD_TO, 2
  upload_zp UPLOAD_LENGTH, 2
  upload_zp UPLOAD_LIMIT, 2
  upload_zp UPLOAD_FLAGS, 1
  upload_zp CHECKSUM_VALUE, 2
  upload_zp TEMP, 1

  .if UPLOAD_ZP_END > $100
  fail "UPLOAD_ZP_END is past zero page"
  .endif
  .ifdef DISPLAY_INTERRUPTS_FLAG
  .if (DISPLAY_INTERRUPTS_FLAG >= UPLOAD_ZP_START) & (DISPLAY_INTERRUPTS_FLAG < UPLOAD_ZP_END)
  fail "DISPLAY_INTERRUPTS_FLAG is in the loader's zero page"
  .endif
  .endif
  .if UPLOAD_STASH_SIZE > $80
  fail "The zero-page stash is too big to clear with one loop"
  .endif
  .if UPLOAD_STASH + UPLOAD_STASH_SIZE > INTERRUPT_ROUTINE + $100
  fail "The zero-page stash runs out of the receive handler's page"
  .endif
  .if UPLOAD_TABLE_END + UPLOAD_STACK_ROOM > UPLOAD_STREAM
  fail "The entry table leaves the stack too little room below the stream"
  .endif
  .if UPLOAD_TABLE < $0100
  fail "The entry table must be in page 1, which uploads can't reach"
  .endif
  .if UPLOAD_MAX_ENTRIES * UPLOAD_ENTRY_SIZE + UPLOAD_ENTRY_SIZE > $100
  fail "Too many entries to count their bytes in 8 bits"
  .endif
