; tinyp8 -- a 6502-native compiler proof-of-concept.
;
; Reads a tinyp8 source file (a strict subset of Prog8) and emits a
; standalone 6502 binary body. The compiler runs on the emulator's
; nmos-default machine, using its file-I/O ABI ($F012/$F018/$F021/$F024)
; and arg vector ($F01B/$F01E).
;
; Run as:
;   emulator.out tinyp8.bin source.tp8 output.body
;
; The emitted output.body is the *body* of the compiled program (no
; reset vector). A Python wrapper attaches the reset vector and
; produces a runnable binary.
;
; tinyp8 v0 language (the absolute minimum):
;   print "string literal"     ; print literal chars + newline
;   print_ub $XX               ; print one byte as 2 hex chars + newline
;   end                        ; exit(0)
;   ; one statement per line, ;-comments to end-of-line
;
; All output goes via the emulator's write_b stub at $F009; "print"
; emits one (lda #ch ; jsr $F009) pair per character.

; --- file I/O entry points (per emulator/stubs.c) ---
read_b    = $F006
write_b   = $F009
exit      = $F00F
open      = $F012
close     = $F015
read      = $F018
argc      = $F01B
argv      = $F01E
openout   = $F021
write     = $F024

; --- zero page ---
src_hand  = $02
dst_hand  = $03
tmp       = $04
peek_buf  = $05
peek_ok   = $06     ; nonzero if peek_buf holds a valid byte

  .org $0200

start:
  ; Need at least 2 args: input + output.
  jsr argc
  cmp #$02
  bcc usage_err

  lda #$00
  jsr argv               ; argv[0] -> filename pointer in A:X
  jsr open
  sta src_hand

  lda #$01
  jsr argv               ; argv[1]
  jsr openout
  sta dst_hand

  ; Reset peek-buffer state.
  lda #$00
  sta peek_ok

  jsr compile_program

  ; Close both files before exiting (otherwise the emulator forces a
  ; non-zero exit code on our behalf, see emulator.c "unclosed_files").
  lda src_hand
  jsr close
  lda dst_hand
  jsr close

  lda #$00
  jsr exit
  brk

usage_err:
  lda #$01
  jsr exit
  brk


; ===== compile loop =====
;
; Read source byte-by-byte. At each iteration, skip whitespace +
; comments then dispatch on the first non-ws byte of the next
; "statement":
;   'p' -> "print" or "print_ub" (peek the 6th char to decide)
;   'e' -> "end"   -> emit exit, return
;   EOF -> emit exit, return
;   anything else -> skip to newline and try again
compile_program:
.next_stmt:
  jsr skip_ws_comments
  jsr read_src
  bcs .eof
  cmp #'p'
  beq .pword
  cmp #'e'
  beq .eword
  jsr skip_to_nl
  jmp .next_stmt
.pword:
  jsr parse_print
  jmp .next_stmt
.eword:
  jsr skip_to_nl
  jsr emit_exit_seq
  rts
.eof:
  jsr emit_exit_seq
  rts


; ===== parse "print..." statements =====
;
; The 'p' is already consumed. We expect "rint" then either:
;   <ws> "<string>"      (the string-literal print)
;   "_ub" <ws> $XX       (the byte-hex print)
parse_print:
  jsr read_src           ; r
  jsr read_src           ; i
  jsr read_src           ; n
  jsr read_src           ; t
  bcc .pp_t_ok
  jmp .err
.pp_t_ok:
  jsr read_src           ; either '_' or whitespace
  bcc .pp_pre_ok
  jmp .err
.pp_pre_ok:
  cmp #'_'
  beq .ub_form

.find_quote:
  cmp #'"'
  beq .got_quote
  jsr read_src
  bcc .fq_ok
  jmp .err
.fq_ok:
  jmp .find_quote
.got_quote:
.s_loop:
  jsr read_src
  bcc .sl_ok
  jmp .err
.sl_ok:
  cmp #'"'
  beq .s_end
  jsr emit_print_char
  jmp .s_loop
.s_end:
  lda #$0A
  jsr emit_print_char
  jsr skip_to_nl
  rts

.ub_form:
  jsr read_src           ; 'u'
  bcs .err
  jsr read_src           ; 'b' or 'w'
  bcs .err
  cmp #'w'
  beq .uw_seek_dollar
  ; fall through: 'b' (ubyte form)
.ub_seek_dollar:
  jsr read_src
  bcs .err
  cmp #'$'
  beq .ub_got_dollar
  cmp #' '
  beq .ub_seek_dollar
  cmp #$09
  beq .ub_seek_dollar
  jmp .err
.ub_got_dollar:
  jsr read_src
  bcs .err
  jsr hex_nibble
  asl
  asl
  asl
  asl
  sta tmp
  jsr read_src
  bcs .err
  jsr hex_nibble
  ora tmp
  ; A = the byte; emit code to print it as 2 hex chars + newline.
  jsr emit_print_ub_seq
  lda #$0A
  jsr emit_print_char
  jsr skip_to_nl
  rts
.uw_seek_dollar:
  jsr read_src
  bcs .err
  cmp #'$'
  beq .uw_got_dollar
  cmp #' '
  beq .uw_seek_dollar
  cmp #$09
  beq .uw_seek_dollar
  jmp .err
.uw_got_dollar:
  ; Read 4 hex digits, emit a print_char sequence for each (precomputed
  ; ASCII), plus a trailing newline. We don't bother packing the digits
  ; into a 16-bit value -- since each nibble is independently emitted,
  ; the 4 read_src + nibble_to_ascii + emit_print_char invocations are
  ; the loop.
  ldx #$04
.uw_digit_loop:
  txa
  pha                    ; preserve loop counter
  jsr read_src
  bcs .uw_err_pop
  jsr hex_nibble
  jsr nibble_to_ascii
  jsr emit_print_char
  pla
  tax
  dex
  bne .uw_digit_loop
  lda #$0A
  jsr emit_print_char
  jsr skip_to_nl
  rts
.uw_err_pop:
  pla
  jmp .err

.err:
  ; Forgiving: emit exit and return cleanly. A real compiler would
  ; surface a diagnostic via write_d / stderr; v0 is silent.
  jsr emit_exit_seq
  rts


; ===== I/O =====

; read_src: returns next source byte in A (C clear), or C set on EOF.
; X and Y preserved. Honors the 1-byte peek buffer.
read_src:
  lda peek_ok
  beq .from_file
  lda #$00
  sta peek_ok
  lda peek_buf
  clc
  rts
.from_file:
  lda src_hand
  jmp read

; peek_src: returns next byte in A (C clear) WITHOUT consuming. C set
; on EOF.
peek_src:
  lda peek_ok
  bne .have
  lda src_hand
  jsr read
  bcs .eof
  sta peek_buf
  lda #$01
  sta peek_ok
  lda peek_buf
  clc
  rts
.have:
  lda peek_buf
  clc
  rts
.eof:
  sec
  rts

; write_dst: A = byte to write to the output file.
write_dst:
  pha
  ldx dst_hand
  pla
  jsr write
  rts


; ===== skip helpers =====

skip_ws_comments:
.loop:
  jsr peek_src
  bcs .out
  cmp #' '
  beq .eat
  cmp #$09
  beq .eat
  cmp #$0A
  beq .eat
  cmp #$0D
  beq .eat
  cmp #';'
  beq .comment
  ; Non-ws non-comment: leave it in peek_buf for the dispatcher.
  rts
.eat:
  jsr read_src           ; consume it
  jmp .loop
.comment:
  jsr skip_to_nl
  jmp .loop
.out:
  rts

skip_to_nl:
.l:
  jsr read_src
  bcs .out
  cmp #$0A
  bne .l
.out:
  rts


; ===== emitters =====
;
; Each emitted "print one char" is 7 bytes:
;   lda #ch         ; A9 ch
;   jsr write_b     ; 20 09 F0
; emit_exit_seq is also 7 bytes: lda #0 ; jsr exit.
; emit_print_ub_seq compiles 2 emit_print_char calls (precomputed
; nibbles), 14 bytes total. The byte-printer is hex-only.

emit_print_char:
  pha
  lda #$A9                ; LDA #
  jsr write_dst
  pla
  jsr write_dst           ; <char>
  lda #$20                ; JSR
  jsr write_dst
  lda #<write_b
  jsr write_dst
  lda #>write_b
  jsr write_dst
  rts

emit_print_ub_seq:
  pha
  ; high nibble first
  lsr
  lsr
  lsr
  lsr
  jsr nibble_to_ascii
  jsr emit_print_char
  pla
  and #$0F
  jsr nibble_to_ascii
  jmp emit_print_char     ; tail-call

emit_exit_seq:
  lda #$A9
  jsr write_dst
  lda #$00
  jsr write_dst
  lda #$20
  jsr write_dst
  lda #<exit
  jsr write_dst
  lda #>exit
  jsr write_dst
  rts


; ===== small helpers =====

; nibble_to_ascii: A = 0..15 -> '0'..'9' / 'a'..'f'.
nibble_to_ascii:
  cmp #$0A
  bcc .digit
  clc
  adc #('a'-$0A)
  rts
.digit:
  clc
  adc #'0'
  rts

; hex_nibble: A = ASCII '0'..'9' / 'a'..'f' / 'A'..'F' -> 0..15.
; Treats malformed input as 0.
hex_nibble:
  cmp #'a'
  bcc .upper_or_digit
  sec
  sbc #'a'-$0A
  rts
.upper_or_digit:
  cmp #'A'
  bcc .digit
  sec
  sbc #'A'-$0A
  rts
.digit:
  sec
  sbc #'0'
  rts


  .org $FFFC
  .word start
  .word $0000
