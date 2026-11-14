; module status_ignored, cpu 6502

; function status_ignored.next
;   no slots
status_ignored__next
    INC status_ignored__n
    LDA #$09
    CMP status_ignored__n
    LDA status_ignored__n
    RTS

; function status_ignored.wide
;   no slots
status_ignored__wide
    SEC
    LDX status_ignored__w+$01
    LDA status_ignored__w
    RTS

; function status_ignored.f
;   slot 0 v: size 1, class 1 (either), local, weight 2
;   calls status_ignored.next
;   calls status_ignored.wide
status_ignored__f
    JSR status_ignored__next
    STA status_ignored__f__v
    JSR status_ignored__wide
    STA status_ignored__w
    STX status_ignored__w+$01
    JSR status_ignored__next
    CLC
    ADC #$01
    STA status_ignored__f__v
    JSR status_ignored__next
    JMP status_ignored__wide

; variable status_ignored.n: size 1, class 1 (either), weight 3

; variable status_ignored.w: size 2, class 1 (either), weight 4
