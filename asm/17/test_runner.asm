; test_runner.asm - Native 6502 test runner for the assembler
;
; Runs assembler test files entirely within the emulated environment.
; The assembler code is called as a black box via JSR start.
; Vectors (exit, argc, argv, write_d) are intercepted to capture results.
; Output is verified by reading back the output file after assembly.
;
; Build:
;   (cd 17 && ../emulator.out out/asm.out asm.asm out/test_runner.out define:enable_test_runner)
;
; Usage:
;   (cd 17/tests/asm && ../../../emulator.out ../../out/test_runner.out 01-instructions.txt)
;
; Directory mode (no arguments):
;   (cd 17/tests/asm && ../../../emulator.out ../../out/test_runner.out)
;
; When no filename is given, opendir(".") is used to discover and run all
; .txt files in the current directory in alphabetical order.


; ============================================================================
; ZERO PAGE VARIABLES
; ============================================================================
; These are allocated after all assembler ZP variables and are NOT clobbered
; by the assembler when it runs.

  .zeropage

TR_SAVED_SP:       .byte       ; Stack pointer saved before JSR start
TR_EXIT_CODE:      .byte       ; Exit code captured from assembler
TR_ARGC:           .byte       ; Virtual argument count for assembler
TR_STDERR_LEN:     .byte       ; Length of captured stderr output
TR_EXPECT_LEN16:   .word       ; Length of expected hex bytes
TR_FILE_HANDLE:    .byte       ; Test file handle
TR_INPUT_HANDLE:   .byte       ; Temp input file handle
TR_LINE_LEN:       .byte       ; Current line buffer length
TR_STATE:          .byte       ; Parser state (0=none, 1=input)
TR_SKIP_FLAG:      .byte       ; Skip flag for current test
TR_EXPECT_ERROR:   .byte       ; Expected error code
TR_EXPECT_LINE16:  .word       ; Expected line number
TR_PASS_COUNT16:   .word       ; Number of passed tests
TR_FAIL_COUNT16:   .word       ; Number of failed tests
TR_SKIP_COUNT16:   .word       ; Number of skipped tests
TR_TEST_TYPE:      .byte       ; 0=hex test, 1=error test
TR_HAS_TEST:       .byte       ; Nonzero if a test has been parsed
TR_ACTUAL_LEN16:   .word       ; Length of actual output bytes
TR_ARGV_COUNT:     .byte       ; Number of extra ARGS entries
TR_LINE_TRUNC:     .byte       ; Nonzero if line was truncated (more in file)
TR_ACTUAL_PTR16:   .word       ; Pointer into TR_EXPECT_BUF for comparison
TR_MISMATCH_FLAG:  .byte       ; Nonzero if byte mismatch detected
TR_MISMATCH_ACTUAL: .byte      ; Actual byte at first mismatch
TR_MISMATCH_EXPECT: .byte      ; Expected byte at first mismatch
TR_MISMATCH_POS16: .word       ; Position of first mismatch
TR_DIR_HANDLE:     .byte       ; Directory handle for directory scanning mode
TR_DIR_META:       .byte       ; Current directory entry metadata byte
TR_VERBOSE:        .byte       ; Nonzero to forward assembler stderr to terminal
TR_FILE_ARG:       .byte       ; Index of filename arg in argv, or $FF for none
TR_QUIET:          .byte       ; Nonzero to suppress passing test output
TR_PTR16:          .word       ; General-purpose 16-bit pointer
TR_TEMP:           .byte       ; Temporary scratch byte
TR_PARSE16:        .word       ; 16-bit parsed value
TR_SCRATCH16:      .word       ; 16-bit scratch for multiply

  .code

  .macro TR_SHOW_CHAR val
  LDA #val
  JSR write_d
  .endmacro

  .macro TR_SHOW_MESSAGEI addr
  SET16 addr, TR_PTR16
  JSR tr_show_message
  .endmacro


; ============================================================================
; BUFFER LAYOUT ($0900-$0FFF)
; ============================================================================

TR_ACTUAL_BUF   = $1000  ; Actual output bytes for failure display (256 bytes, $1000-$10FF)
TR_EXPECT_BUF   = $0900  ; Expected hex bytes (512 bytes, $0900-$0AFF)
TR_STDERR_BUF   = $0B00  ; Captured stderr output (256 bytes, $0B00-$0BFF)
TR_EXPECT_MSG   = $0C00  ; Expected error message (256 bytes, $0C00-$0CFF)
TR_NAME_BUF     = $0D00  ; Test name (256 bytes, $0D00-$0DFF)
TR_ARGV_PTRS    = $0E00  ; Virtual argv pointers (16 entries x 2 = 32 bytes)
TR_ARGV_STRS    = $0E20  ; Virtual argv strings (224 bytes, $0E20-$0EFF)
TR_LINE_BUF     = $0F00  ; Line read buffer (256 bytes, $0F00-$0FFF)

; Temp file names (stored in code)
TR_INPUT_FILE:  .asciiz "_tr_in.tmp"
TR_OUTPUT_FILE: .asciiz "_tr_out.tmp"


  .include tr_core.asm
  .include tr_fields.asm
  .include tr_verify.asm
  .include tr_parse.asm
  .include tr_vectors.asm
  .include tr_print.asm
