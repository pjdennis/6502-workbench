; The WIZnet W5500 Ethernet controller's control bytes and registers, for its drivers: w5500.inc (on the GAL SPI
; interface) and fpga_w5500.inc (on the FPGA bus).

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
