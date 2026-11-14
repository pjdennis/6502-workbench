; module logic, cpu 6502

; function logic.both
;   no slots
logic__both
    LDA logic__a
    CMP logic__b
    BCS .L0015
    LDA logic__b
    CMP logic__c
    BCS .L0015
    LDA #$01
    STA logic__r
.L0015
    RTS

; function logic.either
;   no slots
logic__either
    LDA logic__a
    CMP logic__b
    BCC .L0010
    LDA logic__b
    CMP logic__c
    BCS .L0015
.L0010
    LDA #$01
    STA logic__r
.L0015
    RTS

; function logic.inverted
;   no slots
logic__inverted
    LDA logic__a
    CMP logic__b
    BCC .L000D
    LDA #$01
    STA logic__r
.L000D
    LDA logic__a
    CMP logic__b
    BCS .L001D
    LDA logic__b
    CMP logic__c
    BCC .L0022
.L001D
    LDA #$02
    STA logic__r
.L0022
    RTS

; function logic.mixed
;   no slots
logic__mixed
    LDA logic__a
    CMP #$01
    BNE .L000E
    LDA logic__b
    CMP #$02
    BEQ .L0015
.L000E
    LDA logic__c
    CMP #$03
    BNE .L001A
.L0015
    LDA #$01
    STA logic__r
.L001A
    LDA logic__a
    CMP #$01
    BNE .L0034
    LDA logic__b
    CMP #$02
    BEQ .L002F
    LDA logic__c
    CMP #$03
    BNE .L0034
.L002F
    LDA #$02
    STA logic__r
.L0034
    RTS

; function logic.variables
;   no slots
logic__variables
    LDA logic__f
    BEQ .L000A
    LDA #$01
    STA logic__r
.L000A
    LDA logic__f
    BNE .L0014
    LDA #$02
    STA logic__r
.L0014
    LDA logic__f
    BEQ .L0023
    LDA logic__g
    BEQ .L0023
    LDA #$03
    STA logic__r
.L0023
    RTS

; function logic.values
;   no slots
logic__values
    LDA logic__a
    CMP logic__b
    LDA #$00
    ROL
    STA logic__f
    LDA logic__a
    CMP logic__b
    LDA #$00
    ROL
    EOR #$01
    STA logic__f
    LDA logic__a
    CMP logic__b
    BNE .L0026
    LDA #$01
    BNE .L0028
.L0026
    LDA #$00
.L0028
    STA logic__f
    LDA logic__a
    CMP logic__b
    BCS .L003F
    LDA logic__b
    CMP logic__c
    BCS .L003F
    LDA #$01
    BNE .L0041
.L003F
    LDA #$00
.L0041
    STA logic__f
    LDA logic__g
    BNE .L004D
    LDA #$01
    BNE .L004F
.L004D
    LDA #$00
.L004F
    STA logic__f
    LDA #$01
    STA logic__f
    RTS

; function logic.compared
;   slot 0 $t1: size 1, class 1 (either), temp, weight 2
logic__compared
    LDA logic__f
    CMP logic__g
    BNE .L000D
    LDA #$01
    STA logic__r
.L000D
    LDA logic__f
    CMP #$01
    BEQ .L0019
    LDA #$02
    STA logic__r
.L0019
    LDA logic__a
    CMP logic__b
    LDA #$00
    ROL
    EOR #$01
    STA logic__compared__St1
    LDA logic__b
    CMP logic__c
    LDA #$00
    ROL
    EOR #$01
    CMP logic__compared__St1
    BNE .L003B
    LDA #$01
    BNE .L003D
.L003B
    LDA #$00
.L003D
    STA logic__f
    RTS

; function logic.known
;   no slots
logic__known
    LDA #$01
    STA logic__r
    LDA logic__f
    LDA #$02
    STA logic__r
    LDA logic__f
.L0010
    INC logic__r
    JMP .L0010

; variable logic.a: size 1, class 1 (either), weight 11

; variable logic.b: size 1, class 1 (either), weight 16

; variable logic.c: size 1, class 1 (either), weight 7

; variable logic.r: size 1, class 1 (either), weight 18

; variable logic.f: size 1, class 1 (either), weight 14

; variable logic.g: size 1, class 1 (either), weight 3
