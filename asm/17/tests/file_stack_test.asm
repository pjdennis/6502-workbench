; File Stack Test Program
; Usage: file_stack_test <mode> <input_file>
; Modes:
;   echo   - Read file char by char, write to stdout
;   lines  - Read file, output "N:content" for each line
;   nested - Handle @include markers, echo all content
;   info   - Read file, output statistics
;   memory - Handle @memory and @include markers, test memory sources

* = $0200

FILE_STACK = $F000
TOKEN      = $1D00
TOKEN_MEM  = $1D80  ; Offset in TOKEN buffer for memory content

  .zeropage

; Test state
TEST_MODE:     .data $00     ; 0=echo, 1=lines, 2=nested, 3=info, 4=memory
CHAR_COUNT16:  .data $0000   ; Character count
LINE_COUNT16:  .data $0000   ; Line count
AT_LINE_START: .data $00     ; Flag: at start of line (for lines mode)

; Temporary
TEMP:        .data $00
TABP16:      .data $0000

  .code

  .include environment.asm
  .include macros.asm
  .include to_decimal.asm

; File stack configuration
FS_FILENAME   = TOKEN

; CHECK_FOR_OUT_OF_MEMORY - Macro placeholder for use by file stack
  .macro CHECK_FOR_OUT_OF_MEMORY fs_ptr
  ; Do nothing, for the purposes of the file stack test.
  ; TODO: Consider writing to debug output when it's called, and extend tests to confirm
  .endmacro

; Error handler for file-not-found (required by file_stack.asm)
err_file_not_found:
  BRK
  .data $24 "File not found" $00

  .include file_stack.asm
read_char = file_stack_read_char
CURLINE16 = FS_CURR_LINE16
CURR_CHAR = FS_CURR_CHAR


main:
  JSR file_stack_init
  JSR parse_args
  BCC .args_ok
  JMP error_usage

.args_ok:
  ; Initialize counters
  SET16 $00 CHAR_COUNT16
  SET16 $00 LINE_COUNT16
  LDA #$01
  STA AT_LINE_START

  ; Dispatch based on mode
  LDA TEST_MODE
  BEQ mode_echo
  CMP #$01
  BEQ mode_lines
  CMP #$02
  BEQ .go_nested
  CMP #$03
  BEQ .go_info
  CMP #$04
  BEQ .go_memory
  JMP error_usage
.go_nested:
  JMP mode_nested
.go_info:
  JMP mode_info
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
  LDA #$00
  JMP exit

; ============================================================================
; MODE: lines - Output "N:content" for each line
; ============================================================================
mode_lines:
.loop:
  ; If at line start, save line number BEFORE read_char can increment it
  LDA AT_LINE_START
  BEQ .do_read
  CP16 CURLINE16 TO_DECIMAL_VALUE16
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
  LDA #$00
  STA AT_LINE_START
  PLA
.not_start:
  JSR write_b
  CMP #$0A            ; newline
  BNE .loop
  LDA #$01
  STA AT_LINE_START
  JMP .loop
.done:
  LDA #$00
  JMP exit

; ============================================================================
; MODE: nested - Handle @include markers
; ============================================================================
mode_nested:
.loop:
  JSR read_char_track_line
  BCS .done
  ; Check for '@' at start of line
  CMP #'@'
  BNE .not_include
  LDA AT_LINE_START
  BEQ .not_include
  ; Might be @include - check
  JSR check_include_marker
  BCC .loop           ; Was @include, continue reading from new file
  JMP .loop           ; Not @include, but already output - continue
.not_include:
  JSR write_b
  ; Track line start
  CMP #$0A
  BNE .not_newline
  LDA #$01
  STA AT_LINE_START
  JMP .loop
.not_newline:
  LDA #$00
  STA AT_LINE_START
  JMP .loop
.done:
  LDA #$00
  JMP exit

; Check if we're at "@include " and handle it
; On entry: just read '@'
; On exit: C=0 if was include (file pushed), C=1 if not (already output '@')
check_include_marker:
  ; Read and check "include "
  LDX #$00
.check_loop:
  JSR read_char_track_line
  BCS .not_include_eof
  CMP include_marker,X
  BNE .not_include_char
  INX
  CPX #$08            ; Length of "include "
  BNE .check_loop
  ; It's @include - read filename into TOKEN
  JSR read_include_filename
  JSR push_file_stack
  ; Initialize line to 1 for included file
  SET16 $01 CURLINE16
  LDA #$01
  STA AT_LINE_START
  CLC
  RTS
.not_include_char:
  ; Not @include - output '@' and what we read, then return char
  PHA
  LDA #'@'
  JSR write_b
  ; Output matched portion
  TXA
  BEQ .output_current
  LDY #$00
.output_matched:
  LDA include_marker,Y
  JSR write_b
  INY
  DEX
  BNE .output_matched
.output_current:
  PLA
  JSR write_b
  ; Check if what we just output was a newline
  CMP #$0A
  BNE .not_newline_after
  LDA #$01
  STA AT_LINE_START
  SEC
  RTS
.not_newline_after:
  LDA #$00
  STA AT_LINE_START
  SEC
  RTS
.not_include_eof:
  ; EOF during check - output '@' and matched portion
  LDA #'@'
  JSR write_b
  TXA
  BEQ .eof_done
  LDY #$00
.output_matched_eof:
  LDA include_marker,Y
  JSR write_b
  INY
  DEX
  BNE .output_matched_eof
.eof_done:
  SEC
  RTS

include_marker:
  .data "include "

; Read filename until newline into TOKEN
; Note: Uses read_char (not read_char_track_line) to avoid incrementing
; line number - the line should be saved BEFORE reading the filename
read_include_filename:
  LDX #$00
.loop:
  JSR read_char
  BCS .done
  CMP #$0A
  BEQ .done
  CMP #$0D            ; Also handle CR
  BEQ .skip_cr
  STA TOKEN,X
  INX
  JMP .loop
.skip_cr:
  JMP .loop
.done:
  LDA #$00
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
  CMP #$0A
  BNE .loop
  INC16 LINE_COUNT16
  JMP .loop
.done:
  ; Output "chars:N"
  JSR print_str_chars
  CP16 CHAR_COUNT16 TO_DECIMAL_VALUE16
  JSR print_decimal
  LDA #$0A
  JSR write_b
  ; Output "lines:N"
  JSR print_str_lines
  CP16 LINE_COUNT16 TO_DECIMAL_VALUE16
  JSR print_decimal
  LDA #$0A
  JSR write_b
  ; Output "stack:empty" or "stack:active"
  JSR print_str_stack
  JSR file_stack_empty
  BNE .stack_not_empty
  JSR print_str_empty
  JMP .info_done
.stack_not_empty:
  JSR print_str_active
.info_done:
  LDA #$0A
  JSR write_b
  LDA #$00
  JMP exit

; ============================================================================
; MODE: memory - Handle @memory and @include markers
; ============================================================================
mode_memory:
.loop:
  JSR read_char_track_line
  BCS .done
  ; Check for '@' at start of line
  CMP #'@'
  BNE .not_marker
  LDA AT_LINE_START
  BEQ .not_marker
  ; Might be @include or @memory - check
  JSR check_memory_or_include
  BCC .loop           ; Was a marker, continue reading
  JMP .loop           ; Not a marker, but already output - continue
.not_marker:
  JSR write_b
  ; Track line start
  CMP #$0A
  BNE .not_newline
  LDA #$01
  STA AT_LINE_START
  JMP .loop
.not_newline:
  LDA #$00
  STA AT_LINE_START
  JMP .loop
.done:
  LDA #$00
  JMP exit

; Check if we're at "@include ", "@memory ", or "@traceback" and handle it
; On entry: just read '@'
; On exit: C=0 if was a marker (handled), C=1 if not (already output '@')
check_memory_or_include:
  ; Read char to see if it's 'i' (include), 'm' (memory), or 't' (traceback)
  JSR read_char_track_line
  BCS .not_marker_eof
  CMP #'i'
  BEQ .check_include
  CMP #'m'
  BEQ .go_check_memory
  CMP #'t'
  BEQ .go_check_traceback
  JMP .not_a_marker
.go_check_memory:
  JMP .check_memory
.go_check_traceback:
  JMP .check_traceback
.not_a_marker:
  ; Not a marker - output '@' and this char
  PHA
  LDA #'@'
  JSR write_b
  PLA
  JSR write_b
  CMP #$0A
  BNE .not_marker_not_newline
  LDA #$01
  STA AT_LINE_START
  SEC
  RTS
.not_marker_not_newline:
  LDA #$00
  STA AT_LINE_START
  SEC
  RTS
.not_marker_eof:
  LDA #'@'
  JSR write_b
  SEC
  RTS

.check_include:
  ; Check for "nclude " (we already matched 'i')
  LDX #$00
.include_loop:
  JSR read_char_track_line
  BCS .not_include_eof
  CMP include_rest,X
  BNE .not_include_char
  INX
  CPX #$07            ; Length of "nclude "
  BNE .include_loop
  ; It's @include - read filename into TOKEN
  JSR read_include_filename
  JSR push_file_stack
  ; Initialize line to 1 for included file
  SET16 $01 CURLINE16
  LDA #$01
  STA AT_LINE_START
  CLC
  RTS
.not_include_char:
  ; Not @include - output "@i" and matched portion, then this char
  PHA
  LDA #'@'
  JSR write_b
  LDA #'i'
  JSR write_b
  TXA
  BEQ .include_output_current
  LDY #$00
.include_output_matched:
  LDA include_rest,Y
  JSR write_b
  INY
  DEX
  BNE .include_output_matched
.include_output_current:
  PLA
  JSR write_b
  CMP #$0A
  BNE .include_not_newline
  LDA #$01
  STA AT_LINE_START
  SEC
  RTS
.include_not_newline:
  LDA #$00
  STA AT_LINE_START
  SEC
  RTS
.not_include_eof:
  ; EOF - output "@i" and matched portion
  LDA #'@'
  JSR write_b
  LDA #'i'
  JSR write_b
  TXA
  BEQ .include_eof_done
  LDY #$00
.include_eof_output:
  LDA include_rest,Y
  JSR write_b
  INY
  DEX
  BNE .include_eof_output
.include_eof_done:
  SEC
  RTS

.check_memory:
  ; Check for "emory" then space or newline (we already matched 'm')
  LDX #$00
.memory_loop:
  JSR read_char_track_line
  BCS .go_not_memory_eof
  CMP memory_rest,X
  BNE .go_check_memory_terminator
  JMP .memory_loop_continue
.go_not_memory_eof:
  JMP .not_memory_eof
.go_check_memory_terminator:
  JMP .check_memory_terminator
.memory_loop_continue:
  INX
  CPX #$05            ; Length of "emory" (without trailing space)
  BNE .memory_loop
  ; Got "emory", now check for space or newline
  JSR read_char_track_line
  BCS .memory_empty   ; EOF after @memory = empty content
  CMP #' '
  BEQ .memory_with_content
  CMP #$0A
  BEQ .memory_empty   ; Newline after @memory = empty content
  ; Not space or newline - not a valid @memory marker
  JMP .not_memory_after_emory
.memory_with_content:
  ; It's @memory with content - read into TOKEN until newline
  JSR read_memory_content
  JMP .setup_memory_source
.memory_empty:
  ; It's @memory with no content - don't push anything
  LDA #$01
  STA AT_LINE_START
  CLC
  RTS
.setup_memory_source:
  ; Set up memory source pointers
  ; TOKEN contains the content, X = length
  ; Problem: FS_FILENAME = TOKEN, so we can't put name there without losing content
  ; Solution: Copy content to TOKEN+$80, then put name in TOKEN
  ; Save X (content length)
  STX TEMP
  ; Copy content from TOKEN to TOKEN_MEM
  LDY #$00
.copy_content:
  CPY TEMP
  BEQ .content_done
  LDA TOKEN,Y
  STA TOKEN_MEM,Y
  INY
  JMP .copy_content
.content_done:
  ; Add null terminator after content (Y = length)
  LDA #$00
  STA TOKEN_MEM,Y
  ; Copy "MEMORY" to TOKEN (which is FS_FILENAME)
  LDY #$00
.copy_name:
  LDA str_memory_source,Y
  STA TOKEN,Y
  BEQ .name_done
  INY
  JMP .copy_name
.name_done:
  ; Set memory pointer to TOKEN_MEM (content is now zero-terminated)
  SET16 TOKEN_MEM FS_MEM_PTR16
  ; Push memory source (FS_FILENAME has name, pointer is set)
  JSR push_memory_source
  ; Initialize line to 1 for memory source, at start of line
  SET16 $01 CURLINE16
  LDA #$01
  STA AT_LINE_START
  CLC
  RTS
.check_memory_terminator:
  ; Not @memory - output "@m" and matched portion, then this char
  PHA
  LDA #'@'
  JSR write_b
  LDA #'m'
  JSR write_b
  TXA
  BEQ .memory_output_current
  LDY #$00
.memory_output_matched:
  LDA memory_rest,Y
  JSR write_b
  INY
  DEX
  BNE .memory_output_matched
.memory_output_current:
  PLA
  JSR write_b
  CMP #$0A
  BNE .memory_not_newline
  LDA #$01
  STA AT_LINE_START
  SEC
  RTS
.memory_not_newline:
  LDA #$00
  STA AT_LINE_START
  SEC
  RTS
.not_memory_after_emory:
  ; Got @memory but followed by non-space/non-newline char
  ; Output "@memory" and this char
  PHA
  LDA #'@'
  JSR write_b
  LDA #'m'
  JSR write_b
  LDY #$00
.output_emory:
  LDA memory_rest,Y
  JSR write_b
  INY
  CPY #$05
  BNE .output_emory
  PLA
  JSR write_b
  CMP #$0A
  BNE .after_emory_not_newline
  LDA #$01
  STA AT_LINE_START
  SEC
  RTS
.after_emory_not_newline:
  LDA #$00
  STA AT_LINE_START
  SEC
  RTS
.not_memory_eof:
  ; EOF - output "@m" and matched portion
  LDA #'@'
  JSR write_b
  LDA #'m'
  JSR write_b
  TXA
  BEQ .memory_eof_done
  LDY #$00
.memory_eof_output:
  LDA memory_rest,Y
  JSR write_b
  INY
  DEX
  BNE .memory_eof_output
.memory_eof_done:
  SEC
  RTS

.check_traceback:
  ; Check for "raceback" (we already matched 't')
  LDX #$00
.traceback_loop:
  JSR read_char_track_line
  BCS .not_traceback_eof
  CMP traceback_rest,X
  BNE .not_traceback_char
  INX
  CPX #$08            ; Length of "raceback"
  BNE .traceback_loop
  ; It's @traceback - skip to end of line (consume any trailing content)
  ; Use read_char to avoid incrementing line number
.skip_to_eol:
  JSR read_char
  BCS .do_traceback
  CMP #$0A
  BNE .skip_to_eol
.do_traceback:
  ; Print the traceback (pops all stack entries, closes files)
  JSR print_traceback
  LDA #$01
  STA AT_LINE_START
  CLC
  RTS
.not_traceback_char:
  ; Not @traceback - output "@t" and matched portion, then this char
  PHA
  LDA #'@'
  JSR write_b
  LDA #'t'
  JSR write_b
  TXA
  BEQ .traceback_output_current
  LDY #$00
.traceback_output_matched:
  LDA traceback_rest,Y
  JSR write_b
  INY
  DEX
  BNE .traceback_output_matched
.traceback_output_current:
  PLA
  JSR write_b
  CMP #$0A
  BNE .traceback_not_newline
  LDA #$01
  STA AT_LINE_START
  SEC
  RTS
.traceback_not_newline:
  LDA #$00
  STA AT_LINE_START
  SEC
  RTS
.not_traceback_eof:
  ; EOF - output "@t" and matched portion
  LDA #'@'
  JSR write_b
  LDA #'t'
  JSR write_b
  TXA
  BEQ .traceback_eof_done
  LDY #$00
.traceback_eof_output:
  LDA traceback_rest,Y
  JSR write_b
  INY
  DEX
  BNE .traceback_eof_output
.traceback_eof_done:
  SEC
  RTS

include_rest:
  .data "nclude "
memory_rest:
  .data "emory"
traceback_rest:
  .data "raceback"
str_memory_source:
  .data "MEMORY" $00

; Read memory content until newline into TOKEN
; Returns length in X (includes trailing newline)
; Note: Uses read_char (not read_char_track_line) to avoid incrementing
; line number - the line should be saved BEFORE reading the content
read_memory_content:
  LDX #$00
.loop:
  JSR read_char
  BCS .add_newline    ; EOF - add newline and done
  CMP #$0A
  BEQ .add_newline    ; Newline - add it and done
  CMP #$0D            ; Also handle CR
  BEQ .skip_cr
  STA TOKEN,X
  INX
  JMP .loop
.skip_cr:
  JMP .loop
.add_newline:
  LDA #$0A
  STA TOKEN,X
  INX
.done:
  RTS

; ============================================================================
; String printing utilities
; ============================================================================

print_str_chars:
  SET16 str_chars TABP16
  JMP print_str

print_str_lines:
  SET16 str_lines TABP16
  JMP print_str

print_str_stack:
  SET16 str_stack TABP16
  JMP print_str

print_str_empty:
  SET16 str_empty TABP16
  JMP print_str

print_str_active:
  SET16 str_active TABP16
  JMP print_str

; Print traceback of file stack - pops all entries, closes files
; Output format: "type:name:line\n" for each entry in stack
; where type is "file" or "memory"
; Loop: check if empty -> print current -> pop -> repeat
print_traceback:
  ; Preserve X (output file handle)
  TXA
  PHA
.loop:
  ; Check if stack is empty (no sources)
  JSR file_stack_empty
  BEQ .done
  ; Find curr_type by scanning past the name
  ; FS_P16 points to: name\0 | curr_type | ...
  CP16 FS_P16 TABP16
  LDY #$00
.find_null:
  LDA (TABP16),Y
  BEQ .found_null
  INY
  JMP .find_null
.found_null:
  ; Y points at null, curr_type is at Y+1
  INY
  LDA (TABP16),Y
  BNE .print_memory_type
  ; curr_type = 0: print "file:"
  SET16 str_type_file TABP16
  JSR print_str
  JMP .print_name
.print_memory_type:
  ; curr_type = 1: print "memory:"
  SET16 str_type_memory TABP16
  JSR print_str
.print_name:
  ; Print name (FS_PL points to current entry's name)
  CP16 FS_P16 TABP16
  JSR print_basename
  ; Print ":"
  LDA #':'
  JSR write_b
  ; Print line number
  CP16 CURLINE16 TO_DECIMAL_VALUE16
  JSR print_decimal
  ; Print newline
  LDA #$0A
  JSR write_b
  ; Pop current entry (closes file, restores parent's handle and line)
  JSR pop_file_stack
  ; Continue to next
  JMP .loop
.done:
  ; Restore X
  PLA
  TAX
  RTS

str_type_file:
  .data "file:" $00
str_type_memory:
  .data "memory:" $00

; Print just the basename from a path at TABP16 (skips everything before last '/')
print_basename:
  ; Find the last '/' in the string
  LDY #$00
  STY TEMP              ; TEMP = index of char after last '/'
.scan:
  LDA (TABP16),Y
  BEQ .print_it         ; End of string
  CMP #'/'
  BNE .not_slash
  ; Found '/', remember position after it
  TYA
  CLC
  ADC #$01
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
  LDY #$00
.loop:
  LDA (TABP16),Y
  BEQ .done
  JSR write_b
  INY
  JMP .loop
.done:
  RTS

str_chars:
  .data "chars:" $00
str_lines:
  .data "lines:" $00
str_stack:
  .data "stack:" $00
str_empty:
  .data "empty" $00
str_active:
  .data "active" $00

; ============================================================================
; Print 16-bit decimal number (converts TO_DECIMAL_VALUE16 and prints it)
; ============================================================================
print_decimal:
  JSR to_decimal
  LDY #$00
.loop:
  LDA TO_DECIMAL_RESULT,Y
  BEQ .done
  JSR write_b
  INY
  BNE .loop           ; Always taken (string < 256 chars)
.done:
  RTS

; ============================================================================
; Read character with line tracking (wrapper around file_stack's read_char)
; On exit: A = character, C = 0 if char read, C = 1 if all done
;          CURLINEL/H updated on newline
; ============================================================================
read_char_track_line:
  JSR read_char
  BCS .done
  ; Track line numbers (preserve A and C=0)
  CMP #$0A
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
  CMP #$02
  BCC .error

  ; Get mode argument (argv[0])
  LDA #$00
  JSR argv
  ; A/X contains pointer to arg string
  STA TABP16
  STX TABP16+$01
  JSR parse_mode
  BCS .error

  ; Get filename argument (argv[1])
  LDA #$01
  JSR argv
  ; A/X contains pointer to arg string
  STA TABP16
  STX TABP16+$01
  ; Copy to TOKEN
  LDY #$00
.copy_filename:
  LDA (TABP16),Y
  STA TOKEN,Y
  BEQ .filename_done
  INY
  JMP .copy_filename
.filename_done:
  ; Open file via file stack (this resets line number to 0)
  JSR push_file_stack
  ; Initialize line number to 1 (first line is line 1)
  SET16 $01 CURLINE16
  CLC
  RTS
.error:
  SEC
  RTS

; Parse mode string at TABP16/H
; Sets TEST_MODE, returns C=0 on success
parse_mode:
  LDY #$00
  LDA (TABP16),Y
  CMP #'e'
  BEQ .check_echo
  CMP #'l'
  BEQ .check_lines
  CMP #'n'
  BEQ .check_nested
  CMP #'i'
  BEQ .check_info
  CMP #'m'
  BEQ .check_memory
  SEC
  RTS
.check_echo:
  LDA #$00
  STA TEST_MODE
  CLC
  RTS
.check_lines:
  LDA #$01
  STA TEST_MODE
  CLC
  RTS
.check_nested:
  LDA #$02
  STA TEST_MODE
  CLC
  RTS
.check_info:
  LDA #$03
  STA TEST_MODE
  CLC
  RTS
.check_memory:
  LDA #$04
  STA TEST_MODE
  CLC
  RTS

; ============================================================================
; Error handling
; ============================================================================
error_usage:
  SET16 msg_usage TABP16
  JSR print_str_err
  LDA #$01
  JMP exit

print_str_err:
  LDY #$00
.loop:
  LDA (TABP16),Y
  BEQ .done
  JSR write_d
  INY
  JMP .loop
.done:
  RTS

msg_usage:
  .data "Usage: file_stack_test <mode> <file>" $0A
  .data "Modes: echo, lines, nested, info, memory" $0A $00

; Emulator convention - start address is the last 2 bytes of the file
  .data main
