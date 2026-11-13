; asm01.asm - DATA with single-character labels and strings
; Assembled by version 00, so this source is DATA $XX lines and comments only.
;
; The assembler reads lines from $F006 and writes bytes to $F009:
;   name          at column 0: define a label at the current PC
;    DATA args    indented: emit args, where an arg is
;                   $XX       a byte (two upper-case hex digits)
;                   "text"    its characters (no escapes)
;                   name      a label's address, low byte first
;   ; comment     anywhere outside a string
; Only a name's first character counts, so names must differ in it.
; Labels must be defined before they are used. Whitespace is spaces only.
; Errors stop with BRK, an exit code and a message, as in version 02:
;   1 Duplicate label   2 Opcode not found   3 Label not found
;
; ZP: $00=TMP  $04/$05=PC (low, high)
; LTAB = $3000: two bytes (low, high) per character, at offset 2 * character.
;   A high byte of zero means undefined: labels are always at $2000 or above.
; $F006=read_b (carry set at end of input)  $F009=write_b

; start: $2000
DATA $A9 $20          ; 2000: LDA #$20
DATA $85 $05          ; 2002: STA PCH - PC = $2000 (PCL is already zero)
; main: $2004 - at the start of a line
DATA $20 $E8 $20      ; 2004: JSR rd ($20E8)
DATA $C9 $0A          ; 2007: CMP #$0A
DATA $F0 $F9          ; 2009: BEQ main ($2004)
DATA $C9 $3B          ; 200B: CMP #';'
DATA $F0 $15          ; 200D: BEQ skipln ($2024)
DATA $C9 $20          ; 200F: CMP #' '
DATA $F0 $51          ; 2011: BEQ stmt ($2064)
DATA $0A              ; 2013: ASL - label definition: X = 2 * first character
DATA $AA              ; 2014: TAX
DATA $BD $01 $30      ; 2015: LDA LTAB+1,X
DATA $D0 $13          ; 2018: BNE e_dup ($202D) - high byte set: already defined
DATA $A5 $04          ; 201A: LDA PCL
DATA $9D $00 $30      ; 201C: STA LTAB,X
DATA $A5 $05          ; 201F: LDA PCH
DATA $9D $01 $30      ; 2021: STA LTAB+1,X
; skipln: $2024 - read up to and including the newline
DATA $20 $E8 $20      ; 2024: JSR rd ($20E8)
DATA $C9 $0A          ; 2027: CMP #$0A
DATA $D0 $F9          ; 2029: BNE skipln ($2024)
DATA $F0 $D7          ; 202B: BEQ main ($2004) - always taken
; e_dup: $202D
DATA $00              ; 202D: BRK
DATA $01              ; 202E: error code
DATA $44 $75 $70 $6C $69 $63 $61 $74 $65 $20 $6C $61 $62 $65 $6C $00 ; 202F: "Duplicate label" $00
; e_op: $203F
DATA $00              ; 203F: BRK
DATA $02              ; 2040: error code
DATA $4F $70 $63 $6F $64 $65 $20 $6E $6F $74 $20 $66 $6F $75 $6E $64 $00 ; 2041: "Opcode not found" $00
; e_nf: $2052
DATA $00              ; 2052: BRK
DATA $03              ; 2053: error code
DATA $4C $61 $62 $65 $6C $20 $6E $6F $74 $20 $66 $6F $75 $6E $64 $00 ; 2054: "Label not found" $00
; stmt: $2064
DATA $20 $E0 $20      ; 2064: JSR skipsp ($20E0)
DATA $C9 $0A          ; 2067: CMP #$0A
DATA $F0 $99          ; 2069: BEQ main ($2004)
DATA $C9 $3B          ; 206B: CMP #';'
DATA $F0 $B5          ; 206D: BEQ skipln ($2024)
DATA $C9 $44          ; 206F: CMP #'D'
DATA $D0 $CC          ; 2071: BNE e_op ($203F)
DATA $20 $E8 $20      ; 2073: JSR rd ($20E8) - skip "ATA"
DATA $20 $E8 $20      ; 2076: JSR rd ($20E8)
DATA $20 $E8 $20      ; 2079: JSR rd ($20E8)
; dloop: $207C
DATA $20 $E0 $20      ; 207C: JSR skipsp ($20E0)
DATA $C9 $0A          ; 207F: CMP #$0A
DATA $F0 $81          ; 2081: BEQ main ($2004)
DATA $C9 $3B          ; 2083: CMP #';'
DATA $F0 $9D          ; 2085: BEQ skipln ($2024)
DATA $C9 $24          ; 2087: CMP #'$'
DATA $F0 $25          ; 2089: BEQ hex ($20B0)
DATA $C9 $22          ; 208B: CMP #'"'
DATA $F0 $3B          ; 208D: BEQ str ($20CA)
DATA $0A              ; 208F: ASL - label reference: X = 2 * first character
DATA $AA              ; 2090: TAX
DATA $BD $01 $30      ; 2091: LDA LTAB+1,X
DATA $F0 $BC          ; 2094: BEQ e_nf ($2052) - high byte zero: not defined
DATA $BD $00 $30      ; 2096: LDA LTAB,X
DATA $20 $F0 $20      ; 2099: JSR emit ($20F0)
DATA $BD $01 $30      ; 209C: LDA LTAB+1,X
DATA $20 $F0 $20      ; 209F: JSR emit ($20F0)
; skipnm: $20A2 - skip the rest of the name
DATA $20 $E8 $20      ; 20A2: JSR rd ($20E8)
DATA $C9 $20          ; 20A5: CMP #' '
DATA $F0 $D3          ; 20A7: BEQ dloop ($207C)
DATA $C9 $0A          ; 20A9: CMP #$0A
DATA $D0 $F5          ; 20AB: BNE skipnm ($20A2)
DATA $4C $04 $20      ; 20AD: JMP main ($2004)
; hex: $20B0
DATA $20 $E8 $20      ; 20B0: JSR rd ($20E8)
DATA $20 $D7 $20      ; 20B3: JSR cvt ($20D7)
DATA $0A              ; 20B6: ASL
DATA $0A              ; 20B7: ASL
DATA $0A              ; 20B8: ASL
DATA $0A              ; 20B9: ASL
DATA $85 $00          ; 20BA: STA TMP
DATA $20 $E8 $20      ; 20BC: JSR rd ($20E8)
DATA $20 $D7 $20      ; 20BF: JSR cvt ($20D7)
DATA $05 $00          ; 20C2: ORA TMP
DATA $20 $F0 $20      ; 20C4: JSR emit ($20F0)
DATA $4C $7C $20      ; 20C7: JMP dloop ($207C)
; str: $20CA
DATA $20 $E8 $20      ; 20CA: JSR rd ($20E8)
DATA $C9 $22          ; 20CD: CMP #'"'
DATA $F0 $AB          ; 20CF: BEQ dloop ($207C)
DATA $20 $F0 $20      ; 20D1: JSR emit ($20F0)
DATA $4C $CA $20      ; 20D4: JMP str ($20CA)
; cvt: $20D7 - hex digit to value; letters A-F get 9 added first
DATA $C9 $41          ; 20D7: CMP #'A'
DATA $90 $02          ; 20D9: BCC cvt1 ($20DD)
DATA $69 $08          ; 20DB: ADC #$08 - carry is set: adds 9
; cvt1: $20DD
DATA $29 $0F          ; 20DD: AND #$0F
DATA $60              ; 20DF: RTS
; skipsp: $20E0 - read the next character that is not a space
DATA $20 $E8 $20      ; 20E0: JSR rd ($20E8)
DATA $C9 $20          ; 20E3: CMP #' '
DATA $F0 $F9          ; 20E5: BEQ skipsp ($20E0)
DATA $60              ; 20E7: RTS
; rd: $20E8
DATA $20 $06 $F0      ; 20E8: JSR read_b
DATA $90 $02          ; 20EB: BCC rd1 ($20EF)
DATA $00              ; 20ED: BRK - end of input: exit code 0
DATA $00              ; 20EE: error code
; rd1: $20EF
DATA $60              ; 20EF: RTS
; emit: $20F0
DATA $20 $09 $F0      ; 20F0: JSR write_b
DATA $E6 $04          ; 20F3: INC PCL
DATA $D0 $02          ; 20F5: BNE emit1 ($20F9)
DATA $E6 $05          ; 20F7: INC PCH
; emit1: $20F9
DATA $60              ; 20F9: RTS
; Total code: $2000-$20F9 = 250 bytes

; Start address for this program (reset vector points to $2000)
DATA $00 $20
