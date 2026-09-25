; environment.asm - Environment vector table
;
; Requires: none (symbols are provided by the runtime environment)
; Provides: entry points for I/O, args, and console helpers
;
; Provided by environment:
read_b    = $F006 ; Returns next char in A; C set when at end; X, Y preserved
write_b   = $F009 ; Writes char in A to stdout; A, X, Y preserved
write_d   = $F00C ; Writes char in A to stderr; A, X, Y preserved
exit      = $F00F ; Exits the program; exit code in A
open      = $F012 ; Opens file with name at A;X for reading. Returns handle
                  ; in A; Y preserved
close     = $F015 ; Closes file with handle in A; A, X, Y preserved
read      = $F018 ; Reads from file with handle in A; returns next char in A;
                  ; C set when at end; X, Y preserved
argc      = $F01B ; Returns argument count in A; X, Y preserved
argv      = $F01E ; Returns argument A in A;X; Y preserved
openout   = $F021 ; Opens file with name at A;X for writing. Returns handle
                  ; in A; Y preserved
write     = $F024 ; writs char in A to file with handle in X; Y preserved

; Console I/O ports
con_read  = $F027 ; Read one byte from console (blocking); returns in A
con_flush = $F02A ; Flush stdout
con_ready = $F02D ; Non-blocking poll: A=$FF if byte ready, A=$00 if not yet,
                  ; A=CON_EOF once input has ended
term_rows = $F030 ; Returns terminal height in A
term_cols = $F033 ; Returns terminal width in A
CON_EOF   = $01   ; con_ready result: end of input

; Serial I/O ports
serial_read  = $F036 ; Read one byte from serial (non blocking); returns in A.
                     ; C set if no byte was avaiable, clear otherwise. X, Y preserved
serial_write = $F039 ; Write byte in A to serial (non blocking); returns with C set if
                     ; byte not accepted (buffer full), clear otherwise. A, X, Y preserved

; Directory I/O
opendir      = $F03C ; Opens directory with name at A;X. Returns handle in A (0 if
                     ; not found); Y preserved. Read entries via read: each entry is
                     ; a metadata byte followed by a null-terminated filename.
                     ; Entries sorted alphabetically.
DIR_ENTRY_DIR      = $01 ; Metadata bit 0: entry is a directory
DIR_ENTRY_READONLY = $02 ; Metadata bit 1: entry is read-only
