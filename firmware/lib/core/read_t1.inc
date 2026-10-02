; Reads the 6522's T1 counter in a fixed time, without the misread (off by $100) that reading
; its two bytes one after the other can give when the low byte wraps in between
; Requires T_HI, T_LO - 1 byte each

; On exit T_HI, T_LO = T1's count when the low byte was read. The time taken doesn't depend
;         on the count (a retry would add to some measurements)
;         A is not preserved
;         X, Y are preserved
read_t1:
  lda T1CH
  sta T_HI
  lda T1CL
  sta T_LO
  bpl .done                      ; Read too soon after T_HI for the low byte to have wrapped
  lda T1CH                       ; Near $FF it may just have wrapped: then the high byte has
  sta T_HI                       ; changed, and won't again for another 128 cycles
.done:
  rts
