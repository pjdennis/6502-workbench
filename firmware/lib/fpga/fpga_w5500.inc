; The WIZnet W5500 Ethernet controller on the FPGA bus's network device, FB_NET (docs/michael-fpga-w5500-plan.md).
; The FPGA makes each SPI frame: Michael sends the address, the control byte (a block, w5500_registers.inc: the
; routines here add the write bit themselves) and either a byte count or the data. A read's bytes join the
; reply queue, and fb_read (w5500_read_byte) takes them; a write's data streams (w5500_write_byte) until
; w5500_end. The FPGA checks the header count the W5500 answers ($01 $02 $03) and sets FB_NET_ERROR in the status
; if a frame didn't get it; each routine here waits until the FPGA has finished (BUSY clear), gathering the
; status's error bits on the way, and returns carry set if there were any; W5500_FAULTS counts the times.
;
; Requires: fpga_bus.inc, fb_initialize called; W5500_COUNT and W5500_ERRORS (1 byte each), W5500_WORD and
; W5500_FAULTS (2 bytes each; the program clears W5500_FAULTS)

  .include w5500_registers.inc

w5500_read_byte  = fb_read
w5500_write_byte = fb_data


; Reads W5500_COUNT bytes (0 means 256) into the reply queue, from the address X (high), Y (low) in the block
; whose control byte is A; w5500_read_byte then takes each.
; On exit carry set if a frame went wrong (A = the error bits, w5500_wait); X, Y are preserved
w5500_read:
  pha
  lda #FB_NET_READ
  jsr w5500_header
  pla
  jsr fb_data
  lda W5500_COUNT
  jsr fb_data
  ; fall through

; Waits until the FPGA has finished what it was sent, gathering the status's error bits.
; On exit A = the error bits seen (FB_ERRORS and FB_NET_ERROR), carry set if there were any (and W5500_FAULTS
;         counted); X, Y are preserved
w5500_wait:
  stz W5500_ERRORS
.poll:
  jsr fb_status
  pha
  and #(FB_ERRORS | FB_NET_ERROR)
  tsb W5500_ERRORS
  pla
  bmi .poll                      ; BUSY, bit 7
  lda W5500_ERRORS
  beq .done                      ; None
  inc W5500_FAULTS
  bne .counted
  inc W5500_FAULTS + 1
.counted:
  lda W5500_ERRORS
.done:
  cmp #1                         ; Carry set unless 0
  rts


; Starts a frame writing at the address X (high), Y (low) in the block whose control byte is A; w5500_write_byte
; sends each byte, then w5500_end ends it.
; On exit A, X, Y are preserved
w5500_write:
  pha
  lda #FB_NET_WRITE
  jsr w5500_header
  pla
  pha
  ora #W5500_WRITE
  jsr fb_data
  pla
  rts


; Ends a write's frame and waits for it.
; On exit carry set if it went wrong (A = the error bits, w5500_wait); X, Y are preserved
w5500_end:
  lda #FB_NOP
  jsr fb_command
  bra w5500_wait


; Reads the register at Y in the block whose control byte is X.
; On exit A = its value, Z and N set from it; carry set if the frame went wrong; X, Y are preserved
w5500_read_register:
  lda #1
  jsr w5500_read_registers
  jmp w5500_read_byte_keep_carry


; Reads the 16-bit register (high byte first) at Y in the block whose control byte is X.
; On exit W5500_WORD = its value (low byte first); carry set if the frame went wrong; X, Y are preserved
w5500_read_register16:
  lda #2
  jsr w5500_read_registers
  jsr w5500_read_byte_keep_carry
  sta W5500_WORD + 1
  jsr w5500_read_byte_keep_carry
  sta W5500_WORD
  rts


; Writes A to the register at Y in the block whose control byte is X.
; On exit carry set if the frame went wrong; X, Y are preserved
w5500_write_register:
  pha
  jsr w5500_register_write
  pla
  jsr w5500_write_byte
  bra w5500_end


; Writes W5500_WORD to the 16-bit register (high byte first) at Y in the block whose control byte is X.
; On exit carry set if the frame went wrong; X, Y are preserved
w5500_write_register16:
  jsr w5500_register_write
  lda W5500_WORD + 1
  jsr w5500_write_byte
  lda W5500_WORD
  jsr w5500_write_byte
  bra w5500_end


; Reads A bytes from the register at Y in the block whose control byte is X into the reply queue.
; On exit carry set if the frame went wrong; X, Y are preserved
w5500_read_registers:
  sta W5500_COUNT
  phx
  txa
  ldx #0                         ; Registers' addresses are all below $0100
  jsr w5500_read
  plx
  rts


; Starts a frame writing at the register at Y in the block whose control byte is X. X, Y are preserved
w5500_register_write:
  phx
  txa
  ldx #0
  jsr w5500_write
  plx
  rts


; On exit A = the next byte of the reply queue, Z and N set from it; carry is preserved (fb_read sets it); X, Y
;         are preserved
w5500_read_byte_keep_carry:
  php
  jsr w5500_read_byte
  plp
  ora #0                         ; Z and N from the byte (carry untouched)
  rts


; Sends FB_NET, the operation A and the address X (high), Y (low). X, Y are preserved
w5500_header:
  pha
  lda #FB_NET
  jsr fb_command
  pla
  jsr fb_data
  txa
  jsr fb_data
  tya
  jmp fb_data
