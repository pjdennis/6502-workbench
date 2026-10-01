; wendy2 merge-sort demo (skeleton phase).
;
; See attic/plan-for-wendy2-merge-sort-demo.md for the full design. This file
; is built up TDD-style across multiple commits; right now it just sets
; up the machine, shows a banner with the build-time N_ELEMENTS, and
; halts via STP. Subsequent commits add the fill, sort, and verify
; phases.
;
; Build-time knobs (override on the vasm command line with -DNAME=VAL):
;   N_ELEMENTS  number of 16-bit values to sort. Default 57344 = 0xE000
;               (the full 4-bank side; see plan). Smaller values let
;               tests iterate quickly: 64 fits in one bank, 16384 spans
;               two banks, 32768 spans three, 57344 spans four.

  .ifndef N_ELEMENTS
N_ELEMENTS = 57344
  .endif

  .include base_config_wendy2c.inc

; ----- switch_to_space macro -----
;
; Update the low 5 bits of BANK_PORT (PORTB) to the new cfg in A,
; preserving the upper 3 bits (LCD-E, LED, T1 squarewave).
;
; The demo numbers its 8 upper banks as cfgs $18..$1F so that stepping
; to the next bank is an INC. On the PLD, cfg $18 maps ROM into the
; upper window, so the macro substitutes cfg $02, which gives the
; required lower bank 2 + upper RAM bank 0. Inlined
; because the merge inner loop calls this twice per emitted element
; (once for the target write, once for the source read), so a JSR-
; based version's overhead costs ~20% of the demo's total runtime.
;
; Critical property: BANK_PORT is updated with a SINGLE write that
; transitions directly from the old cfg to the new cfg. There is no
; transient cfg=$00 window where the bank bits are cleared -- at
; cfg=$00 the upper region maps to ROM whose IRQ vector at \$FFFE is
; \$0000, so an interrupt arriving mid-switch would jump to lower
; bank 1's \$0000 (uninitialised) and crash the machine.
;
; The macro uses ZP \$02 (TEMP) for the one byte of scratch needed to
; combine the preserved upper bits with the new bank bits before the
; single write. ZP is in the banked lower 16K, but this is fine:
;   - All sustained-state switches happen between cfgs $02 and
;     $19..$1F, which share lower bank 2, so ZP doesn't change across
;     them.
;   - On the very first switch (boot ROM's cfg $01 -> our cfg $02),
;     the lower bank does change, but only AFTER the sta BANK_PORT.
;     Both the sta TEMP and the ora TEMP execute with BANK_PORT
;     still holding the old cfg, so they see the same ZP \$02 in the
;     OLD lower bank. The post-switch reader (if any) would see a
;     different physical location, but we don't read TEMP again.
;   - Our T1 IRQ handler doesn't touch ZP, so an interrupt arriving
;     between sta TEMP and ora TEMP doesn't corrupt the scratch.
;
; Clobbers A, Y. Preserves X.
INV_BANK_MASK = BANK_MASK ^ $FF
  .macro switch_to_space
  tay                         ; stash new cfg in Y
  lda BANK_PORT
  and #INV_BANK_MASK          ; A = upper 3 bits of BANK_PORT only
  sta TEMP                    ; ZP scratch
  tya
  and #BANK_MASK              ; A = new bank bits only
  cmp #%11000                 ; bank 0 is cfg $02, not $18 (ROM)
  bne .bank_cfg\@
  lda #%00010
.bank_cfg\@:
  ora TEMP                    ; A = preserved upper bits | new bank bits
  sta BANK_PORT               ; single atomic write to the bank-select reg
  .endmacro

; ----- zero page layout -----
; $00..$0E reserved for the display helpers (display_string_immediate,
; display_decimal, display_string). $10+ is ours.
D_S_I_P              = $00 ; 2 bytes -- display_string_immediate
TEMP                 = $02 ; 1 byte  -- switch_to_space inline scratch
TO_DECIMAL_PARAM     = $03 ; 10 bytes -- display_decimal (incl. result buf)
DISPLAY_STRING_PARAM = $0D ; 2 bytes -- display_string

; Merge-sort state. Cursors are laid out in three back-to-back 3-byte
; slots starting at $16 (offsets 0, 3, 6) so that advance_cursor_x can
; share one routine across all three via X-indexed ZP addressing.
LFSR                 = $10 ; 2 bytes
NEXT_A               = $12 ; 2 bytes -- cached element from source A
NEXT_B               = $14 ; 2 bytes -- cached element from source B
SRC_A_CFG            = $16 ; 1 byte
SRC_A_PTR            = $17 ; 2 bytes (16-bit address in $8000..$EFFE)
SRC_B_CFG            = $19 ; 1 byte  (= SRC_A_CFG + 3)
SRC_B_PTR            = $1A ; 2 bytes
TGT_CFG              = $1C ; 1 byte  (= SRC_A_CFG + 6)
TGT_PTR              = $1D ; 2 bytes
A_REM                = $1F ; 2 bytes -- elements left in current run-A
B_REM                = $21 ; 2 bytes
PASS_NUM             = $23 ; 1 byte
RUN_LEN              = $24 ; 2 bytes -- current L
CURRENT_SIDE_IS_A    = $26 ; 1 byte  -- 1 if pass reads from side A
CHUNK_REM            = $27 ; 2 bytes -- elements left in current 2L chunk
TOTAL_REM            = $29 ; 2 bytes -- elements left in pass
PROGRESS_TICK        = $2B ; 2 bytes -- counter for progress bar
PREV_ELEM            = $2D ; 2 bytes -- verify pass: previous element
EMIT_VAL             = $2F ; 2 bytes -- value to write through TGT cursor

CUR_OFFSET_SRC_A     = 0
CUR_OFFSET_SRC_B     = 3
CUR_OFFSET_TGT       = 6

  .org $4000
  jmp program_entry

  ; delay_routines first so timing loops don't cross a page boundary
  .include delay_routines.inc

  .include display_routines_4bit.inc
  .include display_hex.inc
  .include display_decimal.inc
  .include display_string_immediate.inc

program_entry:
  ; Pick a stable lower bank (bank 2) + upper bank 0: demo cfg $18,
  ; which switch_to_space turns into cfg $02. The fill/sort phases
  ; only ever touch demo cfgs $18..$1F, so the lower 16K mapping stays
  ; put after this initial switch.
  lda #%11000
  switch_to_space
  ldx #$ff
  txs

  jsr clear_display

  .ifdef SELFTEST_CURSORS
  jmp cursor_selftest
  .endif
  .ifdef SELFTEST_FILL
  jmp fill_selftest
  .endif
  .ifdef SELFTEST_SORT
  jmp sort_selftest
  .endif

  ; Banner: "Merge Sort" on line 1, "N=NNNNN" on line 2.
  jsr display_string_immediate
  .asciiz "Merge Sort"
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  jsr display_string_immediate
  .asciiz "N="
  lda #<N_ELEMENTS
  ldx #>N_ELEMENTS
  jsr display_decimal

  ; --- start T1 ms-tick timer ---
  jsr timer_start

  ; --- fill phase ---
  lda #<LFSR_SEED
  sta LFSR
  lda #>LFSR_SEED
  sta LFSR+1
  lda #SIDE_A_CFG
  sta TGT_CFG
  stz TGT_PTR
  lda #$80
  sta TGT_PTR+1
  jsr fill_phase

  ; --- sort phase ---
  jsr sort_phase

  ; --- verify phase ---
  jsr verify_phase

  ; --- stop timer, snapshot elapsed ---
  jsr timer_stop

  jsr show_final
  stp


; ----- cursor primitives -----
;
; A cursor is a 3-byte ZP triple (CFG, PTR_LO, PTR_HI) that names an
; element-aligned position within a side's 4-bank region. PTR walks
; $8000..$EFFE within the current cfg; after the last element in a
; bank (PTR == $EFFE) the next advance produces PTR=$8000, CFG++.

; advance_cursor_x: advance the cursor at zero-page offset X by one
; 16-bit element. X must be 0 (SRC_A), 3 (SRC_B), or 6 (TGT).
; Wraps PTR=$F000 -> PTR=$8000 with CFG++.
advance_cursor_x:
  inc SRC_A_PTR,X
  bne .lo_no_carry
  inc SRC_A_PTR+1,X
.lo_no_carry:
  inc SRC_A_PTR,X
  bne .check_wrap
  inc SRC_A_PTR+1,X
.check_wrap:
  lda SRC_A_PTR+1,X
  cmp #$F0
  bne .done
  stz SRC_A_PTR,X
  lda #$80
  sta SRC_A_PTR+1,X
  inc SRC_A_CFG,X
.done:
  rts

; src_a_read_advance: switch to SRC_A's cfg, read 16-bit word at
; SRC_A_PTR into NEXT_A, then advance the cursor.
src_a_read_advance:
  lda SRC_A_CFG
  switch_to_space
  ldy #0
  lda (SRC_A_PTR),Y
  sta NEXT_A
  iny
  lda (SRC_A_PTR),Y
  sta NEXT_A+1
  ldx #CUR_OFFSET_SRC_A
  jmp advance_cursor_x

src_b_read_advance:
  lda SRC_B_CFG
  switch_to_space
  ldy #0
  lda (SRC_B_PTR),Y
  sta NEXT_B
  iny
  lda (SRC_B_PTR),Y
  sta NEXT_B+1
  ldx #CUR_OFFSET_SRC_B
  jmp advance_cursor_x

; tgt_write_advance: switch to TGT's cfg, write the 16-bit value in
; EMIT_VAL to *TGT_PTR, then advance the cursor.
tgt_write_advance:
  lda TGT_CFG
  switch_to_space
  ldy #0
  lda EMIT_VAL
  sta (TGT_PTR),Y
  iny
  lda EMIT_VAL+1
  sta (TGT_PTR),Y
  ldx #CUR_OFFSET_TGT
  jmp advance_cursor_x


; ----- cursor selftest (built with -DSELFTEST_CURSORS=1) -----
;
; Exercises the wraparound case: write 4 distinct 16-bit values
; starting at cfg=$18, ptr=$EFFE (so the second write crosses into
; cfg=$19, ptr=$8000). Then read them back from the same start
; position and verify each one matches.
;
; Writes use the TGT cursor; reads use the SRC_A cursor.
  .ifdef SELFTEST_CURSORS

SELFTEST_START_CFG = $18
SELFTEST_START_PTR = $EFFE   ; deliberately near the bank boundary

cursor_selftest:
  ; -- write phase --
  lda #SELFTEST_START_CFG
  sta TGT_CFG
  lda #<SELFTEST_START_PTR
  sta TGT_PTR
  lda #>SELFTEST_START_PTR
  sta TGT_PTR+1

  ldx #0
.write_loop:
  ; EMIT_VAL = $ABCD + X (low byte gets X, high byte is $AB+X)
  txa
  clc
  adc #$CD
  sta EMIT_VAL
  txa
  clc
  adc #$AB
  sta EMIT_VAL+1
  phx
  jsr tgt_write_advance
  plx
  inx
  cpx #4
  bne .write_loop

  ; -- read-back phase --
  lda #SELFTEST_START_CFG
  sta SRC_A_CFG
  lda #<SELFTEST_START_PTR
  sta SRC_A_PTR
  lda #>SELFTEST_START_PTR
  sta SRC_A_PTR+1

  ldx #0
.read_loop:
  phx
  jsr src_a_read_advance
  plx

  ; Compare NEXT_A vs expected = $ABCD + X
  txa
  clc
  adc #$CD
  cmp NEXT_A
  bne .fail
  txa
  clc
  adc #$AB
  cmp NEXT_A+1
  bne .fail

  inx
  cpx #4
  bne .read_loop

  ; -- report PASS --
  jsr display_string_immediate
  .asciiz "Cursor: OK"
  stp

.fail:
  ; Clobbers X (= failure index) which we want to display.
  phx
  jsr display_string_immediate
  .asciiz "Cursor: FAIL@"
  plx
  txa
  jsr display_hex
  stp

  .endif


; ----- pseudo-random fill -----
;
; 16-bit Galois LFSR, polynomial $B400. Caller seeds LFSR before
; calling lfsr_step or fill_phase.
LFSR_SEED = $ACE1
LFSR_POLY_HI = $B4

; Step the LFSR by one bit. Cycles through all 65535 non-zero states.
; Preserves nothing.
lfsr_step:
  lsr LFSR+1
  ror LFSR
  bcc .skip_xor
  lda LFSR+1
  eor #LFSR_POLY_HI
  sta LFSR+1
.skip_xor:
  rts

; fill_phase: write N_ELEMENTS LFSR-sequence words through the TGT
; cursor (which the caller has positioned to the start of side A).
; Uses TOTAL_REM as a 16-bit countdown.
fill_phase:
  lda #<N_ELEMENTS
  sta TOTAL_REM
  lda #>N_ELEMENTS
  sta TOTAL_REM+1
.loop:
  lda TOTAL_REM
  ora TOTAL_REM+1
  beq .done
  ; emit current LFSR value as the next element
  lda LFSR
  sta EMIT_VAL
  lda LFSR+1
  sta EMIT_VAL+1
  jsr tgt_write_advance
  jsr lfsr_step
  ; decrement 16-bit TOTAL_REM
  lda TOTAL_REM
  bne .lo_nz
  dec TOTAL_REM+1
.lo_nz:
  dec TOTAL_REM
  bra .loop
.done:
  rts


; ----- fill selftest (built with -DSELFTEST_FILL=1) -----
;
; Runs fill_phase, then re-seeds the LFSR and walks the same side via
; SRC_A, comparing each element. On any mismatch displays
; 'Fill: FAIL@HHHH' (16-bit position); on full match 'Fill: OK'.
  .ifdef SELFTEST_FILL

fill_selftest:
  ; seed LFSR
  lda #<LFSR_SEED
  sta LFSR
  lda #>LFSR_SEED
  sta LFSR+1

  ; init TGT to start of side A (cfg=$18, ptr=$8000)
  lda #$18
  sta TGT_CFG
  stz TGT_PTR
  lda #$80
  sta TGT_PTR+1

  jsr fill_phase

  ; -- verify --
  ; re-seed LFSR, init SRC_A to side A start
  lda #<LFSR_SEED
  sta LFSR
  lda #>LFSR_SEED
  sta LFSR+1
  lda #$18
  sta SRC_A_CFG
  stz SRC_A_PTR
  lda #$80
  sta SRC_A_PTR+1
  ; reset counter, plus a separate position counter for FAIL display
  lda #<N_ELEMENTS
  sta TOTAL_REM
  lda #>N_ELEMENTS
  sta TOTAL_REM+1
  stz CHUNK_REM            ; 16-bit position counter
  stz CHUNK_REM+1
.verify_loop:
  lda TOTAL_REM
  ora TOTAL_REM+1
  beq .pass
  jsr src_a_read_advance
  lda NEXT_A
  cmp LFSR
  bne .fail
  lda NEXT_A+1
  cmp LFSR+1
  bne .fail
  jsr lfsr_step
  ; advance position
  inc CHUNK_REM
  bne .pos_no_carry
  inc CHUNK_REM+1
.pos_no_carry:
  ; decrement counter
  lda TOTAL_REM
  bne .lo_nz_v
  dec TOTAL_REM+1
.lo_nz_v:
  dec TOTAL_REM
  bra .verify_loop

.pass:
  jsr display_string_immediate
  .asciiz "Fill: OK"
  stp

.fail:
  jsr display_string_immediate
  .asciiz "Fill: FAIL@"
  lda CHUNK_REM+1
  jsr display_hex
  lda CHUNK_REM
  jsr display_hex
  stp

  .endif


; ----- bottom-up merge sort -----
;
; Each pass walks the current source side front-to-back in chunks of
; 2L elements (a run-A of L followed by a run-B of L) and merges each
; chunk into a single sorted 2L run on the target side. Source/target
; roles swap after every pass. The last chunk of a pass may be partial
; when N is not a multiple of 2L.
;
; Side A occupies cfgs $18..$1B (4 banks); side B occupies $1C..$1F.
; Cursors walk $8000..$EFFE within each cfg, wrapping to the next.

SIDE_A_CFG = $18
SIDE_B_CFG = $1C

; advance_skip_x: advance cursor at offset X by RUN_LEN elements.
; A simple per-element loop -- correct across multi-bank skips, and
; the amortised count is bounded (~N per pass across both cursors).
; Clobbers A; preserves X, Y.
advance_skip_x:
  ; SKIP_COUNT = RUN_LEN, used as countdown
  lda RUN_LEN
  sta SKIP_COUNT
  lda RUN_LEN+1
  sta SKIP_COUNT+1
.skip_loop:
  lda SKIP_COUNT
  ora SKIP_COUNT+1
  beq .skip_done
  phx
  jsr advance_cursor_x
  plx
  lda SKIP_COUNT
  bne .skip_lo_nz
  dec SKIP_COUNT+1
.skip_lo_nz:
  dec SKIP_COUNT
  bra .skip_loop
.skip_done:
  rts

; merge_one_chunk: merge a chunk pair using the cursors as currently
; positioned. On entry A_REM and B_REM hold the run lengths (each <=
; RUN_LEN; B_REM may be 0 for a degenerate trailing chunk).
;
; Walks A_REM elements from SRC_A and B_REM elements from SRC_B in
; ascending order, writing through TGT. Leaves the cursors advanced
; past everything consumed.
merge_one_chunk:
  ; Pre-fill NEXT_A if A run is non-empty.
  lda A_REM
  ora A_REM+1
  beq .pre_b
  jsr src_a_read_advance
.pre_b:
  ; Pre-fill NEXT_B if B run is non-empty.
  lda B_REM
  ora B_REM+1
  beq .drain_a
  jsr src_b_read_advance
  ; fall through

.compare_loop:
  ; Both NEXT_A and NEXT_B valid; emit the smaller.
  lda NEXT_A+1
  cmp NEXT_B+1
  bcc .emit_a
  bne .emit_b
  lda NEXT_A
  cmp NEXT_B
  bcc .emit_a
  ; NEXT_A >= NEXT_B: emit B
.emit_b:
  lda NEXT_B
  sta EMIT_VAL
  lda NEXT_B+1
  sta EMIT_VAL+1
  jsr tgt_write_advance
  lda B_REM
  bne .b_lo_nz
  dec B_REM+1
.b_lo_nz:
  dec B_REM
  lda B_REM
  ora B_REM+1
  beq .drain_a
  jsr src_b_read_advance
  bra .compare_loop

.emit_a:
  lda NEXT_A
  sta EMIT_VAL
  lda NEXT_A+1
  sta EMIT_VAL+1
  jsr tgt_write_advance
  lda A_REM
  bne .a_lo_nz
  dec A_REM+1
.a_lo_nz:
  dec A_REM
  lda A_REM
  ora A_REM+1
  beq .drain_b
  jsr src_a_read_advance
  bra .compare_loop

.drain_a:
  ; B exhausted; emit remaining A_REM elements (NEXT_A is the first if A_REM>0).
  lda A_REM
  ora A_REM+1
  beq .done
.drain_a_loop:
  lda NEXT_A
  sta EMIT_VAL
  lda NEXT_A+1
  sta EMIT_VAL+1
  jsr tgt_write_advance
  lda A_REM
  bne .a_lo_nz2
  dec A_REM+1
.a_lo_nz2:
  dec A_REM
  lda A_REM
  ora A_REM+1
  beq .done
  jsr src_a_read_advance
  bra .drain_a_loop

.drain_b:
  ; A exhausted; emit remaining B_REM elements.
  lda B_REM
  ora B_REM+1
  beq .done
.drain_b_loop:
  lda NEXT_B
  sta EMIT_VAL
  lda NEXT_B+1
  sta EMIT_VAL+1
  jsr tgt_write_advance
  lda B_REM
  bne .b_lo_nz2
  dec B_REM+1
.b_lo_nz2:
  dec B_REM
  lda B_REM
  ora B_REM+1
  beq .done
  jsr src_b_read_advance
  bra .drain_b_loop

.done:
  rts


; sort_phase: full bottom-up sort. Caller has filled side A; on return
; the sorted result lives on the side identified by CURRENT_SIDE_IS_A
; (1 -> side A, 0 -> side B). 16 passes for N=57344 (RUN_LEN doubles
; until >= N_ELEMENTS); on each pass we set cursors at the side starts
; and walk through chunks of 2*RUN_LEN.
sort_phase:
  ; Initial RUN_LEN = 1; source = side A.
  lda #1
  sta RUN_LEN
  stz RUN_LEN+1
  lda #1
  sta CURRENT_SIDE_IS_A   ; source side is A
  stz PASS_NUM

.pass_loop:
  ; Exit when RUN_LEN >= N_ELEMENTS (no more merging possible).
  lda RUN_LEN+1
  cmp #>N_ELEMENTS
  bcc .do_pass            ; RUN_LEN_HI < N_ELEMENTS_HI
  bne .all_done           ; RUN_LEN_HI > N_ELEMENTS_HI
  lda RUN_LEN
  cmp #<N_ELEMENTS
  bcc .do_pass
.all_done:
  ; Source side now holds the sorted data. CURRENT_SIDE_IS_A points
  ; to it because we flipped *after* every pass (so this flag still
  ; matches the last pass's source -> the next pass's source -> the
  ; current sorted side).
  rts

.do_pass:
  ; LCD pass progress: "Pass NN/16 L=NNNN" on line 1 so the user can
  ; watch the demo work. Display routines run with whatever cfg is
  ; active when we get here -- safe because clear_display, move_cursor,
  ; display_string_immediate and display_decimal only touch VIA, LCD,
  ; and ZP $00..$0E (the helper scratch in the lower banked region,
  ; which stays valid as long as we're in cfgs $18..$1F).
  jsr show_pass_header

  ; --- set up cursors for this pass ---
  ; SRC_A points at start of the source side; SRC_B at SRC_A + RUN_LEN
  ; elements; TGT at start of the target side.
  lda CURRENT_SIDE_IS_A
  beq .src_is_b

  ; source = side A, target = side B
  lda #SIDE_A_CFG
  sta SRC_A_CFG
  lda #SIDE_B_CFG
  sta TGT_CFG
  bra .ptrs

.src_is_b:
  lda #SIDE_B_CFG
  sta SRC_A_CFG
  lda #SIDE_A_CFG
  sta TGT_CFG

.ptrs:
  stz SRC_A_PTR
  lda #$80
  sta SRC_A_PTR+1
  stz TGT_PTR
  lda #$80
  sta TGT_PTR+1

  ; SRC_B = SRC_A advanced by RUN_LEN elements.
  ; First copy SRC_A's full cursor (cfg + ptr) to SRC_B.
  lda SRC_A_CFG
  sta SRC_B_CFG
  lda SRC_A_PTR
  sta SRC_B_PTR
  lda SRC_A_PTR+1
  sta SRC_B_PTR+1
  ldx #CUR_OFFSET_SRC_B
  jsr advance_skip_x      ; advance SRC_B by RUN_LEN

  ; --- chunk walk ---
  lda #<N_ELEMENTS
  sta TOTAL_REM
  lda #>N_ELEMENTS
  sta TOTAL_REM+1

.chunk_loop:
  ; If TOTAL_REM == 0, pass done.
  lda TOTAL_REM
  ora TOTAL_REM+1
  bne .chunk_continue
  jmp .pass_done
.chunk_continue:

  ; len_a = min(RUN_LEN, TOTAL_REM)
  ; len_b = min(RUN_LEN, max(0, TOTAL_REM - RUN_LEN))
  ; Compute by saturating subtraction.
  ;
  ; If TOTAL_REM <= RUN_LEN: len_a = TOTAL_REM; len_b = 0.
  ; Else: len_a = RUN_LEN; rem = TOTAL_REM - RUN_LEN; len_b = min(rem, RUN_LEN).

  ; Compare TOTAL_REM vs RUN_LEN (unsigned 16-bit).
  lda TOTAL_REM+1
  cmp RUN_LEN+1
  bcc .total_le_run
  bne .total_gt_run
  lda TOTAL_REM
  cmp RUN_LEN
  bcc .total_le_run
  beq .total_le_run

.total_gt_run:
  ; len_a = RUN_LEN
  lda RUN_LEN
  sta A_REM
  lda RUN_LEN+1
  sta A_REM+1
  ; rem = TOTAL_REM - RUN_LEN
  sec
  lda TOTAL_REM
  sbc RUN_LEN
  sta CHUNK_REM
  lda TOTAL_REM+1
  sbc RUN_LEN+1
  sta CHUNK_REM+1
  ; len_b = min(CHUNK_REM, RUN_LEN)
  lda CHUNK_REM+1
  cmp RUN_LEN+1
  bcc .b_is_rem
  bne .b_is_run
  lda CHUNK_REM
  cmp RUN_LEN
  bcc .b_is_rem
.b_is_run:
  lda RUN_LEN
  sta B_REM
  lda RUN_LEN+1
  sta B_REM+1
  bra .have_lens
.b_is_rem:
  lda CHUNK_REM
  sta B_REM
  lda CHUNK_REM+1
  sta B_REM+1
  bra .have_lens

.total_le_run:
  ; len_a = TOTAL_REM, len_b = 0
  lda TOTAL_REM
  sta A_REM
  lda TOTAL_REM+1
  sta A_REM+1
  stz B_REM
  stz B_REM+1

.have_lens:
  ; Save the consumed count (A_REM + B_REM) so we can decrement
  ; TOTAL_REM after merge_one_chunk clobbers A_REM and B_REM.
  clc
  lda A_REM
  adc B_REM
  sta CHUNK_REM
  lda A_REM+1
  adc B_REM+1
  sta CHUNK_REM+1

  jsr merge_one_chunk

  ; TOTAL_REM -= CHUNK_REM
  sec
  lda TOTAL_REM
  sbc CHUNK_REM
  sta TOTAL_REM
  lda TOTAL_REM+1
  sbc CHUNK_REM+1
  sta TOTAL_REM+1

  ; If more chunks remain, advance SRC_A and SRC_B by RUN_LEN each
  ; so they're positioned at the start of the NEXT chunk's runs.
  lda TOTAL_REM
  ora TOTAL_REM+1
  bne .keep_going
  jmp .pass_done
.keep_going:
  ldx #CUR_OFFSET_SRC_A
  jsr advance_skip_x
  ldx #CUR_OFFSET_SRC_B
  jsr advance_skip_x
  jmp .chunk_loop

.pass_done:
  ; Toggle source side. After flip CURRENT_SIDE_IS_A names the side
  ; we just wrote to (= source of the next pass; = side holding the
  ; up-to-date partial sort, which verify_phase will read).
  lda CURRENT_SIDE_IS_A
  eor #1
  sta CURRENT_SIDE_IS_A
  inc PASS_NUM
  ; RUN_LEN *= 2. If the doubling overflows 16-bit (e.g. the last
  ; pass for N>=32768 takes RUN_LEN from $8000 to $10000), we've
  ; finished sorting -- 2*RUN_LEN is conceptually >= N_ELEMENTS so
  ; the .pass_loop check would otherwise loop forever on RUN_LEN=0.
  asl RUN_LEN
  rol RUN_LEN+1
  bcc .pass_loop_relay    ; no overflow -> continue with next pass
  jmp .all_done           ; overflow -> sort complete
.pass_loop_relay:
  jmp .pass_loop


; SKIP_COUNT lives just past the existing ZP slots used during the
; merge inner loop, so the merge-time and skip-time uses don't overlap.
SKIP_COUNT = $31  ; 2 bytes

; verify_phase result + failure position. Survives between
; verify_phase and show_final.
VERIFY_RESULT    = $33  ; 1 byte: 1 = PASS, 0 = FAIL
VERIFY_FAIL_POS  = $34  ; 2 bytes (only meaningful on FAIL)


; show_pass_header: paint "Pass NN L=NNNN" on line 1 of the LCD so
; the user can watch the demo advance. Clears the line first so
; longer prior text (e.g. "Pass 16 L=32768" -> "Pass 1 L=2") doesn't
; leave stale characters behind.
show_pass_header:
  jsr clear_display
  jsr display_string_immediate
  .asciiz "Pass "
  ; PASS_NUM is 1-based for display; PASS_NUM in ZP starts at 0 and
  ; gets incremented at the end of each pass, but we want to display
  ; the current (0-indexed) pass + 1 here.
  lda PASS_NUM
  clc
  adc #1
  ldx #0
  jsr display_decimal
  jsr display_string_immediate
  .asciiz " L="
  lda RUN_LEN
  ldx RUN_LEN+1
  jsr display_decimal
  rts


; verify_phase: walk the sorted result side once, comparing each
; element to the previous. On the first out-of-order pair, store the
; offending position in VERIFY_FAIL_POS, clear VERIFY_RESULT, and
; return. On full success leave VERIFY_RESULT = 1.
;
; CURRENT_SIDE_IS_A names the side holding the sorted result (sort_phase
; sets this before returning).
verify_phase:
  lda CURRENT_SIDE_IS_A
  beq .v_b
  lda #SIDE_A_CFG
  bra .v_set
.v_b:
  lda #SIDE_B_CFG
.v_set:
  sta SRC_A_CFG
  stz SRC_A_PTR
  lda #$80
  sta SRC_A_PTR+1

  lda #1
  sta VERIFY_RESULT       ; optimistic
  stz VERIFY_FAIL_POS
  stz VERIFY_FAIL_POS+1

  ; Read element 0 into PREV_ELEM. Nothing to compare yet.
  jsr src_a_read_advance
  lda NEXT_A
  sta PREV_ELEM
  lda NEXT_A+1
  sta PREV_ELEM+1

  ; position counter (starts at 1; element 0 is already read).
  lda #1
  sta CHUNK_REM
  stz CHUNK_REM+1

.v_loop:
  ; if CHUNK_REM >= N_ELEMENTS: done.
  lda CHUNK_REM+1
  cmp #>N_ELEMENTS
  bcc .v_continue
  bne .v_done
  lda CHUNK_REM
  cmp #<N_ELEMENTS
  bcs .v_done
.v_continue:
  jsr src_a_read_advance
  ; NEXT_A < PREV_ELEM ?
  lda NEXT_A+1
  cmp PREV_ELEM+1
  bcc .v_fail
  bne .v_ok
  lda NEXT_A
  cmp PREV_ELEM
  bcc .v_fail
.v_ok:
  lda NEXT_A
  sta PREV_ELEM
  lda NEXT_A+1
  sta PREV_ELEM+1
  inc CHUNK_REM
  bne .v_loop
  inc CHUNK_REM+1
  bra .v_loop

.v_fail:
  stz VERIFY_RESULT
  lda CHUNK_REM
  sta VERIFY_FAIL_POS
  lda CHUNK_REM+1
  sta VERIFY_FAIL_POS+1

.v_done:
  rts


; show_final: paints the result on the LCD.
;   line 1: "Sort: complete"
;   line 2: "OK T=NNNNNms"   (on PASS)
;           "FAIL@HHHH"      (on verify failure)
show_final:
  jsr clear_display
  jsr display_string_immediate
  .asciiz "Sort: complete"

  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda VERIFY_RESULT
  beq .show_fail
  jsr display_string_immediate
  .asciiz "OK T="
  lda ELAPSED_MS
  ldx ELAPSED_MS+1
  jsr display_decimal
  jsr display_string_immediate
  .asciiz "ms"
  rts

.show_fail:
  jsr display_string_immediate
  .asciiz "FAIL@"
  lda VERIFY_FAIL_POS+1
  jsr display_hex
  lda VERIFY_FAIL_POS
  jsr display_hex
  rts


; ----- elapsed-time timer (T1 IRQ, ~1ms per tick) -----
;
; T1 latched at CLOCK_FREQ_KHZ-1 = 9719 cycles ≈ 1 ms per underflow.
; The handler increments a 16-bit ms counter at $F800 -- in upper
; fixed RAM bank 1, which is mapped consistently across cfg=$10..$1F
; so the same physical bytes are seen no matter which upper bank the
; main code happens to be visiting when the IRQ fires.
;
; The 6522 IRQ vector at $FFFE/$FFFF lives in that same bank 1; we
; overwrite it (the boot ROM had pointed it at $3F00 in lower-banked
; RAM, which would land on garbage in our lower-bank-2 cfgs).

T1_LATCH        = CLOCK_FREQ_KHZ - 1   ; 9719 cycles ≈ 1ms at 9.72 MHz
OVERFLOW_COUNT  = $F800                ; 2 bytes (ms-tick counter)
IRQ_VECTOR_LO   = $FFFE
IRQ_VECTOR_HI   = $FFFF

; timer_start: install IRQ handler, zero the ms counter, latch and
; start T1, enable T1 interrupts, allow IRQs.
timer_start:
  sei
  lda #<irq_handler
  sta IRQ_VECTOR_LO
  lda #>irq_handler
  sta IRQ_VECTOR_HI

  stz OVERFLOW_COUNT
  stz OVERFLOW_COUNT+1

  ; T1 continuous-counter mode, PB7 disabled. Preserve other ACR bits.
  lda ACR
  and #%00111111            ; mask out the T1 mode bits (6 and 7)
  ora #ACR_T1_CONT
  sta ACR

  ; Load latch + start counter (writing T1CH transfers latch into the
  ; counter and starts decrementing).
  lda #<T1_LATCH
  sta T1CL
  lda #>T1_LATCH
  sta T1CH

  ; Clear any stale T1 IRQ, then enable T1 IRQ.
  lda #IT1
  sta IFR
  lda #(IERSETCLEAR | IT1)
  sta IER

  cli
  rts

; timer_stop: SEI, disable T1 IRQ, capture the current ms counter
; into ELAPSED_MS so show_final can display it later.
timer_stop:
  sei
  lda #IT1
  sta IER                 ; bit-7 clear -> "clear these IER bits" -> disables T1 IRQ
  lda OVERFLOW_COUNT
  sta ELAPSED_MS
  lda OVERFLOW_COUNT+1
  sta ELAPSED_MS+1
  rts

; irq_handler: minimal -- only services T1, ignores any other source.
; Preserves A only (X and Y aren't touched).
irq_handler:
  pha
  lda IFR
  and #IT1
  beq .ih_done
  lda T1CL              ; clear T1 IRQ flag by reading T1CL
  inc OVERFLOW_COUNT
  bne .ih_done
  inc OVERFLOW_COUNT+1
.ih_done:
  pla
  rti

; ELAPSED_MS lives in fixed RAM (not ZP) so it survives all bank
; switches without needing the ZP layout to be valid.
ELAPSED_MS: .word 0


; ----- sort selftest (built with -DSELFTEST_SORT=1) -----
;
; Runs fill_phase + sort_phase, then walks the final sorted side
; comparing each element to the previous. On any out-of-order pair,
; displays 'Sort: FAIL@HHHH' with the offending position; otherwise
; 'Sort: OK'.
  .ifdef SELFTEST_SORT

sort_selftest:
  ; seed LFSR + init TGT to side A start, then fill.
  lda #<LFSR_SEED
  sta LFSR
  lda #>LFSR_SEED
  sta LFSR+1
  lda #SIDE_A_CFG
  sta TGT_CFG
  stz TGT_PTR
  lda #$80
  sta TGT_PTR+1
  jsr fill_phase

  ; sort.
  jsr sort_phase

  ; -- verify sortedness --
  ; SRC_A positioned at the start of the SORTED side. CURRENT_SIDE_IS_A
  ; tells us which one.
  lda CURRENT_SIDE_IS_A
  beq .src_b
  lda #SIDE_A_CFG
  bra .src_set
.src_b:
  lda #SIDE_B_CFG
.src_set:
  sta SRC_A_CFG
  stz SRC_A_PTR
  lda #$80
  sta SRC_A_PTR+1

  ; Read first element; nothing to compare against yet.
  jsr src_a_read_advance
  lda NEXT_A
  sta PREV_ELEM
  lda NEXT_A+1
  sta PREV_ELEM+1

  ; Counter: position of currently-read element (start at 1 since
  ; we already read element 0). Loop until pos == N_ELEMENTS.
  lda #1
  sta CHUNK_REM
  stz CHUNK_REM+1
.verify_loop:
  ; if CHUNK_REM >= N_ELEMENTS: done
  lda CHUNK_REM+1
  cmp #>N_ELEMENTS
  bcc .read_next
  bne .pass
  lda CHUNK_REM
  cmp #<N_ELEMENTS
  bcs .pass
.read_next:
  jsr src_a_read_advance
  ; Compare NEXT_A vs PREV_ELEM. Out-of-order iff NEXT_A < PREV_ELEM.
  lda NEXT_A+1
  cmp PREV_ELEM+1
  bcc .fail
  bne .ok
  lda NEXT_A
  cmp PREV_ELEM
  bcc .fail
.ok:
  lda NEXT_A
  sta PREV_ELEM
  lda NEXT_A+1
  sta PREV_ELEM+1
  inc CHUNK_REM
  bne .verify_loop
  inc CHUNK_REM+1
  bra .verify_loop

.pass:
  jsr clear_display
  jsr display_string_immediate
  .asciiz "Sort: OK"
  stp

.fail:
  jsr clear_display
  jsr display_string_immediate
  .asciiz "Sort: FAIL@"
  lda CHUNK_REM+1
  jsr display_hex
  lda CHUNK_REM
  jsr display_hex
  stp

  .endif
