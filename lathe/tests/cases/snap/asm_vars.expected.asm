; module asm_vars, cpu 6502
; imports: libshared

abs_d020 = $D020
zp_80 = $80
zp_81 = $81

; function asm_vars.add
;   slot 0 amount: size 1, class 1 (either), param, weight 2
;   slot 1 scale: size 2, class 1 (either), param, weight 2
;   slot 2 acc: size 2, class 1 (either), local, weight 7
asm_vars__add
    STA asm_vars__add__amount
    LDA asm_vars__add__scale
    STA asm_vars__add__acc
    LDX asm_vars__add__scale+$01
    STX asm_vars__add__acc+$01
    INC asm_vars__add__calls
    CLC
    LDA asm_vars__add__acc
    ADC asm_vars__add__amount
    STA asm_vars__add__acc
    BCC .L0021
    INC asm_vars__add__acc+$01
.L0021
    LDA asm_vars__add__acc
    STA asm_vars__total
    LDX asm_vars__add__acc+$01
    STX asm_vars__total+$01
    RTS

; variable asm_vars.add.calls: size 1, class 1 (either), weight 1

; function asm_vars.indirect
;   slot 0 index: size 1, class 1 (either), param, weight 2
;   slot 1 p: size 2, class 0 (zp), local, weight 3
asm_vars__indirect
    STA asm_vars__indirect__index
    LDA asm_vars__ptr
    STA asm_vars__indirect__p
    LDX asm_vars__ptr+$01
    STX asm_vars__indirect__p+$01
    LDY asm_vars__indirect__index
    LDA (asm_vars__indirect__p),Y
    STA (asm_vars__ptr),Y
    LDX #$00
    STX zp_80,Y
    STY zp_81
    RTS

; function asm_vars.other
;   no slots
asm_vars__other
    LDA libshared__count
    STA libshared__total+$01
    LDY #$00
    LDA (libshared__pointer),Y
    STA abs_d020
    RTS

; function asm_vars.loops
;   slot 0 n: size 1, class 1 (either), param, weight 9
asm_vars__loops
    STA asm_vars__loops__n
.L0003
    LDA asm_vars__loops__n
    BEQ .L000E
    DEC asm_vars__loops__n
    JMP .L0003
.L000E
    RTS

; function asm_vars.main: exported
;   no slots
;   calls asm_vars.add
;   calls asm_vars.indirect
;   calls asm_vars.other
;   calls asm_vars.loops
asm_vars__main
    LDA #$02
    STA asm_vars__add__scale
    LDA #$00
    STA asm_vars__add__scale+$01
    LDA #$01
    JSR asm_vars__add
    STA asm_vars__total
    STX asm_vars__total+$01
    LDA #$03
    JSR asm_vars__indirect
    JSR asm_vars__other
    LDA #$04
    JMP asm_vars__loops

; variable asm_vars.total: size 2, class 1 (either), weight 4

; variable asm_vars.ptr: size 2, class 0 (zp), weight 3
