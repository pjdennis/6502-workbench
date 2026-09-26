; ============================================================================
; VI - Minimal Vi-like Text Editor for 6502
; ============================================================================
;
; A vi-like text editor running on the 6502 emulator: console I/O by
; default, serial I/O to an ANSI terminal with define:terminal_mode.
;
; Usage (from toolchain/asm2; edits file.txt in place, :w writes it back):
;   ../../emulator/emulator.out editor/out/editor.out --load 0400 --console file.txt
;   ./editor.sh file.txt        (terminal build)
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
  .include editor/macros.asm
  .include 17/to_decimal.asm
  .include editor/zp.asm
  .include editor/io.asm
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
  .include editor/normal_util.asm
  .include editor/word.asm
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
  ; Clear zero page: every zero-page variable starts at 0, which is the
  ; initial value of all editor state except what yank_init and
  ; mark_init set below
  LDA #0
  TAX
.clear_zp:
  STA $00,X
  INX
  BNE .clear_zp

  ; Filename: first argument, or "[No Name]" if none
  LDX #>str_untitled      ; argc preserves X
  JSR argc
  CMP #1
  LDA #<str_untitled
  BCC .have_name
  LDA #0
  JSR argv                ; A;X = first argument
.have_name:
  ; Copy the name to FNAME_BUF
  STAX16 BUF_PTR16
  LDY #0
.copy_fname:
  LDA (BUF_PTR16),Y
  STA FNAME_BUF,Y
  BEQ .fname_copied
  INY
  BNE .copy_fname
.fname_copied:

  ; Try to open the file for reading (returns 0 if not found)
  LDA #<FNAME_BUF
  LDX #>FNAME_BUF
  JSR open
  CMP #0
  BEQ .new_file

  ; File exists - load it (buf_load_file saves the handle in FILE_HANDLE;
  ; a truncated file opens read-only)
  JSR buf_load_file
  LDA FILE_HANDLE
  JSR close
  JMP .init_display

.new_file:
  ; File doesn't exist or no file specified - start with empty buffer
  JSR buf_init

.init_display:
  ; Get the screen size; set up the yank buffer and mark table
  JSR render_init
  JSR yank_init
  JSR mark_init

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
  ; Default: full line render. Handlers may set a partial column.
  LDA #$FF
  STA_LH16 RENDER_FROM_COL16
  STA SHIFT_WRITE            ; No ICH/DCH hint
  ; Default: no render. Snapshot detection infers render level.
  LDA #0
  STA RENDER_FLAG
  STA INSERT_LINE_COUNT
  STA DELETE_SCREEN_ROWS     ; 0 = no pre-computed screen rows
  STA BATCH_EXTRA            ; No typed-ahead keys or pairs taken yet

  ; If entering command mode, handle it specially (it does own I/O)
  LDA MODE
  CMP #MODE_COMMAND
  BNE .not_command_entry
  JSR render_snapshot
  JSR command_handle
  JMP .after_key
.not_command_entry:

  ; Poll for input (non-blocking)
  JSR key_peek
  BCS .key_available

  ; No input - exit if input has ended (console build only)
  .ifndef terminal_mode
  JSR io_ready
  CMP #CON_EOF
  BEQ .editor_exit
  .endif
  JMP main_loop

.key_available:
  JSR file_line_rows
  STA PREV_LINE_ROWS
  JSR render_snapshot
  ; Read a key
  JSR get_key

  ; Exit if the read hit end of input (console build only)
  .ifndef terminal_mode
  TAX
  JSR io_ready             ; preserves X
  CMP #CON_EOF
  BEQ .editor_exit
  TXA
  .endif

  ; Dispatch based on mode
  LDX MODE
  DEX                      ; MODE_INSERT = 1
  BEQ .insert_mode

  ; Normal mode
  JSR normal_handle_key
  JMP .after_key

.insert_mode:
  JSR insert_handle_key

.after_key:
  ; Check if we should quit
  LDA CMD_QUIT
  BNE .editor_exit

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
  JMP exit                 ; Does not return

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
