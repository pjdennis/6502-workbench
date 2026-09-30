;read_b   = $f006
;write_b  = $f009

;TEMP     = $00 ; 1 byte
;TEMP2    = $01 ; 1 byte
;TAB      = $02 ; 2 bytes
;PC       = $04 ; 2 bytes
;TOKEN    = $06 ; multiple bytes

;PC_START = $2000
;LBTAB    = $3000
;LF       = $0a

;  .org $2000


; Instruction table
MNTAB
  DATA "ADC#"    $00 $00 $69
  DATA "ASLA"    $00 $00 $0A
  DATA "BCC"     $00 $00 $90
  DATA "BCS"     $00 $00 $B0
  DATA "BEQ"     $00 $00 $F0
  DATA "BNE"     $00 $00 $D0
  DATA "BRK"     $00 $00 $00
  DATA "CLC"     $00 $00 $18
  DATA "CMPZ,X"  $00 $00 $D5
  DATA "CMP#"    $00 $00 $C9
  DATA "INCZ"    $00 $00 $E6
  DATA "INX"     $00 $00 $E8
  DATA "INY"     $00 $00 $C8
  DATA "JMP"     $00 $00 $4C
  DATA "JSR"     $00 $00 $20
  DATA "LDAZ"    $00 $00 $A5
  DATA "LDA#"    $00 $00 $A9
  DATA "LDA(),Y" $00 $00 $B1
  DATA "LDA,Y"   $00 $00 $B9
  DATA "LDX#"    $00 $00 $A2
  DATA "LDY#"    $00 $00 $A0
  DATA "ORAZ"    $00 $00 $05
  DATA "RTS"     $00 $00 $60
  DATA "SBC#"    $00 $00 $E9
  DATA "SEC"     $00 $00 $38
  DATA "STA"     $00 $00 $8D
  DATA "STA(),Y" $00 $00 $91
  DATA "STAZ"    $00 $00 $85
  DATA "STAZ,X"  $00 $00 $95
  DATA "DATA"    $00 $01 $00
  DATA $00


read
  JMP $F006            ; jmp read_b


emit
  JSR $F009            ; jsr write_b
  INCZ $04             ; inc PC
  BNE $02              ; bne emitdone
  INCZ $05             ; inc PC+1
emitdone
  RTS                  ; rts


ignln
  JSR read             ; jsr read
  CMP# $0A             ; cmp #LF ; newline
  BNE $F9              ; bne ignln
  RTS                  ; rts


skipspc
  CMP# " "             ; cmp #' '
  BNE $06              ; bne skipspc2
  JSR read             ; jsr read
  JMP skipspc          ; jmp skipspc
skipspc2
  RTS                  ; rts


readtoken
  LDX# $00             ; ldx #0
readtokenloop
  STAZ,X $06           ; sta TOKEN,X
  INX                  ; inx
  JSR read             ; jsr read
  CMP# " "             ; cmp #' '
  BEQ $07              ; beq readtokendone ; done
  CMP# $0A             ; cmp #LF
  BEQ $03              ; beq readtokendone
  JMP readtokenloop    ; jmp readtokenloop
readtokendone
  STAZ $00             ; sta TEMP
  LDA# $00             ; lda #0
  STAZ,X $06           ; sta TOKEN,X
  RTS                  ; rts


inctab
  INCZ $02             ; inc TAB
  BNE $02              ; bne inctabdone
  INCZ $03             ; inc TAB + 1
inctabdone
  RTS                  ; rts


findintab
findintab1 ; outer loop
  LDX# $00             ; ldx #0 ; pointer into mnenomic
  LDA(),Y $02          ; lda (TAB),Y
  BNE $02              ; bne findintab2
  ; not found
  SEC                  ; sec
  RTS                  ; rts
;invariant: pointed at first char
; first char of mnenomic in table loaded
findintab2 ; inner loop
  CMPZ,X $06           ; cmp TOKEN,X
  BNE $12              ; bne findintab4 ; no match
  CMP# $00             ; cmp #0
  BNE $05              ; bne findintab3
  ; match
  JSR inctab           ; jsr inctab ; move past 0 terminator
  CLC                  ; clc
  RTS                  ; rts
findintab3
  INX                  ; inx
  JSR inctab           ; jsr inctab
  LDA(),Y $02          ; lda (TAB),Y
  JMP findintab2       ; jmp findintab2 ; inner loop
findintab4 ; no match
  LDA(),Y $02          ; lda (TAB),Y
  BEQ $06              ; beq findintab5 ; done skipping
  JSR inctab           ; jsr inctab
  JMP findintab4       ; jmp findintab4
findintab5 ; done skipping
  JSR inctab           ; jsr inctab ; move past 0 terminator
  JSR inctab           ; jsr inctab ; move past first data byte
  JSR inctab           ; jsr inctab ; move past second data byte
  JMP findintab1       ; jmp findintab1 ; outer loop


capturelabel
  LDA# $00             ; lda #<LBTAB
  STAZ $02             ; sta TAB
  LDA# $30             ; lda #>LBTAB
  STAZ $03             ; sta TAB+1
  JSR findintab        ; jsr findintab
  BCS $12              ; bcs clnotfound
  BRK                  ; brk ; duplicate label
  DATA $01 "Duplicate label" $00
clnotfound
clloop
  LDA,Y $0006          ; lda TOKEN,Y
  STA(),Y $02          ; sta (TAB),Y
  BEQ $04              ; beq cldone
  INY                  ; iny
  JMP clloop           ; jmp clloop
cldone
  INY                  ; iny
  LDAZ $04             ; lda PC
  STA(),Y $02          ; sta (TAB),Y
  INY                  ; iny
  LDAZ $05             ; lda PC+1
  STA(),Y $02          ; sta (TAB),Y
  INY                  ; iny
  LDA# $00             ; lda #0
  STA(),Y $02          ; sta (TAB),Y
  LDY# $00             ; ldy #0 ; restore
  RTS                  ; rts


readlabel
  JSR readtoken        ; jsr readtoken
  JSR capturelabel     ; jsr capturelabel
  LDAZ $00             ; lda TEMP
  CMP# $0A             ; cmp #LF
  BEQ $03              ; beq readlabel1
  JSR ignln            ; jsr ignln
readlabel1
  RTS                  ; rts


; Emit the opcode
emitoc
  LDA# $00             ; lda #<MNTAB
  STAZ $02             ; sta TAB
  LDA# $20             ; lda #>MNTAB
  STAZ $03             ; sta TAB+1
  JSR findintab        ; jsr findintab
  BCC $13              ; bcc emitoc1
  BRK                  ; brk ; Opcode not found
  DATA $02 "Opcode not found" $00
emitoc1
  LDA(),Y $02          ; lda (TAB),Y
  BEQ $01              ; beq emitoc2
  RTS                  ; rts
emitoc2
  JSR inctab           ; jsr inctab
  LDA(),Y $02          ; lda (TAB),Y
  JSR emit             ; jsr emit
  RTS                  ; rts


; read and emit quoted ASCII
emitqu
  JSR read             ; jsr read
  CMP# "\""            ; cmp #'"'
  BNE $04              ; bne emitqu1
  JSR read             ; jsr read
  RTS                  ; rts
emitqu1
  CMP# "\\"            ; cmp #'\\'
  BNE $03              ; bne emitqu2
  JSR read             ; jsr read
emitqu2
  JSR emit             ; jsr emit
  JMP emitqu           ; jmp emitqu


convhex
  CMP# "A"             ; cmp #'A'
  BCC $06              ; bcc convhex1 ; < 'A'
  SBC# "A"             ; sbc #'A'
  CLC                  ; clc
  ADC# $0A             ; adc #10
  RTS                  ; rts
convhex1
  SEC                  ; sec
  SBC# "0"             ; sbc #'0'
  RTS                  ; rts


readhex
  JSR convhex          ; jsr convhex
  ASLA                 ; asl
  ASLA                 ; asl
  ASLA                 ; asl
  ASLA                 ; asl
  STAZ $00             ; sta TEMP
  JSR read             ; jsr read
  JSR convhex          ; jsr convhex
  ORAZ $00             ; ora TEMP
  RTS                  ; rts


emithex
  JSR read             ; jsr read
emithex2
  JSR readhex          ; jsr readhex
  STAZ $01             ; sta TEMP2
  JSR read             ; jsr read
  CMP# " "             ; cmp #' '
  BEQ $11              ; beq emithex3
  CMP# $0A             ; cmp #LF
  BEQ $0D              ; beq emithex3
  CMP# ";"             ; cmp #';'
  BEQ $09              ; beq emithex3
  JSR readhex          ; jsr readhex
  JSR emit             ; jsr emit ; write the low byte
  JSR read             ; jsr read
emithex3
  STAZ $00             ; sta TEMP
  LDAZ $01             ; lda TEMP2
  JSR emit             ; jsr emit
  LDAZ $00             ; lda TEMP
  RTS                  ; rts


emitlabel
  JSR readtoken        ; jsr readtoken
  LDA# $00             ; lda #<LBTAB
  STAZ $02             ; sta TAB
  LDA# $30             ; lda #>LBTAB
  STAZ $03             ; sta TAB+1
  JSR findintab        ; jsr findintab
  BCC $12              ; bcc emitlabel2
  BRK                  ; brk ; Label not found
  DATA $03 "Label not found" $00
emitlabel2
  LDA(),Y $02          ; lda (TAB),Y
  JSR emit             ; jsr emit
  JSR inctab           ; jsr inctab
  LDA(),Y $02          ; lda (TAB),Y
  JSR emit             ; jsr emit
  LDAZ $00             ; lda TEMP
  RTS                  ; rts


checkforend
  CMP# ";"             ; cmp #';'
  BNE $05              ; bne checkforend1
  JSR ignln            ; jsr ignln
  SEC                  ; sec
  RTS                  ; rts
checkforend1
  CMP# $0A             ; cmp #LF
  BNE $02              ; bne checkforend2
  SEC                  ; sec
  RTS                  ; rts
checkforend2
  CLC                  ; clc
  RTS                  ; rts


assemble
lnloop
  JSR read             ; jsr read
  BCC $01              ; bcc lnloop1
  RTS                  ; rts ; at end of input
lnloop1
  JSR checkforend      ; jsr checkforend
  BCC $03              ; bcc lnloop2
  JMP lnloop           ; jmp lnloop
lnloop2
  CMP# " "             ; cmp #' '
  BEQ $06              ; beq lnloop3
  JSR readlabel        ; jsr readlabel
  JMP lnloop           ; jmp lnloop
lnloop3
  JSR skipspc          ; jsr skipspc
  JSR checkforend      ; jsr checkforend
  BCC $03              ; bcc lnloop4
  JMP lnloop           ; jmp lnloop
lnloop4
; Read and emit mnemonic
  JSR readtoken        ; jsr readtoken
  JSR emitoc           ; jsr emitoc
  LDAZ $00             ; lda TEMP
tokloop
  JSR skipspc          ; jsr skipspc
  JSR checkforend      ; jsr checkforend
  BCC $03              ; bcc tokloop1
  JMP lnloop           ; jmp lnloop ; end of line
tokloop1
  CMP# "\""            ; cmp #'"'
  BNE $06              ; bne tokloop2
  JSR emitqu           ; jsr emitqu
  JMP tokloop          ; jmp tokloop
tokloop2
  CMP# "$"             ; cmp #'$'
  BNE $06              ; bne tokloop3
  JSR emithex          ; jsr emithex
  JMP tokloop          ; jmp tokloop
tokloop3
  ; label
  JSR emitlabel        ; jsr emitlabel
  JMP tokloop          ; jmp tokloop


start
  LDA# $00             ; lda #<PC_START
  STAZ $04             ; sta PC
  LDA# $20             ; lda #>PC_START
  STAZ $05             ; sta PC+1
  LDA# $00             ; lda #0
  STA $3000            ; sta LBTAB
  LDY# $00             ; ldy #0 ; Y remains 0 (for indirect addressing)
  JSR assemble         ; jsr assemble
  BRK                  ; brk
  DATA $00 ; Success


  DATA start ; Emulation environment jumps here
