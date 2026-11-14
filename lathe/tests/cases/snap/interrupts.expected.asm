; module interrupts, cpu 6502

abs_fffe = $FFFE
abs_ffff = $FFFF

; function interrupts.spend
;   slot 0 n: size 1, class 1 (either), param, weight 2
interrupts__spend
    LDA interrupts__budget
    CMP interrupts__spend__n
    BCS .L000A
    CLC
    RTS
.L000A
    SEC
    SBC interrupts__spend__n
    STA interrupts__budget
    SEC
    RTS

; function interrupts.handler: interrupt
;   slot 0 n: size 1, class 1 (either), local, weight 1
;   calls interrupts.spend
interrupts__handler
    PHA
    TXA
    PHA
    TYA
    PHA
    CLD
    LDA #$02
    STA interrupts__handler__n
    INC interrupts__ticks
    BNE .L0013
    INC interrupts__ticks+$01
.L0013
    STA interrupts__spend__n
    JSR interrupts__spend
    BCC .L002E
    PHP
    SEI
    INC interrupts__ticks
    BNE .L0025
    INC interrupts__ticks+$01
.L0025
    PLP
    LDA #$01
    STA interrupts__spend__n
    JSR interrupts__spend
.L002E
    PLA
    TAY
    PLA
    TAX
    PLA
    RTI

; function interrupts.quiet: interrupt, exported
;   no slots
interrupts__quiet
    PHA
    TXA
    PHA
    TYA
    PHA
    CLD
    PLA
    TAY
    PLA
    TAX
    PLA
    RTI

; function interrupts.install: exported
;   no slots
interrupts__install
    LDA #<interrupts__handler
    STA abs_fffe
    LDA #>interrupts__handler
    STA abs_ffff
    LDA #<interrupts__quiet
    STA interrupts__spare
    LDA #>interrupts__quiet
    STA interrupts__spare+$01
    RTS

; variable interrupts.ticks: size 2, class 1 (either), weight 4

; variable interrupts.spare: size 2, class 1 (either), weight 2

; variable interrupts.budget: size 1, class 1 (either), weight 2
