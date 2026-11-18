; module unread_stores, cpu 6502

abs_0300 = $0300

; function unread_stores.next
;   no slots
unread_stores__next
    INC unread_stores__count
    LDA #$02
    CMP unread_stores__count
    LDA unread_stores__count
    RTS

; function unread_stores.values
;   slot 0 unused: size 1, class 1 (either), param, weight 0
;   slot 1 k: size 1, class 1 (either), param, weight 2
;   slot 2 v: size 1, class 1 (either), local, weight 3
;   slot 3 ok: size 1, class 1 (either), local, weight 0
;   slot 4 spare: size 2, class 1 (either), local, weight 0
;   slot 5 w: size 2, class 1 (either), local, weight 9
;   calls unread_stores.next
unread_stores__values
    STX unread_stores__values__k
    JSR unread_stores__next
    STA unread_stores__values__v
    LDA #$00
    ROL
    CLC
    LDA unread_stores__values__v
    ADC #$2C
    LDA #$00
    ADC #$01
    LDA unread_stores__values__k
    ASL
    STA unread_stores__values__w
    LDA #$00
    ROL
    STA unread_stores__values__w+$01
    ASL unread_stores__values__w
    ROL unread_stores__values__w+$01
    ASL unread_stores__values__w
    ROL unread_stores__values__w+$01
    ASL unread_stores__values__w
    ROL unread_stores__values__w+$01
    CLC
    LDA unread_stores__values__v
    ADC unread_stores__values__w+$01
    RTS

; function unread_stores.with_asm
;   slot 0 unused: size 1, class 1 (either), param, weight 1
;   slot 1 b: size 1, class 1 (either), local, weight 2
unread_stores__with_asm
    STA unread_stores__with_asm__unused
    LDA #$03
    STA unread_stores__with_asm__b
    LDA unread_stores__with_asm__b
    RTS

; function unread_stores.lasting
;   no slots
unread_stores__lasting
    LDA #$07
    STA unread_stores__lasting__last
    LDA #$09
    STA abs_0300
    LDA #$01
    STA unread_stores__seen
    RTS

; variable unread_stores.lasting.last: size 1, class 1 (either), weight 1

; variable unread_stores.count: size 1, class 1 (either), weight 3

; variable unread_stores.seen: size 1, class 1 (either), weight 1
