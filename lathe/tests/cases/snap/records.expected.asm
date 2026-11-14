; module records, cpu 6502

; function records.fields
;   no slots
records__fields
    LDA #$01
    STA records__s+$02
    CLC
    ADC records__b
    STA records__s+$03
    LDA records__w
    STA records__s+$04
    LDX records__w+$01
    STX records__s+$05
    CLC
    ADC #$01
    STA records__w
    TXA
    ADC #$00
    STA records__w+$01
    LDA #$00
    STA records__s+$05
    LDA records__t+$04
    STA records__b
    LDX records__i
    LDA records__s+$06,X
    STA records__s+$08
    LDA records__s+$0A
    STA records__s+$09,X
    LDA records__s+$0C
    STA records__s+$0B,X
    LDA #$0D
    STA records__b
    RTS

; function records.addresses
;   no slots
records__addresses
    LDA #<records__s+$02
    STA records__p
    LDA #>records__s+$02
    STA records__p+$01
    CLC
    LDA #<records__s+$06
    ADC records__i
    STA records__q
    LDA #>records__s+$06
    ADC #$00
    STA records__q+$01
    LDA #<records__s+$06
    STA records__q
    LDA #>records__s+$06
    STA records__q+$01
    LDA #<records__t
    STA records__w
    LDA #>records__t
    STA records__w+$01
    RTS

; function records.copy
;   slot 0 local: size 2, class 2 (not zp), local, weight 2
records__copy
    LDA records__s
    STA records__t
    LDA records__s+$01
    STA records__t+$01
    LDA records__s+$02
    STA records__t+$02
    LDA records__s+$03
    STA records__t+$03
    LDA records__s+$04
    STA records__t+$04
    LDA records__s+$05
    STA records__t+$05
    LDA records__s+$06
    STA records__t+$06
    LDA records__s+$07
    STA records__t+$07
    LDA records__s+$08
    STA records__t+$08
    LDA records__s+$09
    STA records__t+$09
    LDA records__s+$0A
    STA records__t+$0A
    LDA records__s+$0B
    STA records__t+$0B
    LDA records__s+$0C
    STA records__t+$0C
    LDA records__s+$02
    STA records__copy__local
    LDX records__s+$03
    STX records__copy__local+$01
    STA records__t+$02
    STX records__t+$03
    RTS

; function records.compare
;   no slots
records__compare
    LDA records__s+$02
    CMP records__t+$03
    BNE .L0017
    LDA records__t+$04
    CLC
    SBC records__s+$04
    LDA records__t+$05
    SBC records__s+$05
    BCS .L0018
.L0017
    CLC
.L0018
    RTS

; variable records.s: size 13, class 2 (not zp), weight 29

; variable records.t: size 13, class 2 (not zp), weight 19

; variable records.b: size 1, class 1 (either), weight 3

; variable records.w: size 2, class 1 (either), weight 6

; variable records.i: size 1, class 1 (either), weight 2

; variable records.p: size 2, class 1 (either), weight 2

; variable records.q: size 2, class 1 (either), weight 4
