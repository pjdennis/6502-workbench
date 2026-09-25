; Normal mode - main handler, dispatch tables, and core editing commands

; Initialize normal mode state
normal_init:
  LDA #0
  STA LAST_KEY
  STA_LH16 COUNT16
  STA COUNT_ACTIVE
  STA BATCH_RESTORE_KEY
  STA BATCH_EXTRA
  STA SCROLL_AMOUNT
  RTS

; Handle a keystroke in normal mode
; Key code in A
normal_handle_key:
  STA BUF_TEMP

  ; --- Count prefix handling ---

  ; ESC always clears count and pending key
  CMP #KEY_ESC
  BNE .not_esc_count
  LDA COUNT_ACTIVE
  ORA LAST_KEY
  BEQ .not_esc_count      ; No active count or pending key, let ESC fall through
  JSR clear_count
  RTS
.not_esc_count:

  ; If COUNT_ACTIVE, check for continued digit input
  LDA COUNT_ACTIVE
  BEQ .count_not_active

  ; COUNT_ACTIVE=true: 0-9 continues accumulation
  LDA BUF_TEMP
  CMP #'0'
  BCC .count_done_dispatch
  CMP #'9' + 1
  BCS .count_done_dispatch
  ; Accumulate digit into COUNT16
  JSR count_accumulate_digit
  RTS

.count_done_dispatch:
  ; Non-digit with active count: clear COUNT_ACTIVE, fall through to dispatch
  LDA #0
  STA COUNT_ACTIVE
  JMP .dispatch_key

.count_not_active:
  ; If pending key is set, don't start a new count - dispatch directly
  LDA LAST_KEY
  BNE .dispatch_key
  ; Not counting yet: 1-9 starts a new count
  LDA BUF_TEMP
  CMP #'1'
  BCC .dispatch_key
  CMP #'9' + 1
  BCS .dispatch_key
  ; Start new count
  LDA #$FF
  STA COUNT_ACTIVE
  LDA #0
  STA_LH16 COUNT16
  LDA BUF_TEMP
  JSR count_accumulate_digit
  RTS

.dispatch_key:
  LDA LAST_KEY
  BEQ .normal_dispatch
  JMP pending_key_dispatch
.normal_dispatch:
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
  LDA #<normal_other_keys
  LDX #>normal_other_keys
  JSR dispatch_key
  BCC .done
  ; Check if key starts a multi-key combo
  LDA #<pending_combo_keys
  LDX #>pending_combo_keys
  JSR check_combo_first_key
  BCC .done
  ; Unknown key - clear count and last key, cursor-only update
  JSR clear_count
.done:
  RTS

; --- Pending key dispatch ---
; Called when LAST_KEY is set and a second key arrives in BUF_TEMP.
; Uses table-based dispatch via dispatch_pending_key.
pending_key_dispatch:
  LDA #<pending_combo_keys
  LDX #>pending_combo_keys
  JSR dispatch_pending_key
  BCC .done
  ; No match - reset
  JSR clear_count
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
  .byte 0           ; End sentinel

normal_editing_keys:
  .byte 'x'         .word normal_delete_char
  .byte KEY_DEL     .word normal_delete_char
  .byte 'X'         .word normal_delete_char_back
  .byte 'D'         .word normal_delete_to_eol
  .byte 'i'         .word normal_enter_insert
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
  .byte 'S'         .word normal_substitute_line
  .byte 'u'         .word undo_handle
  .byte 0           ; End sentinel

normal_other_keys:
  .byte ':'         .word normal_enter_command
  .byte 0           ; End sentinel

; Pending combo key table: 5-byte entries [last_key, second_key, flags, handler]
;   second_key=0: wildcard (any second key)
;   flags bit 0: call batch_pending_pairs before handler
;   flags bit 1: editing command (blocked in READONLY mode)
pending_combo_keys:
  .byte 'm', 0, $00         .word do_mark_set
  .byte '\'', 0, $00        .word do_mark_goto
  .byte 'r', 0, $02         .word do_replace_char
  .byte 'd', 'd', $03       .word do_dd
  .byte 'g', 'g', $00       .word do_gg
  .byte 'y', 'y', $00       .word do_yy
  .byte 'y', 'w', $00       .word do_yw
  .byte 'y', 'b', $00       .word do_yb
  .byte 'c', 'c', $02       .word do_cc
  .byte '>', '>', $03       .word do_indent
  .byte '<', '<', $03       .word do_unindent
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

  ; Normalize batching: count + pending x keys, capped at 255
  JSR get_batched_count      ; X = total, BATCH_EXTRA = extras
  STX BUF_TEMP16
  CP16 CURSOR_COL16, RENDER_FROM_COL16
  JMP batched_char_delete
.done:
  JMP clear_count

; X: delete count chars before the cursor (clamped at column 0); the
; cursor moves left with the text
normal_delete_char_back:
  TST16 CURSOR_COL16
  BEQ .done

  ; Normalize batching: count + pending X keys, capped at 255
  JSR get_batched_count      ; X = total, BATCH_EXTRA = extras
  STX BUF_TEMP16
  LDA #0
  STA BUF_TEMP16 + 1
  ; Clamp to the chars before the cursor
  CMP16 CURSOR_COL16, BUF_TEMP16
  BCS .count_ok
  CP16 CURSOR_COL16, BUF_TEMP16
.count_ok:
  ; Move to the range start and delete forward from there
  SEC
  SBC16 CURSOR_COL16, BUF_TEMP16, CURSOR_COL16
  JSR check_cursor_in_line   ; LINE_LEN16 (cursor is now inside the line)
  CP16 CURSOR_COL16, RENDER_FROM_COL16
  JMP batched_char_delete_back
.done:
  JMP clear_count

normal_delete_to_eol:
  JSR check_cursor_in_line
  BCS .done

  JSR get_count
  JSR compute_dollar_range
  CP16 CURSOR_COL16, RENDER_FROM_COL16
  LDA #OP_DELETE
  JSR apply_char_operator
.done:
  JMP clear_count

; dd: yank then delete N lines (N = count, min 1)
; When batched (BATCH_EXTRA > 0): yank only the last line, then delete
; all N lines in a single operation (one shift, one rebuild).
do_dd:
  JSR get_count              ; BUF_TEMP16 = count (16-bit)

  ; Pre-compute screen rows of lines being deleted (before deletion)
  LDA BUF_TEMP16 + 1
  BNE .dd_skip_precompute    ; Count > 255, skip
  JSR set_render_line_to_cursor
  LDA BUF_TEMP16
  JSR compute_delete_screen_rows
  JMP .dd_after_precompute
.dd_skip_precompute:
  LDA #0
  STA DELETE_SCREEN_ROWS
.dd_after_precompute:

  LDA BATCH_EXTRA
  BEQ .do_yank_delete        ; No batching, standard path

  ; Batched: yank last line only, then delete all in one operation
  ; Save total count
  PUSH16 BUF_TEMP16
  ; Yank 1 line at FILE_LINE16 + (total - 1)
  JSR yank_clear
  SEC
  SBCI16 BUF_TEMP16, 1, BUF_TEMP16
  CLC
  ADC16 FILE_LINE16, BUF_TEMP16, BUF_TEMP16
  ; BUF_TEMP16 = last line number; set count=1 via BUF_LEN16, then swap
  LDAX16 BUF_TEMP16          ; A/X = last line number
  PHA                        ; Save A (line number low byte)
  JSR set_buf_temp16_one     ; BUF_TEMP16 = 1 (count)
  PLA                        ; Restore A = last line number low byte
  JSR yank_add_lines
  ; Restore total count and delete all lines
  POP16 BUF_TEMP16
  BCS .yank_overflow
  JSR undo_record_line_delete
  JSR delete_current_lines
  JMP .dd_done

.do_yank_delete:
  JSR yank_delete_current_lines
  BCS .yank_overflow

.dd_done:
  LDA #$FF
  STA MODIFIED
  LDA #$02
  STA RENDER_FLAG        ; Signal line-delete for scroll optimization
  JMP clamp_and_clear_count

.yank_overflow:
  JMP show_yank_overflow

normal_enter_insert:
  JMP enter_insert_mode

normal_enter_insert_after:
  JSR get_line_len_z
  ; Increment iff cursor < len (empty line: cursor 0 >= len 0, no move)
  CMP16 CURSOR_COL16, LINE_LEN16
  BCS .enter
  JSR inc_cursor_col
.enter:
  JMP enter_insert_mode

normal_enter_insert_eol:
  JSR get_current_line_len
  STAX16 CURSOR_COL16
  JMP enter_insert_mode

normal_open_below:
  JSR get_current_line_ptr
  JSR advance_past_line_end

  LDA #'\n'
  JSR buf_insert_char
  BCS open_full
  JSR buf_rebuild_lines

  ; Adjust marks: new line inserted at FILE_LINE16+1
  LDAX16 FILE_LINE16
  CLC
  ADC #1
  BCC .mark_adj
  INX
.mark_adj:
  JSR mark_insert_one

  ; Record undo: opened line at FILE_LINE16+1, restore cursor to FILE_LINE16
  LDA #UNDO_OPEN
  STA UNDO_TYPE
  CP16 FILE_LINE16, UNDO_COL16   ; Restore cursor to original line
  INC16 FILE_LINE16
  CP16 FILE_LINE16, UNDO_LINE16  ; Opened line position

; Shared o/O tail: reset undo redo flag, cursor to col 0, enter insert mode
open_common_finish:
  LDA #0
  STA UNDO_IS_REDO
  STA_LH16 CURSOR_COL16
  LDA #$FF
  STA MODIFIED
  LDA #$03
  STA RENDER_FLAG        ; Signal line-insert for scroll optimization
  JMP enter_insert_mode

; Shared o/O buffer-full handler
open_full:
  JSR show_buffer_full_msg
  JMP clear_count

normal_open_above:
  JSR get_current_line_ptr

  LDA #'\n'
  JSR buf_insert_char
  BCS open_full
  JSR buf_rebuild_lines

  ; Adjust marks: new line inserted at FILE_LINE16
  LDAX16 FILE_LINE16
  JSR mark_insert_one

  ; Record undo: opened line at FILE_LINE16, restore cursor to FILE_LINE16
  LDA #UNDO_OPEN
  STA UNDO_TYPE
  CP16 FILE_LINE16, UNDO_LINE16  ; Opened line position
  CP16 FILE_LINE16, UNDO_COL16   ; Restore cursor to same line
  JMP open_common_finish

