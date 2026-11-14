; module if_while, cpu 6502

; function if_while.simple
;   no slots
if_while__simple
    LDA if_while__a
    CMP if_while__b
    BNE .L000D
    LDA #$01
    STA if_while__r
.L000D
    RTS

; function if_while.parts
;   no slots
if_while__parts
    LDA if_while__a
    CMP #$01
    BNE .L000D
    LDA #$0A
    STA if_while__r
    RTS
.L000D
    CMP #$02
    BNE .L0017
    LDA #$14
    STA if_while__r
    RTS
.L0017
    CMP #$03
    BNE .L0021
    LDA #$1E
    STA if_while__r
    RTS
.L0021
    LDA #$00
    STA if_while__r
    RTS

; function if_while.returns
;   no slots
if_while__returns
    LDA if_while__a
    CMP if_while__b
    BCS .L0009
    RTS
.L0009
    LDA if_while__b
    RTS

; function if_while.nested
;   no slots
if_while__nested
    LDA if_while__a
    BEQ .L0015
    LDA if_while__b
    BEQ .L0010
    LDA #$01
    STA if_while__r
    RTS
.L0010
    LDA #$02
    STA if_while__r
.L0015
    RTS

; function if_while.counting
;   no slots
if_while__counting
    LDA #$00
    STA if_while__i
.L0005
    LDA if_while__i
    CMP if_while__n
    BCS .L0013
    INC if_while__i
    JMP .L0005
.L0013
    RTS

; function if_while.summing
;   no slots
if_while__summing
    LDA #$00
    STA if_while__r
    LDA if_while__n
    STA if_while__i
.L000B
    LDA if_while__i
    BEQ .L0020
    CLC
    LDA if_while__r
    ADC if_while__i
    STA if_while__r
    DEC if_while__i
    JMP .L000B
.L0020
    LDA if_while__r
    RTS

; function if_while.two_levels
;   no slots
if_while__two_levels
    LDA #$00
    STA if_while__a
.L0005
    LDA if_while__a
    CMP if_while__n
    BCS .L0026
    LDA #$00
    STA if_while__b
.L0012
    LDA if_while__b
    CMP if_while__a
    BCS .L0020
    INC if_while__b
    JMP .L0012
.L0020
    INC if_while__a
    JMP .L0005
.L0026
    RTS

; variable if_while.a: size 1, class 1 (either), weight 29

; variable if_while.b: size 1, class 1 (either), weight 40

; variable if_while.i: size 1, class 1 (either), weight 22

; variable if_while.n: size 1, class 1 (either), weight 9

; variable if_while.r: size 1, class 1 (either), weight 17
