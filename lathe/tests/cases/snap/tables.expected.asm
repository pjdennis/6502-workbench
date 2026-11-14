; module tables, cpu 6502

; data tables.$1: 8 bytes
tables__S1
    .byte $01, $02, $03, $00, $00, $00, $00, $00

; data tables.digits: 16 bytes
tables__digits
    .byte $30, $31, $32, $33, $34, $35, $36, $37, $38, $39, $41, $42, $43, $44, $45, $46

; data tables.greeting: 6 bytes
tables__greeting
    .byte $68, $65, $6C, $6C, $6F, $00

; data tables.squares: 12 bytes
tables__squares
    .byte $00, $01, $04, $09, $10, $19, $00, $00, $00, $00, $00, $00

; data tables.$2: 4 bytes
tables__S2
    .byte $6F, $6E, $65, $00

; data tables.$3: 4 bytes
tables__S3
    .byte $74, $77, $6F, $00

; data tables.names: 6 bytes
tables__names
    .byte <tables__S2
    .byte <tables__S3
    .byte <tables__buffer+$02
    .byte >tables__S2
    .byte >tables__S3
    .byte >tables__buffer+$02

; data tables.$4: 300 bytes
tables__S4
    .byte $62, $69, $67, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00, $00

; data tables.$5: 8 bytes
tables__S5
    .byte $34, $05, $00, $00, $12, $00, $00, $00

; data tables.$6: 6 bytes
tables__S6
    .byte $73, $74, $61, $72, $74, $00

; data tables.$7: 4 bytes
tables__S7
    .byte $09, $08, $07, $06

; function tables.digit
;   no slots
tables__digit
    LDX tables__i
    LDA tables__digits,X
    RTS

; function tables.square
;   no slots
tables__square
    LDX tables__i
    LDA tables__squares,X
    STA tables__w
    LDA tables__squares+$06,X
    STA tables__w+$01
    RTS

; data tables.$8: 7 bytes
tables__S8
    .byte $69, $6E, $6C, $69, $6E, $65, $00

; function tables.addresses
;   no slots
tables__addresses
    LDX tables__i
    LDA tables__names,X
    STA tables__p
    LDA tables__names+$03,X
    STA tables__p+$01
    LDA #<tables__greeting
    STA tables__p
    LDA #>tables__greeting
    STA tables__p+$01
    LDA #<tables__greeting+$01
    STA tables__p
    LDA #>tables__greeting+$01
    STA tables__p+$01
    LDA #<tables__S8
    STA tables__p
    LDA #>tables__S8
    STA tables__p+$01
    LDA #$03
    STA tables__i
    RTS

; data tables.$9: 5 bytes
tables__S9
    .byte $61, $62, $63, $64, $00

; function tables.local_copy
;   slot 0 scratch: size 5, class 2 (not zp), local, weight 3
tables__local_copy
    LDX #$05
.L0002
    LDA tables__S9-$01,X
    STA tables__local_copy__scratch-$01,X
    DEX
    BNE .L0002
    LDA tables__i
    STA tables__local_copy__scratch
    TAX
    LDA tables__local_copy__scratch,X
    RTS

; data tables.$10: 2 bytes
tables__S10
    .byte $64, $C8

; function tables.counter
;   no slots
tables__counter
    INC tables__counter__seen
    LDA tables__counter__seen
    RTS

; variable tables.counter.seen: size 2, class 2 (not zp), weight 2

; variable tables.buffer: size 8, class 2 (not zp), weight 0

; variable tables.message: size 300, class 2 (not zp), weight 0

; variable tables.table: size 8, class 2 (not zp), weight 0

; variable tables.cursor: size 2, class 1 (either), weight 0

; variable tables.counts: size 4, class 0 (zp), weight 0

; variable tables.i: size 1, class 1 (either), weight 5

; variable tables.w: size 2, class 1 (either), weight 2

; variable tables.p: size 2, class 1 (either), weight 8

; function tables.$init
;   no slots
tables__Sinit
    LDX #$08
.L0002
    LDA tables__S1-$01,X
    STA tables__buffer-$01,X
    DEX
    BNE .L0002
    LDX #$00
.L000D
    LDA tables__S4,X
    STA tables__message,X
    INX
    BNE .L000D
    LDX #$2C
.L0018
    LDA tables__S4+$FF,X
    STA tables__message+$FF,X
    DEX
    BNE .L0018
    LDX #$08
.L0023
    LDA tables__S5-$01,X
    STA tables__table-$01,X
    DEX
    BNE .L0023
    LDA #<tables__S6
    STA tables__cursor
    LDA #>tables__S6
    STA tables__cursor+$01
    LDX #$04
.L0038
    LDA tables__S7-$01,X
    STA tables__counts-$01,X
    DEX
    BNE .L0038
    LDX #$02
.L0043
    LDA tables__S10-$01,X
    STA tables__counter__seen-$01,X
    DEX
    BNE .L0043
    RTS
