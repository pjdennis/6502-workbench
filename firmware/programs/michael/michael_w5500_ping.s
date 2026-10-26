; Gives the W5500 Ethernet module its network settings (network, below), so that it answers ping by itself,
; then keeps showing the link:
;   W5500 192.168.86.251
;   CONFIG OK              the settings read back as written (CONFIG BAD if not; NO W5500 if VERSIONR isn't $04)
;   LINK UP 100M FULL      or LINK DOWN; 10M, HALF
;   RETRIES 0000           reads and writes tried again after a glitch spoiled them (w5500.inc), in hex
; Then ping 192.168.86.251 from a computer on the same network. The settings suit the home network (the router
; 192.168.86.1), which a GL.iNet GL-MT3000 in extender mode joins Michael to; the MAC address is locally
; administered (02:...). The W5500 uses no DNS.
; Wiring as michael_w5500_version.s: the GAL SPI interface (gal_spi.inc), the W5500's chip select on PA0.
; Interrupts stay off, so the keyboard board never drives port B.
  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $00 ; 2 bytes
TO_DECIMAL_PARAM     = $02 ; 10 bytes
W5500_VALUE          = $0C ; 1 byte
W5500_FIRST          = $0D ; 1 byte
W5500_TRIES_LEFT     = $0E ; 1 byte
W5500_RETRIES        = $0F ; 2 bytes
CONFIG_BAD           = $11 ; 1 byte

  .org PROGRAM_LOAD_ADDRESS
start:
  jmp initialize_machine

  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_decimal.inc
  .include convert_to_hex.inc
  .include gal_spi.inc
  .include w5500.inc

program_start:
  ldx #$ff
  txs
  sei
  jsr w5500_initialize
  jsr reset_and_enable_display_no_cursor
  stz W5500_RETRIES
  stz W5500_RETRIES + 1
  lda #<title
  ldx #>title
  jsr display_string
  jsr show_ip
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor

  ldx #>W5500_VERSIONR
  ldy #<W5500_VERSIONR
  jsr w5500_read_common
  bcs .absent
  cmp #W5500_VERSION
  beq .found
.absent:
  lda #<no_w5500
  ldx #>no_w5500
  jsr display_string
.stop:
  bra .stop

.found:
  ; A software reset (MR reads 0 once it's done, so it isn't read back), then the settings a register at a
  ; time, each read back
  ldx #>W5500_MR
  ldy #<W5500_MR
  lda #W5500_COMMON_WRITE
  jsr w5500_begin
  lda #W5500_MR_RST
  jsr w5500_write_byte
  jsr w5500_end
.resetting:
  jsr w5500_read_common
  bcs .resetting
  and #W5500_MR_RST
  bne .resetting

  stz CONFIG_BAD
  ldx #>W5500_GAR
  ldy #<W5500_GAR
.write:
  lda network - W5500_GAR,Y
  jsr w5500_write_common
  bcc .written
  lda #1
  sta CONFIG_BAD
.written:
  iny
  cpy #<(W5500_GAR + W5500_NETWORK_SIZE)
  bne .write
  lda #<config_ok
  ldx #>config_ok
  ldy CONFIG_BAD
  beq .show_config
  lda #<config_bad
  ldx #>config_bad
.show_config:
  jsr display_string

.watch:
  jsr show_link
  jsr show_retries
  bra .watch


; The IP address, from the settings, in decimal
show_ip:
  ldy #0
.next:
  lda network + W5500_SIPR - W5500_GAR,Y
  ldx #0
  jsr display_decimal
  iny
  cpy #4
  beq .done
  lda #'.'
  jsr display_character
  bra .next
.done:
  rts


show_link:
  lda #DISPLAY_THIRD_LINE
  jsr move_cursor
  ldx #>W5500_PHYCFGR
  ldy #<W5500_PHYCFGR
  jsr w5500_read_common
  tay                            ; PHYCFGR, for the tests below (display_string preserves A, X, Y)
  and #W5500_LINK
  bne .up
  lda #<link_down
  ldx #>link_down
  jmp display_string
.up:
  lda #<link_up
  ldx #>link_up
  jsr display_string
  tya
  and #W5500_100M
  beq .speed
  lda #<speed_100
  ldx #>speed_100
  bra .show_speed
.speed:
  lda #<speed_10
  ldx #>speed_10
.show_speed:
  jsr display_string
  tya
  and #W5500_FULL
  beq .half
  lda #<full
  ldx #>full
  jmp display_string
.half:
  lda #<half
  ldx #>half
  jmp display_string


show_retries:
  lda #DISPLAY_FOURTH_LINE
  jsr move_cursor
  lda #<retries
  ldx #>retries
  jsr display_string
  lda W5500_RETRIES + 1
  jsr show_hex
  lda W5500_RETRIES
  ; fall through

; On entry A = the byte to show in hex
show_hex:
  jsr convert_to_hex
  jsr display_character
  txa
  jmp display_character


; GAR, SUBR, SHAR and SIPR, in the W5500's order
network:
  .byte 192, 168, 86, 1                      ; the gateway: the home router
  .byte 255, 255, 255, 0                     ; the subnet mask
  .byte $02, $65, $02, $00, $00, $01         ; the MAC address
  .byte 192, 168, 86, 251                    ; the IP address

title:      .asciiz "W5500 "
no_w5500:   .asciiz "NO W5500"
config_ok:  .asciiz "CONFIG OK"
config_bad: .asciiz "CONFIG BAD"
link_down:  .asciiz "LINK DOWN        "
link_up:    .asciiz "LINK UP "
speed_100:  .asciiz "100M "
speed_10:   .asciiz "10M  "
full:       .asciiz "FULL"
half:       .asciiz "HALF"
retries:    .asciiz "RETRIES "
