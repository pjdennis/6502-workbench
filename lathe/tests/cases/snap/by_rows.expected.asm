; module by_rows, cpu 6502

; function by_rows.bytes
;   slot 0 $t1: size 2, class 0 (zp), temp, weight 6
;   slot 1 $t2: size 2, class 0 (zp), temp, weight 6
by_rows__bytes
    CLC
    LDA by_rows__i
    ADC #<by_rows__big
    STA by_rows__bytes__St1
    LDA by_rows__i+$01
    ADC #>by_rows__big
    STA by_rows__bytes__St1+$01
    CLC
    LDA by_rows__i
    ADC #<by_rows__big+$01
    STA by_rows__bytes__St2
    LDA by_rows__i+$01
    ADC #>by_rows__big+$01
    STA by_rows__bytes__St2+$01
    LDY #$00
    LDA (by_rows__bytes__St2),Y
    STA (by_rows__bytes__St1),Y
    LDA #$01
    STA by_rows__big+$03E7
    LDA by_rows__i
    STA by_rows__bytes__St1
    CLC
    LDA by_rows__i+$01
    ADC #$04
    STA by_rows__bytes__St1+$01
    CLC
    LDA by_rows__k
    ADC #<by_rows__big
    STA by_rows__bytes__St2
    TYA
    ADC #>by_rows__big
    STA by_rows__bytes__St2+$01
    LDA (by_rows__bytes__St2),Y
    STA (by_rows__bytes__St1),Y
    RTS

; function by_rows.words
;   slot 0 $t1: size 2, class 1 (either), temp, weight 12
;   slot 1 $t2: size 2, class 0 (zp), temp, weight 14
by_rows__words
    LDA by_rows__i
    ASL
    STA by_rows__words__St1
    LDA by_rows__i+$01
    ROL
    STA by_rows__words__St1+$01
    CLC
    LDA by_rows__words__St1
    ADC #<by_rows__cells
    STA by_rows__words__St2
    LDA by_rows__words__St1+$01
    ADC #>by_rows__cells
    STA by_rows__words__St2+$01
    LDY #$00
    LDA (by_rows__words__St2),Y
    STA by_rows__v
    LDY #$01
    LDA (by_rows__words__St2),Y
    STA by_rows__v+$01
    LDA by_rows__k
    ASL
    STA by_rows__words__St1
    LDA #$00
    ROL
    STA by_rows__words__St1+$01
    CLC
    LDA by_rows__words__St1
    ADC #<by_rows__cells
    STA by_rows__words__St2
    LDA by_rows__words__St1+$01
    ADC #>by_rows__cells
    STA by_rows__words__St2+$01
    LDY #$00
    LDA (by_rows__words__St2),Y
    CLC
    ADC #$01
    STA (by_rows__words__St2),Y
    BNE .L005F
    LDY #$01
    LDA (by_rows__words__St2),Y
    CLC
    ADC #$01
    STA (by_rows__words__St2),Y
.L005F
    LDA by_rows__k
    ASL
    STA by_rows__words__St1
    LDA #$00
    ROL
    STA by_rows__words__St1+$01
    CLC
    LDA by_rows__words__St1
    ADC #<by_rows__small
    STA by_rows__words__St2
    LDA by_rows__words__St1+$01
    ADC #>by_rows__small
    STA by_rows__words__St2+$01
    LDY #$00
    LDA (by_rows__words__St2),Y
    STA by_rows__v
    LDY #$01
    LDA (by_rows__words__St2),Y
    STA by_rows__v+$01
    RTS

; function by_rows.line_of_bytes
;   slot 0 $t1: size 2, class 1 (either), temp, weight 16
;   slot 1 $t2: size 2, class 0 (zp), temp, weight 3
;   slot 2 $t3: size 2, class 0 (zp), temp, weight 3
by_rows__line_of_bytes
    LDA by_rows__k
    ASL
    STA by_rows__line_of_bytes__St1
    LDA #$00
    ROL
    STA by_rows__line_of_bytes__St1+$01
    ASL by_rows__line_of_bytes__St1
    ROL by_rows__line_of_bytes__St1+$01
    ASL by_rows__line_of_bytes__St1
    ROL by_rows__line_of_bytes__St1+$01
    CLC
    LDA by_rows__line_of_bytes__St1
    ADC #<by_rows__lines
    STA by_rows__line_of_bytes__St2
    LDA by_rows__line_of_bytes__St1+$01
    ADC #>by_rows__lines
    STA by_rows__line_of_bytes__St2+$01
    LDA by_rows__k
    ASL
    STA by_rows__line_of_bytes__St1
    LDA #$00
    ROL
    STA by_rows__line_of_bytes__St1+$01
    ASL by_rows__line_of_bytes__St1
    ROL by_rows__line_of_bytes__St1+$01
    ASL by_rows__line_of_bytes__St1
    ROL by_rows__line_of_bytes__St1+$01
    CLC
    LDA by_rows__line_of_bytes__St1
    ADC #<by_rows__lines
    STA by_rows__line_of_bytes__St3
    LDA by_rows__line_of_bytes__St1+$01
    ADC #>by_rows__lines
    STA by_rows__line_of_bytes__St3+$01
    LDY #$07
    LDA (by_rows__line_of_bytes__St3),Y
    LDY by_rows__j
    STA (by_rows__line_of_bytes__St2),Y
    LDA #$00
    LDX by_rows__j
    STA by_rows__lines+$18,X
    RTS

; function by_rows.walk
;   slot 0 p: size 2, class 0 (zp), local, weight 30
;   slot 1 total: size 2, class 1 (either), local, weight 20
by_rows__walk
    LDA #$00
    STA by_rows__walk__total
    STA by_rows__walk__total+$01
    LDA #<by_rows__cells
    STA by_rows__walk__p
    LDA #>by_rows__cells
    STA by_rows__walk__p+$01
.L0012
    LDA #<by_rows__cells+$0256
    CMP by_rows__walk__p
    LDA #>by_rows__cells+$0256
    SBC by_rows__walk__p+$01
    BCC .L0041
    LDY #$00
    LDA (by_rows__walk__p),Y
    CLC
    ADC by_rows__walk__total
    STA by_rows__walk__total
    LDA by_rows__walk__total+$01
    LDY #$01
    ADC (by_rows__walk__p),Y
    STA by_rows__walk__total+$01
    CLC
    LDA by_rows__walk__p
    ADC #$02
    STA by_rows__walk__p
    BCC .L003E
    INC by_rows__walk__p+$01
.L003E
    JMP .L0012
.L0041
    LDX by_rows__walk__total+$01
    LDA by_rows__walk__total
    RTS

; variable by_rows.big: size 1000, class 2 (not zp), weight 1

; variable by_rows.cells: size 600, class 2 (not zp), weight 0

; variable by_rows.small: size 40, class 2 (not zp), weight 0

; variable by_rows.lines: size 400, class 2 (not zp), weight 1

; variable by_rows.i: size 2, class 1 (either), weight 8

; variable by_rows.k: size 1, class 1 (either), weight 5

; variable by_rows.j: size 1, class 1 (either), weight 2

; variable by_rows.v: size 2, class 1 (either), weight 4
