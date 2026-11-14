; Spike L5, the main module: always in fixed memory, first in the fixed image.
; Calls are plain JSRs; the configuration decides whether a name is a function or its stub.
; ADDR_f is what @f gives: the stub of a function in a window, else the function.
; With MEASURE it runs only a timing loop (M_LEAF, M_MID, M_SWAP or nothing) and exits.

m_main
    LDX #$FF
    TXS
    CLD
    JSR env_init
    JSR fc_init
    JSR env_start
    .ifdef MEASURE
    LDA #$00                    ; 256 iterations
    .ifdef HALF
    LDA #$80                    ; 128 iterations
    .endif
    STA cnt
.mloop
    .ifdef M_LEAF
    LDA #$05
    JSR a_leaf
    .endif
    .ifdef M_MID
    LDA #$05
    JSR b_mid
    .endif
    .ifdef M_SWAP
    LDA #$05
    JSR a_leaf
    LDA #$05
    JSR b_dbl
    .endif
    DEC cnt
    BNE .mloop
    JMP env_exit
    .endif

    LDA #<m_t_nest              ; M -> A -> B -> A, results back through every return
    LDX #>m_t_nest
    JSR m_print
    LDA #$05
    JSR a_entry
    JSR m_show

    LDA #<m_t_rec               ; recursion across the two modules, 20 levels
    LDX #>m_t_rec
    JSR m_print
    LDA #$14
    JSR a_rec
    JSR m_word

    LDA #<m_t_ptr1              ; M through a pointer to B
    LDX #>m_t_ptr1
    JSR m_print
    LDA #<ADDR_b_dbl
    STA fp
    LDA #>ADDR_b_dbl
    STA fp+1
    LDA #$21
    JSR m_pcall
    JSR m_show

    LDA #<m_t_ptr2              ; A through a pointer to B
    LDX #>m_t_ptr2
    JSR m_print
    LDA #$22
    JSR a_ptrcall
    JSR m_show

    LDA #<m_t_ptr3              ; A through a pointer to A itself
    LDX #>m_t_ptr3
    JSR m_print
    LDA #<ADDR_a_leaf
    STA fp
    LDA #>ADDR_a_leaf
    STA fp+1
    LDA #$30
    JSR a_ptrcall
    JSR m_show

    .ifdef HAS_TIMER
    JSR m_irqtest
    .endif
    JSR env_report
    JSR fc_report               ; carry set: A and X hold the number of overlay loads
    BCC .end
    PHA
    TXA
    PHA
    LDA #<m_t_loads
    LDX #>m_t_loads
    JSR m_print
    PLA
    TAX
    PLA
    JSR m_word
.end
    JMP env_exit

; A timer interrupt every few hundred cycles while the main program makes far calls. The
; handler makes a far call of its own (b_irq), wherever the main program is.
    .ifdef HAS_TIMER
m_irqtest
    LDA #$00
    STA irq_cnt
    STA irq_cnt+1
    STA irq_bad
    STA bad
    LDA #<ADDR_b_dbl
    STA fp
    LDA #>ADDR_b_dbl
    STA fp+1
    JSR env_timer_start
    LDA #$00
    STA cnt
    LDA #$02
    STA cnt2
.loop
    LDA #$05
    JSR a_entry
    CMP #$06
    BNE .bad
    CPX #$A1
    BNE .bad
    BCC .bad
    LDA #$11
    JSR a_ptrcall
    CMP #$22
    BNE .bad
    CPX #$B2
    BNE .bad
    BCS .bad
    JMP .next
.bad
    INC bad
.next
    DEC cnt
    BNE .loop
    DEC cnt2
    BNE .loop
    JSR env_timer_stop
    LDA #<m_t_irq
    LDX #>m_t_irq
    JSR m_print
    LDA bad
    ORA irq_bad
    BNE .fail
    LDA irq_cnt+1               ; at least 256 interrupts
    BEQ .fail
    LDA #<m_t_ok
    LDX #>m_t_ok
    JMP m_print
.fail
    LDA #<m_t_fail
    LDX #>m_t_fail
    JMP m_print

m_irq
    PHA
    TXA
    PHA
    TYA
    PHA
    JSR env_timer_ack
    JSR b_irq
    CMP #$B2
    BEQ .ok
    INC irq_bad
.ok
    INC irq_cnt
    BNE .done
    INC irq_cnt+1
.done
    PLA
    TAY
    PLA
    TAX
    PLA
    RTI
    .endif

; A call through fp: JSR here is the call, as the compiler writes it.
m_pcall
    JMP (fp)

; Prints the zero-terminated string at A (low) and X (high).
m_print
    STA m_s
    STX m_s+1
    LDY #$00
.loop
    LDA (m_s),Y
    BEQ .done
    JSR env_out
    INY
    BNE .loop
.done
    RTS

; Prints A, X and the carry: "AA XX C" and a new line.
m_show
    STA m_ra
    STX m_rx
    LDA #$00
    ROL
    STA m_rc
    LDA m_ra
    JSR m_hex
    LDA #' '
    JSR env_out
    LDA m_rx
    JSR m_hex
    LDA #' '
    JSR env_out
    LDA m_rc
    ORA #'0'
    JSR env_out
    LDA #$0A
    JMP env_out

; Prints the word in A (low) and X (high) as four hex digits and a new line.
m_word
    STA m_ra
    TXA
    JSR m_hex
    LDA m_ra
    JSR m_hex
    LDA #$0A
    JMP env_out

; Prints A as two hex digits.
m_hex
    PHA
    LSR
    LSR
    LSR
    LSR
    JSR .digit
    PLA
    AND #$0F
.digit
    CMP #$0A
    BCC .num
    ADC #$06
.num
    ADC #'0'
    JMP env_out

m_t_nest
    .asciiz "nest "
m_t_rec
    .asciiz "rec "
m_t_ptr1
    .asciiz "ptr1 "
m_t_ptr2
    .asciiz "ptr2 "
m_t_ptr3
    .asciiz "ptr3 "
m_t_loads
    .asciiz "loads "
    .ifdef HAS_TIMER
m_t_irq
    .asciiz "irq "
m_t_ok
    .byte 'o','k',$0A,$00
m_t_fail
    .byte 'f','a','i','l',$0A,$00
    .endif
