CLOCK_FREQ_KHZ          = 2000
INTERRUPT_VECTOR_TARGET = $3f00 ; Interrupt vector in EEPROM points to this address
                                ; Prior value: $3f00, BBC BASIC: $0800
PROGRAM_LOAD_ADDRESS    = $2000 ; Where programs load and start: the ROM's loader (michael_rom.s) takes
                                ; the address from the upload, so this is the programs' choice, below
                                ; their data at $0200-$1FFF. Prior values: $0900, $2000; BBC BASIC's
                                ; loader: $0900
; PORTA assignments
E      = %10000000  ; Display enable
RW     = %01000000  ; Display read/write
RS     = %00100000  ; Display register select

SOEB   = %00010000  ; Input shift register output enable (active low) 
SOLB   = %00001000  ; Output shift register load / clock low (active low)
START  = %00100000  ; Output start bit - multiplexed with RS and ACK bit
ACK    = %00100000  ; Input ACK bit - multiplexed with RS and output start bit
PARITY = %01000000  ; Input and output parity bit - multiplexed with RW

LED    = %00000010  ; Output LED: PA1, lit while high
FPGA_E = %00000100  ; The FPGA bus's strobe: PA2 (fpga_bus.inc), an output, low between transfers

DISPLAY_BITS = 8

; 16x2 LCD
;DISPLAY_WIDTH     = 16
;DISPLAY_HEIGHT    = 2
;DISPLAY_LAST_LINE = DISPLAY_SECOND_LINE

; 20x4 LCD
DISPLAY_WIDTH     = 20
DISPLAY_HEIGHT    = 4
DISPLAY_LAST_LINE = DISPLAY_FOURTH_LINE

; Include additional definitions
  .include display_parameters.inc
  .include 6522.inc

