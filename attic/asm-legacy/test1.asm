; test1.asm - test strings and multi-byte values
DATA "Hello"      ; ASCII string
DATA $0A          ; newline
DATA $1234        ; 16-bit value (should be 34 12)
DATA $00          ; BRK
DATA $00 $20      ; start address
