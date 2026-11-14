; module reg_args, cpu 6502
; imports: rt_frame

; function reg_args.one
;   slot 0 x: size 1, class 1 (either), param, weight 1
reg_args__one
    STA reg_args__one__x
    CLC
    ADC #$01
    RTS

; function reg_args.two
;   slot 0 x: size 1, class 1 (either), param, weight 1
;   slot 1 y: size 1, class 1 (either), param, weight 2
reg_args__two
    STA reg_args__two__x
    STX reg_args__two__y
    SEC
    SBC reg_args__two__y
    RTS

; function reg_args.three
;   slot 0 x: size 1, class 1 (either), param, weight 1
;   slot 1 y: size 1, class 1 (either), param, weight 2
;   slot 2 z: size 1, class 1 (either), param, weight 2
reg_args__three
    STA reg_args__three__x
    STX reg_args__three__y
    STY reg_args__three__z
    EOR reg_args__three__y
    EOR reg_args__three__z
    RTS

; function reg_args.wide
;   slot 0 x: size 2, class 1 (either), param, weight 2
reg_args__wide
    STA reg_args__wide__x
    STX reg_args__wide__x+$01
    CLC
    ADC #$01
    TAY
    TXA
    ADC #$00
    TAX
    TYA
    RTS

; function reg_args.word_byte
;   slot 0 x: size 2, class 1 (either), param, weight 2
;   slot 1 y: size 1, class 1 (either), param, weight 2
reg_args__word_byte
    STA reg_args__word_byte__x
    STX reg_args__word_byte__x+$01
    STY reg_args__word_byte__y
    CLC
    ADC reg_args__word_byte__y
    TAY
    TXA
    ADC #$00
    TAX
    TYA
    RTS

; function reg_args.byte_word
;   slot 0 x: size 1, class 1 (either), param, weight 2
;   slot 1 y: size 2, class 1 (either), param, weight 2
reg_args__byte_word
    STA reg_args__byte_word__x
    SEC
    LDA reg_args__byte_word__y
    SBC reg_args__byte_word__x
    TAY
    LDA reg_args__byte_word__y+$01
    SBC #$00
    TAX
    TYA
    RTS

; function reg_args.four
;   slot 0 x: size 1, class 1 (either), param, weight 1
;   slot 1 y: size 1, class 1 (either), param, weight 2
;   slot 2 z: size 1, class 1 (either), param, weight 2
;   slot 3 q: size 1, class 1 (either), param, weight 1
reg_args__four
    STA reg_args__four__x
    STX reg_args__four__y
    STY reg_args__four__z
    CLC
    ADC reg_args__four__y
    CLC
    ADC reg_args__four__z
    CLC
    ADC reg_args__four__q
    RTS

; function reg_args.signed
;   slot 0 x: size 1, class 1 (either), param, weight 3
;   slot 1 t: size 1, class 1 (either), param, weight 1
reg_args__signed
    STA reg_args__signed__x
    STX reg_args__signed__t
    TXA
    BEQ .L0010
    SEC
    LDA #$00
    SBC reg_args__signed__x
    RTS
.L0010
    LDA reg_args__signed__x
    RTS

; function reg_args.pointed
;   slot 0 q: size 2, class 0 (zp), param, weight 3
;   slot 1 i: size 1, class 1 (either), param, weight 1
reg_args__pointed
    STA reg_args__pointed__q
    STX reg_args__pointed__q+$01
    STY reg_args__pointed__i
    LDA (reg_args__pointed__q),Y
    RTS

; function reg_args.mix
;   slot 0 x: size 1, class 1 (either), param, weight 1
;   slot 1 y: size 2, class 1 (either), param, weight 1
reg_args__mix
    STA reg_args__mix__x
    CLC
    ADC reg_args__mix__y
    RTS

; function reg_args.constants
;   no slots
;   calls reg_args.one
;   calls reg_args.two
;   calls reg_args.three
;   calls reg_args.wide
;   calls reg_args.word_byte
;   calls reg_args.byte_word
;   calls reg_args.four
;   calls reg_args.signed
;   calls reg_args.pointed
reg_args__constants
    LDA #$05
    JSR reg_args__one
    STA reg_args__a
    LDX #$02
    LDA #$01
    JSR reg_args__two
    STA reg_args__a
    LDY #$03
    LDX #$02
    LDA #$01
    JSR reg_args__three
    STA reg_args__a
    LDX #$03
    LDA #$E8
    JSR reg_args__wide
    STA reg_args__w
    STX reg_args__w+$01
    LDY #$07
    LDX #$12
    LDA #$34
    JSR reg_args__word_byte
    STA reg_args__w
    STX reg_args__w+$01
    LDA #$34
    STA reg_args__byte_word__y
    LDA #$12
    STA reg_args__byte_word__y+$01
    LDA #$07
    JSR reg_args__byte_word
    STA reg_args__w
    STX reg_args__w+$01
    LDA #$04
    STA reg_args__four__q
    LDY #$03
    LDX #$02
    LDA #$01
    JSR reg_args__four
    STA reg_args__a
    LDX #$01
    LDA #$FD
    JSR reg_args__signed
    STA reg_args__s
    LDY #$03
    LDX #>reg_args__table
    LDA #<reg_args__table
    JSR reg_args__pointed
    STA reg_args__a
    RTS

; function reg_args.variables
;   slot 0 $t1: size 1, class 1 (either), temp, weight 1
;   calls reg_args.two
;   calls reg_args.three
;   calls reg_args.word_byte
;   calls reg_args.byte_word
;   calls reg_args.pointed
reg_args__variables
    LDX reg_args__c
    LDA reg_args__b
    JSR reg_args__two
    STA reg_args__a
    TAY
    LDX reg_args__b
    LDA reg_args__c
    JSR reg_args__three
    STA reg_args__a
    LDY reg_args__b
    LDX reg_args__v+$01
    LDA reg_args__v
    JSR reg_args__word_byte
    STA reg_args__w
    STX reg_args__w+$01
    LDA reg_args__v
    STA reg_args__byte_word__y
    LDX reg_args__v+$01
    STX reg_args__byte_word__y+$01
    LDA reg_args__b
    JSR reg_args__byte_word
    STA reg_args__w
    STX reg_args__w+$01
    LDY reg_args__b
    LDX reg_args__p+$01
    LDA reg_args__p
    JSR reg_args__pointed
    STA reg_args__a
    LDX reg_args__b
    LDA reg_args__table,X
    STA reg_args__variables__St1
    LDX reg_args__c
    JSR reg_args__two
    STA reg_args__a
    RTS

; function reg_args.computed
;   slot 0 $t1: size 1, class 1 (either), temp, weight 6
;   slot 1 $t2: size 1, class 1 (either), temp, weight 2
;   slot 2 $t3: size 2, class 1 (either), temp, weight 3
;   calls reg_args.one
;   calls reg_args.two
;   calls reg_args.three
;   calls reg_args.wide
;   calls reg_args.word_byte
;   calls reg_args.four
reg_args__computed
    CLC
    LDA reg_args__b
    ADC reg_args__c
    JSR reg_args__one
    STA reg_args__a
    CLC
    LDA reg_args__b
    ADC reg_args__c
    TAX
    LDA reg_args__b
    JSR reg_args__two
    STA reg_args__a
    CLC
    LDA reg_args__b
    ADC reg_args__c
    STA reg_args__computed__St1
    SEC
    LDA reg_args__b
    SBC reg_args__c
    TAX
    LDA reg_args__computed__St1
    JSR reg_args__two
    STA reg_args__a
    CLC
    LDA reg_args__b
    ADC #$01
    STA reg_args__computed__St1
    CLC
    LDA reg_args__c
    ADC #$01
    STA reg_args__computed__St2
    CLC
    LDA reg_args__a
    ADC #$01
    TAY
    LDX reg_args__computed__St2
    LDA reg_args__computed__St1
    JSR reg_args__three
    STA reg_args__a
    CLC
    LDA reg_args__v
    ADC reg_args__w
    TAY
    LDA reg_args__v+$01
    ADC reg_args__w+$01
    TAX
    TYA
    JSR reg_args__wide
    STA reg_args__w
    STX reg_args__w+$01
    CLC
    LDA reg_args__v
    ADC reg_args__w
    TAY
    LDA reg_args__v+$01
    ADC reg_args__w+$01
    TAX
    TYA
    STA reg_args__computed__St3
    STX reg_args__computed__St3+$01
    CLC
    LDA reg_args__b
    ADC #$01
    TAY
    LDA reg_args__computed__St3
    JSR reg_args__word_byte
    STA reg_args__w
    STX reg_args__w+$01
    CLC
    LDA reg_args__b
    ADC #$01
    STA reg_args__computed__St1
    CLC
    LDA reg_args__c
    ADC #$01
    STA reg_args__four__q
    LDY #$03
    LDX #$02
    LDA reg_args__computed__St1
    JSR reg_args__four
    STA reg_args__a
    RTS

; function reg_args.nested
;   slot 0 $t1: size 1, class 1 (either), temp, weight 8
;   slot 1 $t2: size 1, class 1 (either), temp, weight 4
;   slot 2 $t3: size 2, class 1 (either), temp, weight 4
;   slot 3 $t4: size 1, class 1 (either), temp, weight 2
;   calls reg_args.one
;   calls reg_args.two
;   calls reg_args.three
;   calls reg_args.wide
;   calls reg_args.word_byte
;   calls reg_args.four
reg_args__nested
    LDA reg_args__b
    JSR reg_args__one
    STA reg_args__nested__St1
    LDA reg_args__c
    JSR reg_args__one
    TAX
    LDA reg_args__nested__St1
    JSR reg_args__two
    STA reg_args__a
    LDA reg_args__b
    STA reg_args__nested__St1
    LDA reg_args__c
    JSR reg_args__one
    TAX
    LDA reg_args__nested__St1
    JSR reg_args__two
    STA reg_args__a
    JSR reg_args__one
    STA reg_args__nested__St2
    LDA reg_args__b
    STA reg_args__nested__St1
    LDX reg_args__c
    JSR reg_args__two
    TAY
    LDX reg_args__nested__St1
    LDA reg_args__nested__St2
    JSR reg_args__three
    STA reg_args__a
    LDX reg_args__v+$01
    LDA reg_args__v
    JSR reg_args__wide
    STA reg_args__nested__St3
    STX reg_args__nested__St3+$01
    LDA reg_args__b
    JSR reg_args__one
    TAY
    LDX reg_args__nested__St3+$01
    LDA reg_args__nested__St3
    JSR reg_args__word_byte
    STA reg_args__w
    STX reg_args__w+$01
    LDA reg_args__b
    STA reg_args__nested__St1
    LDA reg_args__c
    STA reg_args__nested__St2
    LDA reg_args__a
    JSR reg_args__one
    STA reg_args__nested__St4
    LDX #$02
    LDA #$01
    JSR reg_args__two
    STA reg_args__four__q
    LDY reg_args__nested__St4
    LDX reg_args__nested__St2
    LDA reg_args__nested__St1
    JSR reg_args__four
    STA reg_args__a
    RTS

; function reg_args.conditions
;   no slots
;   calls reg_args.one
;   calls reg_args.two
;   calls reg_args.three
reg_args__conditions
    LDA reg_args__a
    JSR reg_args__one
    CMP #$03
    BNE .L001C
    LDX reg_args__c
    LDA reg_args__b
    JSR reg_args__two
    CMP #$02
    BCC .L001C
    LDA #$00
    STA reg_args__a
.L001C
    LDY reg_args__c
    LDX reg_args__b
    LDA reg_args__a
    JSR reg_args__three
    CMP #$00
    BEQ .L0032
    DEC reg_args__a
    JMP .L001C
.L0032
    RTS

; class reg_args.pair: parameter sizes 1, 2

; reg_args.mix is a member of class reg_args.pair

; function reg_args.through
;   slot 0 $t1: size 1, class 1 (either), temp, weight 2
;   calls reg_args.pair (through pointer)
;   calls reg_args.wide
reg_args__through
    LDA #<reg_args__mix
    STA reg_args__h
    LDA #>reg_args__mix
    STA reg_args__h+$01
    LDA reg_args__w
    STA reg_args__pair__p1
    LDX reg_args__w+$01
    STX reg_args__pair__p1+$01
    LDA reg_args__b
    JSR .L0059
    STA reg_args__a
    CLC
    LDA reg_args__b
    ADC #$01
    STA reg_args__through__St1
    LDX reg_args__w+$01
    LDA reg_args__w
    JSR reg_args__wide
    STA reg_args__pair__p1
    STX reg_args__pair__p1+$01
    LDA reg_args__through__St1
    JSR .L0059
    STA reg_args__a
    LDA reg_args__v
    STA reg_args__pair__p1
    LDX reg_args__v+$01
    STX reg_args__pair__p1+$01
    LDX reg_args__c
    LDA reg_args__table,X
    JSR .L0059
    STA reg_args__a
    RTS
.L0059
    JMP (reg_args__h)

; function reg_args.walk: recursive
;   slot 0 n: size 1, class 1 (either), param, weight 7
;   slot 1 x: size 2, class 1 (either), param, weight 18
;   slot 2 $t1: size 1, class 1 (either), temp, weight 4
;   slot 3 $t2: size 2, class 1 (either), temp, weight 12
;   slot 4 $t3: size 2, class 1 (either), temp, weight 4
;   calls rt_frame.push
;   calls reg_args.walk (saves frame)
;   calls rt_frame.pop_y
reg_args__walk
.L0000
    STA reg_args__walk__n
    CMP #$00
    BNE .L000E
    LDX reg_args__walk__x+$01
    LDA reg_args__walk__x
    RTS
.L000E
    SEC
    SBC #$01
    STA reg_args__walk__St1
    CLC
    LDA reg_args__walk__x
    ADC reg_args__walk__n
    STA reg_args__walk__St2
    LDA reg_args__walk__x+$01
    ADC #$00
    STA reg_args__walk__St2+$01
    LDA reg_args__walk__n
    JSR rt_frame__push
    LDA reg_args__walk__x
    JSR rt_frame__push
    LDA reg_args__walk__x+$01
    JSR rt_frame__push
    LDA reg_args__walk__St2
    STA reg_args__walk__x
    LDA reg_args__walk__St2+$01
    STA reg_args__walk__x+$01
    LDA reg_args__walk__St1
    JSR .L0000
    JSR rt_frame__pop_y
    STY reg_args__walk__x+$01
    JSR rt_frame__pop_y
    STY reg_args__walk__x
    JSR rt_frame__pop_y
    STY reg_args__walk__n
    STA reg_args__walk__St2
    STX reg_args__walk__St2+$01
    SEC
    LDA reg_args__walk__n
    SBC #$01
    STA reg_args__walk__St1
    LDA reg_args__walk__x
    STA reg_args__walk__St3
    LDX reg_args__walk__x+$01
    STX reg_args__walk__St3+$01
    LDA reg_args__walk__n
    JSR rt_frame__push
    LDA reg_args__walk__x
    JSR rt_frame__push
    LDA reg_args__walk__x+$01
    JSR rt_frame__push
    LDA reg_args__walk__St2
    JSR rt_frame__push
    LDA reg_args__walk__St2+$01
    JSR rt_frame__push
    LDA reg_args__walk__St3
    STA reg_args__walk__x
    LDA reg_args__walk__St3+$01
    STA reg_args__walk__x+$01
    LDA reg_args__walk__St1
    JSR .L0000
    JSR rt_frame__pop_y
    STY reg_args__walk__St2+$01
    JSR rt_frame__pop_y
    STY reg_args__walk__St2
    JSR rt_frame__pop_y
    STY reg_args__walk__x+$01
    JSR rt_frame__pop_y
    STY reg_args__walk__x
    JSR rt_frame__pop_y
    STY reg_args__walk__n
    CLC
    ADC reg_args__walk__St2
    TAY
    TXA
    ADC reg_args__walk__St2+$01
    TAX
    TYA
    RTS

; class reg_args.stepper: parameter sizes 1, 2; recursive

; reg_args.walk_through is a member of class reg_args.stepper

; function reg_args.walk_through: recursive
;   slot 0 n: size 1, class 1 (either), param, weight 4
;   slot 1 x: size 2, class 1 (either), param, weight 8
;   slot 2 g: size 2, class 1 (either), local, weight 7
;   slot 3 $t1: size 1, class 1 (either), temp, weight 2
;   slot 4 $t2: size 2, class 1 (either), temp, weight 4
;   calls rt_frame.push
;   calls reg_args.stepper (saves frame, through pointer)
;   calls rt_frame.pop_y
reg_args__walk_through
.L0000
    STA reg_args__walk_through__n
    LDA #<.L0000
    STA reg_args__walk_through__g
    LDA #>.L0000
    STA reg_args__walk_through__g+$01
    LDA reg_args__walk_through__n
    BNE .L0019
    LDX reg_args__walk_through__x+$01
    LDA reg_args__walk_through__x
    RTS
.L0019
    SEC
    SBC #$01
    STA reg_args__walk_through__St1
    CLC
    LDA reg_args__walk_through__x
    ADC #$01
    STA reg_args__walk_through__St2
    LDA reg_args__walk_through__x+$01
    ADC #$00
    STA reg_args__walk_through__St2+$01
    LDA reg_args__walk_through__n
    JSR rt_frame__push
    LDA reg_args__walk_through__x
    JSR rt_frame__push
    LDA reg_args__walk_through__x+$01
    JSR rt_frame__push
    LDA reg_args__walk_through__g
    JSR rt_frame__push
    LDA reg_args__walk_through__g+$01
    JSR rt_frame__push
    LDA reg_args__walk_through__St2
    STA reg_args__stepper__p1
    LDA reg_args__walk_through__St2+$01
    STA reg_args__stepper__p1+$01
    LDA reg_args__walk_through__St1
    JSR .L007F
    JSR rt_frame__pop_y
    STY reg_args__walk_through__g+$01
    JSR rt_frame__pop_y
    STY reg_args__walk_through__g
    JSR rt_frame__pop_y
    STY reg_args__walk_through__x+$01
    JSR rt_frame__pop_y
    STY reg_args__walk_through__x
    JSR rt_frame__pop_y
    STY reg_args__walk_through__n
    RTS
.L007F
    JMP (reg_args__walk_through__g)

; function reg_args.main: exported
;   no slots
;   calls reg_args.constants
;   calls reg_args.variables
;   calls reg_args.computed
;   calls reg_args.nested
;   calls reg_args.conditions
;   calls reg_args.through
;   calls reg_args.walk
;   calls reg_args.walk_through
reg_args__main
    JSR reg_args__constants
    JSR reg_args__variables
    JSR reg_args__computed
    JSR reg_args__nested
    JSR reg_args__conditions
    JSR reg_args__through
    LDA #$0A
    STA reg_args__walk__x
    LDA #$00
    STA reg_args__walk__x+$01
    LDA #$03
    JSR reg_args__walk
    STA reg_args__w
    STX reg_args__w+$01
    LDA #$0A
    STA reg_args__walk_through__x
    LDA #$00
    STA reg_args__walk_through__x+$01
    LDA #$03
    JSR reg_args__walk_through
    STA reg_args__w
    STX reg_args__w+$01
    RTS

; variable reg_args.a: size 1, class 1 (either), weight 33

; variable reg_args.b: size 1, class 1 (either), weight 26

; variable reg_args.c: size 1, class 1 (either), weight 19

; variable reg_args.w: size 2, class 1 (either), weight 28

; variable reg_args.v: size 2, class 1 (either), weight 12

; variable reg_args.p: size 2, class 1 (either), weight 2

; variable reg_args.h: size 2, class 1 (either), weight 5

; variable reg_args.table: size 8, class 2 (not zp), weight 2

; variable reg_args.s: size 1, class 1 (either), weight 1

; variable reg_args.on: size 1, class 1 (either), weight 0
