; Normal mode - main handler, dispatch tables, and core editing commands

; Handle a keystroke in normal mode
; Key code in A
normal_handle_key:
  STA BUF_TEMP

  ; Pending key: dispatch the pair; ESC or no match clears count and key
  LDX LAST_KEY
  BEQ .no_pending
  CMP #KEY_ESC
  BEQ .clear
  LDA #<pending_combo_keys
  LDX #>pending_combo_keys
  JSR dispatch_pending_key
  BCC .done
.clear:
  JMP clear_count

.no_pending:
  ; Count prefix: '1'-'9' start or extend a count, '0' extends one.  A
  ; count is being typed exactly when COUNT16 != 0 with no pending key,
  ; because every command ends in clear_count
  EOR #'0'                   ; '0'-'9' -> 0-9, any other key -> 10 or more
  CMP #10
  BCS .dispatch
  TAX
  BNE .digit                 ; '1'-'9'
  LDX COUNT16
  BNE .digit                 ; '0' within a count
  LDX COUNT16 + 1
  BEQ .dispatch              ; '0' alone: line start
.digit:
  JMP count_accumulate_digit

.dispatch:
  LDA #<normal_movement_keys
  LDX #>normal_movement_keys
  JSR dispatch_key
  BCC .done
  LDA READONLY
  BNE .skip_editing
  LDA #<normal_editing_keys
  LDX #>normal_editing_keys
  JSR dispatch_key
  BCC .done
.skip_editing:
  ; Check if key starts a multi-key combo
  LDA #<pending_combo_keys
  LDX #>pending_combo_keys
  JSR check_combo_first_key
  BCS .clear                 ; Unknown key: clear count and last key
.done:
  RTS

; --- Dispatch tables ---

normal_movement_keys:
  .byte 'h'         .word normal_move_left
  .byte KEY_LEFT    .word normal_move_left
  .byte 'l'         .word normal_move_right
  .byte KEY_RIGHT   .word normal_move_right
  .byte 'j'         .word normal_move_down
  .byte KEY_DOWN    .word normal_move_down
  .byte 'k'         .word normal_move_up
  .byte KEY_UP      .word normal_move_up
  .byte '0'         .word normal_line_start
  .byte KEY_HOME    .word normal_line_start
  .byte '$'         .word normal_line_end
  .byte KEY_END     .word normal_line_end
  .byte KEY_PGDN    .word normal_page_down
  .byte KEY_PGUP    .word normal_page_up
  .byte $06         .word normal_page_down     ; Ctrl-F
  .byte $02         .word normal_page_up       ; Ctrl-B
  .byte $04         .word normal_half_page_down ; Ctrl-D
  .byte $15         .word normal_half_page_up   ; Ctrl-U
  .byte 'G'         .word normal_goto_last
  .byte '/'         .word normal_search
  .byte '?'         .word normal_search_backward
  .byte 'n'         .word normal_find_next
  .byte 'N'         .word normal_find_prev
  .byte 'w'         .word normal_word_forward
  .byte 'b'         .word normal_word_backward
  .byte 'e'         .word normal_word_end
  .byte KEY_WORD_FWD  .word normal_word_forward
  .byte KEY_WORD_BACK .word normal_word_backward
  .byte '^'         .word normal_first_nonblank
  .byte ':'         .word normal_enter_command
  .byte 0           ; End sentinel

normal_editing_keys:
  .byte 'x'         .word normal_delete_char
  .byte KEY_DEL     .word normal_delete_char
  .byte 'X'         .word normal_delete_char_back
  .byte 'D'         .word normal_delete_to_eol
  .byte 'i'         .word enter_insert_mode
  .byte 'a'         .word normal_enter_insert_after
  .byte 'A'         .word normal_enter_insert_eol
  .byte 'o'         .word normal_open_below
  .byte 'O'         .word normal_open_above
  .byte 'p'         .word normal_paste_below
  .byte 'P'         .word normal_paste_above
  .byte '~'         .word normal_toggle_case
  .byte 'J'         .word normal_join_lines
  .byte 's'         .word normal_substitute_char
  .byte 'C'         .word normal_change_to_eol
  .byte 'S'         .word do_cc              ; S = substitute line = cc
  .byte 'u'         .word undo_handle
  .byte 0           ; End sentinel

; Pending combo key table: 5-byte entries [last_key, second_key, flags, handler]
;   second_key=0: wildcard (any second key)
;   flags bit 0: run the handler once per typed-ahead pair (dispatch_replay;
;     dd, >> and << take their pairs themselves)
;   flags bit 1: editing command (blocked in READONLY mode).  Only
;     check_combo_first_key tests it (READONLY accepts a first key if any
;     of its entries has bit 1 clear); dispatch_pending_key does not, so
;     all entries that share a first key must agree on bit 1
pending_combo_keys:
  .byte 'm', 0, $00         .word do_mark_set
  .byte '\'', 0, $00        .word do_mark_goto
  .byte 'r', 0, $02         .word do_replace_char
  .byte 'd', 'd', $02       .word do_dd      ; batches its own pairs
  .byte 'g', 'g', $00       .word do_gg
  .byte 'y', 'y', $00       .word do_yy
  .byte 'y', 'w', $00       .word do_yw
  .byte 'y', 'b', $00       .word do_yb
  .byte 'c', 'c', $02       .word do_cc
  .byte '>', '>', $02       .word do_indent
  .byte '<', '<', $02       .word do_unindent
  .byte 'd', '$', $02       .word do_d_dollar
  .byte 'd', '0', $02       .word do_d_zero
  .byte 'y', '$', $00       .word do_y_dollar
  .byte 'y', '0', $00       .word do_y_zero
  .byte 'd', 'w', $03       .word do_dw
  .byte 'd', 'b', $03       .word do_db
  .byte 'c', 'w', $02       .word do_cw
  .byte 'c', 'b', $02       .word do_cb
  .byte 'd', 'e', $03       .word do_de
  .byte 'y', 'e', $00       .word do_ye
  .byte 'c', 'e', $02       .word do_ce
  .byte 0                   ; End sentinel

; --- Editing ---

normal_delete_char:
  JSR check_cursor_in_line
  BCS .done

  ; Normalize batching: count + pending x keys
  JSR get_batched_count      ; X = total, BATCH_EXTRA = extras
  JMP batched_char_delete
.done:
  JMP clear_count

; X: delete count chars before the cursor (clamped at column 0); the
; cursor moves left with the text
normal_delete_char_back:
  TST16 CURSOR_COL16
  BEQ .done

  JSR get_line_len_z         ; LINE_LEN16 (the range lies inside the line)
  ; Normalize batching: count + pending X keys
  JSR get_batched_count      ; X = total, BATCH_EXTRA = extras
  ; Clamp to the chars before the cursor
  LDA CURSOR_COL16 + 1
  BNE .count_ok
  CPX CURSOR_COL16
  BCC .count_ok
  LDX CURSOR_COL16
.count_ok:
  ; Move to the range start (col -= X) and delete forward from there
  TXA
  EOR #$FF
  SEC
  ADC CURSOR_COL16
  STA CURSOR_COL16
  BCS .no_borrow
  DEC CURSOR_COL16 + 1
.no_borrow:
  JMP batched_char_delete_back
.done:
  JMP clear_count

; dd: yank then delete N lines (N = count, min 1)
; Typed-ahead dd pairs add to N while it stays within the lines left: past
; the last line each dd deletes the line above (the cursor moves up), so
; the pairs that do not fit stay queued and run one at a time.
; When batched (BATCH_EXTRA > 0): yank only the last line, then delete
; all N lines in a single operation (one shift, one rebuild).
do_dd:
  JSR get_count_clamp_lines  ; BUF_TEMP16 = count, BUF_LEN16 = lines left
  LDA BUF_LEN16
  SEC
  SBC BUF_TEMP16
  TAX                        ; X = lines left after the count
  LDA BUF_LEN16 + 1
  SBC BUF_TEMP16 + 1
  BEQ .room
  LDX #$FF                   ; 256 or more
.room:
  JSR batch_pending_pairs_upto  ; X = pairs taken
  TXA
  ADDA16 BUF_TEMP16          ; BUF_TEMP16 = count + pairs (the limit kept it
                             ; within the lines left)

  ; Pre-compute screen rows of lines being deleted (before deletion)
  JSR compute_delete_rows_temp16

  LDA BATCH_EXTRA
  BEQ .do_yank_delete        ; No batching, standard path

  ; Batched: yank last line only, then delete all in one operation
  PUSH16 BUF_TEMP16          ; Save total count
  ; Yank 1 line at FILE_LINE16 + (total - 1)
  JSR dec_buf_temp16
  CLC
  LDA FILE_LINE16
  ADC BUF_TEMP16
  PHA
  LDA FILE_LINE16 + 1
  ADC BUF_TEMP16 + 1
  TAX                        ; X = last line number high byte
  JSR set_buf_temp16_one     ; BUF_TEMP16 = 1 (count); preserves X
  PLA                        ; A = last line number low byte
  JSR yank_add_lines
  POP16 BUF_TEMP16           ; Restore total count (PLA keeps carry)
  BCS .yank_overflow
  JSR undo_delete_current_lines  ; Returns C = 0
  BCC .dd_done               ; Always

.do_yank_delete:
  JSR yank_delete_current_lines
  BCS .yank_overflow

.dd_done:
  LDA #RF_DEL            ; Signal line-delete for scroll optimization
  JSR set_modified_render
  JMP clamp_and_clear_count

.yank_overflow:
  JMP show_yank_overflow

normal_enter_insert_after:
  ; Increment iff cursor < len (empty line: cursor 0 >= len 0, no move)
  JSR check_cursor_in_line
  BCS .enter
  JSR inc_cursor_col
.enter:
  JMP enter_insert_mode

normal_enter_insert_eol:
  JSR insert_end             ; col = len
  JMP enter_insert_mode

normal_open_below:
  JSR get_current_line_ptr
  JSR advance_past_line_end
  LDX #1
  BNE open_line_x            ; Always
normal_open_above:
  JSR get_current_line_ptr
  LDX #0
; Open a blank line at BUF_PTR16 as line FILE_LINE16 + X (X = 1: below
; the cursor line, X = 0: above it), move the cursor to it and enter
; insert mode
open_line_x:
  STX NORMAL_TEMP
  TXA
  CLC
  ADC FILE_LINE16
  LDX FILE_LINE16 + 1
  BCC .open
  INX
.open:
  JSR buf_open_line          ; A/X = the new line's number
  BCS open_full

  ; Record undo: u deletes the opened line and returns to this one
  LDA #UNDO_OPEN
  STA UNDO_TYPE
  CP16 FILE_LINE16, UNDO_COL16   ; Line to restore the cursor to
  LDA NORMAL_TEMP
  BEQ .on_new_line               ; O: the new line took this number
  INC16 FILE_LINE16
.on_new_line:
  CP16 FILE_LINE16, UNDO_LINE16  ; Opened line position
  LDA #RF_INS                       ; Signal line-insert for scroll optimization
  JSR undo_opened_finish
  JMP enter_insert_mode

; o/O buffer-full handler
open_full:
  JSR show_buffer_full_msg
  JMP clear_count

