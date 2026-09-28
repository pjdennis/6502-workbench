; Normal mode editing commands - paste, toggle case, join, substitute,
; replace char, change line, and the word operators' linewise rules
; (>> <<, word and dollar operators are in normal_shift.asm)

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
  JSR add_x_temp16
.no_batch:
  CP16 BUF_TEMP16, UNDO_PASTE_COUNT16
  RTS

normal_paste_above:
  JSR undo_clear
  LDA YANK_TYPE
  BNE char_paste_above
  JSR paste_prologue
  JSR yank_paste_above_n
  BCS paste_fail
  JSR paste_adjust_marks
  LDA #RF_INS
  STA RENDER_FLAG        ; Signal line-insert for scroll optimization
  ; No cursor adjustment - yank_paste_above_n doesn't change FILE_LINE16
  ; Batching must not widen undo: the last pasted copy sits at the top
  ; of the block (paste-above prepends), where the P before left the
  ; cursor
  LDA #UNDO_LINE_PASTE_ABOVE
  SEC
  BCS paste_undo_type        ; Always

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
  BCS paste_fail
  ; Batching must not widen undo: a multi-line yank's last copy sits
  ; first (paste-above inserts before the cursor), at the cursor
  LDA NORMAL_TEMP
  ASL                        ; C = multi-line yank
  LDA #UNDO_CHAR_PASTE_ABOVE
  BNE paste_undo_type        ; Always

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
  BCS paste_fail
  LDA #UNDO_CHAR_PASTE_BELOW ; (C = 0: only a single-line yank batches p)
  ; fall through

; Record the paste's undo type (A).  Batching must not widen undo: after
; typed-ahead keys it takes back only the last key's copy, pasted where
; the key before left the cursor.  C = 0: a single-line char paste,
; where each key leaves the cursor on its last pasted char, so the last
; copy starts at cursor + 1 - yank size
paste_undo_type:
  STA UNDO_TYPE
  LDA BATCH_EXTRA
  BEQ paste_done
  JSR undo_record_pos        ; (keeps C)
  BCS paste_undo_one
  SEC
  SBC16 UNDO_COL16, YANK_SIZE16, UNDO_COL16
  INC16 UNDO_COL16
; Batching must not widen undo: record only the last pasted copy
paste_undo_one:
  SET16 $0001, UNDO_PASTE_COUNT16
paste_done:
  JMP clear_count
; A paste that fails (nothing yanked, the buffer full) is an empty
; change, as vim's (it saves undo before it finds the register empty),
; and keeps the column
paste_fail:
  JSR undo_record_empty
  JMP keep_clear_count

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
  BCS paste_fail
  JSR paste_adjust_marks
  LDA #UNDO_LINE_PASTE_BELOW
  STA UNDO_TYPE
  ; Cursor: yank_paste_below_n does INC16 once; add extras for iterative
  ; semantics (a one-line yank: each typed-ahead p moves down one line)
  LDA BATCH_EXTRA
  BEQ .paste_below_scroll
  ADDA16 FILE_LINE16
  ; Batching must not widen undo: record only the last p, typed on the
  ; line above the cursor, at the column the p before left it
  JSR undo_record_pos
  DEC16 UNDO_LINE16
  ; With no count (the copies are the keys: UNDO_PASTE_COUNT16 = extras
  ; + 1) they follow the line the cursor was on, and the cursor is on the
  ; last: drawn as an Enter batch that split that line at its end (with
  ; a count they go on past the cursor line: RENDER_FLAG stays 0, a full
  ; repaint)
  LDA UNDO_PASTE_COUNT16 + 1
  BNE .undo_one
  LDX BATCH_EXTRA
  INX
  CPX UNDO_PASTE_COUNT16
  BNE .undo_one
  LDAX16 SNAP_LINE16
  JSR buf_get_line_len
  STAX16 RENDER_FROM_COL16
  LDA #RF_ENTER
  STA RENDER_FLAG
.undo_one:
  JMP paste_undo_one
.paste_below_scroll:
  LDA #RF_INS                   ; Signal line-insert for scroll optimization
  JMP set_render_clear_count

; Char paste modes (A for do_char_paste): bit 7 set = the undo of a char
; delete (marks by column, no cursor clamp), bit 5 set = P
CP_BELOW = $00               ; p
CP_AT    = $80               ; Undo of a char delete
CP_ABOVE = $20               ; P

; Core char paste below (p, and its redo): paste BUF_TEMP16 copies after
; the cursor char, or at the cursor (column 0) on an empty line.  After
; the cursor char the line repaints from that char, where the frame
; finds the terminal's cursor: rewriting it costs less than a move (the
; ICH hint, if any, writes one more cell).
; Returns carry set = failed (cursor unchanged), as do_char_paste
do_char_paste_below:
  JSR get_line_len_z
  BEQ .at_cursor             ; Empty line
  JSR inc_cursor_col         ; Insertion column = cursor + 1
  JSR .at_cursor
  BCS .failed
  LDX SHIFT_WRITE
  INX
  BEQ .from_cursor           ; ($FF: no hint)
  STX SHIFT_WRITE
.from_cursor:
  LDA RENDER_FROM_COL16
  BNE .dec
  DEC RENDER_FROM_COL16 + 1
.dec:
  DEC RENDER_FROM_COL16      ; (C = 0: pasted)
  RTS
.failed:
  JMP dec_cursor_col         ; Cursor back on its char (C stays set)
.at_cursor:
  LDA #CP_BELOW
  BEQ do_char_paste          ; Always

; Core char paste above (P, and its redo): paste BUF_TEMP16 copies at the
; cursor.  Input: BATCH_EXTRA = extras (batched P keys)
do_char_paste_above:
  LDA #CP_ABOVE
  ; fall through

; Char paste core: BUF_TEMP16 copies of the char yank at column CURSOR_COL16
; of the cursor line, which repaints from there (with an ICH hint when
; the paste has no newline; p moves the start one left).  A = mode:
;   CP_BELOW: p.  A multi-line paste shifts the marks from the next line
;             on (those of the cursor line stay there, as in vim, even at
;             column 0)
;   CP_ABOVE: P.  Marks as p; a single-line yank fills with
;             interleaved_fill (the cursor ends BATCH_EXTRA chars before
;             the last pasted char, as separate P keys leave it)
;   CP_AT:    marks as p (the undo then puts back the marks the delete
;             moved: mark_restore); the cursor is left unclamped (the
;             caller restores it)
; Output: cursor on the last pasted char (single-line yank) or the first
; (multi-line), clamped unless CP_AT; NORMAL_TEMP bit 7 = multi-line yank;
; MODIFIED set.
; Returns carry set = failed (empty yank, or the text buffer or the line
; table full: text unchanged)
do_char_paste:
  STA NORMAL_TEMP
  JSR yank_count_newlines    ; YANK_LINES16 = lines per copy, for the check
  ROR NORMAL_TEMP            ; Bit 7 = multi-line, 6 = CP_AT, 4 = P
  JSR yank_paste_setup       ; BUF_LEN16 = total size, YANK_SIZE16 = single size
  BCS .ret
  JSR set_render_from_cursor ; The line repaints from the insertion column
  JSR get_cursor_buf_ptr     ; BUF_PTR16 = insertion point
  CP16 LINE_COUNT16, COUNT16 ; Line count before, for mark adjustment
  JSR buf_shift_right_16
  BCC .shifted
  JMP paste_full             ; "Buffer full", carry set
.ret:
  RTS
.shifted:
  LDA NORMAL_TEMP
  AND #$90
  CMP #$10
  BEQ .interleaved           ; P of a single-line yank
  JSR yank_copy_n            ; Fill the gap
  BIT NORMAL_TEMP
  BPL .placed
  JSR buf_rebuild_lines      ; A multi-line yank: its lines go in
  BCS .placed                ; Always (the rebuild returns C = 1)
.interleaved:
  ; The cursor ends BATCH_EXTRA chars early
  LDA CURSOR_COL16
  SEC
  SBC BATCH_EXTRA
  STA CURSOR_COL16
  BCS .fill
  DEC CURSOR_COL16 + 1
.fill:
  JSR interleaved_fill
.placed:
  JSR set_modified
  BIT NORMAL_TEMP
  BMI .multiline
  ; Single-line: an ICH hint, n cells written at the insertion column, if
  ; it fits SHIFT_NET's signed byte (n <= 127; a longer paste takes the
  ; row rewrite, which costs no more once n passes the row width)
  LDA BUF_LEN16 + 1
  BNE .no_hint
  LDA BUF_LEN16
  BMI .no_hint
  STA SHIFT_NET
  STA SHIFT_WRITE
.no_hint:
  ; The cursor on the last pasted char, and the lines after the cursor
  ; line move by the total (only its length changed)
  CLC
  ADC16 CURSOR_COL16, BUF_LEN16, CURSOR_COL16
  JSR dec_cursor_col
  JSR buf_adjust_lines_len
  JMP .clamp
.multiline:
  ; Marks for the inserted lines (BUF_TEMP16 = their count): from the
  ; next line on, even at column 0
  SEC
  SBC16 LINE_COUNT16, COUNT16, BUF_TEMP16
  JSR next_line_ax
  JSR mark_adjust_insert
  ; The cursor line split in lines
  LDA #RF_SPLIT
  STA RENDER_FLAG
.clamp:
  BIT NORMAL_TEMP
  BVS .done                  ; CP_AT: the caller restores the cursor
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
  JSR cursor_col_div         ; A = col % SCREEN_COLS
  EOR #$FF
  SEC
  ADC SCREEN_COLS            ; SCREEN_COLS - A
  STA BUF_DELTA              ; BUF_DELTA = echo budget (0 = deferred)
  JSR undo_clear             ; A = 0
  STA UNDO_SPAN_LEN          ; span length
  STA CUR_VALID              ; the echo moves the cursor
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
  BCS .tilde_fail            ; An empty line: ~ fails
  ; Batched pending keys merge execution, but undo must behave as if
  ; the keys ran separately: it covers only the last ~ keystroke.
  JSR get_batched_count      ; X = count + pending, BATCH_EXTRA = pending
  STX NORMAL_TEMP            ; loop counter
  JSR echo_span_setup

.tilde_start:
  ; (BUF_PTR16),Y = the char at the cursor, which the loop steps with Y
  JSR get_cursor_buf_ptr
  LDY #0

.tilde_loop:
  JSR cursor_in_line         ; (~ does not change the line's length)
  BCS .tilde_line_end        ; Past the last char
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
  INY                        ; (255 presses at most: Y wraps only as
  JSR inc_cursor_col         ; the count ends)
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
  BEQ .tilde_start           ; went out, so the line repaints (always)

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
.tilde_fail:
  JMP keep_clear_count

; --- Join lines (J) ---
; NJ joins N-1 lines, J and 1J one, and each typed-ahead J one more (undo
; then covers the last J's join).  The count's joins, at most the lines
; below, must fit the undo record: that is checked first, before any
; other work and before the typed-ahead J's are taken, which then run
; one at a time, as when typed singly.
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

  ; Record undo state (the join column goes in UNDO_COL16 at the end)
  LDA #UNDO_JOIN
  JSR undo_rec_set

  ; The content before the first join point (the end of the first line)
  ; is unchanged, so the line repaints from there
  JSR set_render_from_line_end
  ; Get line start for offset calculations
  JSR get_current_line_ptr        ; BUF_PTR16 = line start
  JSR ptr_to_src             ; BUF_SRC16 = line start (base for offsets)
  ; BUF_PTR16 = the first line's '\n'
  CLC
  ADC16 BUF_SRC16, RENDER_FROM_COL16, BUF_PTR16

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

  ; The joined lines' marks move to the cursor line, as in vim
  JSR mark_join_lines_nt

  LDA #RF_JOIN           ; Signal line-delete, skip cursor row scroll
  JSR set_modified_render
  JMP clamp_and_clear_count

str_join_limit: .asciiz "Too many lines to join"

; --- Substitute char (s) ---
normal_substitute_char:
  JSR check_cursor_in_line
  BCS sub_change_insert

  JSR chars_left             ; BUF_LEN16 = available
  JSR get_count
  ; BUF_LEN16 = min(count, available chars)
  CMP16 BUF_TEMP16, BUF_LEN16
  BCS .sub_count_ok
  CP16 BUF_TEMP16, BUF_LEN16
.sub_count_ok:

; Shared s/C tail: change range at cursor
sub_change_tail:
  LDA #OP_CHANGE
  JMP apply_char_operator

; --- Change to EOL (C) ---
normal_change_to_eol:
  JSR get_count_clamp_lines  ; (a count on the last line ends it)
  JSR dollar_range_setup
  BCC sub_change_tail
  ; fall through: nothing to change on the line

; Shared s/C empty-line entry to insert mode (cw's too): an empty
; change, as in vim
sub_change_insert:
  JSR undo_record_empty
  JMP enter_insert_mode

; --- Replace char (r) ---
; The replacement is the key typed, a control key too, or the key after
; Ctrl-V (a Ctrl-V first, as in vim).  Enter and Ctrl-J replace the N
; chars with one line break instead: the loop stores them as KEY_ENTER (a
; placeholder, never a replacement char), then replace_split makes the
; break.  Keys that are no char (arrows and other KEY_* codes, $00 for
; non-ASCII, BS) cancel r like Esc, and so does a count past the line
; end: vim leaves the line alone then.  ($7F never arrives: read_key
; maps it to KEY_BS.)
do_replace_char:
  LDA BUF_TEMP
  CMP #$16
  BNE .typed
  JSR get_key                ; Ctrl-V: the next key
  STA BUF_TEMP
.typed:
  CMP #'\n'
  BNE .char
  LDA #KEY_ENTER             ; Ctrl-J is Enter
  STA BUF_TEMP
.char:
  TAX
  BMI .replace_fail          ; A KEY_* code
  BEQ .replace_fail          ; $00
  CMP #KEY_BS
  BEQ .replace_fail
  ; The N chars must be in the line (not an empty one)
  JSR get_count              ; BUF_TEMP16 = N
  JSR get_line_len_z
  JSR chars_left
  CMP16 BUF_LEN16, BUF_TEMP16
  BCC .replace_fail          ; Fewer than N
  LDA BUF_TEMP
  CMP #KEY_ENTER
  BNE .replace_start
  ; r<Enter>: a line more must fit
  LDA #1
  LDX #0
  JSR check_line_room
  BCC .replace_start
  JMP open_full              ; "Buffer full"
.replace_fail:
  JMP keep_clear_count
.replace_start:
  JSR echo_span_setup
  ; Count, capped at 255 (replacement span is recorded in one page)
  JSR get_count_x
  STX NORMAL_TEMP            ; loop counter
  ; (BUF_PTR16),Y = the char at the cursor, which the loop steps with Y
  JSR get_cursor_buf_ptr
  LDY #0

.replace_loop:
  ; Save the original char for undo
  LDA (BUF_PTR16),Y
  STA UNDO_DATA_BUF,Y
  ; Store the replacement, echo it or defer
  LDA BUF_TEMP
  STA (BUF_PTR16),Y
  JSR echo_or_defer
  INY
  CPY NORMAL_TEMP
  BEQ .replace_done
  JSR inc_cursor_col
  JMP .replace_loop

.replace_done:
  STY UNDO_SPAN_LEN          ; (at least one char)
  JSR set_modified
  ; Finalize undo record
  LDA #UNDO_REPLACE
  STA UNDO_TYPE
  LDA BUF_TEMP
  STA UNDO_REPL_CHAR     ; replacement char (for redo)
  CMP #KEY_ENTER
  BEQ replace_split
  JMP clear_count

; r<Enter> and its redo: the UNDO_SPAN_LEN chars from UNDO_LINE16/
; UNDO_COL16 become one line break, as vim's 5r<CR> does.  Their last
; char turns into the break and the ones before it go; the marks below
; the line move down, and the cursor goes to the start of the new line.
; The render is an Enter batch's (RF_ENTER), from the first replaced char.
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
; cc of BUF_TEMP16 lines (op_lines enters here)
cc_lines:
  JSR yank_current_lines
  BCS .cc_overflow
  ; Record undo: u removes the empty line and pastes the lines back,
  ; then puts back the marks (mark_save)
  SEC
  ROR UNDO_EMPTY_LINE
  LDA #UNDO_CC
  JSR undo_rec_set
  JSR mark_save
  JSR cc_clear_lines
  JMP enter_insert_change

.cc_overflow:
  JMP show_yank_overflow

; Replace BUF_TEMP16 lines at FILE_LINE16 with one empty line and put the
; cursor on it, for a displacement-based scroll (cc/S and their redo).
; As in vim, the marks of the first line stay on the empty line, those
; of the others are unset, and the marks below move up N-1 lines.
; Clobbers A, X, Y
cc_clear_lines:
  JSR compute_delete_rows_temp16 ; The lines' rows before
  LDAX16 FILE_LINE16
  JSR buf_clear_lines        ; (keeps BUF_TEMP16)
  JSR dec_buf_temp16
  JSR next_line_ax
  JSR mark_adjust_delete     ; The N - 1 lines after the first
  LDA #RF_JOIN
  JMP undo_opened_finish     ; Cursor to col 0, modified

; vi's linewise rules for the word and $ operators (normal_shift.asm),
; here by the cc they can turn into: the char operator in A on the
; BUF_LEN16 bytes at the cursor works on whole lines if it starts in its
; line's indentation (only blanks before the cursor) and either
; - a w or b operator ended on column 0 of a later line (OP_EXCL_LINE;
;   its range already stops at the end of the line before), or
; - it deletes over lines and leaves only blanks on the last one;
; then it runs as yy, dd or cc of the range's lines, and the command
; ends there.  Otherwise returns carry set if the range is empty.
; NORMAL_TEMP = the operator.  Clobbers A, X, Y, BUF_PTR16, BUF_SRC16,
; BUF_DST16, BUF_TEMP16 (the range's newlines)
op_lines:
  STA NORMAL_TEMP
  JSR count_newlines           ; BUF_TEMP16 = the range's newlines, Y = 0
  ASL OP_EXCL_LINE             ; C = the exclusive rule applies (clears it)
  BCS .indent
  LDX NORMAL_TEMP
  DEX
  BNE .char                    ; Not a delete
  TST16 BUF_TEMP16
  BEQ .char                    ; Within one line
.rest:
  LDA (BUF_DST16),Y            ; After the range, to the end of its line
  CMP #'\n'
  BEQ .indent                  ; Only blanks
  JSR char_class
  BNE .char
  INY
  BNE .rest                    ; (256 blanks or more: as chars)
.char:
  JMP range_epilogue           ; C = 1: an empty range
.indent:
  JSR in_indent                ; C = 1: only blanks before the cursor
  BCC .char
  ; The lines from the cursor's to the range's last
  INC16 BUF_TEMP16
  PLA
  PLA                          ; The command ends here
  LDA NORMAL_TEMP
  LSR                          ; C = OP_DELETE, A = 1: OP_CHANGE
  BCS .dd
  BNE cc_lines
  JMP yy_lines
.dd:
  JMP dd_lines                 ; (dispatch_replay left BATCH_EXTRA 0)
