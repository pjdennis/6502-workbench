; asm0.asm - Minimal bootstrap assembler
; Only: DATA $XX ..., ; comments
; ZP: $00=TMP | $F006=read, $F009=write

; LAYOUT:
; $2000: main (47b)   $202F: skip_sp (17b)  $2040: data (50b)
; $2072: cvt (14b)    $2080: eof (1b)

; ===== MAIN: $2000 (47 bytes) =====
DATA $20 $06 $F0  ; 2000: JSR read
DATA $90 $03      ; 2003: BCC $2008
DATA $4C $80 $20  ; 2005: JMP eof ($2080)
DATA $C9 $0A      ; 2008: CMP# $0A
DATA $F0 $F4      ; 200A: BEQ $2000 (main)
DATA $C9 $3B      ; 200C: CMP# ';'
DATA $D0 $09      ; 200E: BNE $2019
; skip_comment: read until newline
DATA $20 $06 $F0  ; 2010: JSR read
DATA $C9 $0A      ; 2013: CMP# $0A
DATA $D0 $F9      ; 2015: BNE $2010
DATA $F0 $E7      ; 2017: BEQ $2000
; continue checking for whitespace
DATA $C9 $20      ; 2019: CMP# ' '
DATA $F0 $E3      ; 201B: BEQ $2000
DATA $C9 $09      ; 201D: CMP# $09
DATA $F0 $DF      ; 201F: BEQ $2000
DATA $C9 $44      ; 2021: CMP# 'D'
DATA $F0 $1B      ; 2023: BEQ data ($2040)
; skip_unknown: read until newline, then back to main
DATA $20 $06 $F0  ; 2025: JSR read
DATA $C9 $0A      ; 2028: CMP# $0A
DATA $D0 $F9      ; 202A: BNE $2025
DATA $4C $00 $20  ; 202C: JMP $2000
; Main ends at $202E, next is $202F

; ===== SKIP_SP: $202F (17 bytes) =====
DATA $20 $06 $F0  ; 202F: JSR read
DATA $90 $03      ; 2032: BCC $2037
DATA $4C $80 $20  ; 2034: JMP eof ($2080)
DATA $C9 $20      ; 2037: CMP# ' '
DATA $F0 $F4      ; 2039: BEQ $202F
DATA $C9 $09      ; 203B: CMP# $09
DATA $F0 $F0      ; 203D: BEQ $202F
DATA $60          ; 203F: RTS
; Skip_sp ends at $203F, next is $2040

; ===== HANDLE_DATA: $2040 (50 bytes) =====
DATA $20 $06 $F0  ; 2040: JSR read (skip 'A')
DATA $20 $06 $F0  ; 2043: JSR read (skip 'T')
DATA $20 $06 $F0  ; 2046: JSR read (skip 'A')
; data_loop: $2049
DATA $20 $2F $20  ; 2049: JSR skip_sp
DATA $C9 $0A      ; 204C: CMP# $0A (newline)
DATA $F0 $B0      ; 204E: BEQ $2000
DATA $C9 $3B      ; 2050: CMP# ';' (comment)
DATA $F0 $BC      ; 2052: BEQ skip_comment ($2010)
DATA $C9 $24      ; 2054: CMP# '$'
DATA $D0 $A8      ; 2056: BNE $2000 (error)
; parse $XX
DATA $20 $06 $F0  ; 2058: JSR read (d1)
DATA $20 $72 $20  ; 205B: JSR cvt ($2072)
DATA $0A          ; 205E: ASL
DATA $0A          ; 205F: ASL
DATA $0A          ; 2060: ASL
DATA $0A          ; 2061: ASL
DATA $85 $00      ; 2062: STA $00
DATA $20 $06 $F0  ; 2064: JSR read (d2)
DATA $20 $72 $20  ; 2067: JSR cvt
DATA $05 $00      ; 206A: ORA $00
DATA $20 $09 $F0  ; 206C: JSR write
DATA $4C $49 $20  ; 206F: JMP data_loop ($2049)
; Data ends at $2071, next is $2072

; ===== CVT_HEX: $2072 (14 bytes) =====
DATA $C9 $41      ; 2072: CMP# 'A'
DATA $90 $06      ; 2074: BCC $207C (digit path)
DATA $E9 $41      ; 2076: SBC# 'A' (carry set from CMP)
DATA $18          ; 2078: CLC
DATA $69 $0A      ; 2079: ADC# $0A
DATA $60          ; 207B: RTS
DATA $38          ; 207C: SEC (need carry for SBC)
DATA $E9 $30      ; 207D: SBC# '0'
DATA $60          ; 207F: RTS
; Cvt ends at $207F, next is $2080

; ===== EOF: $2080 (1 byte) =====
DATA $00          ; 2080: BRK

; Total code: $2000-$2080 = 129 bytes

; Start address for this program (reset vector points to $2000)
DATA $00 $20
