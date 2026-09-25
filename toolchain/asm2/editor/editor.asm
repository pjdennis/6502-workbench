; ============================================================================
; VI - Minimal Vi-like Text Editor for 6502
; ============================================================================
;
; A vi-like text editor running on the 6502 emulator in console mode.
;
; Usage:
;   ./emulator.out editor/out/editor.out --load 0400 --console outfile.txt infile.txt
;
; Modes:
;   Normal:  h/j/k/l movement, x/dd delete, i/a/o/O insert, : command
;   Insert:  Type text, Enter for newline, Backspace to delete, ESC to exit
;   Command: :w save, :q quit, :wq save+quit, :q! force quit, :NNN goto line
;
; MEMORY LAYOUT
;   $0000-$00FF   Zero page variables
;   $0100-$01FF   6502 stack
;   $0200-$02FF   Filename buffer
;   $0300-$03FF   Command buffer
;   $0400         Editor code loads here
;   TEXT_BUF      Text buffer (page-aligned after code, up to $D5FF)
;   $D600-$D61F   Batch insert staging buffer (BATCH_BUF)
;   $D620-$D653   Mark table (MARK_TBL)
;   $D654-$D6FF   Search buffer (SEARCH_BUF)
;   $D700-$D7FF   Undo data buffer (UNDO_DATA_BUF)
;   $D800-$DFFF   Line pointer table (LINE_TBL)
;   $E000-$EFFF   Yank buffer (4KB)
;   $F000+        Emulator I/O
; ============================================================================

FNAME_BUF   = $0200   ; Filename buffer (256 bytes)

* = $0400

  JMP editor_main

  .include 17/environment.asm
  .include 17/macros.asm
  .include editor/io.asm

; PRINT_STR addr - Print null-terminated string at addr
; Clobbers A, Y
  .macro PRINT_STR addr
  SET16 addr, STR_PTR16
  JSR write_string
  .endmacro

  .include 17/to_decimal.asm
  .include editor/terminal.asm
  .include editor/input.asm
  .include editor/buffer_mem.asm
  .include editor/buffer.asm
  .include editor/undo_state.asm
  .include editor/render.asm
  .include editor/render_decide.asm
  .include editor/render_scroll.asm
  .include editor/yank.asm
  .include editor/search.asm
  .include editor/word.asm
  .include editor/normal_util.asm
  .include editor/normal.asm
  .include editor/normal_move.asm
  .include editor/normal_edit.asm
  .include editor/normal_shift.asm
  .include editor/insert.asm
  .include editor/command.asm
  .include editor/mark.asm
  .include editor/undo.asm

; ============================================================================
; Entry point
; ============================================================================
editor_main:
  ; Initialize flags
  LDA #0
  STA CMD_QUIT
  STA READONLY
  LDA #>TEXT_LIMIT
  STA BUF_LIMIT

  ; Get filename from argv
  JSR argc
  CMP #1
  BCC .no_file
  ; Get first argument (the input filename)
  LDA #0
  JSR argv
  ; A;X = pointer to filename string, copy to FNAME_BUF and set FNAME_PTR16
  STAX16 BUF_PTR16
.set_fname:
  LDY #0
.copy_fname:
  LDA (BUF_PTR16),Y
  STA FNAME_BUF,Y
  BEQ .fname_copied
  INY
  BNE .copy_fname
.fname_copied:
  SET16 FNAME_BUF, FNAME_PTR16

  ; Try to open the file for reading (returns 0 if not found)
  LDAX16 FNAME_PTR16
  JSR open
  CMP #0
  BEQ .new_file

  ; File exists - load it
  STA FILE_HANDLE
  LDA FILE_HANDLE
  JSR buf_load_file
  PHP                  ; Save carry (truncation flag)
  LDA FILE_HANDLE
  JSR close
  PLP                  ; Restore carry
  BCC .init_display
  ; File was truncated - set read-only mode
  LDA #$FF
  STA READONLY
  JMP .init_display

.no_file:
  ; No file specified - use default name and empty buffer
  ; (FNAME_PTR16 is set at .fname_copied after the copy)
  SET16 str_untitled, BUF_PTR16
  JMP .set_fname

.new_file:
  ; File doesn't exist or no file specified - start with empty buffer
  JSR buf_init

.init_display:
  ; Initialize rendering and normal mode state
  JSR render_init
  JSR normal_init
  JSR yank_init
  JSR search_init
  JSR mark_init
  JSR undo_init

  ; Draw initial screen
  JSR render_screen

  ; Show truncation warning if file was truncated
  LDA READONLY
  BEQ .no_truncation_warning
  LDA #<str_truncated
  LDX #>str_truncated
  JSR show_message_ax
.no_truncation_warning:

; ============================================================================
; Main loop
; ============================================================================
main_loop:
  ; Default: no render. Snapshot detection infers render level.
  LDA #0
  STA RENDER_FLAG
  ; Default: full line render. Handlers may set a partial column.
  LDA #$FF
  STA_LH16 RENDER_FROM_COL16
  STA SHIFT_WRITE            ; No ICH/DCH hint
  LDA #0
  STA INSERT_LINE_COUNT

  ; If entering command mode, handle it specially (it does own I/O)
  LDA MODE
  CMP #MODE_COMMAND
  BNE .not_command_entry
  JSR render_snapshot
  JSR command_handle
  JMP .after_key
.not_command_entry:

  ; Poll for input (non-blocking)
  JSR key_ready
  CMP #$FF
  BEQ .key_available

  ; No input - exit if input has ended (console build only)
  .ifndef terminal_mode
  JSR io_ready
  CMP #CON_EOF
  BEQ .editor_exit
  .endif
  JSR background_work
  JMP main_loop

.key_available:
  JSR get_current_line_len
  JSR line_screen_rows
  STA PREV_LINE_ROWS
  ; Save whether old line's last row was full (WRAP_REM == 0 after line_screen_rows)
  LDA WRAP_REM
  STA PREV_LINE_FULL       ; 0 = last row full, non-zero = not full
  JSR render_snapshot
  ; Read a key
  JSR get_key

  ; Exit if the read hit end of input (console build only)
  .ifndef terminal_mode
  PHA
  JSR io_ready
  CMP #CON_EOF
  BNE .not_eof
  PLA
  JMP .editor_exit
.not_eof:
  PLA
  .endif

  ; Dispatch based on mode
  LDX MODE
  CPX #MODE_INSERT
  BEQ .insert_mode

  ; Normal mode
  JSR normal_handle_key
  JMP .after_key

.insert_mode:
  JSR insert_handle_key
  JMP .after_key

.after_key:
  ; Check if we should quit
  LDA CMD_QUIT
  BNE .editor_exit

  ; Batch pending combo keys: when the first key of a two-key combo has
  ; been received and another key is already available, process it
  ; immediately without rendering.  This eliminates the intermediate
  ; status-bar frame for rapid combos like dw, yw, dd, gg, ra, etc.
  LDA MODE
  BNE .render              ; Only batch in normal mode
  LDA LAST_KEY
  BEQ .render              ; No pending combo key
  JSR key_ready
  CMP #$FF
  BNE .render              ; No key available yet, render normally
  JMP .key_available       ; Process next key without rendering

.render:
  ; Ensure cursor is on screen (may scroll viewport)
  JSR ensure_cursor_visible

  ; Compare state snapshots and dispatch render
  JSR render_decide

  JMP main_loop

.editor_exit:
  ; Reset scroll region and clear screen before exit
  JSR ansi_reset_scroll_region
  JSR ansi_clear_screen
  JSR io_flush
  LDA #0
  JSR exit

; ============================================================================
; Background work
; ============================================================================

; Called when no input is available - hook for background tasks
background_work:
  RTS

; ============================================================================
; Data
; ============================================================================
str_untitled: .asciiz "[No Name]"

; Entry point address - emulator uses last 2 bytes of binary as reset vector
  .word editor_main

; ============================================================================
; TEXT_BUF - floating text buffer start address
; ============================================================================
; Page-aligned to the next page boundary after the end of program code.
; This ensures TEXT_BUF automatically moves as the code grows, preventing
; overlap between program code and the text buffer.
_code_end:
TEXT_BUF = _code_end + $00FF >> $08 << $08

; Buffer size: normal build = up to $D600 (BATCH_BUF), small build = 256 bytes
  .ifndef small_buffer
TEXT_LIMIT  = $D600  ; End of text buffer space (up to start of BATCH_BUF)
  .else
TEXT_LIMIT  = TEXT_BUF + $0100  ; Small test buffer (256 bytes)
  .endif
