; Spike L5: the storage every image shares, at fixed addresses (what the linker would allocate).
; Every image starts with this file. Zero page first, then main memory.
fc_p = $10          ; far-call routine: pointer to the stub's inline bytes (2)
fc_a = $12          ; far-call routine: A, X, Y kept while it works
fc_x = $13
fc_y = $14
fc_nb = $15         ; far-call routine: the bank or overlay asked for
fc_pp = $16         ; overlay routine: the flags of a result, while an overlay is reloaded
ld_p = $18          ; loader: where the next byte goes (2)
ld_s = $1A          ; loader: the file name (2)
ld_h = $1C          ; loader: the file handle
ov_cur = $1D        ; overlay routine: the overlay in the window, 0 for none
ld_n = $1E          ; overlay routine: loads so far (2)
fp = $20            ; a function pointer (2)
m_s = $22           ; main: the string being printed (2)
m_ra = $24          ; main: registers shown
m_rx = $25
m_rc = $26
cnt = $27           ; main: loop counters
cnt2 = $28
irq_cnt = $29       ; interrupts taken (2)
irq_bad = $2B       ; interrupts that saw the wrong bank
bad = $2C           ; far calls in the main loop that came back wrong
a_rt = $2D          ; module A: temporary of a_rec
b_rt = $2E          ; module B: temporary of b_rec
b_mid_n = $0200     ; module B: the static parameter slot of b_mid, in fixed main memory
