; The WIZnet W5500 Ethernet controller's control bytes and registers, for its drivers: w5500.inc (on the GAL SPI
; interface) and fpga_w5500.inc (on the FPGA bus).

; Control bytes: the block (bits 7-3; 0 the common registers), write (bit 2), variable length (bits 1-0 0: the
; frame lasts until the chip select rises)
W5500_COMMON_READ  = $00
W5500_COMMON_WRITE = $04
W5500_WRITE        = $04
; The blocks, as control bytes: the common registers; socket 0's registers, TX buffer and RX buffer
W5500_COMMON       = $00
W5500_S0_REGISTERS = $08
W5500_S0_TX        = $10
W5500_S0_RX        = $18

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

; A socket's registers (in its block)
W5500_SN_MR        = $0000 ; mode: the protocol
W5500_SN_MR_TCP    = $01
W5500_SN_CR        = $0001 ; command: reads 0 once the W5500 has taken it
W5500_SN_CR_OPEN   = $01
W5500_SN_CR_LISTEN = $02
W5500_SN_CR_DISCON = $08
W5500_SN_CR_CLOSE  = $10
W5500_SN_CR_SEND   = $20
W5500_SN_CR_RECV   = $40
W5500_SN_IR        = $0002 ; interrupts: a 1 written clears one
W5500_SN_IR_SEND_OK = $10
W5500_SN_IR_TIMEOUT = $08
W5500_SN_SR        = $0003 ; status
W5500_SOCK_CLOSED  = $00
W5500_SOCK_INIT    = $13
W5500_SOCK_LISTEN  = $14
W5500_SOCK_SYNRECV = $16
W5500_SOCK_ESTABLISHED = $17
W5500_SOCK_CLOSE_WAIT = $1C
W5500_SN_PORT      = $0004 ; the source port (2 bytes, high first, as every 16-bit register)
W5500_SN_TX_FSR    = $0020 ; the TX buffer's free bytes
W5500_SN_TX_WR     = $0024 ; where the next byte to send goes in the TX buffer (its address there)
W5500_SN_RX_RSR    = $0026 ; bytes received, not yet taken
W5500_SN_RX_RD     = $0028 ; the next byte received to take, in the RX buffer
