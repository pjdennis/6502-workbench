; environment.asm - Environment vector table
;
; Requires: none (symbols are provided by the runtime environment)
; Provides: entry points for I/O, args, and console helpers
;
; The vectors are 3-byte JMP slots at fixed offsets from ENV_BASE.
; (asm16 builds asm17 with this file, so it stays free of .else and
; .ifndef.) Michael's ROM has the same vectors at the same addresses
; (firmware/boards/michael/michael_rom.inc), so the editor's define:michael
; build uses this file too.
;
; A call preserves the registers it says it preserves, and returns only
; the flags it names: the other flags are undefined on return (the
; emulator's --strict-api inverts them).
ENV_BASE  = $F000

; Provided by environment:
read_b    = ENV_BASE + $06 ; Returns next char in A; C set when at end; X, Y preserved
write_b   = ENV_BASE + $09 ; Writes char in A to stdout; A, X, Y preserved
write_d   = ENV_BASE + $0C ; Writes char in A to stderr; A, X, Y preserved
exit      = ENV_BASE + $0F ; Exits the program; exit code in A
open      = ENV_BASE + $12 ; Opens file with name at A;X for reading. Returns handle
                           ; in A; Y preserved
close     = ENV_BASE + $15 ; Closes file with handle in A; A, X, Y preserved
read      = ENV_BASE + $18 ; Reads from file with handle in A; returns next char in A;
                           ; C set when at end; X, Y preserved
argc      = ENV_BASE + $1B ; Returns argument count in A; X, Y preserved
argv      = ENV_BASE + $1E ; Returns argument A in A;X; Y preserved
openout   = ENV_BASE + $21 ; Opens file with name at A;X for writing. Returns handle
                           ; in A; Y preserved
write     = ENV_BASE + $24 ; writs char in A to file with handle in X; Y preserved

; Console I/O ports
con_read  = ENV_BASE + $27 ; Read one byte from console (blocking); returns in A;
                           ; X, Y preserved
con_flush = ENV_BASE + $2A ; Flush stdout; A, X, Y preserved
con_ready = ENV_BASE + $2D ; Non-blocking poll: A=$FF if byte ready, A=$00 if not yet,
                           ; A=CON_EOF once input has ended; X, Y preserved
term_rows = ENV_BASE + $30 ; Returns terminal height in A (255 if taller); X, Y preserved
term_cols = ENV_BASE + $33 ; Returns terminal width in A (255 if wider); X, Y preserved
CON_EOF   = $01   ; con_ready result: end of input

; Serial I/O ports
serial_read  = ENV_BASE + $36 ; Read one byte from serial (non blocking); returns in A.
                              ; C set if no byte was avaiable, clear otherwise. X, Y preserved
serial_write = ENV_BASE + $39 ; Write byte in A to serial (non blocking); returns with C set if
                              ; byte not accepted (buffer full), clear otherwise. A, X, Y preserved

; Directory I/O
opendir      = ENV_BASE + $3C ; Opens directory with name at A;X. Returns handle in A (0 if
                              ; not found); Y preserved. Read entries via read: each entry is
                              ; a metadata byte followed by a null-terminated filename.
                              ; Entries sorted alphabetically.
wait_ready   = ENV_BASE + $3F ; Waits until an input byte is ready (console input, or serial
                              ; input in terminal mode) or A;X (low;high) milliseconds have
                              ; passed. Returns A=$FF (N set) if a byte is ready, A=$00 if
                              ; the time passed first, A=CON_EOF once console input has
                              ; ended (N clear). X, Y preserved. With --input every byte is ready at once;
                              ; with a clock rate (--mhz, --cpu-mhz or --baud) the time is
                              ; emulated time, otherwise it is real time.

; Screen calls, for programs built to call them instead of writing ANSI
; sequences (the asm2 editor's define:direct_io build; the emulator's
; --direct-io). Rows and columns are 1-based. All preserve X; they may
; change A and Y.
scr_goto         = ENV_BASE + $42 ; Move the cursor to row A, column Y
scr_clear        = ENV_BASE + $45 ; Clear the screen; cursor to row 1, column 1
scr_clear_eol    = ENV_BASE + $48 ; Clear from the cursor to the end of its row
scr_cursor_on    = ENV_BASE + $4B ; Show the cursor
scr_cursor_off   = ENV_BASE + $4E ; Hide the cursor
scr_reverse      = ENV_BASE + $51 ; Write reverse video from here on
scr_normal       = ENV_BASE + $54 ; Write normal video from here on
scr_region       = ENV_BASE + $57 ; Scroll region rows A to Y
scr_region_reset = ENV_BASE + $5A ; Scroll region the whole screen
scr_insert       = ENV_BASE + $5D ; Insert A blanks at the cursor, shifting the row right
scr_delete       = ENV_BASE + $60 ; Delete A characters at the cursor, shifting the row left
scr_scroll_up    = ENV_BASE + $63 ; Scroll the region up A rows (blank rows at the bottom)
scr_scroll_down  = ENV_BASE + $66 ; Scroll the region down A rows (blank rows at the top)
; With direct_io, con_read returns key codes for special keys: $80 up,
; $81 down, $82 left, $83 right, $84 Home, $85 End, $86 PgUp, $87 PgDn,
; $88 Delete, $89 Ctrl+Right, $8A Ctrl+Left, $1B Escape, $08 Backspace.

DIR_ENTRY_DIR      = $01 ; Metadata bit 0: entry is a directory
DIR_ENTRY_READONLY = $02 ; Metadata bit 1: entry is read-only
