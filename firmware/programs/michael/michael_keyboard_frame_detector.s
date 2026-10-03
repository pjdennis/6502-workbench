; Measures the idle time of Michael's PS/2 frame detector: how long CA2 stays low after the
; keyboard clock is released. It holds the clock low with SOLB (START high, so no command is
; sent), releases it and times CA2's rising edge with T1. It shows 8 measurements in hex, in
; T1 ticks (0.5 us at 2 MHz). See docs/michael-keyboard-frame-detection.md.

  .include base_config_v2.inc

T_HI                 = $00 ; 1 byte
T_LO                 = $01 ; 1 byte
START_HI             = $02 ; 1 byte
START_LO             = $03 ; 1 byte

RESULTS              = $0200 ; 2 bytes per measurement, high byte first
MEASUREMENTS         = 8

  .org PROGRAM_LOAD_ADDRESS      ; Loader loads programs to this address
start:
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_hex.inc
  .include read_t1.inc


program_start:
  ; Initialize stack
  ldx #$ff
  txs

  jsr reset_and_enable_display_no_cursor

  sei
  lda #$7f
  sta IER                        ; No interrupts: IFR is polled

  lda #ACR_T1_CONT               ; T1 free-running from $FFFF
  sta ACR
  lda #$ff
  sta T1CL
  sta T1CH

  lda #START
  tsb PORTA                      ; Data line high when the clock is released: no command

  ldx #0
measure:
  lda #PCR_CA2_IND_NEG_E
  sta PCR
  lda #ICA2
  sta IFR
  lda #SOLB
  trb PORTA                      ; Hold the clock low
  lda #ICA2
.wait_for_low:
  bit IFR
  beq .wait_for_low
  sta IFR
  lda #PCR_CA2_IND_POS_E
  sta PCR
  lda #SOLB
  tsb PORTA                      ; Release the clock
  jsr read_t1
  lda T_HI
  sta START_HI
  lda T_LO
  sta START_LO
  lda #ICA2
.wait_for_high:
  bit IFR
  beq .wait_for_high
  jsr read_t1

  ; T1 counts down, so the time taken is START - T
  lda START_LO
  sec
  sbc T_LO
  sta RESULTS + 1, X
  lda START_HI
  sbc T_HI
  sta RESULTS, X

  lda #20
  jsr delay_10_thousandths       ; 2 ms between measurements
  inx
  inx
  cpx #MEASUREMENTS * 2
  bne measure

  lda #START
  trb PORTA                      ; START is also the LCD's RS

  ; Show 4 measurements per line
  lda #DISPLAY_FIRST_LINE
  jsr move_cursor
  ldx #0
show:
  cpx #MEASUREMENTS
  bne .not_second_line
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  bra .show
.not_second_line:
  cpx #0
  beq .show
  jsr display_space
.show:
  lda RESULTS, X
  jsr display_hex
  lda RESULTS + 1, X
  jsr display_hex
  inx
  inx
  cpx #MEASUREMENTS * 2
  bne show

forever:
  bra forever
