; 31 .ifdef/.endif pairs with undefined labels
; Used for testing .ifdef decision buffer limits
; 8 includes x 31 = 248, leaving room for 7 more to hit 255 limit
  .ifdef UNDEF_00
  .endif
  .ifdef UNDEF_01
  .endif
  .ifdef UNDEF_02
  .endif
  .ifdef UNDEF_03
  .endif
  .ifdef UNDEF_04
  .endif
  .ifdef UNDEF_05
  .endif
  .ifdef UNDEF_06
  .endif
  .ifdef UNDEF_07
  .endif
  .ifdef UNDEF_08
  .endif
  .ifdef UNDEF_09
  .endif
  .ifdef UNDEF_10
  .endif
  .ifdef UNDEF_11
  .endif
  .ifdef UNDEF_12
  .endif
  .ifdef UNDEF_13
  .endif
  .ifdef UNDEF_14
  .endif
  .ifdef UNDEF_15
  .endif
  .ifdef UNDEF_16
  .endif
  .ifdef UNDEF_17
  .endif
  .ifdef UNDEF_18
  .endif
  .ifdef UNDEF_19
  .endif
  .ifdef UNDEF_20
  .endif
  .ifdef UNDEF_21
  .endif
  .ifdef UNDEF_22
  .endif
  .ifdef UNDEF_23
  .endif
  .ifdef UNDEF_24
  .endif
  .ifdef UNDEF_25
  .endif
  .ifdef UNDEF_26
  .endif
  .ifdef UNDEF_27
  .endif
  .ifdef UNDEF_28
  .endif
  .ifdef UNDEF_29
  .endif
  .ifdef UNDEF_30
  .endif
