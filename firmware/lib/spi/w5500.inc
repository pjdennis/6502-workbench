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
; Requires: gal_spi.inc. Interrupts off around a frame (see gal_spi.inc).

W5500_CS           = %00000001 ; PA0, active low; the module pulls it up

; Control bytes: the block (bits 7-3; 0 the common registers), write (bit 2), variable length (bits 1-0 0: the
; frame lasts until the chip select rises)
W5500_COMMON_READ  = $00
W5500_COMMON_WRITE = $04

; Common registers
W5500_MR           = $0000 ; mode: RST (bit 7) resets every register, then reads 0; PB (bit 4) blocks ping replies
W5500_MR_RST       = $80
W5500_GAR          = $0001 ; the gateway (4 bytes), then in one run SUBR, the subnet mask (4), SHAR, the MAC
W5500_SUBR         = $0005 ; address (6), and SIPR, the IP address (4)
W5500_SHAR         = $0009
W5500_SIPR         = $000F
W5500_NETWORK_SIZE = 18    ; GAR to the end of SIPR
W5500_PHYCFGR      = $002E ; the PHY: link up (bit 0), 100 Mbps (bit 1), full duplex (bit 2)
W5500_LINK         = %00000001
W5500_100M         = %00000010
W5500_FULL         = %00000100
W5500_VERSIONR     = $0039 ; always W5500_VERSION
W5500_VERSION      = $04


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
