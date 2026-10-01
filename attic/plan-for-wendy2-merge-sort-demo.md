# Wendy2 Merge Sort Memory Demo

> **Attic note:** implemented as `firmware/programs/wendy2/wendy2_merge_sort.s`. The `base_config_wendy2.inc` named below is now `firmware/boards/wendy2/base_config_wendy2c.inc`, and upload is via `tools/upload/compile_and_upload_wendy2.sh`.


## Context

> **Update:** commit `8a8eb82` was later reverted: cfg `$18` maps ROM into the upper window again
> (the lower-bank-2 analogue of cfg `$10`). The demo still numbers its banks `$18..$1F`, and its
> `switch_to_space` macro substitutes cfg `$02` (lower bank 2, upper RAM bank 0) for `$18`.

The wendy2 PLD was just fixed (commit `8a8eb82` cherry-picked onto `michael_keyboard_wip`) so that cfgs `$18..$1F` correctly map all 8 upper-RAM banks instead of `$18` aliasing to a ROM config. This demo exercises every one of those upper banks end-to-end by doing a real workload — a bottom-up merge sort of ~57k 16-bit values across 4 "source" banks and 4 "target" banks — while showing live progress and a final verification pass on the LCD.

Goals:
- Use **all 8** upper-RAM banks (cfgs `$18..$1F`) for data, splitting them 4 source / 4 target.
- Implement a textbook bottom-up merge sort starting from runs of length 1.
- Stream-process so we never need random-access offsets that straddle bank boundaries.
- Provide visible progress (pass counter + progress bar) so the user can watch it work.
- Verify final sorted order and report pass/fail with total elapsed time.

## Memory layout

| Region        | Range            | Notes                                              |
|---------------|------------------|----------------------------------------------------|
| Code + consts | `$4000..$7FFF`   | Always-present SRAM bank 0 (16K) — survives all cfg changes |
| Stack + ZP    | `$0000..$01FF`   | Lower bank 2 (selected by `C3=1` in cfgs `$18..$1F`) |
| Side A data   | `$8000..$EFFF` × cfgs `$18..$1B` | 4 upper banks, 4 × 28K = 112K = 57,344 × 16-bit elements |
| Side B data   | `$8000..$EFFF` × cfgs `$1C..$1F` | 4 upper banks, same size as side A |
| VIA           | `$F000..$F7FF`   | Bank-select register at `PORTB` (= `$F000`), T1 timer |

We stay inside the `$18..$1F` cfg range for the entire demo so the lower 16K mapping (bank 2 of SRAM) never changes — ZP and stack remain stable across every `switch_to_space` call.

## Algorithm — bottom-up merge sort, streaming

- N = **57,344** elements (16-bit unsigned, 0xE000 total).
- Run length L starts at 1, doubles each pass. After pass k, L = 2^(k+1). Sort completes when L ≥ N, i.e. **16 passes** (last pass handles uneven 32768+24576 split).
- Each pass walks one side (source) front-to-back and writes the other side (target) front-to-back. Source/target roles swap after every pass.
- Within a pass: process the source in chunks of 2L elements, merging the first-L vs. second-L into a single sorted 2L run. Last chunk may have second-half shorter — drain it accordingly.

### Stream cursors (zero-page resident)

Three cursors, one for each: source-A reader, source-B reader, target writer.

Each cursor:
- `*_cfg` (1 byte) — current upper-bank cfg (one of `$18..$1F`)
- `*_ptr` (2 bytes) — address in `$8000..$EFFE`
- `*_run_remaining` (2 bytes) — elements left in current run (source cursors only)

Cursor advance (after read or write of one 16-bit value):
- `*_ptr += 2`; if `*_ptr == $F000`, set `*_cfg += 1`, `*_ptr = $8000`.
- No mid-element straddle: 28K is even, last element in each bank is at `$EFFE-$EFFF`.

Cursor read/write: `lda #cfg; jsr switch_to_space` to make the cursor's bank visible, then `lda (ptr),Y` / `sta (ptr),Y` (ZP indirect with Y=0 and Y=1, or with a dedicated 16-bit load/store helper). Cache the last-read element from each source in ZP (`next_a`, `next_b`) so each compare step does at most one extra read.

### Merge inner loop (per output element)

```
; Precondition: next_a, next_b hold the next unread element from each run;
;               a_rem, b_rem hold remaining elements in each run.
compare next_a vs next_b
emit the smaller (via target cursor write + advance)
advance the chosen source cursor
  - decrement its run_remaining
  - if 0: switch to drain mode for the other run
  - else: read next element into next_a or next_b
```

Each iteration: 1 target-bank switch + 1 source-bank switch (only when reading), plus the actual mem accesses. Estimated ~150 cycles/element × 57344 elements/pass × 16 passes ≈ 140M cycles ≈ 14s at 10MHz. Acceptable for a demo.

### Fill phase (before pass 1)

Walk side A (4 banks, cfgs `$18..$1B`) writing pseudo-random 16-bit values. PRNG: 16-bit Galois LFSR, polynomial `$B400`, seed `$ACE1`. Update LCD progress bar.

```
lfsr_step:        ; takes ~20 cycles
  lsr lfsr+1
  ror lfsr
  bcc :+
  lda lfsr+1
  eor #$B4
  sta lfsr+1
:
```

### Verify phase (after sort)

Walk the final sorted side once. For each element compare to the previous; if any element is less than the previous, record the position and report FAIL. Otherwise PASS.

### Tracking which side holds the final result

After pass k (0-indexed), sorted data is on side B if k is even, side A if k is odd. With k = 0..15 (16 passes), the last pass writes to side A (since 15 is odd, target = A). Or we just track `current_target_side` in a byte and use it for the verify phase.

## LCD output (16×2)

```
During fill:               During sort:                After sort:                Final:
+----------------+         +----------------+          +----------------+         +----------------+
|Filling banks...|         |Pass 07/16 L=128|          |Verifying...    |         |Sort: complete  |
|[####.         ]|         |[##########.   ]|          |[#######.      ]|         |Verify: PASS    |
+----------------+         +----------------+          +----------------+         +----------------+

                                                                                  On FAIL:
                                                                                  +----------------+
                                                                                  |Sort: complete  |
                                                                                  |FAIL@NNNNN  Ts.s|
                                                                                  +----------------+

Time display (overwrites verify line briefly, then leaves PASS):
                                                                                  +----------------+
                                                                                  |Sort: complete  |
                                                                                  |OK   T= NNN.Ns  |
                                                                                  +----------------+
```

- Progress bar: 15 cells. Update every 2048 emitted/processed elements (≈ 28 increments per pass, 14 bar fills, smooth visual progress).
- `display_decimal` (existing, in `display_decimal.inc`) for the pass-number, run-length, and elapsed-time formatting.
- Format helpers from `display_string_immediate.inc` (existing) for the static labels.

## Timing — total elapsed

VIA T1 in free-running PB7-disabled mode, T1 latch = `$FFFF` (so each underflow = 65,536 cycles ≈ 6.74 ms at 9720 kHz). Wire T1 IRQ to a tiny handler that increments a 24-bit overflow counter at `$F800..$F802` (top RAM). 24-bit × 65,536 cycles = ~1700 sec range, plenty.

Display total elapsed seconds as `T= NNN.Ns` after verify completes:
```
elapsed_seconds = (overflow_count × 65536 + T1C_at_end - T1C_at_start) / 9720000
```
Use `display_decimal` for the integer-second portion; one fractional digit can come from `(remainder × 10) / 9720000`. Round generously; this is for human display, not a benchmark.


## Files

**Create:**
- `/home/pjdennis/research/6502_3/wendy2_merge_sort.s` — new top-level program, `.org $4000`

**Reuse (include) — all existing:**
- `base_config_wendy2.inc` — banking constants, VIA address, LCD geometry
- `delay_routines.inc` — for any small spin-waits (optional)
- `display_routines_4bit.inc` — `display_character`, `clear_display`, etc.
- `display_hex.inc` — for debug or hex element dump
- `display_decimal.inc` — pass number, run length, element count, elapsed time
- `display_string_immediate.inc` — for static labels embedded inline
- `6522.inc` (transitively via `base_config_wendy2.inc`) — VIA register addresses

**Refactor opportunity (optional):** extract `switch_to_space` from `wendy2_verification.s` into a new `switch_to_space.inc` so both files can include it. If we skip this in the first pass, copy the routine inline.

## Program skeleton

```
  .include base_config_wendy2.inc

; ----- zero page -----
D_S_I_P            = $00 ; 2 bytes (for display_string_immediate)
TEMP               = $02
TO_DECIMAL_PARAM   = $03 ; 10 bytes (for display_decimal)

LFSR               = $10 ; 2 bytes
NEXT_A             = $12 ; 2 bytes (cached next source-A element)
NEXT_B             = $14 ; 2 bytes
SRC_A_CFG          = $16 ; 1 byte
SRC_A_PTR          = $17 ; 2 bytes
SRC_B_CFG          = $19
SRC_B_PTR          = $1A
TGT_CFG            = $1C
TGT_PTR            = $1D
A_REM              = $1F ; 2 bytes, elements left in current run-A
B_REM              = $21
PASS               = $23 ; 1 byte
RUN_LEN            = $24 ; 2 bytes (current L)
CURRENT_SIDE_IS_A  = $26 ; 1 byte: side holding source for this pass (1=A, 0=B)
CHUNK_REM          = $27 ; 2 bytes (elements left in the current 2L chunk pair)
TOTAL_REM          = $29 ; 2 bytes (elements left in pass)
PROGRESS_TICK      = $2B ; 2 bytes (counter for progress bar updates)
PREV_ELEM          = $2D ; 2 bytes (verify pass: previous element)

  .org $4000
  jmp program_entry

  .include delay_routines.inc       ; first, page-aligned for timing
  .include display_routines_4bit.inc
  .include display_hex.inc
  .include display_decimal.inc
  .include display_string_immediate.inc

program_entry:
  lda #$18                ; switch to lower bank 2, upper bank 0
  switch_to_space         ; macro to be written
  ldx #$ff                ; fresh stack after possible lower-bank change
  txs

  jsr clear_display
  jsr setup_t1_irq        ; or skip if falling back to no-timer
  jsr fill_phase
  jsr sort_phase
  jsr verify_phase
  jsr show_final
  stp                     ; halt

; ----- subroutines -----
;   fill_phase, sort_phase, verify_phase
;   merge_one_chunk(src_a_cur, src_b_cur, tgt_cur, len_a, len_b)
;   read_word_at_cursor, write_word_at_cursor, advance_cursor
;   show_pass_header, update_progress_bar
;   lfsr_step
;   switch_to_space  (copied from verification.s)

  ; ... actual implementation here ...
```

## Verification (testing this demo end-to-end)

1. **Compile + upload.** Use the existing build/upload chain (`upload_and_run_ram_wendy2.s` style) to assemble `wendy2_merge_sort.s` and transfer over serial via `transfer.py` (now with auto-USB detection). The program loads at `$4000` and starts.
2. **Watch the LCD** through the four phases (fill → sort → verify → final). Each phase should advance the progress bar smoothly; no apparent hang.
3. **Confirm PASS.** Final line should read `Verify: PASS` (or `OK T= NNN.Ns`). On FAIL, the position is shown — re-run with a fixed PRNG seed to reproduce.
4. **Quick-iteration knob.** Add an assemble-time constant `N_ELEMENTS` (default 57344) so we can drop it to e.g. 2048 during debug to iterate fast, then bump back up for the real demo.
5. **Stress test.** Re-run with different seeds (build-time constant) to make sure both the boundary case (last partial chunk in pass 15→16) and the uniform PRNG distribution don't trigger the FAIL branch. If a FAIL occurs, the position pinpoints exactly which bank/cursor boundary went wrong.
6. **Cross-check.** Optionally, after sort but before verify, dump the first / last / a-middle element as hex to the LCD second line, manually pause, and confirm against expected bounds — useful early in implementation.

## Out of scope

- Performance tuning (no attempt to overlap LCD updates with sorting, no specialized merge for runs of length 1 even though pass 0 could be a simple in-pair swap).
- Persisting sorted data to EEPROM or sending it over serial.
- Multi-threading / interrupt-driven progress UI beyond the optional T1 timer.
