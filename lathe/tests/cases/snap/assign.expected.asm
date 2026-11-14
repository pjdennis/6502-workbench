; module assign, cpu 6502

abs_d020 = $D020
zp_80 = $80

; function assign.plain
;   no slots
assign__plain
    LDA assign__b
    STA assign__a
    LDA assign__v
    STA assign__w
    LDX assign__v+$01
    STX assign__w+$01
    LDA assign__a
    STA assign__w
    LDA #$00
    STA assign__w+$01
    LDA #$07
    STA assign__a
    LDA #$34
    STA assign__w
    LDA #$12
    STA assign__w+$01
    LDA #$07
    STA assign__w
    STA assign__w+$01
    RTS

; function assign.by_one
;   no slots
assign__by_one
    INC assign__a
    DEC assign__a
    INC assign__a
    INC assign__a
    INC assign__w
    BNE .L0014
    INC assign__w+$01
.L0014
    LDA assign__w
    BNE .L001C
    DEC assign__w+$01
.L001C
    DEC assign__w
    RTS

; function assign.bytes
;   no slots
assign__bytes
    CLC
    LDA assign__a
    ADC assign__b
    STA assign__a
    SEC
    SBC assign__b
    STA assign__a
    AND #$0F
    STA assign__a
    ORA assign__b
    STA assign__a
    EOR #$FF
    STA assign__a
    CLC
    ADC #$02
    STA assign__a
    RTS

; function assign.words
;   no slots
assign__words
    CLC
    LDA assign__w
    ADC assign__v
    STA assign__w
    LDA assign__w+$01
    ADC assign__v+$01
    STA assign__w+$01
    CLC
    LDA assign__w
    ADC assign__a
    STA assign__w
    BCC .L0022
    INC assign__w+$01
.L0022
    SEC
    SBC assign__a
    STA assign__w
    BCS .L002E
    DEC assign__w+$01
.L002E
    CLC
    ADC #$2C
    STA assign__w
    LDA assign__w+$01
    ADC #$01
    STA assign__w+$01
    LDA #$00
    STA assign__w+$01
    ORA #$80
    STA assign__w+$01
    RTS

; function assign.computed
;   no slots
assign__computed
    LDA assign__b
    AND #$03
    CLC
    ADC assign__a
    STA assign__a
    LDA assign__b
    AND #$03
    EOR #$FF
    SEC
    ADC assign__a
    STA assign__a
    LDA assign__v
    AND #$0F
    TAY
    LDA assign__v+$01
    AND #$0F
    TAX
    TYA
    CLC
    ADC assign__w
    STA assign__w
    TXA
    ADC assign__w+$01
    STA assign__w+$01
    RTS

; function assign.halves
;   no slots
assign__halves
    LDA assign__a
    STA assign__w
    LDA #$00
    STA assign__w+$01
    STA assign__a
    INC assign__w+$01
    CLC
    LDA assign__w
    ADC assign__v+$01
    STA assign__b
    RTS

; function assign.fixed
;   no slots
assign__fixed
    LDA #$01
    STA abs_d020
    STA abs_d020
    LDA abs_d020
    STA assign__a
    LDA abs_d020
    STA assign__b
    LDA assign__a
    STA zp_80
    INC zp_80
    LDA abs_d020
    ORA #$80
    STA abs_d020
    RTS

; variable assign.a: size 1, class 1 (either), weight 24

; variable assign.b: size 1, class 1 (either), weight 8

; variable assign.w: size 2, class 1 (either), weight 35

; variable assign.v: size 2, class 1 (either), weight 7
