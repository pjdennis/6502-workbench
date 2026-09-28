;Timing of the serial receiver (serial_receive.inc) for the board's clock and baud rate.
;Requires CLOCK_FREQ_KHZ and BPS_HUNDREDS (see upload_and_run.inc)

  .if CLOCK_FREQ_KHZ > 6553
HALF_BIT_INTERVAL      = CLOCK_FREQ_KHZ / (BPS_HUNDREDS / 5)
  .else
HALF_BIT_INTERVAL      = CLOCK_FREQ_KHZ * 5 / BPS_HUNDREDS
  .endif

CLOCK_FREQ_MHZ_DIV_100 = CLOCK_FREQ_KHZ / 10

; -2 -26 is the most that can be reduced at 57600 without causing the shift
; start to be delayed... presuming anything less results in T2 expiring before
; the low order latch has been reset
INITIAL_INTERVAL       = HALF_BIT_INTERVAL * 2 - 2 - 24
SUBSEQUENT_INTERVAL    = HALF_BIT_INTERVAL - 2
