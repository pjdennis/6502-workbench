; asm01.asm - Assembler level 1, in the syntax of version 00b
; DATA lines of hex bytes, strings and labels. Only a label's first
; character counts in 00b, so each name starts with a distinct one.
; Each instruction is on its own line with its mnemonic as a comment.
; Branch offsets are still counted by hand.

; === MNTAB: Instruction table ($2000) ===
 DATA "ADC#"    $00 $00 $69
 DATA "ADCZ"    $00 $00 $65
 DATA "ASLA"    $00 $00 $0A
 DATA "BCC"     $00 $00 $90
 DATA "BCS"     $00 $00 $B0
 DATA "BEQ"     $00 $00 $F0
 DATA "BNE"     $00 $00 $D0
 DATA "BRK"     $00 $00 $00
 DATA "CLC"     $00 $00 $18
 DATA "CMPZ,X"  $00 $00 $D5
 DATA "CMP#"    $00 $00 $C9
 DATA "CMP,Y"   $00 $00 $D9
 DATA "DEY"     $00 $00 $88
 DATA "INCZ"    $00 $00 $E6
 DATA "INX"     $00 $00 $E8
 DATA "INY"     $00 $00 $C8
 DATA "JMP"     $00 $00 $4C
 DATA "JSR"     $00 $00 $20
 DATA "LDAZ"    $00 $00 $A5
 DATA "LDA#"    $00 $00 $A9
 DATA "LDA(),Y" $00 $00 $B1
 DATA "LDA,Y"   $00 $00 $B9
 DATA "LDX#"    $00 $00 $A2
 DATA "LDY#"    $00 $00 $A0
 DATA "ORAZ"    $00 $00 $05
 DATA "RTS"     $00 $00 $60
 DATA "SBC#"    $00 $00 $E9
 DATA "SEC"     $00 $00 $38
 DATA "STA"     $00 $00 $8D
 DATA "STA(),Y" $00 $00 $91
 DATA "STAZ"    $00 $00 $85
 DATA "STAZ,X"  $00 $00 $95
 DATA "TYA"     $00 $00 $98
 DATA "DATA"    $00 $01 $00
 DATA $00                        ; DATA $00 (end of table)

; === read ===
r_read ; $20EC
 DATA $4C $06 $F0                ; JMP $F006

; === emit ===
e_emit ; $20EF
 DATA $20 $09 $F0                ; JSR $F009
 DATA $E6 $04                    ; INCZ $04
 DATA $D0 $02                    ; BNE emitdone
 DATA $E6 $05                    ; INCZ $05
; emitdone: $20F8
 DATA $60                        ; RTS

; === ignln ===
i_ignln ; $20F9
 DATA $20 r_read                 ; JSR read
 DATA $C9 $0A                    ; CMP# $0A
 DATA $D0 $F9                    ; BNE ignln
 DATA $60                        ; RTS

; === skipspc ===
s_skipspc ; $2101
 DATA $C9 " "                    ; CMP# " "
 DATA $D0 $06                    ; BNE skipspc2
 DATA $20 r_read                 ; JSR read
 DATA $4C s_skipspc              ; JMP skipspc
; skipspc2: $210B
 DATA $60                        ; RTS

; === readtoken ===
t_readtoken ; $210C
 DATA $A2 $00                    ; LDX# $00
; readtokenloop: $210E
T_readtokenloop ; $210E
 DATA $95 $06                    ; STAZ,X $06
 DATA $E8                        ; INX
 DATA $20 r_read                 ; JSR read
 DATA $C9 " "                    ; CMP# " "
 DATA $F0 $07                    ; BEQ readtokendone
 DATA $C9 $0A                    ; CMP# $0A
 DATA $F0 $03                    ; BEQ readtokendone
 DATA $4C T_readtokenloop        ; JMP readtokenloop
; readtokendone: $211F
 DATA $85 $00                    ; STAZ $00
 DATA $A9 $00                    ; LDA# $00
 DATA $95 $06                    ; STAZ,X $06
 DATA $60                        ; RTS

; === advanceintab ===
a_advanceintab ; $2126
 DATA $C8                        ; INY
 DATA $98                        ; TYA
 DATA $A0 $00                    ; LDY# $00
 DATA $18                        ; CLC
 DATA $65 $02                    ; ADCZ $02
 DATA $85 $02                    ; STAZ $02
 DATA $98                        ; TYA
 DATA $65 $03                    ; ADCZ $03
 DATA $85 $03                    ; STAZ $03
 DATA $60                        ; RTS

; === findintab ===
; findintab1 (outer loop):
f_findintab ; $2135
 DATA $B1 $02                    ; LDA(),Y $02
 DATA $D0 $02                    ; BNE findintab2
 DATA $38                        ; SEC
 DATA $60                        ; RTS
; findintab2 (inner loop): $213B
F_findintab2 ; $213B
 DATA $D9 $06 $00                ; CMP,Y $0006
 DATA $D0 $0F                    ; BNE findintab4
 DATA $C9 $00                    ; CMP# $00
 DATA $D0 $05                    ; BNE findintab3
 DATA $20 a_advanceintab         ; JSR advanceintab
 DATA $18                        ; CLC
 DATA $60                        ; RTS
; findintab3: $2149
 DATA $C8                        ; INY
 DATA $B1 $02                    ; LDA(),Y $02
 DATA $4C F_findintab2           ; JMP findintab2
; findintab4: $214F
g_findintab4 ; $214F
 DATA $B1 $02                    ; LDA(),Y $02
 DATA $F0 $04                    ; BEQ findintab5
 DATA $C8                        ; INY
 DATA $4C g_findintab4           ; JMP findintab4
; findintab5: $2157
 DATA $C8                        ; INY
 DATA $C8                        ; INY
 DATA $20 a_advanceintab         ; JSR advanceintab
 DATA $4C f_findintab            ; JMP findintab1

; === capturelabel ===
c_capturelabel ; $215F
 DATA $A9 $00                    ; LDA# $00
 DATA $85 $02                    ; STAZ $02
 DATA $A9 $30                    ; LDA# $30
 DATA $85 $03                    ; STAZ $03
 DATA $20 f_findintab            ; JSR findintab
 DATA $B0 $12                    ; BCS clnotfound
 DATA $00                        ; BRK
 DATA $01                        ; error code
 DATA "Duplicate label" $00
; clnotfound/clloop: $217E
C_clloop ; $217E
 DATA $B9 $06 $00                ; LDA,Y $0006
 DATA $91 $02                    ; STA(),Y $02
 DATA $F0 $04                    ; BEQ cldone
 DATA $C8                        ; INY
 DATA $4C C_clloop               ; JMP clloop
; cldone: $2189
 DATA $C8                        ; INY
 DATA $A5 $04                    ; LDAZ $04
 DATA $91 $02                    ; STA(),Y $02
 DATA $C8                        ; INY
 DATA $A5 $05                    ; LDAZ $05
 DATA $91 $02                    ; STA(),Y $02
 DATA $C8                        ; INY
 DATA $A9 $00                    ; LDA# $00
 DATA $91 $02                    ; STA(),Y $02
 DATA $A0 $00                    ; LDY# $00
 DATA $60                        ; RTS

; === readlabel ===
l_readlabel ; $219B
 DATA $20 t_readtoken            ; JSR readtoken
 DATA $20 c_capturelabel         ; JSR capturelabel
 DATA $A5 $00                    ; LDAZ $00
 DATA $C9 $0A                    ; CMP# $0A
 DATA $F0 $03                    ; BEQ readlabel1
 DATA $20 i_ignln                ; JSR ignln
; readlabel1: $21AA
 DATA $60                        ; RTS

; === emitoc ===
o_emitoc ; $21AB
 DATA $A9 $00                    ; LDA# $00
 DATA $85 $02                    ; STAZ $02
 DATA $A9 $20                    ; LDA# $20
 DATA $85 $03                    ; STAZ $03
 DATA $20 f_findintab            ; JSR findintab
 DATA $90 $13                    ; BCC emitoc1
 DATA $00                        ; BRK
 DATA $02                        ; error code
 DATA "Opcode not found" $00
; emitoc1: $21CB
 DATA $B1 $02                    ; LDA(),Y $02
 DATA $F0 $01                    ; BEQ emitoc2
 DATA $60                        ; RTS
; emitoc2: $21D0
 DATA $C8                        ; INY
 DATA $B1 $02                    ; LDA(),Y $02
 DATA $88                        ; DEY
 DATA $20 e_emit                 ; JSR emit
 DATA $60                        ; RTS

; === emitqu ===
q_emitqu ; $21D8
 DATA $20 r_read                 ; JSR read
 DATA $C9 $22                    ; CMP# "\""
 DATA $D0 $04                    ; BNE emitqu1
 DATA $20 r_read                 ; JSR read
 DATA $60                        ; RTS
; emitqu1: $21E3
 DATA $C9 $5C                    ; CMP# "\\"
 DATA $D0 $09                    ; BNE emitqu2
 DATA $20 r_read                 ; JSR read
 DATA $C9 "n"                    ; CMP# "n"
 DATA $D0 $02                    ; BNE emitqu2
 DATA $A9 $0A                    ; LDA# $0A
; emitqu2: $21F0
 DATA $20 e_emit                 ; JSR emit
 DATA $4C q_emitqu               ; JMP emitqu

; === convhex ===
v_convhex ; $21F6
 DATA $C9 "A"                    ; CMP# "A"
 DATA $90 $06                    ; BCC convhex1
 DATA $E9 "A"                    ; SBC# "A"
 DATA $18                        ; CLC
 DATA $69 $0A                    ; ADC# $0A
 DATA $60                        ; RTS
; convhex1: $2200
 DATA $38                        ; SEC
 DATA $E9 "0"                    ; SBC# "0"
 DATA $60                        ; RTS

; === readhex ===
h_readhex ; $2204
 DATA $20 v_convhex              ; JSR convhex
 DATA $0A                        ; ASLA
 DATA $0A                        ; ASLA
 DATA $0A                        ; ASLA
 DATA $0A                        ; ASLA
 DATA $85 $00                    ; STAZ $00
 DATA $20 r_read                 ; JSR read
 DATA $20 v_convhex              ; JSR convhex
 DATA $05 $00                    ; ORAZ $00
 DATA $60                        ; RTS

; === emithex ===
x_emithex ; $2216
 DATA $20 r_read                 ; JSR read
; emithex2: $2219
 DATA $20 h_readhex              ; JSR readhex
 DATA $85 $01                    ; STAZ $01
 DATA $20 r_read                 ; JSR read
 DATA $C9 " "                    ; CMP# " "
 DATA $F0 $11                    ; BEQ emithex3
 DATA $C9 $0A                    ; CMP# $0A
 DATA $F0 $0D                    ; BEQ emithex3
 DATA $C9 ";"                    ; CMP# ";"
 DATA $F0 $09                    ; BEQ emithex3
 DATA $20 h_readhex              ; JSR readhex
 DATA $20 e_emit                 ; JSR emit
 DATA $20 r_read                 ; JSR read
; emithex3: $2236
 DATA $85 $00                    ; STAZ $00
 DATA $A5 $01                    ; LDAZ $01
 DATA $20 e_emit                 ; JSR emit
 DATA $A5 $00                    ; LDAZ $00
 DATA $60                        ; RTS

; === emitlabel ===
L_emitlabel ; $2240
 DATA $20 t_readtoken            ; JSR readtoken
 DATA $A9 $00                    ; LDA# $00
 DATA $85 $02                    ; STAZ $02
 DATA $A9 $30                    ; LDA# $30
 DATA $85 $03                    ; STAZ $03
 DATA $20 f_findintab            ; JSR findintab
 DATA $90 $12                    ; BCC emitlabel2
 DATA $00                        ; BRK
 DATA $03                        ; error code
 DATA "Label not found" $00
; emitlabel2: $2262
 DATA $B1 $02                    ; LDA(),Y $02
 DATA $20 e_emit                 ; JSR emit
 DATA $C8                        ; INY
 DATA $B1 $02                    ; LDA(),Y $02
 DATA $88                        ; DEY
 DATA $20 e_emit                 ; JSR emit
 DATA $A5 $00                    ; LDAZ $00
 DATA $60                        ; RTS

; === checkforend ===
k_checkforend ; $2271
 DATA $C9 ";"                    ; CMP# ";"
 DATA $D0 $05                    ; BNE checkforend1
 DATA $20 i_ignln                ; JSR ignln
 DATA $38                        ; SEC
 DATA $60                        ; RTS
; checkforend1: $227A
 DATA $C9 $0A                    ; CMP# $0A
 DATA $D0 $02                    ; BNE checkforend2
 DATA $38                        ; SEC
 DATA $60                        ; RTS
; checkforend2: $2280
 DATA $18                        ; CLC
 DATA $60                        ; RTS

; === assemble ===
; lnloop:
n_lnloop ; $2282
 DATA $20 r_read                 ; JSR read
 DATA $90 $01                    ; BCC lnloop1
 DATA $60                        ; RTS
; lnloop1: $2288
 DATA $20 k_checkforend          ; JSR checkforend
 DATA $90 $03                    ; BCC lnloop2
 DATA $4C n_lnloop               ; JMP lnloop
; lnloop2: $2290
 DATA $C9 " "                    ; CMP# " "
 DATA $F0 $06                    ; BEQ lnloop3
 DATA $20 l_readlabel            ; JSR readlabel
 DATA $4C n_lnloop               ; JMP lnloop
; lnloop3: $229A
 DATA $20 s_skipspc              ; JSR skipspc
 DATA $20 k_checkforend          ; JSR checkforend
 DATA $90 $03                    ; BCC lnloop4
 DATA $4C n_lnloop               ; JMP lnloop
; lnloop4: $22A5
 DATA $20 t_readtoken            ; JSR readtoken
 DATA $20 o_emitoc               ; JSR emitoc
 DATA $A5 $00                    ; LDAZ $00
; tokloop: $22AD
p_tokloop ; $22AD
 DATA $20 s_skipspc              ; JSR skipspc
 DATA $20 k_checkforend          ; JSR checkforend
 DATA $90 $03                    ; BCC tokloop1
 DATA $4C n_lnloop               ; JMP lnloop
; tokloop1: $22B8
 DATA $C9 $22                    ; CMP# "\""
 DATA $D0 $06                    ; BNE tokloop2
 DATA $20 q_emitqu               ; JSR emitqu
 DATA $4C p_tokloop              ; JMP tokloop
; tokloop2: $22C2
 DATA $C9 "$"                    ; CMP# "$"
 DATA $D0 $06                    ; BNE tokloop3
 DATA $20 x_emithex              ; JSR emithex
 DATA $4C p_tokloop              ; JMP tokloop
; tokloop3: $22CC
 DATA $20 L_emitlabel            ; JSR emitlabel
 DATA $4C p_tokloop              ; JMP tokloop

; === start ===
S_start ; $22D2
 DATA $A9 $00                    ; LDA# $00
 DATA $85 $04                    ; STAZ $04
 DATA $A9 $20                    ; LDA# $20
 DATA $85 $05                    ; STAZ $05
 DATA $A9 $00                    ; LDA# $00
 DATA $8D $00 $30                ; STA $3000
 DATA $A0 $00                    ; LDY# $00
 DATA $20 n_lnloop               ; JSR assemble
 DATA $00                        ; BRK
 DATA $00                        ; DATA $00 (success)

; Start address (reset vector points to $22D2)
 DATA S_start
