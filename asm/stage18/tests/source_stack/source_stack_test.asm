; Source Stack Test Program
; Usage: source_stack_test <mode> <input_file>
; Modes:
;   echo   - Read file char by char, write to stdout
;   lines  - Read file, output "N:content" for each line
;   info   - Read file, output statistics
;   memory - Handle @memory, @include, and @traceback markers
;   frames - Same as memory, plus @frames prints frame chain
;   oom    - Same as memory, but with a tight stack limit so
;            push_source_frame triggers err_out_of_memory after a few pushes
;
; Requires:
;   environment.asm vectors (argc, argv, write_b, write_d, exit)
;   source_stack.asm routines (source_stack_init, push_file_source, pop_source,
;                            push_memory_source_reserve_payload,
;                            source_stack_empty, read_char)
;   to_decimal.asm (TO_DECIMAL_RESULT, to_decimal)

* = $0200

SOURCE_STACK = $F000
TOKEN      = $1D00
TOKEN_MEM  = $1D80  ; Offset in TOKEN buffer for memory content

  .zeropage

; Test state
TEST_MODE:     .byte         ; 0=echo, 1=lines, 2=info, 3=memory, 4=frames, 5=oom
CHAR_COUNT16:  .word         ; Character count
LINE_COUNT16:  .word         ; Line count
AT_LINE_START: .byte         ; Flag: at start of line (for lines mode)

; Temporary
TEMP:        .byte
TABP16:      .word
MARKER_TERM: .byte         ; Character that terminated the keyword ($FF = EOF)

; Frame walker state (frames mode). FRAME_DEPTH is updated by the
; print_frame_callback, not the walker itself.
FRAME_DEPTH:     .byte

; @payload_memory state.
PAYLOAD_REQUESTED_SIZE: .byte
PAYLOAD_DEST16:         .word         ; Indirect-Y target for payload pre-write
                                      ; (set to SS_P16 - PAYLOAD_REQUESTED_SIZE
                                      ; before push_memory_source_reserve_payload)

; OOM injection: minimum allowed value of SS_TEMP16 during push.
; Default $0000 means "no limit"; oom mode sets a tight value.
OOM_LIMIT16:     .word

  .code

  .include environment.asm
  .include macros.asm
  .include to_decimal.asm

  .macro PRINT_STR str_addr
  SET16 str_addr, TABP16
  JSR print_str
  .endmacro

; Source stack configuration
SS_NAME = TOKEN

; CHECK_FOR_OUT_OF_MEMORY - Stack-overflow check used by push_source_frame.
; Compares the proposed new stack pointer (fs_ptr) against OOM_LIMIT16.
; If fs_ptr < OOM_LIMIT16 the push is rejected via err_out_of_memory.
; Default OOM_LIMIT16 is $0000, so the check is a no-op outside oom mode.
  .macro CHECK_FOR_OUT_OF_MEMORY fs_ptr
  LDA fs_ptr + 1
  CMP OOM_LIMIT16 + 1
  BCC .oom_fail
  BNE .oom_ok
  LDA fs_ptr
  CMP OOM_LIMIT16
  BCS .oom_ok
.oom_fail:
  JMP err_out_of_memory
.oom_ok:
  .endmacro

; Error handler for file-not-found (required by source_stack.asm)
err_file_not_found:
  BRK
  .asciiz 36, "File not found"

; Error handler for stack overflow (required by source_stack.asm via macro).
; Print the error then walk the source stack popping every frame (which
; closes the file in each one) before exiting. Without this the emulator
; reports orphaned file handles and treats the run as a non-zero exit,
; which the in-process test harness can't tolerate.
err_out_of_memory:
  SET16 msg_oom, TABP16
  JSR print_str_err
  ; Pop everything still on the source stack so its files get closed.
.close_loop:
  JSR source_stack_empty
  BEQ .close_done
  JSR pop_source
  JMP .close_loop
.close_done:
  LDA #2
  JMP exit
msg_oom:
  .asciiz "OUT OF MEMORY\n"

; Memory-frame pop handler: a bare RTS. The test program doesn't carry
; any per-frame state that needs restoring -- it's just exercising the
; source-stack mechanics.
ss_test_memory_pop:
  RTS

; Wire the handler in via the compile-time equate. Defining the equate
; here (after the label, before the include) avoids relying on
; forward-reference resolution in equate values.
MEMORY_POP_HANDLER = ss_test_memory_pop

  .include source_stack.asm
read_char = source_stack_read_char
CURLINE16 = SS_CURR_LINE16
CURR_CHAR = SS_CURR_CHAR


main:
  ; Default: no OOM injection (any fs_ptr >= $0000 passes the check)
  SET16 0, OOM_LIMIT16
  JSR source_stack_init
  JSR parse_args
  BCC .args_ok
  JMP error_usage

.args_ok:
  ; Initialize counters
  SET16 0, CHAR_COUNT16
  SET16 0, LINE_COUNT16
  LDA #1
  STA AT_LINE_START

  ; Dispatch based on mode
  LDA TEST_MODE
  BEQ mode_echo
  CMP #1
  BEQ mode_lines
  CMP #2
  BEQ .go_info
  CMP #3
  BEQ .go_memory
  CMP #4
  BEQ .go_memory      ; frames mode shares memory mode body; differs only in markers
  CMP #5
  BEQ .go_oom
  JMP error_usage
.go_info:
  JMP mode_info
.go_oom:
  ; Tight stack limit so push triggers err_out_of_memory after a few frames.
  ; SS_P16 starts at SOURCE_STACK ($F000) and grows down. Limit at $EF80 leaves
  ; only $80 bytes of stack -- a handful of pushes before OOM.
  SET16 $EF80, OOM_LIMIT16
.go_memory:
  JMP mode_memory

; ============================================================================
; MODE: echo - Simply read and echo each character
; ============================================================================
mode_echo:
.loop:
  JSR read_char
  BCS .done
  JSR write_b
  JMP .loop
.done:
  LDA #0
  JMP exit

; ============================================================================
; MODE: lines - Output "N:content" for each line
; ============================================================================
mode_lines:
.loop:
  ; If at line start, save line number BEFORE read_char can increment it
  LDA AT_LINE_START
  BEQ .do_read
  CP16 CURLINE16, TO_DECIMAL_VALUE16
.do_read:
  ; Read first, then decide if we need line prefix
  JSR read_char_track_line
  BCS .done
  ; Check if at start of line - output prefix before the char
  LDX AT_LINE_START
  BEQ .not_start
  ; Save char, print saved line number, restore char
  PHA
  JSR print_decimal
  LDA #':'
  JSR write_b
  LDA #0
  STA AT_LINE_START
  PLA
.not_start:
  JSR write_b
  CMP #'\n'
  BNE .loop
  LDA #1
  STA AT_LINE_START
  JMP .loop
.done:
  LDA #0
  JMP exit

; Read filename until newline into TOKEN
; Note: Uses read_char (not read_char_track_line) to avoid incrementing
; line number - the line should be saved BEFORE reading the filename
read_include_filename:
  LDX #0
.loop:
  JSR read_char
  BCS .done
  CMP #'\n'
  BEQ .done
  CMP #'\r'
  BEQ .skip_cr
  STA TOKEN,X
  INX
  JMP .loop
.skip_cr:
  JMP .loop
.done:
  LDA #0
  STA TOKEN,X
  RTS

; ============================================================================
; MODE: info - Read file and output statistics
; ============================================================================
mode_info:
.loop:
  JSR read_char
  BCS .done
  ; Count characters
  INC16 CHAR_COUNT16
  ; Count newlines
  CMP #'\n'
  BNE .loop
  INC16 LINE_COUNT16
  JMP .loop
.done:
  ; Output "chars:N"
  PRINT_STR str_chars
  CP16 CHAR_COUNT16, TO_DECIMAL_VALUE16
  JSR print_decimal
  LDA #'\n'
  JSR write_b
  ; Output "lines:N"
  PRINT_STR str_lines
  CP16 LINE_COUNT16, TO_DECIMAL_VALUE16
  JSR print_decimal
  LDA #'\n'
  JSR write_b
  ; Output "stack:empty" or "stack:active"
  PRINT_STR str_stack
  JSR source_stack_empty
  BNE .stack_not_empty
  PRINT_STR str_empty
  JMP .info_done
.stack_not_empty:
  PRINT_STR str_active
.info_done:
  LDA #'\n'
  JSR write_b
  LDA #0
  JMP exit

; ============================================================================
; MODE: memory - Handle @memory, @include, and @traceback markers
; ============================================================================
mode_memory:
.loop:
  JSR read_char_track_line
  BCS .done
  ; Check for '@' at start of line
  CMP #'@'
  BNE .not_at_sign
  LDA AT_LINE_START
  BEQ .at_not_start
  ; Might be a marker - check
  JSR check_markers
  JMP .loop           ; Continue (marker handled or text already flushed)
.at_not_start:
  LDA #'@'            ; Restore the clobbered character
.not_at_sign:
  JSR write_b
  ; Track line start
  CMP #'\n'
  BNE .not_newline
  LDA #1
  STA AT_LINE_START
  JMP .loop
.not_newline:
  LDA #0
  STA AT_LINE_START
  JMP .loop
.done:
  LDA #0
  JMP exit

; ============================================================================
; Buffer-based marker matching
; On entry: just read '@' at start of line
; Buffers keyword into TOKEN, then compares against known markers.
; On exit: C=0 if marker handled, C=1 if not (text already flushed)
; ============================================================================
check_markers:
  ; Buffer the keyword after '@' into TOKEN
  LDX #0
.buffer_loop:
  JSR read_char
  BCS .buffer_eof
  CMP #' '
  BEQ .buffer_done
  CMP #'\n'
  BEQ .buffer_done
  STA TOKEN,X
  INX
  JMP .buffer_loop
.buffer_eof:
  LDA #$FF            ; Sentinel for EOF
.buffer_done:
  STA MARKER_TERM     ; Save terminator (space, newline, or $FF)
  LDA #0
  STA TOKEN,X         ; Null-terminate the keyword

  ; Try matching against each known marker. Use BCS-skip / JMP rather
  ; than direct BCC so the dispatch can grow without short-branch
  ; range failures.
  SET16 str_include, TABP16
  JSR cmp_marker
  BCS .not_inc
  JMP .handle_include
.not_inc:
  SET16 str_memory, TABP16
  JSR cmp_marker
  BCS .not_mem
  JMP .handle_memory
.not_mem:
  SET16 str_traceback, TABP16
  JSR cmp_marker
  BCS .not_tb
  JMP .handle_traceback
.not_tb:

  ; @frames, @top_frame_size, and @payload_memory are only recognized
  ; in frames mode (TEST_MODE=4)
  LDA TEST_MODE
  CMP #4
  BNE .no_frames_marker
  SET16 str_frames, TABP16
  JSR cmp_marker
  BCS .not_frames
  JMP .handle_frames
.not_frames:
  SET16 str_top_frame_size, TABP16
  JSR cmp_marker
  BCS .not_tfs
  JMP .handle_top_frame_size
.not_tfs:
  SET16 str_payload_memory, TABP16
  JSR cmp_marker
  BCS .not_pm
  JMP .handle_payload_memory
.not_pm:
  SET16 str_reserve_only, TABP16
  JSR cmp_marker
  BCS .not_ro
  JMP .handle_reserve_only
.not_ro:
  SET16 str_reserve_commit_pop, TABP16
  JSR cmp_marker
  BCS .not_rcp
  JMP .handle_reserve_commit_pop
.not_rcp:
.no_frames_marker:

  ; No match - flush '@' + keyword + terminator as text
  JMP flush_as_text

.handle_include:
  ; @include requires space terminator (filename follows)
  LDA MARKER_TERM
  CMP #' '
  BEQ .include_ok
  JMP flush_as_text   ; Not followed by space, treat as text
.include_ok:
  ; Read filename into TOKEN (overwrites keyword)
  JSR read_include_filename
  JSR push_file_source
  ; Initialize line to 1 for included file
  SET16 1, CURLINE16
  LDA #1
  STA AT_LINE_START
  CLC
  RTS

.handle_memory:
  LDA MARKER_TERM
  CMP #' '
  BEQ .memory_with_content
  CMP #'\n'
  BEQ .memory_empty
  ; EOF after @memory = empty content
  ; ($FF terminator means EOF)
.memory_empty:
  ; @memory with no content - just set line start
  ; Increment line if terminated by newline
  LDA MARKER_TERM
  CMP #'\n'
  BNE .memory_empty_no_newline
  INC16 CURLINE16
.memory_empty_no_newline:
  LDA #1
  STA AT_LINE_START
  CLC
  RTS
.memory_with_content:
  ; Read content into TOKEN until newline
  JSR read_memory_content
  JMP setup_memory_source

.handle_traceback:
  ; Consume any remaining content on the line
  ; Use read_char to avoid incrementing line number
  LDA MARKER_TERM
  CMP #'\n'
  BEQ .do_traceback
  CMP #$FF
  BEQ .do_traceback
  ; Terminator was space - skip to end of line
.skip_to_eol:
  JSR read_char
  BCS .do_traceback
  CMP #'\n'
  BNE .skip_to_eol
.do_traceback:
  ; Print the traceback (pops all stack entries, closes files)
  JSR print_traceback
  LDA #1
  STA AT_LINE_START
  CLC
  RTS

.handle_frames:
  ; Consume any remaining content on the line, then print frame chain
  LDA MARKER_TERM
  CMP #'\n'
  BEQ .do_frames
  CMP #$FF
  BEQ .do_frames
  ; Terminator was space - skip to end of line
.frames_skip_eol:
  JSR read_char
  BCS .do_frames
  CMP #'\n'
  BNE .frames_skip_eol
.do_frames:
  JSR print_frames
  LDA #1
  STA AT_LINE_START
  CLC
  RTS

.handle_top_frame_size:
  ; Consume any remaining content on the line, then print top frame size
  LDA MARKER_TERM
  CMP #'\n'
  BEQ .do_tfs
  CMP #$FF
  BEQ .do_tfs
.tfs_skip_eol:
  JSR read_char
  BCS .do_tfs
  CMP #'\n'
  BNE .tfs_skip_eol
.do_tfs:
  JSR print_top_frame_size
  LDA #1
  STA AT_LINE_START
  CLC
  RTS

; @payload_memory <decimal_digit>
;
; Pushes a memory source named "PAYLOAD" with N bytes of payload (N a
; decimal digit 0-9). Payload bytes are filled with a sentinel pattern
; ($A0, $A1, ...) so they're easy to identify if dumped. The memory
; source carries no body content -- the directive prints "ps:<size>"
; (the frame_size byte from offset 0 of the new frame) and then
; immediately pops the frame.
;
; This exercises push_memory_source_reserve_payload's frame_size accounting:
; tests verify that the printed size equals the standard memory-frame
; size plus the requested payload size.
.handle_payload_memory:
  LDA MARKER_TERM
  CMP #' '
  BNE .pm_no_arg
  ; Read the size digit (single decimal char, 0-9)
  JSR read_char
  BCS .pm_no_arg
  CMP #'\n'
  BEQ .pm_no_arg
  SEC
  SBC #'0'
  STA PAYLOAD_REQUESTED_SIZE
  ; Skip the rest of the line
.pm_skip_eol:
  JSR read_char
  BCS .pm_have_size
  CMP #'\n'
  BNE .pm_skip_eol
  JMP .pm_have_size
.pm_no_arg:
  LDA #0
  STA PAYLOAD_REQUESTED_SIZE
.pm_have_size:
  ; Set SS_NAME = "PAYLOAD"
  LDY #0
.pm_copy_name:
  LDA str_payload_source,Y
  STA TOKEN,Y
  BEQ .pm_name_done
  INY
  JMP .pm_copy_name
.pm_name_done:
  ; Pre-write the payload contents into the unallocated source-stack
  ; bytes that will become the new frame's payload region. After
  ; push_memory_source_reserve_payload commits the frame, those bytes
  ; sit at the end of the new frame untouched. The bytes are filled
  ; with a sentinel pattern ($A0, $A1, ...) so they're easy to
  ; identify if dumped.
  LDX PAYLOAD_REQUESTED_SIZE
  BEQ .pm_push                  ; size 0 -> nothing to pre-write
  ; PAYLOAD_DEST16 = SS_P16 - PAYLOAD_REQUESTED_SIZE (low byte; high
  ; byte borrows from SS_P16+1 if needed).
  SEC
  LDA SS_P16
  SBC PAYLOAD_REQUESTED_SIZE
  STA PAYLOAD_DEST16
  LDA SS_P16 + 1
  SBC #$00
  STA PAYLOAD_DEST16 + 1
  LDY #0
.pm_fill:
  TYA
  CLC
  ADC #$A0
  STA (PAYLOAD_DEST16),Y
  INY
  DEX
  BNE .pm_fill
.pm_push:
  ; Push the memory frame, reserving PAYLOAD_REQUESTED_SIZE bytes for
  ; the payload we just wrote.
  LDA PAYLOAD_REQUESTED_SIZE
  JSR push_memory_source_reserve_payload
  ; Print "ps:" prefix
  PUSH16 TABP16
  SET16 str_pm_size_label, TABP16
  JSR print_str
  POP16 TABP16
  ; Print frame_size (offset 0 of the new top frame) as decimal
  LDY #0
  LDA (SS_P16),Y
  STA TO_DECIMAL_VALUE16
  LDA #0
  STA TO_DECIMAL_VALUE16 + 1
  JSR print_decimal
  LDA #'\n'
  JSR write_b
  ; Pop the frame so subsequent reads continue from the parent
  JSR pop_source
  LDA #1
  STA AT_LINE_START
  CLC
  RTS

; @reserve_only
;
; Reserves a memory frame named "PENDING" (no payload) without
; committing. Verifies that:
;   1) SS_P16 is unchanged after the reserve (the reservation is
;      invisible to consumers reading SS_P16).
;   2) The committed-top frame_size still reflects the parent.
; Prints "ps:<top_frame_size>" -- the parent's size.
; Then discards the reservation (SS_PEND_P16 := SS_P16) so subsequent
; pushes start from a clean steady state.
.handle_reserve_only:
  ; Skip remaining content on the line.
  LDA MARKER_TERM
  CMP #'\n'
  BEQ .ro_have_eol
  CMP #$FF
  BEQ .ro_have_eol
.ro_skip_eol:
  JSR read_char
  BCS .ro_have_eol
  CMP #'\n'
  BNE .ro_skip_eol
.ro_have_eol:
  ; SS_NAME = "PENDING"
  LDY #0
.ro_copy_name:
  LDA str_pending_source,Y
  STA TOKEN,Y
  BEQ .ro_name_done
  INY
  JMP .ro_copy_name
.ro_name_done:
  ; Reserve a memory frame, no payload
  LDA #0
  STA SS_PAYLOAD_SIZE
  LDA #SS_SRC_TYPE_MEMORY
  JSR ss_reserve_frame
  ; Print "ps:" + size byte at offset 0 of the COMMITTED top (SS_P16).
  ; If the reservation is correctly invisible, this is the parent's
  ; frame_size, not the reserved frame's.
  PUSH16 TABP16
  SET16 str_pm_size_label, TABP16
  JSR print_str
  POP16 TABP16
  LDY #0
  LDA (SS_P16),Y
  STA TO_DECIMAL_VALUE16
  LDA #0
  STA TO_DECIMAL_VALUE16 + 1
  JSR print_decimal
  LDA #'\n'
  JSR write_b
  ; Discard the reservation: SS_PEND_P16 := SS_P16. Restores steady
  ; state so subsequent pushes work normally.
  CP16 SS_P16, SS_PEND_P16
  LDA #1
  STA AT_LINE_START
  CLC
  RTS

; @reserve_commit_pop
;
; Reserves a memory frame named "RESERVED" (no payload), commits it,
; installs an empty body so reads exhaust immediately, prints
; "ps:<frame_size>" of the new top, then pops. Net effect should be a
; round-trip equivalent to push_memory_source_reserve_payload + pop.
.handle_reserve_commit_pop:
  ; Skip remaining content on the line.
  LDA MARKER_TERM
  CMP #'\n'
  BEQ .rcp_have_eol
  CMP #$FF
  BEQ .rcp_have_eol
.rcp_skip_eol:
  JSR read_char
  BCS .rcp_have_eol
  CMP #'\n'
  BNE .rcp_skip_eol
.rcp_have_eol:
  ; SS_NAME = "RESERVED"
  LDY #0
.rcp_copy_name:
  LDA str_reserved_source,Y
  STA TOKEN,Y
  BEQ .rcp_name_done
  INY
  JMP .rcp_copy_name
.rcp_name_done:
  ; Reserve a memory frame, no payload
  LDA #0
  STA SS_PAYLOAD_SIZE
  LDA #SS_SRC_TYPE_MEMORY
  JSR ss_reserve_frame
  ; Commit
  JSR ss_commit_pending_frame
  ; Install an empty memory body (zero byte) so reads exhaust
  ; immediately.
  SET16 empty_body, SS_MEM_PTR16
  ; Print "ps:" + frame_size of new top
  PUSH16 TABP16
  SET16 str_pm_size_label, TABP16
  JSR print_str
  POP16 TABP16
  LDY #0
  LDA (SS_P16),Y
  STA TO_DECIMAL_VALUE16
  LDA #0
  STA TO_DECIMAL_VALUE16 + 1
  JSR print_decimal
  LDA #'\n'
  JSR write_b
  ; Pop the frame
  JSR pop_source
  LDA #1
  STA AT_LINE_START
  CLC
  RTS

; Compare null-terminated keyword in TOKEN against pattern at (TABP16)
; Returns: C=0 if match, C=1 if no match
cmp_marker:
  LDY #0
.loop:
  LDA TOKEN,Y
  CMP (TABP16),Y
  BNE .no_match
  ; If both are null, it's a match
  CMP #0
  BEQ .match
  INY
  JMP .loop
.match:
  CLC
  RTS
.no_match:
  SEC
  RTS

; Flush '@' + TOKEN keyword + terminator as literal text
; Updates AT_LINE_START and CURLINE16 as needed
; Returns: C=1 (not a marker)
flush_as_text:
  LDA #'@'
  JSR write_b
  ; Output keyword from TOKEN
  LDY #0
.loop:
  LDA TOKEN,Y
  BEQ .keyword_done
  JSR write_b
  INY
  JMP .loop
.keyword_done:
  ; Output the terminator character
  LDA MARKER_TERM
  CMP #$FF
  BEQ .not_newline    ; EOF - nothing to output
  JSR write_b
  CMP #'\n'
  BNE .not_newline
  INC16 CURLINE16
  LDA #1
  STA AT_LINE_START
  SEC
  RTS
.not_newline:
  LDA #0
  STA AT_LINE_START
  SEC
  RTS

; Set up memory source from content in TOKEN (X = length)
setup_memory_source:
  ; TOKEN contains the content, X = length
  ; Problem: SS_NAME = TOKEN, so we can't put name there without losing content
  ; Solution: Copy content to TOKEN+$80, then put name in TOKEN
  ; Save X (content length)
  STX TEMP
  ; Copy content from TOKEN to TOKEN_MEM
  LDY #0
.copy_content:
  CPY TEMP
  BEQ .content_done
  LDA TOKEN,Y
  STA TOKEN_MEM,Y
  INY
  JMP .copy_content
.content_done:
  ; Add null terminator after content (Y = length)
  LDA #0
  STA TOKEN_MEM,Y
  ; Copy "MEMORY" to TOKEN (which is SS_NAME)
  LDY #0
.copy_name:
  LDA str_memory_source,Y
  STA TOKEN,Y
  BEQ .name_done
  INY
  JMP .copy_name
.name_done:
  ; Push memory source FIRST so push_source_frame can capture the parent's
  ; SS_MEM_PTR16 (when the parent is itself a memory source). Only after the
  ; push do we install the new memory pointer. A=0 reserves no payload
  ; (this is a plain memory source -- no activation state to carry).
  LDA #$00
  JSR push_memory_source_reserve_payload
  SET16 TOKEN_MEM, SS_MEM_PTR16
  ; Initialize line to 1 for memory source, at start of line
  SET16 1, CURLINE16
  LDA #1
  STA AT_LINE_START
  CLC
  RTS

str_include:
  .asciiz "include"
str_memory:
  .asciiz "memory"
str_traceback:
  .asciiz "traceback"
str_frames:
  .asciiz "frames"
str_top_frame_size:
  .asciiz "top_frame_size"
str_payload_memory:
  .asciiz "payload_memory"
str_reserve_only:
  .asciiz "reserve_only"
str_reserve_commit_pop:
  .asciiz "reserve_commit_pop"
str_memory_source:
  .asciiz "MEMORY"
str_payload_source:
  .asciiz "PAYLOAD"
str_pending_source:
  .asciiz "PENDING"
str_reserved_source:
  .asciiz "RESERVED"
str_pm_size_label:
  .asciiz "ps:"
empty_body:
  .byte 0
payload_buf:
  .reserve 16

; Read memory content until newline into TOKEN
; Returns length in X (includes trailing newline)
; Note: Uses read_char (not read_char_track_line) to avoid incrementing
; line number - the line should be saved BEFORE reading the content
read_memory_content:
  LDX #0
.loop:
  JSR read_char
  BCS .add_newline    ; EOF - add newline and done
  CMP #'\n'
  BEQ .add_newline    ; Newline - add it and done
  CMP #'\r'
  BEQ .skip_cr
  STA TOKEN,X
  INX
  JMP .loop
.skip_cr:
  JMP .loop
.add_newline:
  LDA #'\n'
  STA TOKEN,X
  INX
  RTS

; Print traceback of source stack - pops all entries, closes files
; Output format: "type:name:line\n" for each entry in stack
; where type is "file" or "memory"
; Loop: check if empty -> print current -> pop -> repeat
print_traceback:
  ; Preserve X (output file handle)
  TXA
  PHA
.loop:
  ; Check if stack is empty (no sources)
  JSR source_stack_empty
  BEQ .done
  ; Frame layout: [0]=frame_size, [1]=curr_type, [2]=prev_type,
  ; [3..4]=prev_line, [5..]=name\0, prev_data, payload.
  CP16 SS_P16, TABP16
  LDY #1
  LDA (TABP16),Y
  BNE .print_memory_type
  ; curr_type = 0: print "file:"
  SET16 str_type_file, TABP16
  JSR print_str
  JMP .print_name
.print_memory_type:
  ; curr_type = 1: print "memory:"
  SET16 str_type_memory, TABP16
  JSR print_str
.print_name:
  ; Name lives at offset 7 of the frame.
  CLC
  ADCI16 SS_P16, $07, TABP16
  JSR print_basename
  ; Print ":"
  LDA #':'
  JSR write_b
  ; Print line number
  CP16 CURLINE16, TO_DECIMAL_VALUE16
  JSR print_decimal
  ; Print newline
  LDA #'\n'
  JSR write_b
  ; Pop current entry (closes file, restores parent's handle and line)
  JSR pop_source
  ; Continue to next
  JMP .loop
.done:
  ; Restore X
  PLA
  TAX
  RTS

str_type_file:
  .asciiz "file:"
str_type_memory:
  .asciiz "memory:"

; Print the byte size of the topmost frame on the source stack.
; Reads frame_size directly from offset 0 of the frame.
; Output: a single decimal number followed by '\n'
; Preserves X
print_top_frame_size:
  TXA
  PHA
  LDY #0
  LDA (SS_P16),Y
  STA TO_DECIMAL_VALUE16
  LDA #0
  STA TO_DECIMAL_VALUE16 + 1
  JSR print_decimal
  LDA #'\n'
  JSR write_b
  PLA
  TAX
  RTS

; Print the current frame chain non-destructively.
; Walks frames from SS_P16 upward until reaching SOURCE_STACK, advancing
; by the frame_size byte at offset 0 of each frame.
; Output: one line per frame "depth:type:name" with depth 0 = top of stack.
; Preserves X. The walker is inlined here -- the source-stack module no
; longer carries a generic ss_walk_frames since this is the only caller.
print_frames:
  TXA
  PHA
  LDA #0
  STA FRAME_DEPTH
  CP16 SS_P16, TABP16
.pf_loop:
  CMPI16 TABP16, SOURCE_STACK
  BCS .pf_done
  JSR print_frame_callback     ; TABP16 unchanged across the call
  ; Advance TABP16 by frame_size at offset 0.
  LDY #0
  LDA (TABP16),Y
  CLC
  ADCA16 TABP16, TABP16
  JMP .pf_loop
.pf_done:
  PLA
  TAX
  RTS

; Per-frame callback used by print_frames. On entry TABP16 = current
; frame; Y free; must leave TABP16 untouched (PUSH16/POP16 around any
; routine that clobbers it).
print_frame_callback:
  ; Print depth as decimal (single byte fits in low half of TO_DECIMAL_VALUE16).
  LDA FRAME_DEPTH
  STA TO_DECIMAL_VALUE16
  LDA #0
  STA TO_DECIMAL_VALUE16 + 1
  JSR print_decimal
  LDA #':'
  JSR write_b
  ; curr_type lives at fixed offset 1 (post-Phase-2.x reorg).
  LDY #1
  LDA (TABP16),Y
  BEQ .is_file
  ; curr_type = 1 (memory)
  PUSH16 TABP16
  SET16 str_type_memory, TABP16
  JSR print_str
  POP16 TABP16
  JMP .print_name
.is_file:
  PUSH16 TABP16
  SET16 str_type_file, TABP16
  JSR print_str
  POP16 TABP16
.print_name:
  ; Names live at offset 7 of the frame, so temporarily advance TABP16
  ; past the [size, curr_type, prev_type, line_L, line_H, prev_data_L,
  ; prev_data_H] header for the print_basename call, then restore
  ; (callback contract).
  PUSH16 TABP16
  CLC
  ADCI16 TABP16, $07, TABP16
  JSR print_basename
  POP16 TABP16
  LDA #'\n'
  JSR write_b
  INC FRAME_DEPTH
  RTS

; Print just the basename from a path at TABP16 (skips everything before last '/')
print_basename:
  ; Find the last '/' in the string
  LDY #0
  STY TEMP              ; TEMP = index of char after last '/'
.scan:
  LDA (TABP16),Y
  BEQ .print_it         ; End of string
  CMP #'/'
  BNE .not_slash
  ; Found '/', remember position after it
  TYA
  CLC
  ADC #1
  STA TEMP
.not_slash:
  INY
  JMP .scan
.print_it:
  ; Print from TEMP to end
  LDY TEMP
.print_loop:
  LDA (TABP16),Y
  BEQ .print_done
  JSR write_b
  INY
  JMP .print_loop
.print_done:
  RTS

print_str:
  LDY #0
.loop:
  LDA (TABP16),Y
  BEQ .done
  JSR write_b
  INY
  JMP .loop
.done:
  RTS

str_chars:
  .asciiz "chars:"
str_lines:
  .asciiz "lines:"
str_stack:
  .asciiz "stack:"
str_empty:
  .asciiz "empty"
str_active:
  .asciiz "active"

; ============================================================================
; Print 16-bit decimal number (converts TO_DECIMAL_VALUE16 and prints it)
; ============================================================================
print_decimal:
  JSR to_decimal
  LDY #0
.loop:
  LDA TO_DECIMAL_RESULT,Y
  BEQ .done
  JSR write_b
  INY
  BNE .loop           ; Always taken (string < 256 chars)
.done:
  RTS

; ============================================================================
; Read character with line tracking (wrapper around source_stack's read_char)
; On exit: A = character, C = 0 if char read, C = 1 if all done
;          CURLINEL/H updated on newline
; ============================================================================
read_char_track_line:
  JSR read_char
  BCS .done
  ; Track line numbers (preserve A and C=0)
  CMP #'\n'
  BNE .success
  INC16 CURLINE16
.success:
  LDA CURR_CHAR       ; Restore A (CMP changed flags)
  CLC                 ; Ensure C=0 for success
.done:
  RTS

; ============================================================================
; Argument parsing
; On exit: C=0 if OK (TEST_MODE set, file opened), C=1 if error
; ============================================================================
parse_args:
  ; Check argc >= 2 (mode, file - emulator doesn't include program name)
  JSR argc
  CMP #2
  BCC .error

  ; Get mode argument (argv[0])
  LDA #0
  JSR argv
  ; A/X contains pointer to arg string
  STA TABP16
  STX TABP16+1
  JSR parse_mode
  BCS .error

  ; Get filename argument (argv[1])
  LDA #1
  JSR argv
  ; A/X contains pointer to arg string
  STA TABP16
  STX TABP16+1
  ; Copy to TOKEN
  LDY #0
.copy_filename:
  LDA (TABP16),Y
  STA TOKEN,Y
  BEQ .filename_done
  INY
  JMP .copy_filename
.filename_done:
  ; Open file via source stack (this resets line number to 0)
  JSR push_file_source
  ; Initialize line number to 1 (first line is line 1)
  SET16 1, CURLINE16
  CLC
  RTS
.error:
  SEC
  RTS

; Parse mode string at TABP16/H
; Sets TEST_MODE, returns C=0 on success
parse_mode:
  LDY #0
  LDA (TABP16),Y
  LDX #0
  CMP #'e'
  BEQ .set_mode
  INX
  CMP #'l'
  BEQ .set_mode
  INX
  CMP #'i'
  BEQ .set_mode
  INX
  CMP #'m'
  BEQ .set_mode
  INX
  CMP #'f'
  BEQ .set_mode
  INX
  CMP #'o'
  BEQ .set_mode
  SEC
  RTS
.set_mode:
  STX TEST_MODE
  CLC
  RTS

; ============================================================================
; Error handling
; ============================================================================
error_usage:
  SET16 msg_usage, TABP16
  JSR print_str_err
  LDA #1
  JMP exit

print_str_err:
  LDY #0
.loop:
  LDA (TABP16),Y
  BEQ .done
  JSR write_d
  INY
  JMP .loop
.done:
  RTS

msg_usage:
  .asciiz "Usage: source_stack_test <mode> <file>\nModes: echo, lines, info, memory, frames, oom\n"

; Emulator convention - start address is the last 2 bytes of the file
  .word main
