; Normal mode editing commands - paste, toggle case, join, substitute,
; replace char, change line (>> <<, word and dollar operators are in
; normal_shift.asm)

; --- Paste ---

; Shared paste prologue: record undo position, get the paste count plus
; the extra p/P keys already typed ahead (BUF_TEMP = the key, set by
; dispatch).  paste_prologue_c with C = 1 takes no typed-ahead keys: p of
; a multi-line yank, where each p pastes inside the copy before (after
; its first line or char, where that p left the cursor), not after it
; Output: BUF_TEMP16 = count + extras, BATCH_EXTRA = extras,
;         UNDO_LINE16/UNDO_COL16/UNDO_PASTE_COUNT16 recorded
paste_prologue:
  CLC
paste_prologue_c:
  JSR undo_record_pos
  JSR get_count              ; BUF_TEMP16 = count (both keep the carry)
  BCS .no_batch
  JSR count_pending_key      ; X = pending matching keys
  STX BATCH_EXTRA
  TXA
  ADDA16 BUF_TEMP16
.no_batch:
  CP16 BUF_TEMP16, UNDO_PASTE_COUNT16
  RTS

normal_paste_below:
  JSR undo_clear
  LDA YANK_TYPE
  BNE char_paste_below
  LDA YANK_LINES16
  EOR #1
  ORA YANK_LINES16 + 1
  CMP #1                     ; C = 1: a multi-line yank, no batching
  JSR paste_prologue_c
  JSR yank_paste_below_n
  BCS paste_done
  JSR paste_adjust_marks
  LDA #UNDO_LINE_PASTE_BELOW
  STA UNDO_TYPE
  ; Cursor: yank_paste_below_n does INC16 once; add extras for iterative
  ; semantics (a one-line yank: each typed-ahead p moves down one line)
  LDA BATCH_EXTRA
  BEQ .paste_below_scroll
  ; Batched paste: cursor adjustment shifts FILE_LINE16 past first pasted
  ; lines, so scroll walk would start at wrong position.
  ADDA16 FILE_LINE16
  ; Batching must not widen undo: record only the last p, typed on the
  ; line above the cursor, at the column the p before left it
  JSR undo_record_pos
  DEC16 UNDO_LINE16
  JMP paste_undo_one              ; RENDER_FLAG stays 0 → full repaint
.paste_below_scroll:
  LDA #RF_INS                   ; Signal line-insert for scroll optimization
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
  LDA #RF_INS
  STA RENDER_FLAG        ; Signal line-insert for scroll optimization
  ; No cursor adjustment - yank_paste_above_n doesn't change FILE_LINE16
  ; Batching must not widen undo: the last pasted copy sits at the top
  ; of the block (paste-above prepends), where the P before left the
  ; cursor
  BNE paste_batched_undo     ; Always (A = $03)

; Character paste above (before cursor).  Each P leaves the cursor where
; the next one pastes, on the last pasted char (the first of a multi-line
; yank), except when that first char is a newline: it lies past the line
; end, and the cursor steps back a column.  Such P keys run one at a time
; (C = 1 for a first char up to '\n', so for a tab too, only slower).
char_paste_above:
  LDA #'\n'
  CMP YANK_BUF               ; C = 1: the yank starts with a newline
  JSR paste_prologue_c
  JSR do_char_paste_above
  BCS paste_done
  LDA #UNDO_CHAR_PASTE_ABOVE
  STA UNDO_TYPE
  ; Batching must not widen undo: a multi-line yank's last copy sits
  ; first (paste-above inserts before the cursor), at the cursor
  BIT NORMAL_TEMP
  BPL char_paste_last_copy
; Batched P: undo takes back the last P's copy, pasted at the cursor
; (line and column) that the P before it left
paste_batched_undo:
  LDA BATCH_EXTRA
  BEQ paste_done
  JSR undo_record_pos
; Batching must not widen undo: record only the last pasted copy
paste_undo_one:
  SET16 $0001, UNDO_PASTE_COUNT16
paste_done:
  JMP clear_count

; Character paste below (after cursor)
; For non-empty lines, inserts after cursor char; for empty lines, inserts at line start
char_paste_below:
  JSR yank_count_newlines    ; C = 1: a multi-line yank, no batching
  JSR paste_prologue_c       ; UNDO_COL16 = cursor column (0 on an empty line)
  ; Insertion column for undo: cursor + 1 (non-empty line) or 0 (empty)
  JSR get_line_len_z
  BEQ .cpb_paste
  INC16 UNDO_COL16
.cpb_paste:
  JSR do_char_paste_below
  BCS paste_done
  LDA #UNDO_CHAR_PASTE_BELOW
  STA UNDO_TYPE
  ; fall through (only a single-line yank batches p)

; Batched single-line char paste (p or P): record only the last copy.
; Each key leaves the cursor on its last pasted char, so the last copy
; ends at the cursor: UNDO_COL16 = cursor + 1 - yank size
char_paste_last_copy:
  LDA BATCH_EXTRA
  BEQ paste_done
  SEC
  SBC16 CURSOR_COL16, YANK_SIZE16, UNDO_COL16
  INC16 UNDO_COL16
  JMP paste_undo_one

; Char paste modes (A for do_char_paste): bit 7 set = not p, bit 6 set = P,
; bit 5 set = the caller places the cursor itself (no clamp)
CP_BELOW = $00               ; p
CP_AT    = $A0               ; Undo of a char delete
CP_ABOVE = $C0               ; P

; Core char paste below (p, and its redo): paste BUF_TEMP16 copies after
; the cursor char, or at the cursor (column 0) on an empty line.
; Returns carry set = failed (cursor unchanged), as do_char_paste
do_char_paste_below:
  JSR get_line_len_z
  BEQ .at_cursor             ; Empty line
  JSR inc_cursor_col         ; Insertion column = cursor + 1
  JSR .at_cursor
  BCC .done
  JMP dec_cursor_col         ; Failed: cursor back on its char (C stays set)
.at_cursor:
  LDA #CP_BELOW
  BEQ do_char_paste          ; Always
.done:
  RTS

; Core char paste above (P, and its redo): paste BUF_TEMP16 copies at the
; cursor.  Input: BATCH_EXTRA = extras (batched P keys)
do_char_paste_above:
  LDA #CP_ABOVE
  ; fall through

; Char paste core: BUF_TEMP16 copies of the char yank at column CURSOR_COL16
; of the cursor line.  A = mode:
;   CP_BELOW: p.  Renders from one column left of the insertion column
;             ($FFFF, the whole line, at column 0); a multi-line paste
;             shifts the marks from the next line on
;   CP_AT:    renders from the insertion column; marks by mark_adjust_col;
;             the cursor is left unclamped (the caller restores it)
;   CP_ABOVE: as CP_AT, but a single-line yank fills with
;             interleaved_fill (the cursor ends BATCH_EXTRA chars before
;             the last pasted char, as separate P keys leave it)
; Output: cursor on the last pasted char (single-line yank) or the first
; (multi-line), clamped unless CP_AT; NORMAL_TEMP bit 7 = multi-line yank;
; MODIFIED set.
; Returns carry set = failed (empty yank, or the text buffer or the line
; table full: text unchanged)
do_char_paste:
  STA NORMAL_TEMP
  JSR yank_count_newlines    ; YANK_LINES16 = lines per copy, for the check
  ROR NORMAL_TEMP            ; Bit 7 = multi-line, 6 = not p, 5 = P, 4 = no clamp
  JSR yank_paste_setup       ; BUF_LEN16 = total size, YANK_SIZE16 = single size
  BCS .ret
  ; RENDER_FROM_COL16 = insertion column, minus 1 for p
  LDA NORMAL_TEMP
  ASL
  ASL                        ; C = 1 unless p
  LDA CURSOR_COL16
  SBC #0
  STA RENDER_FROM_COL16
  LDA CURSOR_COL16 + 1
  SBC #0
  STA RENDER_FROM_COL16 + 1
  JSR get_cursor_buf_ptr     ; BUF_PTR16 = insertion point
  CP16 LINE_COUNT16, COUNT16 ; Line count before, for mark adjustment
  LDA NORMAL_TEMP
  AND #$A0
  CMP #$20
  BEQ .interleaved           ; P of a single-line yank
  JSR yank_paste_core        ; Shift, copy, rebuild ("Buffer full" if no room)
  BCC .placed
.ret:
  RTS
.interleaved:
  JSR buf_shift_right_16
  BCC .shifted
  JMP paste_full             ; "Buffer full", carry set
.shifted:
  ; The cursor ends BATCH_EXTRA chars early (BUF_LEN16 is only needed for
  ; the cursor from here on)
  LDA BUF_LEN16
  SEC
  SBC BATCH_EXTRA
  STA BUF_LEN16
  BCS .fill
  DEC BUF_LEN16 + 1
.fill:
  JSR interleaved_fill
  JSR buf_rebuild_lines
.placed:
  JSR set_modified
  BIT NORMAL_TEMP
  BMI .multiline
  ; Single-line: cursor on the last pasted char
  CLC
  ADC16 CURSOR_COL16, BUF_LEN16, CURSOR_COL16
  JSR dec_cursor_col
  JMP .clamp
.multiline:
  ; Marks for the inserted lines (BUF_TEMP16 = their count)
  SEC
  SBC16 LINE_COUNT16, COUNT16, BUF_TEMP16
  LDAX16 FILE_LINE16
  CLC
  BIT NORMAL_TEMP
  BVS .by_col
  ; p: from the next line on, even at column 0 of an empty line
  ADC #1
  BCC .next_line
  INX
.next_line:
  JSR mark_adjust_insert
  JMP .scroll
.by_col:
  JSR mark_adjust_col        ; At the insertion column (the cursor)
.scroll:
  ; Line-insert scroll below the split line
  LDA #RF_SPLIT
  STA RENDER_FLAG
  LDX BUF_TEMP16
  INX
  STX INSERT_LINE_COUNT      ; New lines + 1 (the split cursor line)
.clamp:
  LDA NORMAL_TEMP
  AND #$10
  BNE .done                  ; CP_AT: the caller restores the cursor
  JSR clamp_cursor_col
.done:
  CLC
  RTS

; Interleaved fill for single-line char paste above
; Writes iterative-correct pattern into gap:
;   (C-1) full copies, (E+1) prefixes [0..S-2], (E+1) last bytes [S-1]
; Input: BUF_PTR16 = write position (gap start)
;        BUF_TEMP16 = total count N (C = N - E), BATCH_EXTRA = extras E
;        YANK_SIZE16 = single yank size S (16-bit)
; Clobbers: A, X, Y, BUF_TEMP16, BUF_SRC16, BUF_DST16
interleaved_fill:
  ; Phase 1: (C-1) full copies (carry clear: N - E - 1)
  CLC
  SBC16_8 BUF_TEMP16, BATCH_EXTRA, BUF_TEMP16
  JSR yank_copy_n            ; (Exits with BUF_TEMP16 = 0)

  ; Phase 2: (E+1) copies of the prefix: the yank without its last byte,
  ; which YANK_END16 then points at (restored below)
  DEC16 YANK_END16
  DEC16 YANK_SIZE16
  LDX BATCH_EXTRA
  INX                        ; X = E + 1 (yank_copy_n keeps it)
  STX BUF_TEMP16             ; BUF_TEMP16 = E + 1
  JSR yank_copy_n

  ; Phase 3: (E+1) copies of the last byte yank[S-1]
  LDY #0
  LDA (YANK_END16),Y         ; A = last byte
.suffix_loop:
  STA (BUF_PTR16),Y
  INY
  DEX
  BNE .suffix_loop
  INC16 YANK_END16
  INC16 YANK_SIZE16
  RTS

; --- Shared r/~ echo machinery ---
; Both r and ~ modify chars in place and echo them directly so no
; repaint is needed in the common case.  Every visited char is echoed
; (changed or not) so the terminal cursor tracks the buffer position --
; skipping chars without echoing would misplace later writes.  Echo
; stops at the wrap-row boundary or on an unprintable char; the rest of
; the line is then repainted via a partial line render from that column.

; Start a new r/~ undo record at the cursor (it replaces the previous
; one) and compute the direct-echo budget (columns left in the cursor's
; wrap row).  Clobbers A, X.
echo_span_setup:
  JSR undo_record_pos
  CP16 CURSOR_COL16, DIV_INPUT16
  JSR div_mod_screen_cols_16 ; A = col % SCREEN_COLS
  EOR #$FF
  SEC
  ADC SCREEN_COLS            ; SCREEN_COLS - A
  STA BUF_DELTA              ; BUF_DELTA = echo budget (0 = deferred)
  JSR undo_clear             ; A = 0
  STA UNDO_SPAN_LEN          ; span length
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
  LDA #RF_LINE
  STA RENDER_FLAG            ; partial line repaint from this column
  JSR set_render_from_cursor
  LDA #0
  STA BUF_DELTA              ; no more direct echo
.done:
  RTS

; Toggle alpha case in A.  Carry clear if A was alpha (and toggled),
; set if not (A unchanged).  Preserves X, Y.
toggle_alpha:
  PHA
  ORA #$20                   ; Fold case: alpha iff now 'a'..'z'
  SEC
  SBC #'a'
  CMP #'z' - 'a' + 1         ; C = 0: alpha
  PLA
  BCS .done
  EOR #$20
.done:
  RTS

; --- Toggle case (~) ---
; Scratch while ~ runs (aliases; the record is UNDO_COL16/UNDO_SPAN_LEN)
TILDE_LAST_COL16 = UNDO_PASTE_COUNT16 ; column of the last visited char
TILDE_TOGGLED    = SHIFT_MODE         ; nonzero: that char was toggled

; On an empty line ~ fails and leaves the previous undo intact.
normal_toggle_case:
  JSR check_cursor_in_line
  BCS .tilde_end
  ; Batched pending keys merge execution, but undo must behave as if
  ; the keys ran separately: it covers only the last ~ keystroke.
  JSR get_batched_count      ; X = count + pending, BATCH_EXTRA = pending
  STX NORMAL_TEMP            ; loop counter
  JSR echo_span_setup

.tilde_loop:
  JSR check_cursor_in_line
  BCS .tilde_line_end        ; Past the last char
.tilde_toggle:
  JSR get_cursor_buf_ptr
  LDY #0
  INC UNDO_SPAN_LEN
  ; Track the last visited char for batched undo grouping
  CP16 CURSOR_COL16, TILDE_LAST_COL16
  LDA #0
  STA TILDE_TOGGLED             ; last-char-toggled flag
  LDA (BUF_PTR16),Y
  JSR toggle_alpha
  BCS .tilde_echo            ; not alpha: echo as-is
  STA (BUF_PTR16),Y
  LDA #$FF
  STA TILDE_TOGGLED
  STA MODIFIED
  LDA #UNDO_TILDE
  STA UNDO_TYPE

.tilde_echo:
  JSR echo_or_defer
  JSR inc_cursor_col
  DEC NORMAL_TEMP
  BNE .tilde_loop

.tilde_line_end:
  JSR clamp_cursor_col       ; Back onto the last char
  ; One at a time, the cursor stays on the last char and each ~ left
  ; over toggles it again (a count stops at the line end): the parity of
  ; min(presses left, typed-ahead presses) decides one more toggle
  LDA NORMAL_TEMP
  CMP BATCH_EXTRA
  BCC .left_ok
  LDA BATCH_EXTRA
.left_ok:
  LSR
  BCC .tilde_done            ; Even: no net change
  LDA #1
  STA NORMAL_TEMP            ; One more pass, which ends the loop
  LSR                        ; A = 0
  STA BUF_DELTA              ; No direct echo: the char's first echo
  BEQ .tilde_toggle          ; went out, so the line repaints (always)

.tilde_done:
  LDA UNDO_TYPE
  BEQ .tilde_end             ; nothing toggled: undo stays clear
  LDA BATCH_EXTRA
  BEQ .tilde_end             ; not batched: span already correct
  ; Batched: undo only the last ~ (one char at the last visited col)
  LDA TILDE_TOGGLED
  BEQ .tilde_clear           ; last ~ toggled nothing: nothing to undo
  CP16 TILDE_LAST_COL16, UNDO_COL16
  LDA #1
  STA UNDO_SPAN_LEN
  JMP .tilde_end
.tilde_clear:
  JSR undo_clear
.tilde_end:
  JMP clear_count

; --- Join lines (J) ---
; NJ joins N-1 lines, J and 1J one, and each typed-ahead J one more (undo
; then covers the last J's join).  The count's joins, at most the lines
; below, must fit the undo record: that is checked first, before any
; other work and before the typed-ahead J's are taken, which then run
; one at a time (the first dismisses the message), as when typed singly.
; A J with nothing to join, or too much, fails and leaves the previous
; undo intact: the record is written only once the join is sure
normal_join_lines:
  JSR get_count_x            ; X = count (256 or more: 255, over the limit)
  DEX
  BNE .joins
  INX                        ; J and 1J: one join
.joins:
  ; The lines below: LINE_COUNT16 - FILE_LINE16 - 1
  CLC                        ; (the borrow subtracts the 1)
  SBC16 LINE_COUNT16, FILE_LINE16, BUF_TEMP16
  JSR .clamp_joins
  TXA
  BEQ .join_done             ; The last line: nothing to join
  CPX #JOIN_UNDO_MAX + 1
  BCC .join_limit_ok
  LDA #<str_join_limit
  LDX #>str_join_limit
  JSR show_message_ax
.join_done:
  JMP clear_count

; X = min(X, BUF_TEMP16)
.clamp_joins:
  LDA BUF_TEMP16 + 1
  BNE .clamped
  CPX BUF_TEMP16
  BCC .clamped
  LDX BUF_TEMP16
.clamped:
  RTS

.join_limit_ok:
  STX NORMAL_TEMP
  JSR count_pending_key      ; X = typed-ahead J's (BUF_TEMP = 'J')
  STX BATCH_EXTRA
  TXA
  CLC
  ADC NORMAL_TEMP            ; (at most JOIN_UNDO_MAX + BATCH_MAX)
  TAX
  JSR .clamp_joins
  CPX NORMAL_TEMP
  BNE .joins_set
  ; No typed-ahead J joined a line: they all failed, as when typed
  ; singly, so the count's join stays the one to undo
  LDA #0
  STA BATCH_EXTRA
.joins_set:
  STX NORMAL_TEMP            ; NORMAL_TEMP = number of joins to do

  ; Pre-compute old_total screen rows for displacement-based scroll
  TXA
  JSR compute_delete_rows_join

  ; Undo count: batched, 1 (the last J), else all of the joins
  LDA NORMAL_TEMP
  LDX BATCH_EXTRA            ; batching flag
  BEQ .set_undo_count
  LDA #1
.set_undo_count:
  STA UNDO_JOIN_COUNT

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
  ; The content before the first join point (the end of the first line)
  ; is unchanged, so the line repaints from there
  STY RENDER_FROM_COL16
  STX RENDER_FROM_COL16 + 1
  ; Advance BUF_PTR16 by Y so BUF_PTR16 points directly to the '\n'
  TYA
  JSR ptr_add_a

  LDX #0                     ; X = undo buffer write index
  LDA NORMAL_TEMP
  STA BUF_TEMP               ; loop counter

  ; Single pass: scan forward replacing newlines with spaces
.join_loop:
  LDY #0
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BNE .join_next
  ; Undo puts the cursor back where the (last) J was typed: the cursor's
  ; column before the first join, or for batched J's (whose write index
  ; stays 0) before the last one, the previous join point
  TXA
  BNE .col_saved
  CP16 CURSOR_COL16, UNDO_JOIN_COL16
.col_saved:
  ; Record offset in undo buffer: offset = BUF_PTR16 - BUF_SRC16, the
  ; join point, where the cursor goes (the last one, as in vim)
  SEC
  LDA BUF_PTR16
  SBC BUF_SRC16
  STA UNDO_DATA_BUF,X
  STA CURSOR_COL16
  LDA BUF_PTR16 + 1
  SBC BUF_SRC16 + 1
  STA UNDO_DATA_BUF + 1,X
  STA CURSOR_COL16 + 1
  ; Advance write index only if not batching
  LDA BATCH_EXTRA            ; batching flag
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
  ; Save join-point cursor for redo
  CP16 CURSOR_COL16, UNDO_COL16
  ; Single rebuild
  JSR buf_rebuild_lines

  ; Single mark adjust for all removed lines
  LDA NORMAL_TEMP
  JSR mark_args_next_line
  JSR mark_adjust_delete

  LDA #RF_JOIN           ; Signal line-delete, skip cursor row scroll
  JSR set_modified_render
  JMP clamp_and_clear_count

str_join_limit: .asciiz "Too many lines to join"

; --- Substitute char (s) ---
normal_substitute_char:
  JSR check_cursor_in_line
  BCS sub_change_insert

  ; available = LINE_LEN16 - CURSOR_COL16
  SEC
  SBC16 LINE_LEN16, CURSOR_COL16, BUF_LEN16
  JSR get_count
  ; BUF_LEN16 = min(count, available chars)
  CMP16 BUF_TEMP16, BUF_LEN16
  BCS .sub_count_ok
  CP16 BUF_TEMP16, BUF_LEN16
.sub_count_ok:

; Shared s/C tail: change range at cursor
sub_change_tail:
  JSR set_render_from_cursor
  LDA #OP_CHANGE
  JMP apply_char_operator

; Shared s/C empty-line entry to insert mode
sub_change_insert:
  JMP enter_insert_mode

; --- Change to EOL (C) ---
normal_change_to_eol:
  JSR dollar_range_setup
  BCS sub_change_insert
  JMP sub_change_tail

; --- Replace char (r) ---
; The replacement must type text: printable or Tab.  Enter and Ctrl-J
; replace the N chars with one line break instead, as in vim, which also
; leaves the line alone when fewer than N are left: the loop stores them
; as KEY_ENTER (a placeholder, never a replacement char), then
; replace_split makes the break.  Any other key (arrows and other KEY_*
; codes, BS, $00 for non-ASCII) cancels r like Esc. ($7F never arrives:
; read_key maps it to KEY_BS.)
do_replace_char:
  LDA BUF_TEMP
  CMP #'\n'
  BEQ .replace_nl            ; Ctrl-J is Enter
  CMP #KEY_ENTER
  BEQ .replace_nl
  TAX                        ; N = a KEY_* code
  BMI .replace_no_undo
  CMP #' '
  BCS .replace_key_ok
  CMP #KEY_TAB
  BNE .replace_no_undo
.replace_key_ok:
  ; On an empty line r fails and leaves the previous undo intact
  JSR check_cursor_in_line
  BCS .replace_no_undo
  JSR echo_span_setup
  ; Count, capped at 255 (replacement span is recorded in one page)
  JSR get_count_x
  STX NORMAL_TEMP            ; loop counter

.replace_loop:
  JSR check_cursor_in_line
  BCS .replace_done

  JSR get_cursor_buf_ptr
  LDY #0
  ; Save the original char for undo
  LDA (BUF_PTR16),Y
  LDX UNDO_SPAN_LEN
  STA UNDO_DATA_BUF,X
  INC UNDO_SPAN_LEN
  ; Store the replacement, echo it or defer
  LDA BUF_TEMP
  STA (BUF_PTR16),Y
  JSR echo_or_defer
  LDA #$FF
  STA MODIFIED
  DEC NORMAL_TEMP
  BEQ .replace_done
  JSR inc_cursor_col
  JMP .replace_loop

.replace_done:
  ; Finalize undo record (the span holds a char at least)
  LDA #UNDO_REPLACE
  STA UNDO_TYPE
  LDA BUF_TEMP
  STA UNDO_REPL_CHAR     ; replacement char (for redo)
  CMP #KEY_ENTER
  BEQ replace_split
.replace_no_undo:
  ; A count past the line end stepped the cursor one past the last
  ; replaced char: clamp it back onto that char
  JMP clamp_and_clear_count

.replace_nl:
  LDA #KEY_ENTER
  STA BUF_TEMP
  ; The N chars must be in the line, and a line more must fit
  JSR get_count              ; BUF_TEMP16 = N
  JSR get_line_len_z
  SEC
  LDA LINE_LEN16
  SBC CURSOR_COL16
  TAX
  LDA LINE_LEN16 + 1
  SBC CURSOR_COL16 + 1       ; A/X = the chars left
  CPX BUF_TEMP16
  SBC BUF_TEMP16 + 1
  BCC .replace_no_undo       ; Fewer than N
  LDA #1
  LDX #0
  JSR check_line_room
  BCC .replace_key_ok
  JMP open_full              ; "Buffer full"

; r<Enter> and its redo: the UNDO_SPAN_LEN chars from UNDO_LINE16/
; UNDO_COL16 become one line break, as vim's 5r<CR> does.  Their last
; char turns into the break and the ones before it go; the marks below
; the line move down, and the cursor goes to the start of the new line.
; The render is an Enter batch's ($05), from the first replaced char.
replace_split:
  JSR undo_span_setup        ; Cursor and BUF_PTR16 to the span start
  LDA #'\n'
  JSR replace_extra_len      ; Y = N - 1
  STA (BUF_PTR16),Y
  BEQ .split                 ; N = 1: in place
  JSR buf_shift_left_16
.split:
  JSR buf_rebuild_lines
  LDA #1
  JSR mark_args_next_line    ; A/X = the new line
  STAX16 FILE_LINE16
  JSR mark_adjust_insert
  LDA #RF_ENTER
  JSR undo_opened_finish     ; Column 0, redone, modified
  JMP clear_count

; BUF_LEN16 = Y = UNDO_SPAN_LEN - 1: the chars r<Enter> removes besides
; the one that becomes its line break (Z = there are none).  Preserves A
replace_extra_len:
  LDX #0
  STX BUF_LEN16 + 1
  LDY UNDO_SPAN_LEN
  DEY
  STY BUF_LEN16
  RTS

; --- Change line (cc, and S, which dispatches here too) ---
; Yank line(s), replace them with one empty line, enter insert at col 0.
do_cc:
  JSR get_count_clamp_lines  ; BUF_TEMP16 = count, at most the lines left
  JSR yank_current_lines
  BCS .cc_overflow
  ; Record undo: u removes the empty line and pastes the lines back
  SEC
  ROR UNDO_EMPTY_LINE
  LDA #UNDO_CC
  JSR undo_rec_set
  JSR cc_clear_lines
  JMP enter_insert_mode

.cc_overflow:
  JMP show_yank_overflow

; Replace BUF_TEMP16 lines at FILE_LINE16 with one empty line and put the
; cursor on it, for a displacement-based scroll (cc/S and their redo).
; Marks on the lines are unset, marks below them move up N-1 lines.
; Clobbers A, X, Y
cc_clear_lines:
  JSR compute_delete_rows_temp16 ; The lines' rows before
  LDAX16 FILE_LINE16
  JSR mark_adjust_delete
  LDAX16 FILE_LINE16
  JSR buf_clear_lines
  LDAX16 FILE_LINE16
  JSR mark_insert_one
  LDA #RF_JOIN
  JMP undo_opened_finish     ; Cursor to col 0, modified
