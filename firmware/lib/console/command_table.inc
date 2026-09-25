; Requires:
;   CT_ZERO_PAGE_BASE    - zero page location for variables
;   CT_COMMANDS          - table of commands - zero terminated name followed by function address
;                          table is zero-terminated

CT_TABLE_PTR            = CT_ZERO_PAGE_BASE + $00 ; 2 bytes
CT_COMMAND_PTR          = CT_ZERO_PAGE_BASE + $02 ; 2 bytes
CT_COMMAND_FUNCTION_PTR = CT_ZERO_PAGE_BASE + $04 ; 2 bytes

CT_ZERO_PAGE_STOP       = CT_ZERO_PAGE_BASE + $06


  ; The name comes last: vasm 2.0+ does not split macro arguments after a
  ; quoted string. The table layout is still name, then address.
  .macro ct_entry,address,command
  .asciiz \command
  .word \address
  .endm


; On entry A, X (low, high) points to the potential command
; On exit CT_CT_COMMAND_FUNCTION_PTR contains the address of the command function if found
;         C is set if command found or clear if not found
;         Y is preserved
;         A, X are not preserved
; Uses GC_LINE_PTR
ct_find_command:
  phy
  sta CT_COMMAND_PTR
  stx CT_COMMAND_PTR + 1

  ; CT_TABLE_PTR <- address of 'commands' table
  lda #<CT_COMMANDS
  sta CT_TABLE_PTR
  lda #>CT_COMMANDS
  sta CT_TABLE_PTR + 1

  .command_loop:
  lda (CT_TABLE_PTR)
  beq .not_found

  ; Compare with potential command
  ldy #0
  .char_loop:
  lda (CT_TABLE_PTR),Y
  cmp (CT_COMMAND_PTR),Y
  bne .next
  lda (CT_TABLE_PTR),Y
  beq .found
  iny
  bra .char_loop

; Found. Read address
.found:
  iny
  lda (CT_TABLE_PTR),Y
  sta CT_COMMAND_FUNCTION_PTR
  iny
  lda (CT_TABLE_PTR),Y
  sta CT_COMMAND_FUNCTION_PTR + 1
  sec
  bra .done

.next:
  lda (CT_TABLE_PTR),Y
  beq .skip_to_next
  iny
  bra .next

.skip_to_next: ; skip past the trailing 0 and 2 bytes of address
  clc
  tya
  adc #3

  ; carry assumed clear
  adc CT_TABLE_PTR
  sta CT_TABLE_PTR
  lda #0
  adc CT_TABLE_PTR + 1
  sta CT_TABLE_PTR + 1

  bra .command_loop

.not_found:
  clc
  ; Fall through

.done:
  ply
  rts
