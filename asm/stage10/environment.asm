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
