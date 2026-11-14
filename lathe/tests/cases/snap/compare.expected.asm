; module compare, cpu 6502

; function compare.bytes
;   no slots
compare__bytes
    LDA compare__a
    CMP compare__b
    BNE .L000D
    LDA #$01
    STA compare__r
.L000D
    LDA compare__a
    CMP compare__b
    BEQ .L001A
    LDA #$02
    STA compare__r
.L001A
    LDA compare__a
    CMP compare__b
    BCS .L0027
    LDA #$03
    STA compare__r
.L0027
    LDA compare__a
    CMP compare__b
    BCC .L0034
    LDA #$04
    STA compare__r
.L0034
    RTS

; function compare.bytes_exchanged
;   no slots
compare__bytes_exchanged
    LDA compare__b
    CMP compare__a
    BCS .L000D
    LDA #$01
    STA compare__r
.L000D
    LDA compare__b
    CMP compare__a
    BCC .L001A
    LDA #$02
    STA compare__r
.L001A
    RTS

; function compare.byte_constants
;   no slots
compare__byte_constants
    LDA compare__a
    CMP #$06
    BCC .L000C
    LDA #$01
    STA compare__r
.L000C
    LDA compare__a
    CMP #$06
    BCS .L0018
    LDA #$02
    STA compare__r
.L0018
    LDA compare__a
    CMP #$05
    BCS .L0024
    LDA #$03
    STA compare__r
.L0024
    LDA compare__a
    CMP #$06
    BCC .L0030
    LDA #$04
    STA compare__r
.L0030
    LDA compare__a
    CMP #$05
    BNE .L003C
    LDA #$05
    STA compare__r
.L003C
    RTS

; function compare.zero
;   no slots
compare__zero
    LDA compare__a
    BNE .L000A
    LDA #$01
    STA compare__r
.L000A
    CLC
    LDA compare__a
    ADC compare__b
    STA compare__r
    BEQ .L001B
    LDA #$02
    STA compare__r
.L001B
    LDA compare__a
    AND #$0F
    BNE .L0027
    LDA #$03
    STA compare__r
.L0027
    RTS

; function compare.signed_bytes
;   no slots
compare__signed_bytes
    LDA compare__s
    SEC
    SBC compare__t
    BVC .L000B
    EOR #$80
.L000B
    BPL .L0012
    LDA #$01
    STA compare__r
.L0012
    LDA compare__s
    SEC
    SBC compare__t
    BVC .L001D
    EOR #$80
.L001D
    BMI .L0024
    LDA #$02
    STA compare__r
.L0024
    LDA compare__t
    SEC
    SBC compare__s
    BVC .L002F
    EOR #$80
.L002F
    BPL .L0036
    LDA #$03
    STA compare__r
.L0036
    LDA compare__s
    SEC
    SBC #$06
    BVC .L0040
    EOR #$80
.L0040
    BPL .L0047
    LDA #$04
    STA compare__r
.L0047
    RTS

; function compare.signs
;   no slots
compare__signs
    LDA compare__s
    BPL .L000A
    LDA #$01
    STA compare__r
.L000A
    LDA compare__s
    BMI .L0014
    LDA #$02
    STA compare__r
.L0014
    LDA compare__i+$01
    BPL .L001E
    LDA #$03
    STA compare__r
.L001E
    RTS

; function compare.words
;   no slots
compare__words
    LDA compare__w
    CMP compare__v
    BNE .L0015
    LDA compare__w+$01
    CMP compare__v+$01
    BNE .L0015
    LDA #$01
    STA compare__r
.L0015
    LDA compare__w
    CMP compare__v
    BNE .L0025
    LDA compare__w+$01
    CMP compare__v+$01
    BEQ .L002A
.L0025
    LDA #$02
    STA compare__r
.L002A
    LDA compare__w
    ORA compare__w+$01
    BNE .L0037
    LDA #$03
    STA compare__r
.L0037
    LDA compare__w
    BNE .L0043
    LDA compare__w+$01
    CMP #$12
    BEQ .L0048
.L0043
    LDA #$04
    STA compare__r
.L0048
    LDA compare__w
    AND compare__w+$01
    CMP #$FF
    BNE .L0057
    LDA #$05
    STA compare__r
.L0057
    LDA compare__i
    AND compare__i+$01
    CMP #$FF
    BEQ .L0066
    LDA #$06
    STA compare__r
.L0066
    RTS

; function compare.word_order
;   no slots
compare__word_order
    LDA compare__w
    CMP compare__v
    LDA compare__w+$01
    SBC compare__v+$01
    BCS .L0013
    LDA #$01
    STA compare__r
.L0013
    LDA compare__w
    CMP compare__v
    LDA compare__w+$01
    SBC compare__v+$01
    BCC .L0026
    LDA #$02
    STA compare__r
.L0026
    LDA compare__v
    CMP compare__w
    LDA compare__v+$01
    SBC compare__w+$01
    BCS .L0039
    LDA #$03
    STA compare__r
.L0039
    LDA compare__w
    CMP #$E9
    LDA compare__w+$01
    SBC #$03
    BCS .L004A
    LDA #$04
    STA compare__r
.L004A
    LDA compare__i
    CMP compare__j
    LDA compare__i+$01
    SBC compare__j+$01
    BVC .L005A
    EOR #$80
.L005A
    BPL .L0061
    LDA #$05
    STA compare__r
.L0061
    RTS

; function compare.mixed
;   no slots
compare__mixed
    LDA compare__a
    CMP compare__w
    BNE .L0012
    LDA compare__w+$01
    BNE .L0012
    LDA #$01
    STA compare__r
.L0012
    LDA compare__w
    CMP compare__a
    LDA compare__w+$01
    SBC #$00
    BCS .L0024
    LDA #$02
    STA compare__r
.L0024
    RTS

; function compare.computed
;   slot 0 $t1: size 1, class 1 (either), temp, weight 2
;   slot 1 $t2: size 2, class 1 (either), temp, weight 4
compare__computed
    CLC
    LDA compare__a
    ADC #$01
    CMP compare__b
    BCS .L0010
    LDA #$01
    STA compare__r
.L0010
    CLC
    LDA compare__b
    ADC #$01
    STA compare__computed__St1
    LDA compare__a
    CMP compare__computed__St1
    BCS .L0026
    LDA #$02
    STA compare__r
.L0026
    CLC
    LDA compare__b
    ADC #$01
    CMP compare__a
    BNE .L0036
    LDA #$03
    STA compare__r
.L0036
    CLC
    LDA compare__w
    ADC #$01
    TAY
    LDA compare__w+$01
    ADC #$00
    TAX
    TYA
    CMP compare__v
    TXA
    SBC compare__v+$01
    BCS .L0052
    LDA #$04
    STA compare__r
.L0052
    CLC
    LDA compare__v
    ADC #$01
    STA compare__computed__St2
    LDA compare__v+$01
    ADC #$00
    STA compare__computed__St2+$01
    LDA compare__w
    CMP compare__computed__St2
    LDA compare__w+$01
    SBC compare__computed__St2+$01
    BCS .L0076
    LDA #$05
    STA compare__r
.L0076
    RTS

; function compare.known
;   no slots
compare__known
    LDA #$01
    STA compare__r
    RTS

; variable compare.a: size 1, class 1 (either), weight 19

; variable compare.b: size 1, class 1 (either), weight 10

; variable compare.s: size 1, class 1 (either), weight 6

; variable compare.t: size 1, class 1 (either), weight 3

; variable compare.w: size 2, class 1 (either), weight 26

; variable compare.v: size 2, class 1 (either), weight 14

; variable compare.i: size 2, class 1 (either), weight 5

; variable compare.j: size 2, class 1 (either), weight 2

; variable compare.r: size 1, class 1 (either), weight 42
