; Normal mode editing commands - paste, toggle case, join, substitute,
; change line, indent/unindent, word delete/change

; --- Paste ---

; Shared paste prologue: record undo position, get the paste count plus
; the extra p/P keys already typed ahead (BUF_TEMP = the key, set by dispatch)
; Output: BUF_TEMP16 = count + extras, BATCH_EXTRA = extras,
;         UNDO_LINE16/UNDO_COL16/UNDO_PASTE_COUNT16 recorded
paste_prologue:
  CP16 FILE_LINE16, UNDO_LINE16
  CP16 CURSOR_COL16, UNDO_COL16
  JSR get_count              ; BUF_TEMP16 = count
  JSR count_pending_key      ; X = pending matching keys
  STX BATCH_EXTRA
  TXA
  CLC
  ADCA16 BUF_TEMP16, BUF_TEMP16
  CP16 BUF_TEMP16, UNDO_PASTE_COUNT16
  RTS

normal_paste_below:
  JSR undo_clear
  LDA YANK_TYPE
  BNE char_paste_below
  JSR paste_prologue
  JSR yank_paste_below_n
  BCS paste_done
  JSR paste_adjust_marks
  LDA #UNDO_LINE_PASTE_BELOW
  STA UNDO_TYPE
  ; Cursor: yank_paste_below_n does INC16 once; add extras for iterative semantics
  LDA BATCH_EXTRA
  BEQ .paste_below_scroll
  ; Batched paste: cursor adjustment shifts FILE_LINE16 past first pasted
  ; lines, so scroll walk would start at wrong position.
  CLC
  ADCA16 FILE_LINE16, FILE_LINE16
  ; Batching must not widen undo: record only the last pasted copy.
  ; It occupies YANK_LINES16 lines starting (N-1)*YANK_LINES16 + 1 past
  ; the original cursor line.
  DEC16 UNDO_PASTE_COUNT16
  JSR undo_compute_paste_lines    ; BUF_TEMP16 = (N-1) * YANK_LINES16
  CLC
  ADC16 UNDO_LINE16, BUF_TEMP16, UNDO_LINE16
  JMP paste_undo_one              ; RENDER_FLAG stays 0 → full repaint
.paste_below_scroll:
  LDA #$03                   ; Signal line-insert for scroll optimization
  JMP set_render_clear_count

normal_paste_above:
  JSR undo_clear
  LDA YANK_TYPE
  BNE char_paste_above
  JSR paste_prologue
  JSR yank_paste_above_n
  BCS paste_done
  JSR paste_adjust_marks
  LDA #UNDO_LINE_PASTE_ABOVE
  STA UNDO_TYPE
  LDA #$03
  STA RENDER_FLAG        ; Signal line-insert for scroll optimization
  ; No cursor adjustment - yank_paste_above_n doesn't change FILE_LINE16
  ; Batching must not widen undo: the last pasted copy sits at the top
  ; of the block (paste-above prepends), i.e. at UNDO_LINE16 already.
  BNE paste_batched_undo     ; Always (A = $03)

; Character paste above (before cursor)
; Handles newlines in yanked content via find_line_for_ptr
; Single-shift interleaved fill for all yank sizes
char_paste_above:
  JSR paste_prologue
  JSR do_char_paste_above
  BCS paste_done
  LDA #UNDO_CHAR_PASTE_ABOVE
  STA UNDO_TYPE
  ; Batching must not widen undo: the last pasted copy sits first
  ; (paste-above inserts before the cursor), i.e. at UNDO_COL16 already.
paste_batched_undo:
  LDA BATCH_EXTRA
  BEQ paste_done
; Batching must not widen undo: record only the last pasted copy
paste_undo_one:
  SET16 $0001, UNDO_PASTE_COUNT16
paste_done:
  JMP clear_count

; Character paste below (after cursor)
; For non-empty lines, inserts after cursor char; for empty lines, inserts at line start
; Handles newlines in yanked content via find_line_for_ptr
char_paste_below:
  JSR paste_prologue         ; UNDO_COL16 = cursor column (0 on an empty line)
  ; Insertion column for undo: cursor + 1 (non-empty line) or 0 (empty)
  JSR get_line_len_z
  BEQ .cpb_paste
  INC16 UNDO_COL16
.cpb_paste:
  JSR do_char_paste_below
  BCS paste_done
  LDA #UNDO_CHAR_PASTE_BELOW
  STA UNDO_TYPE
  ; Batching must not widen undo: record only the last pasted copy,
  ; which ends at the cursor (UNDO_COL16 = cursor + 1 - yank size)
  LDA BATCH_EXTRA
  BEQ paste_done
  JSR yank_has_newline
  BCS .cpb_no_undo           ; multi-line char yank: column math invalid
  SEC
  SBC16 CURSOR_COL16, YANK_SIZE16, UNDO_COL16
  INC16 UNDO_COL16
  JMP paste_undo_one
.cpb_no_undo:
  JSR undo_clear             ; A = UNDO_NONE = 0
  BEQ paste_done             ; Always

; Core char paste below: paste BUF_TEMP16 copies after cursor
; Returns carry set = failed/empty, carry clear = success
do_char_paste_below:
  JSR yank_paste_setup
  BCC .not_empty
  RTS                          ; Empty yank (carry set)
.not_empty:

  ; Save total paste size on stack
  PUSH16 BUF_LEN16

  ; Compute insertion point
  JSR get_line_len_z
  BEQ .empty_line

  ; Non-empty line: insert after cursor
  JSR get_cursor_buf_ptr
  INC16 BUF_PTR16
  CP16 CURSOR_COL16, RENDER_FROM_COL16
  JMP .do_paste

.empty_line:
  JSR get_cursor_buf_ptr     ; Insert at line start

.do_paste:
  CP16 LINE_COUNT16, COUNT16 ; Save line count for mark adjustment
  PUSH16 BUF_PTR16           ; Save insertion point
  JSR yank_paste_core
  POP16 BUF_PTR16            ; Recover insertion point
  POP16 BUF_LEN16            ; Recover total paste size
  BCS .done                  ; Paste failed (buffer full)

  ; Check if pasted content is multi-line
  JSR yank_has_newline
  BCS .multiline

  ; Single-line: cursor at last pasted byte
  CLC
  ADC16 BUF_PTR16, BUF_LEN16, BUF_PTR16
  DEC16 BUF_PTR16
  JMP paste_find_pos

.multiline:
  ; Adjust marks for inserted lines (paste below: at_line = FILE_LINE16 + 1)
  JSR paste_mark_prefix
  ADC #1
  BCC .mark_adj
  INX
.mark_adj:
  JSR mark_adjust_insert
  ; Shared multiline finish + cursor positioning (in do_char_paste_above)
  JMP paste_finish

.done:
  RTS

; Core char paste above: paste BUF_TEMP16 copies at cursor
; Input: BUF_TEMP16 = count, BATCH_EXTRA = extras
; Returns carry set = failed/empty, carry clear = success
do_char_paste_above:
  JSR yank_paste_setup       ; BUF_LEN16 = total size, YANK_SIZE16 = single size
  BCC .not_empty
  RTS                        ; Empty yank (carry set)
.not_empty:

  ; Save total count N for fill routines
  LDA BUF_TEMP16
  STA NORMAL_TEMP

  ; Save total paste size on stack
  PUSH16 BUF_LEN16

  ; Insertion point: at cursor position
  JSR get_cursor_buf_ptr
  CP16 CURSOR_COL16, RENDER_FROM_COL16

  PUSH16 BUF_PTR16           ; Save insertion point
  CP16 LINE_COUNT16, COUNT16 ; Save line count for mark adjustment

  ; Single buffer shift
  JSR buf_shift_right_16
  BCC .shift_ok
  JMP paste_shift_fail
.shift_ok:

  ; Choose fill strategy based on yank content
  JSR yank_has_newline
  BCS .do_contiguous

  ; Single-line: interleaved fill
  JSR interleaved_fill
  JMP .fill_done

.do_contiguous:
  ; Multi-line: N contiguous copies
  JSR contiguous_fill

.fill_done:
  JSR buf_rebuild_lines

  ; Recover insertion point and total size
  POP16 BUF_PTR16
  POP16 BUF_LEN16

  ; Cursor positioning
  JSR yank_has_newline
  BCS .multiline

  ; Single-line: cursor at insertion + total_size - 1 - BATCH_EXTRA
  ; (BUF_LEN16 -= BATCH_EXTRA + 1 via carry-clear SBC, then one add;
  ; BUF_LEN16 is dead after this point)
  CLC
  LDA BUF_LEN16
  SBC BATCH_EXTRA
  STA BUF_LEN16
  LDA BUF_LEN16+1
  SBC #0
  STA BUF_LEN16+1
  CLC
  ADC16 BUF_PTR16, BUF_LEN16, BUF_PTR16
  JMP paste_find_pos

.multiline:
  ; Adjust marks for inserted lines
  JSR paste_mark_prefix
  JSR mark_adjust_col

; Shared multiline char-paste finish (below path JMPs here too)
paste_finish:
  ; Skip cursor row in scroll region (save/restore BUF_PTR16 across buf_get_line_len)
  PUSH16 BUF_PTR16
  JSR file_line_rows
  STA PREV_LINE_ROWS
  POP16 BUF_PTR16
  LDA #$09
  STA RENDER_FLAG            ; Line-insert scroll, skip cursor row
  ; INSERT_LINE_COUNT = new_lines + 1 (for split cursor line)
  LDA BUF_TEMP16
  CLC
  ADC #1
  STA INSERT_LINE_COUNT
  ; Cursor at first pasted byte (BUF_PTR16 = insertion point)

paste_find_pos:
  JSR find_line_for_ptr      ; sets FILE_LINE16, CURSOR_COL16
  JSR clamp_cursor_col
  LDA #$FF
  STA MODIFIED
  CLC
  RTS

paste_shift_fail:
  POP16 BUF_PTR16            ; Clean up stack
  POP16 BUF_LEN16
  JSR show_buffer_full_msg
  SEC
  RTS

; Shared multiline paste mark-adjust prefix:
; BUF_TEMP16 = lines inserted, A/X = FILE_LINE16, carry clear
paste_mark_prefix:
  SEC
  SBC16 LINE_COUNT16, COUNT16, BUF_TEMP16
  LDAX16 FILE_LINE16
  CLC
  RTS

; Interleaved fill for single-line char paste above
; Writes iterative-correct pattern into gap:
;   (C-1) full copies, (E+1) prefixes [0..S-2], (E+1) last bytes [S-1]
; Input: BUF_PTR16 = write position (gap start)
;        NORMAL_TEMP = total count N, BATCH_EXTRA = extras E
;        YANK_SIZE16 = single yank size S (low byte, assumed < 256)
; Clobbers: A, X, Y, NORMAL_TEMP
interleaved_fill:
  ; Phase 1: (C-1) full copies where C = N - E
  LDA NORMAL_TEMP
  SEC
  SBC BATCH_EXTRA
  SBC #1                     ; A = C - 1
  BEQ .phase2
  TAX                        ; X = loop counter

.full_loop:
  LDY #0
.full_byte:
  LDA YANK_BUF,Y
  STA (BUF_PTR16),Y
  INY
  CPY YANK_SIZE16
  BNE .full_byte
  ; Advance write ptr by S
  TYA
  CLC
  ADCA16 BUF_PTR16, BUF_PTR16
  DEX
  BNE .full_loop

.phase2:
  ; (E+1) copies of prefix (first S-1 bytes)
  LDA YANK_SIZE16
  SEC
  SBC #1                     ; A = prefix size = S - 1
  BEQ .phase3                ; S=1, no prefix to write
  STA NORMAL_TEMP            ; Repurpose NORMAL_TEMP = prefix size
  LDX BATCH_EXTRA
  INX                        ; X = E + 1

.prefix_loop:
  LDY #0
.prefix_byte:
  LDA YANK_BUF,Y
  STA (BUF_PTR16),Y
  INY
  CPY NORMAL_TEMP
  BNE .prefix_byte
  ; Advance write ptr by prefix size
  TYA
  CLC
  ADCA16 BUF_PTR16, BUF_PTR16
  DEX
  BNE .prefix_loop

.phase3:
  ; (E+1) copies of last byte yank[S-1]
  LDY YANK_SIZE16
  DEY                        ; Y = S - 1
  LDA YANK_BUF,Y             ; A = last byte
  LDX BATCH_EXTRA
  INX                        ; X = E + 1
  LDY #0
.suffix_loop:
  STA (BUF_PTR16),Y
  INY
  DEX
  BNE .suffix_loop
  RTS

; Contiguous fill: write N copies of yank buffer at BUF_PTR16
; Input: BUF_PTR16 = write position, NORMAL_TEMP = count N
; Clobbers: A, X, Y, BUF_SRC16, BUF_DST16
contiguous_fill:
  LDX NORMAL_TEMP
.loop:
  PUSH16 BUF_PTR16           ; Save write position
  CP16 BUF_PTR16, BUF_DST16  ; BUF_DST16 = write position
  SET16 YANK_BUF, BUF_SRC16
  CP16 YANK_END16, BUF_PTR16 ; BUF_PTR16 = end of yank data
  TXA
  PHA                        ; Save loop counter
  JSR mem_copy_down
  PLA
  TAX                        ; Restore loop counter
  POP16 BUF_PTR16            ; Restore write position
  ; Advance write position by single yank size
  CLC
  ADC16 BUF_PTR16, YANK_SIZE16, BUF_PTR16
  DEX
  BNE .loop
  RTS

; --- Shared r/~ echo machinery ---
; Both r and ~ modify chars in place and echo them directly so no
; repaint is needed in the common case.  Every visited char is echoed
; (changed or not) so the terminal cursor tracks the buffer position --
; skipping chars without echoing would misplace later writes.  Echo
; stops at the wrap-row boundary or on an unprintable char; the rest of
; the line is then repainted via a partial line render from that column.

; Record the span start for undo and compute the direct-echo budget
; (columns left in the cursor's wrap row).  Clobbers A, X.
echo_span_setup:
  CP16 FILE_LINE16, UNDO_LINE16
  CP16 CURSOR_COL16, UNDO_COL16
  CP16 CURSOR_COL16, DIV_INPUT16
  JSR div_mod_screen_cols_16 ; A = col % SCREEN_COLS
  STA BUF_DELTA
  LDA SCREEN_COLS
  SEC
  SBC BUF_DELTA
  STA BUF_DELTA              ; BUF_DELTA = echo budget (0 = deferred)
  LDA #0
  STA UNDO_JOIN_COUNT        ; span length
  RTS

; Echo the char at (BUF_PTR16),Y if the budget allows and it is
; printable; otherwise stop echoing and defer the rest of the line to a
; partial repaint from the cursor column.  Preserves X, Y.
echo_or_defer:
  LDA BUF_DELTA
  BEQ echo_defer
  LDA (BUF_PTR16),Y
  CMP #' '
  BCC echo_defer             ; control char: defer to renderer
  CMP #$7F
  BCS echo_defer             ; DEL/high-bit: defer to renderer
  JSR io_write
  DEC BUF_DELTA
  RTS
echo_defer:
  LDA RENDER_FLAG
  BNE .done                  ; already deferring
  LDA #1
  STA RENDER_FLAG            ; partial line repaint from this column
  CP16 CURSOR_COL16, RENDER_FROM_COL16
  LDA #0
  STA BUF_DELTA              ; no more direct echo
.done:
  RTS

; Toggle alpha case in A.  Carry set if A was alpha (and toggled).
toggle_alpha:
  CMP #'A'
  BCC .no
  CMP #$5B
  BCC .yes
  CMP #'a'
  BCC .no
  CMP #$7B
  BCS .no
.yes:
  EOR #$20
  SEC
  RTS
.no:
  CLC
  RTS

; --- Toggle case (~) ---
normal_toggle_case:
  JSR undo_clear
  JSR get_batched_count      ; X = count + pending, BUF_DELTA = count
  ; Batched pending keys merge execution, but undo must behave as if
  ; the keys ran separately: it covers only the last ~ keystroke.
  TXA
  SEC
  SBC BUF_DELTA
  STA BUF_LEN16              ; nonzero = batched
  STX NORMAL_TEMP
  JSR echo_span_setup
  LDX NORMAL_TEMP

.tilde_loop:
  STX NORMAL_TEMP
  JSR check_cursor_in_line
  BCS .tilde_done

  JSR get_cursor_buf_ptr
  LDY #0
  INC UNDO_JOIN_COUNT
  ; Track the last visited char for batched undo grouping
  CP16 CURSOR_COL16, UNDO_PASTE_COUNT16
  LDA #0
  STA SHIFT_MODE             ; last-char-toggled flag
  LDA (BUF_PTR16),Y
  JSR toggle_alpha
  BCC .tilde_echo            ; not alpha: echo as-is
  STA (BUF_PTR16),Y
  LDA #$FF
  STA SHIFT_MODE
  STA MODIFIED
  LDA #UNDO_TILDE
  STA UNDO_TYPE

.tilde_echo:
  JSR echo_or_defer

.tilde_advance:
  SEC
  SBCI16 LINE_LEN16, 1, BUF_TEMP16
  CMP16 CURSOR_COL16, BUF_TEMP16
  BCS .tilde_done            ; at end of line, stop
  JSR inc_cursor_col

.tilde_next:
  LDX NORMAL_TEMP
  DEX
  BNE .tilde_loop

.tilde_done:
  LDA UNDO_TYPE
  BEQ .tilde_end             ; nothing toggled: undo stays clear
  LDA BUF_LEN16
  BEQ .tilde_end             ; not batched: span already correct
  ; Batched: undo only the last ~ (one char at the last visited col)
  LDA SHIFT_MODE
  BEQ .tilde_clear           ; last ~ toggled nothing: nothing to undo
  CP16 UNDO_PASTE_COUNT16, UNDO_COL16
  LDA #1
  STA UNDO_JOIN_COUNT
  JMP .tilde_end
.tilde_clear:
  JSR undo_clear
.tilde_end:
  JMP clear_count

; --- Join lines (J) ---
normal_join_lines:
  JSR undo_clear
  JSR get_batched_count

  ; Detect batching: BUF_DELTA = count prefix, X = total (count + pending)
  ; If X > BUF_DELTA, there are pending keys (batching)
  TXA
  SEC
  SBC BUF_DELTA              ; A = pending count
  STA UNDO_COL16             ; Repurpose: nonzero = batching

  ; Adjust for explicit count: NJ joins N-1 lines
  LDA COUNT16
  ORA COUNT16 + 1
  BEQ .join_start
  DEX
  BNE .join_start
  JMP .join_done

.join_start:
  STX NORMAL_TEMP            ; NORMAL_TEMP = number of joins to do

  ; Clamp to available lines: can join at most LINE_COUNT16 - FILE_LINE16 - 1
  SEC
  SBC16 LINE_COUNT16, FILE_LINE16, BUF_TEMP16
  DEC16 BUF_TEMP16           ; BUF_TEMP16 = available joins
  LDA BUF_TEMP16 + 1
  BNE .clamp_ok              ; > 255 available, no clamp needed
  LDA NORMAL_TEMP
  CMP BUF_TEMP16
  BCC .clamp_ok
  BEQ .clamp_ok
  LDA BUF_TEMP16
  STA NORMAL_TEMP
.clamp_ok:
  LDA NORMAL_TEMP
  BNE .join_has_work
  JMP .join_done
.join_has_work:

  ; Pre-compute old_total screen rows for displacement-based scroll
  LDA NORMAL_TEMP
  JSR compute_delete_rows_join

  ; Join column = current line length (content before is unchanged)
  JSR get_current_line_len
  STA RENDER_FROM_COL16
  STX RENDER_FROM_COL16 + 1

  ; Compute undo_count: if batching → 1, else → NORMAL_TEMP
  LDA UNDO_COL16             ; batching flag
  BEQ .no_batch
  LDA #1
  JMP .set_undo_count
.no_batch:
  LDA NORMAL_TEMP
.set_undo_count:
  STA UNDO_JOIN_COUNT

  ; Limit check: undo_count must fit in UNDO_DATA_BUF
  CMP #JOIN_UNDO_MAX + 1
  BCC .join_limit_ok
  JMP .join_limit_exceeded
.join_limit_ok:

  ; Record undo state
  CP16 FILE_LINE16, UNDO_LINE16
  LDA #UNDO_JOIN
  STA UNDO_TYPE
  LDA #0
  STA UNDO_IS_REDO

  ; Get line start for offset calculations
  JSR get_current_line_ptr        ; BUF_PTR16 = line start
  CP16 BUF_PTR16, BUF_SRC16  ; BUF_SRC16 = line start (base for offsets)

  JSR find_line_end           ; (BUF_PTR16),Y points to '\n'
  ; Set cursor to join point (end of original first line)
  STY CURSOR_COL16
  STX CURSOR_COL16 + 1
  ; Advance BUF_PTR16 by Y so BUF_PTR16 points directly to the '\n'
  TYA
  CLC
  ADCA16 BUF_PTR16, BUF_PTR16

  LDX #0                     ; X = undo buffer write index
  LDA NORMAL_TEMP
  STA BUF_TEMP               ; loop counter

  ; Single pass: scan forward replacing newlines with spaces
.join_loop:
  LDY #0
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BNE .join_next
  ; Record offset in undo buffer: offset = BUF_PTR16 - BUF_SRC16
  SEC
  LDA BUF_PTR16
  SBC BUF_SRC16
  STA UNDO_DATA_BUF,X
  LDA BUF_PTR16 + 1
  SBC BUF_SRC16 + 1
  STA UNDO_DATA_BUF + 1,X
  ; Advance write index only if not batching
  LDA UNDO_COL16             ; batching flag
  BNE .skip_advance
  INX
  INX
.skip_advance:
  ; Replace newline with space
  LDA #' '
  STA (BUF_PTR16),Y
  DEC BUF_TEMP
  BEQ .join_finish
.join_next:
  INC16 BUF_PTR16
  JMP .join_loop

.join_finish:
  ; For batched joins, cursor goes to last join point
  LDA UNDO_COL16             ; batching flag
  BEQ .cursor_done
  SEC
  SBC16 BUF_PTR16, BUF_SRC16, CURSOR_COL16
.cursor_done:
  ; Save join-point cursor for redo
  CP16 CURSOR_COL16, UNDO_COL16
  ; Single rebuild
  JSR buf_rebuild_lines

  ; Single mark adjust for all removed lines
  LDA NORMAL_TEMP
  JSR set_buf_temp16_a
  LDAX16 FILE_LINE16
  CLC
  ADC #1
  BCC .mark_adj
  INX
.mark_adj:
  JSR mark_adjust_delete

  LDA #$FF
  STA MODIFIED
  LDA #$06
  STA RENDER_FLAG        ; Signal line-delete, skip cursor row scroll
  JSR clamp_cursor_col

.join_done:
  JMP clear_count

.join_limit_exceeded:
  LDA #<str_join_limit
  LDX #>str_join_limit
  JSR show_message_ax
  JMP clear_count

str_join_limit: .asciiz "Too many lines to join"

; --- Substitute char (s) ---
normal_substitute_char:
  JSR check_cursor_in_line
  BCS sub_change_insert

  ; available = LINE_LEN16 - CURSOR_COL16
  SEC
  SBC16 LINE_LEN16, CURSOR_COL16, BUF_LEN16
  JSR get_count
  ; Clamp count to available chars
  CMP16 BUF_TEMP16, BUF_LEN16
  BCC .sub_count_ok
  BEQ .sub_count_ok
  CP16 BUF_LEN16, BUF_TEMP16
.sub_count_ok:
  CP16 BUF_TEMP16, BUF_LEN16

; Shared s/C tail: change range at cursor
sub_change_tail:
  CP16 CURSOR_COL16, RENDER_FROM_COL16
  LDA #OP_CHANGE
  JMP apply_char_operator

; Shared s/C empty-line entry to insert mode
sub_change_insert:
  JMP enter_insert_mode

; --- Change to EOL (C) ---
normal_change_to_eol:
  JSR check_cursor_in_line
  BCS sub_change_insert

  JSR get_count
  JSR compute_dollar_range
  JMP sub_change_tail

; --- Replace char (r) ---
do_replace_char:
  JSR undo_clear
  JSR get_count
  JSR echo_span_setup
  ; Count, clamped to 255 (replacement span is recorded in one page)
  LDX BUF_TEMP16
  LDA BUF_TEMP16 + 1
  BEQ .replace_loop
  LDX #$FF

.replace_loop:
  STX NORMAL_TEMP
  JSR check_cursor_in_line
  BCS .replace_done

  JSR get_cursor_buf_ptr
  LDY #0
  ; Save the original char for undo
  LDA (BUF_PTR16),Y
  LDX UNDO_JOIN_COUNT
  STA UNDO_DATA_BUF,X
  INC UNDO_JOIN_COUNT
  ; Store the replacement, echo it or defer
  LDA BUF_TEMP
  STA (BUF_PTR16),Y
  JSR echo_or_defer
  LDA #$FF
  STA MODIFIED
  LDX NORMAL_TEMP
  DEX
  BEQ .replace_done
  JSR inc_cursor_col
  JMP .replace_loop

.replace_done:
  ; Finalize undo record
  LDA UNDO_JOIN_COUNT
  BEQ .replace_no_undo
  LDA #UNDO_REPLACE
  STA UNDO_TYPE
  LDA BUF_TEMP
  STA UNDO_PASTE_COUNT16     ; replacement char (for redo)
.replace_no_undo:
  JMP clear_count

; --- Change line (cc) ---
; Yank line(s), delete, insert newline, enter insert at col 0.
; S = substitute line (alias for cc with count=1)
normal_substitute_line:
  JSR get_count
  JMP cc_have_count

do_cc:
  JSR get_count
cc_have_count:
  ; Pre-compute screen rows for displacement-based scroll
  JSR compute_delete_rows_temp16
  JSR yank_delete_current_lines
  BCS .cc_overflow
  ; Check if current line is already empty (from buf_delete_lines empty handling)
  JSR get_line_len_z
  BEQ .cc_already_empty

  ; Insert a blank line at FILE_LINE16
  JSR get_current_line_ptr       ; BUF_PTR16 = start of current line
  LDA #'\n'
  JSR buf_insert_char
  BCS .cc_buf_full
  JSR buf_rebuild_lines

  ; Adjust marks for inserted line
  LDAX16 FILE_LINE16
  JSR mark_insert_one
  JSR undo_record_cc         ; Upgrade line-delete undo to cc type (blank inserted)
  LDA #$06
  JMP .cc_set_render

.cc_already_empty:
  ; No blank inserted - next line was already empty.
  ; Use $02 (standard delete-scroll) instead of $06 (displacement-based)
  ; because displacement=0 would cause $06 to skip the scroll.
  LDA #$02
.cc_set_render:
  STA RENDER_FLAG
  LDA #0
  STA_LH16 CURSOR_COL16
  LDA #$FF
  STA MODIFIED
  JMP enter_insert_mode

.cc_overflow:
  JMP show_yank_overflow

.cc_buf_full:
  JSR show_buffer_full_msg
  JMP clear_count
