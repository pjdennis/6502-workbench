; Buffer memory copy routines - low-level memory move operations

; Forward copy (safe when dst <= src or non-overlapping)
; Input: BUF_SRC16 = source start, BUF_PTR16 = source end (exclusive),
;        BUF_DST16 = destination start
; Preserves BUF_PTR16. Clobbers A, Y, BUF_SRC16, BUF_DST16
mem_copy_down:
  ; Check empty case (SRC >= END)
  JSR cmp_src_ptr
  BCS .done

  ; Set up page-aligned source and Y offset
  ; Y = low byte of BUF_SRC16, BUF_SRC16 = page base
  ; Adjust BUF_DST16 so (BUF_DST16),Y gives correct dest address:
  ;   BUF_DST16 = BUF_DST16 - SRC_low_byte
  LDA BUF_SRC16
  TAY                      ; Y = source low byte offset
  SEC
  LDA BUF_DST16
  SBC BUF_SRC16            ; Subtract source low byte only
  STA BUF_DST16
  BCS .no_borrow
  DEC BUF_DST16 + 1
.no_borrow:
  LDA #0
  STA BUF_SRC16            ; BUF_SRC16 = page-aligned base

  ; Check if end is on the same page as start
  LDA BUF_SRC16 + 1
  CMP BUF_PTR16 + 1
  BNE .full_page

  ; Same page: copy Y up to (end low - 1)
.last_page:
  LDA (BUF_SRC16),Y
  STA (BUF_DST16),Y
  INY
  CPY BUF_PTR16
  BNE .last_page
  JMP .done

.full_page:
  ; Copy from Y up through $FF on this page
  LDA (BUF_SRC16),Y
  STA (BUF_DST16),Y
  INY
  BNE .full_page

  ; Move to next page
  INC BUF_SRC16 + 1
  INC BUF_DST16 + 1
  LDY #0

  ; Check if this is the last page
  LDA BUF_SRC16 + 1
  CMP BUF_PTR16 + 1
  BNE .full_page

  ; Check if end low byte is 0 (end is at page boundary)
  LDA BUF_PTR16
  BEQ .done

  JMP .last_page

.done:
  RTS

; Compare BUF_SRC16 with BUF_PTR16 (CMP16 semantics: C/Z as after CMP)
; Clobbers: A
cmp_src_ptr:
  LDA BUF_SRC16 + 1
  CMP BUF_PTR16 + 1
  BNE .d
  LDA BUF_SRC16
  CMP BUF_PTR16
.d:
  RTS
