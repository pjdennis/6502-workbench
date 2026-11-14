; Spike L5, configuration "overlays" on the emulator's default machine: the far-call routine
; for overlays loaded from disk through the host file services. The window is $8000-$8FFF.
;
; A stub has the same form as for banks (written by l5build.py):
;
;     STUB_f  JSR fc_call
;             .byte OVERLAY         ; 1, 2, ...
;             .word f-1
;
; If OVERLAY is in the window already, fc_call enters f directly and f returns straight to
; the caller: no frame, nothing to restore. Otherwise it loads OVERLAY, and f returns into
; fc_back, which loads again the overlay that was in the window at the call (if there was
; one), so the caller's code is there when it returns. The overlay to restore is on the
; stack, so nesting and recursion are safe. The loader is not reentrant: an interrupt
; handler must not make a far call into an overlay (a link error in the design).
; ov_names (written by l5build.py) holds each overlay's file name.

fc_init
    LDA #$00
    STA ov_cur
    STA ld_n
    STA ld_n+1
    RTS

fc_call                         ; stack: stub+2 (2), the caller's return (2)
    STA fc_a
    STX fc_x
    STY fc_y
    TSX                         ; $0101,X = stub+2 low, $0102,X high
    LDA $0101,X
    STA fc_p
    LDA $0102,X
    STA fc_p+1
    LDY #$01
    LDA (fc_p),Y                ; the overlay
    CMP ov_cur
    BNE .far
    INY                         ; in the window: return address := f-1, and go
    LDA (fc_p),Y
    STA $0101,X
    INY
    LDA (fc_p),Y
    STA $0102,X
    LDA fc_a
    LDX fc_x
    LDY fc_y
    RTS
.far
    STA fc_nb
    LDA #<fc_back-$01           ; frame: f-1 (2), fc_back-1 (2), the overlay to restore
    PHA
    LDY #$03
    LDA (fc_p),Y
    PHA
    DEY
    LDA (fc_p),Y
    PHA
    LDA #>fc_back-$01
    STA $0101,X
    LDA ov_cur
    STA $0102,X
    LDA fc_nb
    JSR ov_load
    LDA fc_a
    LDX fc_x
    LDY fc_y
    RTS                         ; to f

fc_back                         ; stack: the overlay to restore (1), the caller's return (2)
    PHP
    STA fc_a
    STX fc_x
    PLA
    STA fc_pp
    PLA
    BEQ .keep                   ; none was loaded: the caller is in fixed memory
    CMP ov_cur
    BEQ .keep
    JSR ov_load
.keep
    LDA fc_pp
    PHA
    LDA fc_a
    LDX fc_x
    PLP
    RTS
fc_end

; Loads overlay A into the window.
ov_load
    STA ov_cur
    TAX
    LDA ov_nlo,X
    STA ld_s
    LDA ov_nhi,X
    STA ld_s+1
    LDA #$00
    STA ld_p
    LDA #$80
    STA ld_p+1
    INC ld_n
    BNE .go
    INC ld_n+1
.go
    JMP env_load
ov_end

fc_report                       ; carry set, A and X = the number of loads
    LDA ld_n
    LDX ld_n+1
    SEC
    RTS
