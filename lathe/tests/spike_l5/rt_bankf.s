; Spike L5, configuration "banked, fast stubs" on Wendy 2. NMOS 6502 instructions only.
;
; The stub is longer and does the call itself, so the routine reads nothing through the
; return address and builds no frame (written by l5build.py):
;
;     STUB_f  PHA                   ; the caller's A
;             LDA #BANK
;             JSR fc_enter          ; switch; A back as the caller left it
;             JSR f
;             JMP fc_leave          ; switch back; A, X, carry as f left them
;
; fc_enter puts the bank to restore in the stack byte that held the caller's A, so nothing is
; kept in memory across the call, as in rt_bank.s; scratch bytes only with interrupts off.
BANK_PORT = $F000

fc_call
fc_enter                        ; A = bank; stack: return (2), the caller's A, the caller's return
    PHP
    SEI
    STX fc_x
    STA fc_nb
    TSX                         ; $0101,X = P, $0102-3,X = return, $0104,X = the caller's A
    LDA $0104,X
    STA fc_a
    LDA BANK_PORT
    AND #$1F
    STA $0104,X                 ; the bank to restore
    EOR BANK_PORT               ; = port B with bits 0-4 clear
    ORA fc_nb
    STA BANK_PORT
    LDX fc_x
    LDA fc_a
    PLP
    RTS

fc_leave                        ; stack: the bank to restore (1), the caller's return (2)
    PHP
    SEI
    STA fc_a
    STX fc_x
    TSX
    LDA BANK_PORT
    AND #$E0
    ORA $0102,X
    STA BANK_PORT
    PLA
    STA $0102,X
    LDX fc_x
    LDA fc_a
    PLP
    RTS
fc_end

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
