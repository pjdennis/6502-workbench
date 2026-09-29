; asm1.asm - Assembler level 1 (asm4b translated to DATA format)
; Each instruction on its own line with original source as comment

; === MNTAB: Instruction table ($2000) ===
 DATA $41 $44 $43 $23 $00 $00 $69              ; DATA "ADC#"    $00 $00 $69
 DATA $41 $44 $43 $5A $00 $00 $65              ; DATA "ADCZ"    $00 $00 $65
 DATA $41 $53 $4C $41 $00 $00 $0A              ; DATA "ASLA"    $00 $00 $0A
 DATA $42 $43 $43 $00 $00 $90                  ; DATA "BCC"     $00 $00 $90
 DATA $42 $43 $53 $00 $00 $B0                  ; DATA "BCS"     $00 $00 $B0
 DATA $42 $45 $51 $00 $00 $F0                  ; DATA "BEQ"     $00 $00 $F0
 DATA $42 $4E $45 $00 $00 $D0                  ; DATA "BNE"     $00 $00 $D0
 DATA $42 $52 $4B $00 $00 $00                  ; DATA "BRK"     $00 $00 $00
 DATA $43 $4C $43 $00 $00 $18                  ; DATA "CLC"     $00 $00 $18
 DATA $43 $4D $50 $5A $2C $58 $00 $00 $D5      ; DATA "CMPZ,X"  $00 $00 $D5
 DATA $43 $4D $50 $23 $00 $00 $C9              ; DATA "CMP#"    $00 $00 $C9
 DATA $43 $4D $50 $2C $59 $00 $00 $D9          ; DATA "CMP,Y"   $00 $00 $D9
 DATA $44 $45 $59 $00 $00 $88                  ; DATA "DEY"     $00 $00 $88
 DATA $49 $4E $43 $5A $00 $00 $E6              ; DATA "INCZ"    $00 $00 $E6
 DATA $49 $4E $58 $00 $00 $E8                  ; DATA "INX"     $00 $00 $E8
 DATA $49 $4E $59 $00 $00 $C8                  ; DATA "INY"     $00 $00 $C8
 DATA $4A $4D $50 $00 $00 $4C                  ; DATA "JMP"     $00 $00 $4C
 DATA $4A $53 $52 $00 $00 $20                  ; DATA "JSR"     $00 $00 $20
 DATA $4C $44 $41 $5A $00 $00 $A5              ; DATA "LDAZ"    $00 $00 $A5
 DATA $4C $44 $41 $23 $00 $00 $A9              ; DATA "LDA#"    $00 $00 $A9
 DATA $4C $44 $41 $28 $29 $2C $59 $00 $00 $B1  ; DATA "LDA(),Y" $00 $00 $B1
 DATA $4C $44 $41 $2C $59 $00 $00 $B9          ; DATA "LDA,Y"   $00 $00 $B9
 DATA $4C $44 $58 $23 $00 $00 $A2              ; DATA "LDX#"    $00 $00 $A2
 DATA $4C $44 $59 $23 $00 $00 $A0              ; DATA "LDY#"    $00 $00 $A0
 DATA $4F $52 $41 $5A $00 $00 $05              ; DATA "ORAZ"    $00 $00 $05
 DATA $52 $54 $53 $00 $00 $60                  ; DATA "RTS"     $00 $00 $60
 DATA $53 $42 $43 $23 $00 $00 $E9              ; DATA "SBC#"    $00 $00 $E9
 DATA $53 $45 $43 $00 $00 $38                  ; DATA "SEC"     $00 $00 $38
 DATA $53 $54 $41 $00 $00 $8D                  ; DATA "STA"     $00 $00 $8D
 DATA $53 $54 $41 $28 $29 $2C $59 $00 $00 $91  ; DATA "STA(),Y" $00 $00 $91
 DATA $53 $54 $41 $5A $00 $00 $85              ; DATA "STAZ"    $00 $00 $85
 DATA $53 $54 $41 $5A $2C $58 $00 $00 $95      ; DATA "STAZ,X"  $00 $00 $95
 DATA $54 $59 $41 $00 $00 $98                  ; DATA "TYA"     $00 $00 $98
 DATA $44 $41 $54 $41 $00 $01 $00              ; DATA "DATA"    $00 $01 $00
 DATA $00                                      ; DATA $00 (end of table)

; === read: $20EC ===
 DATA $4C $06 $F0                 ; JMP $F006

; === emit: $20EF ===
 DATA $20 $09 $F0                 ; JSR $F009
 DATA $E6 $04                     ; INCZ $04
 DATA $D0 $02                     ; BNE emitdone
 DATA $E6 $05                     ; INCZ $05
; emitdone: $20F8
 DATA $60                         ; RTS

; === ignln: $20F9 ===
 DATA $20 $EC $20                 ; JSR read
 DATA $C9 $0A                     ; CMP# $0A
 DATA $D0 $F9                     ; BNE ignln
 DATA $60                         ; RTS

; === skipspc: $2101 ===
 DATA $C9 $20                     ; CMP# " "
 DATA $D0 $06                     ; BNE skipspc2
 DATA $20 $EC $20                 ; JSR read
 DATA $4C $01 $21                 ; JMP skipspc
; skipspc2: $210C
 DATA $60                         ; RTS

; === readtoken: $210D ===
 DATA $A2 $00                     ; LDX# $00
; readtokenloop: $210F
 DATA $95 $06                     ; STAZ,X $06
 DATA $E8                         ; INX
 DATA $20 $EC $20                 ; JSR read
 DATA $C9 $20                     ; CMP# " "
 DATA $F0 $07                     ; BEQ readtokendone
 DATA $C9 $0A                     ; CMP# $0A
 DATA $F0 $03                     ; BEQ readtokendone
 DATA $4C $0E $21                 ; JMP readtokenloop
; readtokendone: $2120
 DATA $85 $00                     ; STAZ $00
 DATA $A9 $00                     ; LDA# $00
 DATA $95 $06                     ; STAZ,X $06
 DATA $60                         ; RTS

; === advanceintab: $2126 ===
 DATA $C8                         ; INY
 DATA $98                         ; TYA
 DATA $A0 $00                     ; LDY# $00
 DATA $18                         ; CLC
 DATA $65 $02                     ; ADCZ $02
 DATA $85 $02                     ; STAZ $02
 DATA $98                         ; TYA
 DATA $65 $03                     ; ADCZ $03
 DATA $85 $03                     ; STAZ $03
 DATA $60                         ; RTS

; === findintab: $2135 ===
; findintab1 (outer loop):
 DATA $B1 $02                     ; LDA(),Y $02
 DATA $D0 $02                     ; BNE findintab2
 DATA $38                         ; SEC
 DATA $60                         ; RTS
; findintab2 (inner loop): $213B
 DATA $D9 $06 $00                 ; CMP,Y $0006
 DATA $D0 $0F                     ; BNE findintab4
 DATA $C9 $00                     ; CMP# $00
 DATA $D0 $05                     ; BNE findintab3
 DATA $20 $26 $21                 ; JSR advanceintab
 DATA $18                         ; CLC
 DATA $60                         ; RTS
; findintab3: $214A
 DATA $C8                         ; INY
 DATA $B1 $02                     ; LDA(),Y $02
 DATA $4C $3B $21                 ; JMP findintab2
; findintab4: $2150
 DATA $B1 $02                     ; LDA(),Y $02
 DATA $F0 $04                     ; BEQ findintab5
 DATA $C8                         ; INY
 DATA $4C $4F $21                 ; JMP findintab4
; findintab5: $2158
 DATA $C8                         ; INY
 DATA $C8                         ; INY
 DATA $20 $26 $21                 ; JSR advanceintab
 DATA $4C $35 $21                 ; JMP findintab1

; === capturelabel: $215F ===
 DATA $A9 $00                     ; LDA# $00
 DATA $85 $02                     ; STAZ $02
 DATA $A9 $30                     ; LDA# $30
 DATA $85 $03                     ; STAZ $03
 DATA $20 $35 $21                 ; JSR findintab
 DATA $B0 $12                     ; BCS clnotfound
 DATA $00                         ; BRK
 DATA $01                         ; error code
 DATA $44 $75 $70 $6C $69 $63 $61 $74 $65 $20 $6C $61 $62 $65 $6C $00  ; "Duplicate label"
; clnotfound/clloop: $217E
 DATA $B9 $06 $00                 ; LDA,Y $0006
 DATA $91 $02                     ; STA(),Y $02
 DATA $F0 $04                     ; BEQ cldone
 DATA $C8                         ; INY
 DATA $4C $7E $21                 ; JMP clloop
; cldone: $2189
 DATA $C8                         ; INY
 DATA $A5 $04                     ; LDAZ $04
 DATA $91 $02                     ; STA(),Y $02
 DATA $C8                         ; INY
 DATA $A5 $05                     ; LDAZ $05
 DATA $91 $02                     ; STA(),Y $02
 DATA $C8                         ; INY
 DATA $A9 $00                     ; LDA# $00
 DATA $91 $02                     ; STA(),Y $02
 DATA $A0 $00                     ; LDY# $00
 DATA $60                         ; RTS

; === readlabel: $219B ===
 DATA $20 $0C $21                 ; JSR readtoken
 DATA $20 $5F $21                 ; JSR capturelabel
 DATA $A5 $00                     ; LDAZ $00
 DATA $C9 $0A                     ; CMP# $0A
 DATA $F0 $03                     ; BEQ readlabel1
 DATA $20 $F9 $20                 ; JSR ignln
; readlabel1: $21AA
 DATA $60                         ; RTS

; === emitoc: $21AB ===
 DATA $A9 $00                     ; LDA# $00
 DATA $85 $02                     ; STAZ $02
 DATA $A9 $20                     ; LDA# $20
 DATA $85 $03                     ; STAZ $03
 DATA $20 $35 $21                 ; JSR findintab
 DATA $90 $13                     ; BCC emitoc1
 DATA $00                         ; BRK
 DATA $02                         ; error code
 DATA $4F $70 $63 $6F $64 $65 $20 $6E $6F $74 $20 $66 $6F $75 $6E $64 $00  ; "Opcode not found"
; emitoc1: $21CD
 DATA $B1 $02                     ; LDA(),Y $02
 DATA $F0 $01                     ; BEQ emitoc2
 DATA $60                         ; RTS
; emitoc2: $21D2
 DATA $C8                         ; INY
 DATA $B1 $02                     ; LDA(),Y $02
 DATA $88                         ; DEY
 DATA $20 $EF $20                 ; JSR emit
 DATA $60                         ; RTS

; === emitqu: $21D8 ===
 DATA $20 $EC $20                 ; JSR read
 DATA $C9 $22                     ; CMP# "\""
 DATA $D0 $04                     ; BNE emitqu1
 DATA $20 $EC $20                 ; JSR read
 DATA $60                         ; RTS
; emitqu1: $21E3
 DATA $C9 $5C                     ; CMP# "\\"
 DATA $D0 $09                     ; BNE emitqu2
 DATA $20 $EC $20                 ; JSR read
 DATA $C9 $6E                     ; CMP# "n"
 DATA $D0 $02                     ; BNE emitqu2
 DATA $A9 $0A                     ; LDA# $0A
; emitqu2: $21F0
 DATA $20 $EF $20                 ; JSR emit
 DATA $4C $D8 $21                 ; JMP emitqu

; === convhex: $21F6 ===
 DATA $C9 $41                     ; CMP# "A"
 DATA $90 $06                     ; BCC convhex1
 DATA $E9 $41                     ; SBC# "A"
 DATA $18                         ; CLC
 DATA $69 $0A                     ; ADC# $0A
 DATA $60                         ; RTS
; convhex1: $2200
 DATA $38                         ; SEC
 DATA $E9 $30                     ; SBC# "0"
 DATA $60                         ; RTS

; === readhex: $2204 ===
 DATA $20 $F6 $21                 ; JSR convhex
 DATA $0A                         ; ASLA
 DATA $0A                         ; ASLA
 DATA $0A                         ; ASLA
 DATA $0A                         ; ASLA
 DATA $85 $00                     ; STAZ $00
 DATA $20 $EC $20                 ; JSR read
 DATA $20 $F6 $21                 ; JSR convhex
 DATA $05 $00                     ; ORAZ $00
 DATA $60                         ; RTS

; === emithex: $2216 ===
 DATA $20 $EC $20                 ; JSR read
; emithex2: $2219
 DATA $20 $04 $22                 ; JSR readhex
 DATA $85 $01                     ; STAZ $01
 DATA $20 $EC $20                 ; JSR read
 DATA $C9 $20                     ; CMP# " "
 DATA $F0 $11                     ; BEQ emithex3
 DATA $C9 $0A                     ; CMP# $0A
 DATA $F0 $0D                     ; BEQ emithex3
 DATA $C9 $3B                     ; CMP# ";"
 DATA $F0 $09                     ; BEQ emithex3
 DATA $20 $04 $22                 ; JSR readhex
 DATA $20 $EF $20                 ; JSR emit
 DATA $20 $EC $20                 ; JSR read
; emithex3: $2238
 DATA $85 $00                     ; STAZ $00
 DATA $A5 $01                     ; LDAZ $01
 DATA $20 $EF $20                 ; JSR emit
 DATA $A5 $00                     ; LDAZ $00
 DATA $60                         ; RTS

; === emitlabel: $2240 ===
 DATA $20 $0C $21                 ; JSR readtoken
 DATA $A9 $00                     ; LDA# $00
 DATA $85 $02                     ; STAZ $02
 DATA $A9 $30                     ; LDA# $30
 DATA $85 $03                     ; STAZ $03
 DATA $20 $35 $21                 ; JSR findintab
 DATA $90 $12                     ; BCC emitlabel2
 DATA $00                         ; BRK
 DATA $03                         ; error code
 DATA $4C $61 $62 $65 $6C $20 $6E $6F $74 $20 $66 $6F $75 $6E $64 $00  ; "Label not found"
; emitlabel2: $2264
 DATA $B1 $02                     ; LDA(),Y $02
 DATA $20 $EF $20                 ; JSR emit
 DATA $C8                         ; INY
 DATA $B1 $02                     ; LDA(),Y $02
 DATA $88                         ; DEY
 DATA $20 $EF $20                 ; JSR emit
 DATA $A5 $00                     ; LDAZ $00
 DATA $60                         ; RTS

; === checkforend: $2271 ===
 DATA $C9 $3B                     ; CMP# ";"
 DATA $D0 $05                     ; BNE checkforend1
 DATA $20 $F9 $20                 ; JSR ignln
 DATA $38                         ; SEC
 DATA $60                         ; RTS
; checkforend1: $227B
 DATA $C9 $0A                     ; CMP# $0A
 DATA $D0 $02                     ; BNE checkforend2
 DATA $38                         ; SEC
 DATA $60                         ; RTS
; checkforend2: $2281
 DATA $18                         ; CLC
 DATA $60                         ; RTS

; === assemble: $2282 ===
; lnloop:
 DATA $20 $EC $20                 ; JSR read
 DATA $90 $01                     ; BCC lnloop1
 DATA $60                         ; RTS
; lnloop1: $2288
 DATA $20 $71 $22                 ; JSR checkforend
 DATA $90 $03                     ; BCC lnloop2
 DATA $4C $82 $22                 ; JMP lnloop
; lnloop2: $2290
 DATA $C9 $20                     ; CMP# " "
 DATA $F0 $06                     ; BEQ lnloop3
 DATA $20 $9B $21                 ; JSR readlabel
 DATA $4C $82 $22                 ; JMP lnloop
; lnloop3: $229B
 DATA $20 $01 $21                 ; JSR skipspc
 DATA $20 $71 $22                 ; JSR checkforend
 DATA $90 $03                     ; BCC lnloop4
 DATA $4C $82 $22                 ; JMP lnloop
; lnloop4: $22A7
 DATA $20 $0C $21                 ; JSR readtoken
 DATA $20 $AB $21                 ; JSR emitoc
 DATA $A5 $00                     ; LDAZ $00
; tokloop: $22AD
 DATA $20 $01 $21                 ; JSR skipspc
 DATA $20 $71 $22                 ; JSR checkforend
 DATA $90 $03                     ; BCC tokloop1
 DATA $4C $82 $22                 ; JMP lnloop
; tokloop1: $22B9
 DATA $C9 $22                     ; CMP# "\""
 DATA $D0 $06                     ; BNE tokloop2
 DATA $20 $D8 $21                 ; JSR emitqu
 DATA $4C $AD $22                 ; JMP tokloop
; tokloop2: $22C4
 DATA $C9 $24                     ; CMP# "$"
 DATA $D0 $06                     ; BNE tokloop3
 DATA $20 $16 $22                 ; JSR emithex
 DATA $4C $AD $22                 ; JMP tokloop
; tokloop3: $22CF
 DATA $20 $40 $22                 ; JSR emitlabel
 DATA $4C $AD $22                 ; JMP tokloop

; === start: $22D2 ===
 DATA $A9 $00                     ; LDA# $00
 DATA $85 $04                     ; STAZ $04
 DATA $A9 $20                     ; LDA# $20
 DATA $85 $05                     ; STAZ $05
 DATA $A9 $00                     ; LDA# $00
 DATA $8D $00 $30                 ; STA $3000
 DATA $A0 $00                     ; LDY# $00
 DATA $20 $82 $22                 ; JSR assemble
 DATA $00                         ; BRK
 DATA $00                         ; DATA $00 (success)

; Start address (reset vector points to $22D2)
 DATA $D2 $22
