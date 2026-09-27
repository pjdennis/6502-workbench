; environment.asm - Environment vector table
;
; Requires: none (symbols are provided by the runtime environment)
; Provides: entry points for I/O, args, and console helpers
;
; The vectors are 3-byte JMP slots at fixed offsets from ENV_BASE.
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
con_read  = ENV_BASE + $27 ; Read one byte from console (blocking); returns in A
con_flush = ENV_BASE + $2A ; Flush stdout
con_ready = ENV_BASE + $2D ; Non-blocking poll: A=$FF if byte ready, A=$00 if not yet,
                           ; A=CON_EOF once input has ended
term_rows = ENV_BASE + $30 ; Returns terminal height in A
term_cols = ENV_BASE + $33 ; Returns terminal width in A
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
DIR_ENTRY_DIR      = $01 ; Metadata bit 0: entry is a directory
DIR_ENTRY_READONLY = $02 ; Metadata bit 1: entry is read-only
