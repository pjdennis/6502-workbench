; The WIZnet W5500 Ethernet controller on Michael's GAL SPI interface (gal_spi.inc), its chip select on PA0.
; A frame is w5500_begin (the address and the control byte), data bytes (w5500_write_byte, w5500_read_byte),
; then w5500_end; the address counts up through the data.
;
; While the address and control bytes go in, the W5500 answers on MISO with $01, $02 and $03. w5500_begin
; checks the third, so a frame it didn't take whole (a glitch on its chip select starts it again, and it would
; answer $01 or $02) is reported rather than trusted. (Reading the address bytes' answers too would have the
; '299 drive $01 and $02 over them: more falling lines than port B can take at once.)
;
; If the chip select carries a capacitor (against glitches), a program defines W5500_CS_SETTLE first: then,
; after each change, w5500_begin and w5500_end wait for it, W5500_CS_SETTLE loops of 5 cycles (36 is about
; 100 us at 2 MHz).
;
; A glitch can still spoil a frame now and then, so w5500_read_common and w5500_write_common check their work:
; a register is read twice in two frames, and must read the same both times, and a write is read back; each
; tries again, up to W5500_TRIES times in all, and counts the extra tries in W5500_RETRIES.
;
; Requires: gal_spi.inc; W5500_VALUE, W5500_FIRST and W5500_TRIES_LEFT (1 byte each), W5500_RETRIES (2 bytes,
; which the program clears). Interrupts off around a frame (see gal_spi.inc).

W5500_CS           = %00000001 ; PA0, active low; the module pulls it up

  .include w5500_registers.inc

W5500_TRIES        = 8     ; w5500_read_common and w5500_write_common try this many times at most


; Deselects the W5500 and makes its chip select an output. A, X, Y are preserved
w5500_initialize:
  pha
  lda #W5500_CS
  tsb PORTA                      ; Deselected before PA0 becomes an output
  tsb DDRA
  pla
  rts


; Starts a frame. On entry X, Y = the address's high, low bytes; A = the control byte
; On exit carry clear if the W5500 answered the control byte with $03, set if not; the frame is open either way
;         X, Y are preserved
w5500_begin:
  pha
  lda #W5500_CS
  trb PORTA                      ; Select
  .ifdef W5500_CS_SETTLE
  jsr w5500_cs_settle
  .endif
  txa
  jsr gal_spi_write
  tya
  jsr gal_spi_write
  pla
  jsr gal_spi_read
  eor #$03
  cmp #1                         ; Carry set unless it was $03
  rts


; Ends the frame. A, X, Y are preserved
w5500_end:
  pha
  lda #W5500_CS
  tsb PORTA
  pla
  .ifndef W5500_CS_SETTLE
  rts
  .else
  ; fall through

; Waits for the chip select to reach its new level. A, X, Y are preserved
w5500_cs_settle:
  pha
  lda #W5500_CS_SETTLE
.loop:
  dec
  bne .loop
  pla
  rts
  .endif


; Sends A, a data byte. X, Y are preserved
w5500_write_byte = gal_spi_write


; On exit A = the next data byte. X, Y are preserved
w5500_read_byte:
  lda #$00
  jmp gal_spi_read


; Reads the common register at X (high), Y (low): twice, each in a frame of its own whose header the W5500
; answered as it should, until both reads agree (W5500_TRIES times at most).
; On exit A = the value; carry clear if two reads agreed, set if they never did; X, Y are preserved
w5500_read_common:
  lda #W5500_TRIES
  sta W5500_TRIES_LEFT
.try:
  jsr w5500_read_once
  bcs .again
  sta W5500_FIRST
  jsr w5500_read_once
  bcs .again
  cmp W5500_FIRST
  beq .done                      ; Carry clear: equal
.again:
  jsr w5500_count_retry
  dec W5500_TRIES_LEFT
  bne .try
  sec
  rts
.done:
  clc
  rts


; Writes A to the common register at X (high), Y (low) in a frame of its own, then reads it back
; (w5500_read_common), until it reads back as written (W5500_TRIES times at most).
; On exit A = the value; carry clear if it read back as written, set if it never did; X, Y are preserved
w5500_write_common:
  sta W5500_VALUE
  lda #W5500_TRIES
.try:
  pha                            ; Tries left
  lda #W5500_COMMON_WRITE
  jsr w5500_begin
  lda W5500_VALUE
  jsr w5500_write_byte
  jsr w5500_end
  jsr w5500_read_common
  bcs .again
  cmp W5500_VALUE
  beq .written
.again:
  jsr w5500_count_retry
  pla
  dec
  bne .try
  lda W5500_VALUE
  sec
  rts
.written:
  pla
  lda W5500_VALUE
  clc
  rts


; One read of the common register at X, Y in a frame of its own.
; On exit A = the value; carry set if the W5500 didn't answer the header as it should; X, Y are preserved
w5500_read_once:
  lda #W5500_COMMON_READ
  jsr w5500_begin
  php
  jsr w5500_read_byte
  jsr w5500_end
  plp
  rts


; A, X, Y are preserved
w5500_count_retry:
  inc W5500_RETRIES
  bne .counted
  inc W5500_RETRIES + 1
.counted:
  rts
