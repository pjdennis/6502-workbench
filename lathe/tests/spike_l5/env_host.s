; Spike L5: the emulator's default machine. Host services at $F006 and up
; (asm/17/environment.asm). No timer, so no HAS_TIMER.

env_init
    RTS

env_start
    RTS

env_out
    JMP $F009

env_exit
    LDA #$00
    JMP $F00F

env_report
    RTS

; Loads the file named at ld_s (zero-terminated) to ld_p and on, to its end.
env_load
    LDA ld_s
    LDX ld_s+1
    JSR $F012                   ; open: handle in A, 0 if it failed
    STA ld_h
    CMP #$00
    BEQ .fail
    LDY #$00
.loop
    LDA ld_h
    JSR $F018                   ; read: byte in A, carry at the end; X and Y kept
    BCS .done
    STA (ld_p),Y
    INY
    BNE .loop
    INC ld_p+1
    JMP .loop
.done
    LDA ld_h
    JMP $F015                   ; close
.fail
    LDA #$02
    JMP $F00F
