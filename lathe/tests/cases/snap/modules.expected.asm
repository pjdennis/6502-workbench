; module modules, cpu 6502
; imports: libshared

abs_d020 = $D020
zp_40 = $40

; function modules.constants
;   no slots
modules__constants
    LDA #$2C
    STA modules__w
    LDA #$01
    STA modules__w+$01
    LDA #$08
    STA modules__b
    LDA #$FF
    STA modules__i
    STA modules__i+$01
    LDA #$01
    STA modules__b
    RTS

; function modules.variables
;   no slots
modules__variables
    LDA #$03
    STA libshared__count
    STA modules__b
    CLC
    LDA libshared__total
    ADC modules__b
    STA libshared__total
    BCC .L0017
    INC libshared__total+$01
.L0017
    LDA modules__w
    STA libshared__pointer
    LDA modules__w+$01
    STA libshared__pointer+$01
    LDA libshared__pointer
    STA libshared__buffer_end
    LDA libshared__pointer+$01
    STA libshared__buffer_end+$01
    LDA #$01
    STA abs_d020
    LDA modules__b
    STA zp_40
    BNE .L003B
    LDA #$01
    BNE .L003D
.L003B
    LDA #$00
.L003D
    STA libshared__busy
    RTS

; function modules.calls
;   no slots
;   calls libshared.add
;   calls libshared.scaled
modules__calls
    LDA #$05
    STA libshared__add__amount
    JSR libshared__add
    LDA modules__b
    STA libshared__add__amount
    JSR libshared__add
    LDA modules__w
    STA libshared__scaled__value
    LDA modules__w+$01
    STA libshared__scaled__value+$01
    LDA #$03
    STA libshared__scaled__shift
    JSR libshared__scaled
    STA modules__w
    STX modules__w+$01
    STA libshared__scaled__value
    STX libshared__scaled__value+$01
    LDA #$01
    STA libshared__scaled__shift
    JSR libshared__scaled
    STA libshared__scaled__value
    STX libshared__scaled__value+$01
    LDA modules__b
    STA libshared__scaled__shift
    JSR libshared__scaled
    STA modules__w
    STX modules__w+$01
    RTS

; function modules.statuses
;   no slots
;   calls libshared.is_empty
;   calls libshared.take
modules__statuses
    JSR libshared__is_empty
    BCC .L000A
    LDA #$00
    STA modules__b
.L000A
    JSR libshared__take
    STA modules__b
    BCC .L0024
    CLC
    LDA modules__w
    ADC modules__b
    STA modules__w
    BCC .L0021
    INC modules__w+$01
.L0021
    JMP .L000A
.L0024
    JSR libshared__take
    STA modules__b
    LDA #$00
    ROL
    STA libshared__busy
    RTS

; variable modules.b: size 1, class 1 (either), weight 17

; variable modules.w: size 2, class 1 (either), weight 22

; variable modules.i: size 2, class 1 (either), weight 2
