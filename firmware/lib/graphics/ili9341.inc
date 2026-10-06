; The ILI9341 display controller's commands and parameters, and the colours, as Michael's graphic driver
; (graphics_display.inc) and the ROM's graphic screen use them.

ILI9341_TFTWIDTH  = 240 ; ILI9341 max TFT width
ILI9341_TFTHEIGHT = 320 ; ILI9341 max TFT height

ILI9341_NOP     = $00 ; No-op register
ILI9341_SWRESET = $01 ; Software reset register
ILI9341_RDDID   = $04 ; Read display identification information
ILI9341_RDDST   = $09 ; Read Display Status

ILI9341_SLPIN  = $10 ; Enter Sleep Mode
ILI9341_SLPOUT = $11 ; Sleep Out
ILI9341_PTLON  = $12 ; Partial Mode ON
ILI9341_NORON  = $13 ; Normal Display Mode ON

ILI9341_RDMODE     = $0a ; Read Display Power Mode
ILI9341_RDMADCTL   = $0b ; Read Display MADCTL
ILI9341_RDPIXFMT   = $0c ; Read Display Pixel Format
ILI9341_RDIMGFMT   = $0d ; Read Display Image Format
ILI9341_RDSELFDIAG = $0f ; Read Display Self-Diagnostic Result

ILI9341_INVOFF   = $20 ; Display Inversion OFF
ILI9341_INVON    = $21 ; Display Inversion ON
ILI9341_GAMMASET = $26 ; Gamma Set
ILI9341_DISPOFF  = $28 ; Display OFF
ILI9341_DISPON   = $29 ; Display ON

ILI9341_CASET = $2a ; Column Address Set
ILI9341_PASET = $2b ; Page Address Set
ILI9341_RAMWR = $2c ; Memory Write
ILI9341_RAMRD = $2e ; Memory Read

ILI9341_PTLAR    = $30 ; Partial Area
ILI9341_VSCRDEF  = $33 ; Vertical Scrolling Definition
ILI9341_MADCTL   = $36 ; Memory Access Control
ILI9341_VSCRSADD = $37 ; Vertical Scrolling Start Address
ILI9341_PIXFMT   = $3a ; COLMOD: Pixel Format Set

ILI9341_FRMCTR1 = $b1 ; Frame Rate Control (In Normal Mode/Full Colors)
ILI9341_FRMCTR2 = $b2 ; Frame Rate Control (In Idle Mode/8 colors)
ILI9341_FRMCTR3 = $b3 ; Frame Rate control (In Partial Mode/Full Colors)
ILI9341_INVCTR  = $b4 ; Display Inversion Control
ILI9341_DFUNCTR = $b6 ; Display Function Control

ILI9341_PWCTR1 = $c0 ; Power Control 1
ILI9341_PWCTR2 = $c1 ; Power Control 2
ILI9341_PWCTR3 = $c2 ; Power Control 3
ILI9341_PWCTR4 = $c3 ; Power Control 4
ILI9341_PWCTR5 = $c4 ; Power Control 5
ILI9341_VMCTR1 = $c5 ; VCOM Control 1
ILI9341_VMCTR2 = $c7 ; VCOM Control 2

ILI9341_RDID1 = $da ; Read ID 1
ILI9341_RDID2 = $db ; Read ID 2
ILI9341_RDID3 = $dc ; Read ID 3
ILI9341_RDID4 = $dd ; Read ID 4

ILI9341_GMCTRP1 = $e0 ; Positive Gamma Correction
ILI9341_GMCTRN1 = $e1 ; Negative Gamma Correction
;ILI9341_PWCTR6 = $fc

; Parameter definitions for the ILI9341_MADCTL command
ILI9341_MADCTL_MY  = %10000000 ; Starts from bottom when set, top otherwise
ILI9341_MADCTL_MX  = %01000000 ; Starts from right of screen when set, left otherwise
ILI9341_MADCTL_MV  = %00100000 ; Orientation vertical when set, horizontal otherwise
ILI9341_MADCTL_ML  = %00010000 ; Affects vertical scrolling orientation
ILI9341_MADCTL_BGR = %00001000 ; LCD pixel color order is BGR when set, RGB otherwise
ILI9341_MADCTL_MH  = %00000100 ; Affects horizontal refresh direction

; Second parameter of the ILI9341_DFUNCTR command
ILI9341_DFUNCTR_REV = %10000000 ; Normally white panel
ILI9341_DFUNCTR_GS  = %01000000 ; Gate scan reversed: the picture is upside down
ILI9341_DFUNCTR_SS  = %00100000 ; Source scan reversed: the picture is mirrored left to right
ILI9341_DFUNCTR_ISC = %00000010 ; Gate scan cycle in the non-display area

; Michael's display, as mounted on the FPGA interface (hardware/michael/fpga/spi-display), needs the picture
; rotated 180 degrees: both scans reversed. Reversing the panel's scan, rather than the memory access order
; (MADCTL), keeps hardware scrolling (VSCRSADD) moving the right way.
GD_PANEL_SCAN = ILI9341_DFUNCTR_REV | ILI9341_DFUNCTR_GS | ILI9341_DFUNCTR_SS | ILI9341_DFUNCTR_ISC

; Color definitions
ILI9341_BLACK       = $0000 ;   0,   0,   0
ILI9341_NAVY        = $000f ;   0,   0, 123
ILI9341_DARKGREEN   = $03e0 ;   0, 125,   0
ILI9341_DARKCYAN    = $03ef ;   0, 125, 123
ILI9341_MAROON      = $7800 ; 123,   0,   0
ILI9341_PURPLE      = $780f ; 123,   0, 123
ILI9341_OLIVE       = $7be0 ; 123, 125,   0
ILI9341_LIGHTGREY   = $c618 ; 198, 195, 198
ILI9341_DARKGREY    = $7bef ; 123, 125, 123
ILI9341_BLUE        = $001f ;   0,   0, 255
ILI9341_GREEN       = $07e0 ;   0, 255,   0
ILI9341_CYAN        = $07ff ;   0, 255, 255
ILI9341_RED         = $f800 ; 255,   0,   0
ILI9341_MAGENTA     = $f81f ; 255,   0, 255
ILI9341_YELLOW      = $ffe0 ; 255, 255,   0
ILI9341_WHITE       = $ffff ; 255, 255, 255
ILI9341_ORANGE      = $fd20 ; 255, 165,   0
ILI9341_GREENYELLOW = $afe5 ; 173, 255,  41
ILI9341_PINK        = $fc18 ; 255, 130, 198
