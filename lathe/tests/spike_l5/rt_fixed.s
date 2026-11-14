; Spike L5, configuration "all fixed": every module in fixed memory, every call a plain JSR.
; There is no far-call routine and there are no stubs.

fc_init
    RTS

fc_report
    CLC
    RTS
