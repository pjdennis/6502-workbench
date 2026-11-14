; module critical_blocks, cpu 6502

; function critical_blocks.read_ticks
;   no slots
critical_blocks__read_ticks
    PHP
    SEI
    LDA critical_blocks__ticks
    STA critical_blocks__copy
    LDX critical_blocks__ticks+$01
    STX critical_blocks__copy+$01
    PLP
    RTS

; function critical_blocks.early
;   no slots
critical_blocks__early
    PHP
    SEI
    LDA critical_blocks__n
    BNE .L000F
    LDX critical_blocks__ticks+$01
    LDA critical_blocks__ticks
    PLP
    RTS
.L000F
    INC critical_blocks__ticks
    BNE .L0017
    INC critical_blocks__ticks+$01
.L0017
    PLP
    LDX #$00
    TXA
    RTS

; function critical_blocks.loops
;   no slots
critical_blocks__loops
    PHP
    SEI
.L0002
    PHP
    SEI
    DEC critical_blocks__n
    LDA critical_blocks__n
    CMP #$03
    BNE .L0012
    PLP
    JMP .L0002
.L0012
    PHP
    SEI
    CMP #$00
    BNE .L001D
    PLP
    PLP
    JMP .L0022
.L001D
    PLP
    PLP
    JMP .L0002
.L0022
    PLP
    RTS

; function critical_blocks.flags_after
;   no slots
critical_blocks__flags_after
    DEC critical_blocks__n
    PHP
    SEI
    PLP
    LDA critical_blocks__n
    BNE .L0010
    LDA #$01
    STA critical_blocks__n
.L0010
    RTS

; function critical_blocks.ends_with_return
;   no slots
critical_blocks__ends_with_return
    PHP
    SEI
    LDA #$00
    STA critical_blocks__n
    PLP
    RTS

; variable critical_blocks.ticks: size 2, class 1 (either), weight 6

; variable critical_blocks.copy: size 2, class 1 (either), weight 2

; variable critical_blocks.n: size 1, class 1 (either), weight 13
