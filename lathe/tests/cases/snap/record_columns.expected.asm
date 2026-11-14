; module record_columns, cpu 6502

; function record_columns.fields
;   no slots
record_columns__fields
    LDX record_columns__i
    LDA record_columns__syms+$0190,X
    STA record_columns__k
    LDA record_columns__syms+$0258,X
    STA record_columns__w
    LDA record_columns__syms+$0320,X
    STA record_columns__w+$01
    LDA record_columns__syms,X
    STA record_columns__n
    LDA record_columns__syms+$C8,X
    STA record_columns__n+$01
    INC record_columns__syms+$0258,X
    BNE .L0029
    INC record_columns__syms+$0320,X
.L0029
    LDA record_columns__b
    LDX record_columns__j
    STA record_columns__syms+$0259,X
    LDA #$02
    STA record_columns__syms+$0193
    LDA record_columns__syms+$03E7
    STA record_columns__b
    RTS

; function record_columns.copies
;   no slots
record_columns__copies
    LDA record_columns__r
    LDX record_columns__i
    STA record_columns__syms,X
    LDA record_columns__r+$01
    STA record_columns__syms+$C8,X
    LDA record_columns__r+$02
    STA record_columns__syms+$0190,X
    LDA record_columns__r+$03
    STA record_columns__syms+$0258,X
    LDA record_columns__r+$04
    STA record_columns__syms+$0320,X
    LDX record_columns__j
    LDA record_columns__syms,X
    STA record_columns__r
    LDA record_columns__syms+$C8,X
    STA record_columns__r+$01
    LDA record_columns__syms+$0190,X
    STA record_columns__r+$02
    LDA record_columns__syms+$0258,X
    STA record_columns__r+$03
    LDA record_columns__syms+$0320,X
    STA record_columns__r+$04
    LDA record_columns__syms,X
    LDX record_columns__i
    STA record_columns__syms,X
    LDX record_columns__j
    LDA record_columns__syms+$C8,X
    LDX record_columns__i
    STA record_columns__syms+$C8,X
    LDX record_columns__j
    LDA record_columns__syms+$0190,X
    LDX record_columns__i
    STA record_columns__syms+$0190,X
    LDX record_columns__j
    LDA record_columns__syms+$0258,X
    LDX record_columns__i
    STA record_columns__syms+$0258,X
    LDX record_columns__j
    LDA record_columns__syms+$0320,X
    LDX record_columns__i
    STA record_columns__syms+$0320,X
    RTS

; function record_columns.arrays_in_records
;   no slots
record_columns__arrays_in_records
    LDA record_columns__grid+$02
    LDX record_columns__i
    STA record_columns__grid+$03,X
    LDA record_columns__grid+$07
    STA record_columns__grid+$06,X
    LDA record_columns__grid+$0A
    STA record_columns__grid+$09,X
    RTS

; function record_columns.is_var
;   no slots
record_columns__is_var
    LDX record_columns__i
    LDA record_columns__syms+$0190,X
    CMP #$01
    BEQ .L000B
    CLC
.L000B
    RTS

; function record_columns.address
;   no slots
record_columns__address
    CLC
    LDA #<record_columns__syms+$0190
    ADC record_columns__i
    TAY
    LDA #>record_columns__syms+$0190
    ADC #$00
    TAX
    TYA
    RTS

; variable record_columns.syms: size 1000, class 2 (not zp), weight 31

; variable record_columns.grid: size 12, class 2 (not zp), weight 6

; variable record_columns.r: size 5, class 2 (not zp), weight 10

; variable record_columns.i: size 1, class 1 (either), weight 10

; variable record_columns.j: size 1, class 1 (either), weight 6

; variable record_columns.b: size 1, class 1 (either), weight 2

; variable record_columns.w: size 2, class 1 (either), weight 2

; variable record_columns.n: size 2, class 1 (either), weight 2

; variable record_columns.k: size 1, class 1 (either), weight 1
