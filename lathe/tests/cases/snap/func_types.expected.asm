; module func_types, cpu 6502

; function func_types.beep
;   slot 0 code: size 1, class 1 (either), param, weight 1
;   slot 1 arg: size 2, class 1 (either), param, weight 0
func_types__beep
    STA func_types__beep__code
    CMP #$03
    BEQ .L0008
    CLC
.L0008
    RTS

; function func_types.flash
;   slot 0 c: size 1, class 1 (either), param, weight 1
;   slot 1 a: size 2, class 1 (either), param, weight 0
func_types__flash
    STA func_types__flash__c
    CLC
    RTS

; function func_types.idle
;   no slots
func_types__idle
    RTS

; class func_types.handler: parameter sizes 1, 2

; func_types.beep is a member of class func_types.handler

; func_types.flash is a member of class func_types.handler

; data func_types.handlers: 6 bytes
func_types__handlers
    .byte <func_types__beep
    .byte <func_types__flash
    .byte <func_types__beep
    .byte >func_types__beep
    .byte >func_types__flash
    .byte >func_types__beep

; function func_types.take
;   slot 0 h: size 2, class 1 (either), param, weight 2
func_types__take
    STA func_types__take__h
    STX func_types__take__h+$01
    STA func_types__on_key
    STX func_types__on_key+$01
    RTS

; class func_types.action: parameter sizes none

; func_types.idle is a member of class func_types.action

; function func_types.set_up
;   slot 0 i: size 1, class 1 (either), param, weight 3
;   slot 1 local: size 2, class 1 (either), local, weight 6
;   calls func_types.take
func_types__set_up
    STA func_types__set_up__i
    LDA #<func_types__idle
    STA func_types__set_up__local
    LDA #>func_types__idle
    STA func_types__set_up__local+$01
    LDA func_types__set_up__local
    LDX func_types__set_up__i
    STA func_types__keys+$04,X
    LDA func_types__set_up__local+$01
    STA func_types__keys+$08,X
    LDA #<func_types__idle
    STA func_types__actions,X
    LDA #>func_types__idle
    STA func_types__actions+$03,X
    LDX #>func_types__flash
    LDA #<func_types__flash
    JSR func_types__take
    LDX func_types__set_up__i
    LDA func_types__handlers,X
    STA func_types__on_key
    LDA func_types__handlers+$03,X
    STA func_types__on_key+$01
    LDA func_types__on_key
    CMP func_types__handlers+$02
    BNE .L0050
    LDA func_types__on_key+$01
    CMP func_types__handlers+$05
    BNE .L0050
    LDA #$01
    BNE .L0052
.L0050
    LDA #$00
.L0052
    STA func_types__same
    LDA func_types__actions,X
    ORA func_types__actions+$03,X
    BEQ .L0074
    LDA func_types__set_up__local
    CMP #<func_types__idle
    BNE .L006F
    LDA func_types__set_up__local+$01
    CMP #>func_types__idle
    BNE .L006F
    LDA #$01
    BNE .L0071
.L006F
    LDA #$00
.L0071
    STA func_types__same
.L0074
    LDA #<func_types__idle
    STA func_types__where
    LDA #>func_types__idle
    STA func_types__where+$01
    LDA #$00
    STA func_types__on_key
    STA func_types__on_key+$01
    RTS

; variable func_types.on_key: size 2, class 1 (either), weight 8

; variable func_types.keys: size 12, class 2 (not zp), weight 2

; variable func_types.actions: size 6, class 2 (not zp), weight 4

; variable func_types.same: size 1, class 1 (either), weight 2

; variable func_types.where: size 2, class 1 (either), weight 2

; function func_types.$init
;   no slots
func_types__Sinit
    LDA #<func_types__beep
    STA func_types__on_key
    LDA #>func_types__beep
    STA func_types__on_key+$01
    RTS
