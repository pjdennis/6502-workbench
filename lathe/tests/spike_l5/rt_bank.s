; Spike L5, configuration "banked" on Wendy 2: the far-call routine for a bank switch.
; NMOS 6502 instructions only, so the same routine serves any board with a bank register.
;
; A stub, in fixed memory, one per function in a bank that is called from elsewhere or whose
; address is taken (written by the "linker", l5build.py):
;
;     STUB_f  JSR fc_call
;             .byte BANK            ; the bank's value for port B bits 0-4
;             .word f-1
;
; fc_call switches the window to BANK and enters f with A, X, Y and the flags as the caller
; left them. f returns into fc_back, which puts back the bank that was in the window at the
; call and returns to the caller with A, X and the carry as f left them (Y is lost).
; Nothing is kept in memory across the call: the bank to restore is on the stack, so nested
; and recursive far calls and far calls from an interrupt handler are safe. The scratch bytes
; fc_a ... fc_nb are used only with interrupts disabled.
BANK_PORT = $F000

fc_call                         ; stack: stub+2 (2), the caller's return (2)
    PHP
    SEI
    STA fc_a
    STX fc_x
    STY fc_y
    TSX                         ; S0: $0101,X = P, $0102,X = stub+2 low, $0103,X high
    LDA $0102,X
    STA fc_p
    LDA $0103,X
    STA fc_p+1
    LDY #$01
    LDA (fc_p),Y                ; the bank
    STA fc_nb
    LDY #$03
    LDA (fc_p),Y                ; f-1, high: will be pulled by the RTS below
    PHA
    DEY
    LDA (fc_p),Y                ; f-1, low
    PHA
    LDA $0101,X                 ; the flags, for the PLP below
    PHA
    LDA #<fc_back-$01           ; where f returns to
    STA $0101,X
    LDA #>fc_back-$01
    STA $0102,X
    LDA BANK_PORT               ; the bank now in the window, to restore
    TAY
    AND #$1F
    STA $0103,X
    TYA                         ; the switch keeps bits 5-7 (the LCD's E, LED, PB7)
    AND #$E0
    ORA fc_nb
    STA BANK_PORT
    LDA fc_a
    LDX fc_x
    LDY fc_y
    PLP                         ; the caller's flags, and its interrupt flag
    RTS                         ; to f

fc_back                         ; stack: the bank to restore (1), the caller's return (2)
    PHP                         ; the carry of f's result
    SEI
    STA fc_a
    STX fc_x
    TSX                         ; $0101,X = P, $0102,X = the bank
    LDA BANK_PORT
    AND #$E0
    ORA $0102,X
    STA BANK_PORT
    PLA                         ; P over the bank byte, for the PLP
    STA $0102,X
    LDX fc_x
    LDA fc_a
    PLP
    RTS
fc_end

; Sets port B bits 0-4 to A, keeping bits 5-7. Used by the start-up code that loads the banks.
fc_select
    STA fc_nb
    LDA BANK_PORT
    AND #$E0
    ORA fc_nb
    STA BANK_PORT
    RTS

fc_report
    CLC
    RTS
