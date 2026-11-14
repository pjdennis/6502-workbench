; Spike L5: emulated Wendy 2 (--machine wendy2c) run with --disk DIR, which adds the file
; ports at $F800-$F80F (emulator/chips/syscall_ports.h). Output goes to the file out.txt.
; Port B: bits 0-4 the bank, bit 5 the LCD's E, bit 6 an LED; the far-call routine must keep
; bits 5-7, so this module sets bit 6 at the start and env_report checks it at the end.
VIA_PORTB = $F000
VIA_DDRB = $F002
VIA_T1CL = $F004
VIA_T1CH = $F005
VIA_ACR = $F00B
VIA_IER = $F00E
SYS_NAME = $F800
SYS_CLEAR = $F801
SYS_OPENR = $F802
SYS_OPENW = $F803
SYS_READ = $F805
SYS_EOF = $F806
SYS_WRITE = $F807
SYS_CLOSE = $F808
TIMER_PERIOD = $0131            ; 307 cycles: not a multiple of anything in the loop

env_init
    LDA #$FF                    ; every bit of port B an output: it reads back as written
    STA VIA_DDRB
    LDA #$41                    ; bank configuration $01, LED on
    STA VIA_PORTB
    RTS

env_start
    LDA #<env_outname
    STA ld_s
    LDA #>env_outname
    STA ld_s+1
    JSR env_name
    LDA SYS_OPENW               ; stays the current handle: env_out writes to it
    RTS

env_out
    STA SYS_WRITE
    RTS

env_exit
    STA SYS_CLOSE
    .byte $DB                   ; STP

env_report
    LDA VIA_PORTB
    AND #$E0
    CMP #$40
    BNE .bad
    LDA #<env_t_ok
    LDX #>env_t_ok
    JMP m_print
.bad
    LDA #<env_t_bad
    LDX #>env_t_bad
    JMP m_print

; Sends the name at ld_s to the file ports.
env_name
    STA SYS_CLEAR
    LDY #$00
.loop
    LDA (ld_s),Y
    BEQ .done
    STA SYS_NAME
    INY
    BNE .loop
.done
    RTS

; Loads the file named at ld_s to ld_p and on, to its end.
env_load
    JSR env_name
    LDA SYS_OPENR
    BEQ .fail
    LDY #$00
.loop
    LDA SYS_EOF
    BMI .done
    LDA SYS_READ
    STA (ld_p),Y
    INY
    BNE .loop
    INC ld_p+1
    JMP .loop
.done
    STA SYS_CLOSE
    RTS
.fail
    .byte $DB

env_timer_start
    SEI
    LDA #<m_irq
    STA $FFFE
    LDA #>m_irq
    STA $FFFF
    LDA #$40                    ; timer 1 runs free
    STA VIA_ACR
    LDA #<TIMER_PERIOD-$02
    STA VIA_T1CL
    LDA #>TIMER_PERIOD-$02
    STA VIA_T1CH
    LDA #$C0
    STA VIA_IER
    CLI
    RTS

env_timer_stop
    LDA #$40
    STA VIA_IER
    RTS

env_timer_ack
    LDA VIA_T1CL
    RTS

env_outname
    .asciiz "out.txt"
env_t_ok
    .byte 'p','o','r','t',' ','o','k',$0A,$00
env_t_bad
    .byte 'p','o','r','t',' ','b','a','d',$0A,$00
