; How Michael's display is initialised (after its reset), read by gd_initialize (graphics_display.inc) and
; the ROM's graphic screen: each entry a command, then a count of parameters whose bit 7 asks for a 150 ms
; delay after, then the parameters; a 0 ends the list. Needs ili9341.inc.

INIT_COMMANDS:
  .byte $ef,              3, $03, $80, $02
  .byte $cf,              3, $00, $c1, $30
  .byte $ed,              4, $64, $03, $12, $81
  .byte $e8,              3, $85, $00, $78
  .byte $cb,              5, $39, $2c, $00, $34, $02
  .byte $f7,              1, $20
  .byte $ea,              2, $00, $00
  .byte ILI9341_PWCTR1,   1, $23                     ; Power control VRH[5:0]
  .byte ILI9341_PWCTR2,   1, $10                     ; Power control SAP[2:0];BT[3:0]
  .byte ILI9341_VMCTR1,   2, $3e, $28                ; VCM control
  .byte ILI9341_VMCTR2,   1, $86                     ; VCM control2
  .byte ILI9341_MADCTL,   1, $48                     ; Memory Access Control
  .byte ILI9341_VSCRSADD, 1, $00                     ; Vertical scroll zero
  .byte ILI9341_PIXFMT,   1, $55
  .byte ILI9341_FRMCTR1,  2, $00, $18
  .byte ILI9341_DFUNCTR,  3, $08, GD_PANEL_SCAN, $27 ; Display Function Control
  .byte $f2,              1, $00                     ; 3Gamma Function Disable
  .byte ILI9341_GAMMASET, 1, $01                     ; Gamma curve selected
  .byte ILI9341_GMCTRP1, 15, $0f, $31, $2b, $0c, $0e ; Set Gamma
  .byte                      $08, $4e, $f1, $37, $07
  .byte                      $10, $03, $0e, $09, $00
  .byte ILI9341_GMCTRN1, 15, $00, $0e, $14, $03, $11 ; Set Gamma
  .byte                      $07, $31, $c1, $48, $08
  .byte                      $0f, $0c, $31, $36, $0f
  .byte ILI9341_SLPOUT, $80                          ; Exit Sleep
  .byte ILI9341_DISPON,   0                          ; Display on
  .byte $00                                          ; End of list
