; tr_core.asm - Entry point, main loop, test execution, and state management


; ============================================================================
; ENTRY POINT
; ============================================================================

test_runner_start:
  ; Save original vector targets before any patching
  JSR tr_save_vectors
  ; Default: suppress assembler stderr output, show all results
  LDA #$00
  STA TR_VERBOSE
  STA TR_QUIET
  ; Scan argv for flags (-v) and find filename arg
  LDA #$FF
  STA TR_FILE_ARG           ; No filename found yet
  JSR argc
  STA tr_argc_total
  LDX #$00                  ; Arg index
.scan_args:
  CPX tr_argc_total
  BCS .args_done
  TXA
  PHA                       ; Save arg index
  JSR argv                  ; A/X = pointer to arg string
  STAX16 TR_PTR16
  LDY #$00
  LDA (TR_PTR16),Y
  CMP #'-'
  BNE .is_file
  ; Verify exactly "-X" (null terminator at index 2)
  LDY #$02
  LDA (TR_PTR16),Y
  BNE .skip_arg             ; Not a 2-char flag
  LDY #$01
  LDA (TR_PTR16),Y            ; Flag character
  LDX #$00
.flag_loop:
  LDY tr_flag_table,X
  BEQ .skip_arg             ; Sentinel: unknown flag, ignore
  CMP tr_flag_table,X
  BEQ .flag_found
  INX
  INX
  JMP .flag_loop
.flag_found:
  LDA tr_flag_table + 1,X   ; ZP address from table
  TAX
  LDA #$01
  STA $00,X                  ; Store $01 to the ZP variable
  JMP .skip_arg
.is_file:
  PLA
  STA TR_FILE_ARG
  PHA
.skip_arg:
  PLA                       ; Restore arg index
  TAX
  INX
  JMP .scan_args
.args_done:
  LDA TR_FILE_ARG
  CMP #$FF
  BEQ .dir_mode
  ; --- Single file mode ---
  JSR argv
  JSR open
  STA TR_FILE_HANDLE
  ; Print header
  TR_SHOW_MESSAGEI tr_msg_running
  LDA TR_FILE_ARG
  JSR argv
  STAX16 TR_PTR16
  JSR tr_show_message
  TR_SHOW_CHAR '\n'
  ; Run all tests from this file
  JSR tr_run_file
  JMP .summary
.dir_mode:
  ; --- Directory mode: scan for .txt files ---
  JSR tr_run_directory
.summary:
  ; Print summary
  JSR tr_print_summary
  ; Exit with failure code if any tests failed
  LDA TR_FAIL_COUNT16
  ORA TR_FAIL_COUNT16 + 1
  BNE .exit_fail
  LDA #$00
  JMP exit
.exit_fail:
  LDA #$01
  JMP exit

tr_msg_running:
  .asciiz "Running tests from "

tr_argc_total: .byte 0

; Flag table: (char, zp_address) pairs, null sentinel
tr_flag_table:
  .byte 'v', TR_VERBOSE
  .byte 'q', TR_QUIET
  .byte 0


; ============================================================================
; FILE PROCESSING
; ============================================================================

; Run all tests from the file in TR_FILE_HANDLE
; On entry: TR_FILE_HANDLE = open file handle
; On exit: TR_FILE_HANDLE is closed, pass/fail/skip counts updated
tr_run_file:
  JSR tr_init_test
.main_loop:
  JSR tr_read_line
  BCS .eof
  ; Check for --- separator (always, even in input state)
  JSR tr_check_separator
  BCC .handle_sep
  ; Try field keywords (ends input state if matched)
  JSR tr_dispatch_field
  BCC .field_done
  ; No field matched
  LDA TR_STATE
  BEQ .idle_line
  CMP #$02
  BEQ .stderr_line
  JSR tr_handle_input_line
  JMP .main_loop
.stderr_line:
  JSR tr_handle_stderr_line
  JMP .main_loop
.idle_line:
  ; Not in a section: skip empty lines and comments
  JSR tr_skip_rest_of_line
  JMP .main_loop
.field_done:
  JSR tr_skip_rest_of_line
  JMP .main_loop
.handle_sep:
  JSR tr_skip_rest_of_line
  JSR tr_close_input_state
  JSR tr_handle_separator
  JMP .main_loop
.eof:
  ; Handle last test in file (no trailing ---)
  JSR tr_close_input_state
  LDA TR_HAS_TEST
  BEQ .done
  JSR tr_finalize_test
.done:
  ; Close test file
  LDA TR_FILE_HANDLE
  JSR close
  RTS


; ============================================================================
; DIRECTORY SCANNING
; ============================================================================

; Scan current directory for .txt files and run each one
; Uses opendir(".") to list entries, filters for non-directory .txt files
tr_run_directory:
  LDA #<tr_dot_path
  LDX #>tr_dot_path
  JSR opendir
  CMP #$00
  BEQ .done
  STA TR_DIR_HANDLE
.entry_loop:
  ; Read metadata byte
  LDA TR_DIR_HANDLE
  JSR read
  BCS .close_dir
  STA TR_DIR_META
  ; Read filename into TR_LINE_BUF (null-terminated by opendir)
  LDY #$00
.name_loop:
  LDA TR_DIR_HANDLE
  JSR read
  BCS .close_dir               ; Unexpected EOF mid-entry
  STA TR_LINE_BUF,Y
  BEQ .name_done               ; Null terminator
  INY
  JMP .name_loop
.name_done:
  STY TR_LINE_LEN
  ; Skip directories
  LDA TR_DIR_META
  AND #DIR_ENTRY_DIR
  BNE .entry_loop
  ; Check if filename ends with ".txt"
  JSR tr_check_txt_extension
  BCS .entry_loop
  ; Print header for this file
  TR_SHOW_MESSAGEI tr_msg_running
  SET16 TR_LINE_BUF, TR_PTR16
  JSR tr_show_message
  TR_SHOW_CHAR '\n'
  ; Open the file and run all tests from it
  LDA #<TR_LINE_BUF
  LDX #>TR_LINE_BUF
  JSR open
  STA TR_FILE_HANDLE
  JSR tr_run_file
  JMP .entry_loop
.close_dir:
  LDA TR_DIR_HANDLE
  JSR close
.done:
  RTS

tr_dot_path: .asciiz "."


; Check if TR_LINE_BUF[0..TR_LINE_LEN) ends with ".txt"
; On exit: C clear = ends with .txt, C set = does not
tr_check_txt_extension:
  LDA TR_LINE_LEN
  CMP #$05                    ; Must be at least 5 chars (x.txt)
  BCC .no
  TAY
  DEY                          ; Y = index of last char
  LDA TR_LINE_BUF,Y
  CMP #'t'
  BNE .no
  DEY
  LDA TR_LINE_BUF,Y
  CMP #'x'
  BNE .no
  DEY
  LDA TR_LINE_BUF,Y
  CMP #'t'
  BNE .no
  DEY
  LDA TR_LINE_BUF,Y
  CMP #'.'
  BNE .no
  CLC
  RTS
.no:
  SEC
  RTS


; ============================================================================
; TEST EXECUTION
; ============================================================================

; Finalize the current test: skip or run it
tr_finalize_test:
  LDA TR_SKIP_FLAG
  BEQ .run
  ; Skip this test
  LDA TR_QUIET
  BNE .skip_quiet
  JSR tr_print_test_name
  TR_SHOW_MESSAGEI tr_msg_skip
.skip_quiet:
  INC16 TR_SKIP_COUNT16
  RTS
.run:
  JMP tr_run_test           ; Tail call

; Run a single test: set up argv, patch vectors, call assembler
tr_run_test:
  ; Set up virtual argv
  JSR tr_setup_argv
  ; Clear stderr capture
  LDA #$00
  STA TR_STDERR_LEN
  ; Patch vectors to intercept
  JSR tr_patch_vectors
  ; Save stack pointer
  TSX
  STX TR_SAVED_SP
  ; Run assembler (skip the JMP test_runner_start at start:)
  JSR start + $03
  ; NOTE: We never reach here - fake_exit intercepts and jumps to tr_test_resume

; Resume point after assembler exits (fake_exit jumps here via stack unwind)
; The stack has been restored to the state before JSR start+3,
; so RTS returns to the caller of tr_run_test.
tr_test_resume:
  ; Restore original vectors immediately
  JSR tr_restore_vectors
  ; Verify results based on test type
  LDA TR_TEST_TYPE
  CMP #$02
  BEQ .stderr_test
  CMP #$01
  BEQ .error_test
  ; === Hex test ===
  JSR tr_verify_hex
  BCS .fail
  JMP .pass
.stderr_test:
  ; === Stderr test ===
  JSR tr_verify_stderr
  BCS .fail
  JMP .pass
.error_test:
  ; === Error test ===
  JSR tr_verify_error
  BCS .fail
.pass:
  LDA TR_QUIET
  BNE .pass_quiet
  JSR tr_print_test_name
  TR_SHOW_MESSAGEI tr_msg_pass
.pass_quiet:
  INC16 TR_PASS_COUNT16
  RTS
.fail:
  INC16 TR_FAIL_COUNT16
  RTS

; Set up virtual argv for the assembler
; argv[0] = "_tr_in.tmp", argv[1] = "_tr_out.tmp", argv[2+] = ARGS tokens
tr_setup_argv:
  SET16 TR_INPUT_FILE, TR_ARGV_PTRS
  SET16 TR_OUTPUT_FILE, TR_ARGV_PTRS + $02
  LDA #$02
  STA TR_ARGC
  ; Parse ARGS string if present
  LDX TR_ARGV_COUNT
  BEQ .done
  ; Walk TR_ARGV_STRS, splitting on spaces
  ; Each token becomes argv[TR_ARGC]
  LDY #$00                 ; Index into TR_ARGV_STRS
.skip_spaces:
  LDA TR_ARGV_STRS,Y
  BEQ .done                ; Null terminator
  CMP #' '
  BNE .start_token
  INY
  JMP .skip_spaces
.start_token:
  ; Record pointer to this token in argv table
  LDX TR_ARGC
  CPX #$08                 ; Max 8 argv entries (16 bytes of pointers)
  BCS .done
  TXA
  ASL                      ; *2 for word-sized entries
  TAX
  CLC
  TYA
  ADC #<TR_ARGV_STRS
  STA TR_ARGV_PTRS,X
  LDA #$00
  ADC #>TR_ARGV_STRS
  STA TR_ARGV_PTRS + 1,X
  INC TR_ARGC
.scan_token:
  LDA TR_ARGV_STRS,Y
  BEQ .done                ; End of string
  CMP #' '
  BEQ .end_token
  INY
  JMP .scan_token
.end_token:
  LDA #$00
  STA TR_ARGV_STRS,Y       ; Null-terminate this token
  INY
  JMP .skip_spaces
.done:
  RTS

tr_msg_skip:        .asciiz " SKIP\n"
tr_msg_pass:        .asciiz " PASS\n"
tr_msg_fail:        .asciiz " !!FAIL!!"
tr_msg_close_paren: .asciiz ")\n"
tr_msg_expected:    .asciiz " (expected "
tr_msg_got:         .asciiz ", got "
tr_msg_bytes:       .asciiz " bytes"
tr_msg_error:       .asciiz "error "
tr_msg_line:        .asciiz "line "
tr_msg_msg:         .asciiz "msg \""
tr_msg_quote:       .asciiz "\""
tr_msg_byte_at:     .asciiz " (byte "
tr_msg_colon_space: .asciiz ": "
tr_msg_exp_prefix:  .asciiz "    exp: "
tr_msg_got_prefix:  .asciiz "    got: "
tr_msg_wrong_msg:   .asciiz " (msg mismatch)\n"
tr_msg_wrong_line:  .asciiz " (line mismatch)\n"
tr_msg_wrong_code:  .asciiz " (error code mismatch)\n"


; ============================================================================
; TEST STATE MANAGEMENT
; ============================================================================

; Initialize/reset test state for a new test
tr_init_test:
  LDA #$00
  STA TR_HAS_TEST
  STA TR_NAME_BUF         ; Clear name (null terminator at start)
  STA TR_SKIP_FLAG
  STA TR_EXPECT_ERROR
  STA_LH16 TR_EXPECT_LEN16
  STA_LH16 TR_EXPECT_LINE16
  STA TR_EXPECT_MSG        ; Clear expected message
  STA TR_TEST_TYPE
  STA TR_STATE
  STA TR_ARGV_COUNT
  RTS

; Print the test name (indented, no newline)
tr_print_test_name:
  TR_SHOW_MESSAGEI tr_msg_indent
  SET16 TR_NAME_BUF, TR_PTR16
  JMP tr_show_message          ; Tail call

tr_msg_indent:    .asciiz "  "

; Copy from TR_LINE_BUF[Y..TR_LINE_LEN) to TR_NAME_BUF
; On entry: Y = starting offset in TR_LINE_BUF
tr_copy_field_to_name:
  LDX #$00
.loop:
  CPY TR_LINE_LEN
  BCS .done
  LDA TR_LINE_BUF,Y
  STA TR_NAME_BUF,X
  INY
  INX
  BNE .loop
.done:
  LDA #$00
  STA TR_NAME_BUF,X       ; Null-terminate
  RTS
