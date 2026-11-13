; tr_vectors.asm - Vector interception and fake handlers


; ============================================================================
; VECTOR INTERCEPTION
; ============================================================================
; The emulator's environment vectors are JMP instructions at fixed addresses.
; Each JMP is 3 bytes: opcode ($4C) + 2-byte target address.
; We patch the target bytes to redirect to our fake handlers.
;
;   Vector    JMP at   Target bytes    Fake handler
;   ------    ------   ------------    ------------
;   write_d   $F00C    $F00D-$F00E     fake_write_d
;   exit      $F00F    $F010-$F011     fake_exit
;   argc      $F01B    $F01C-$F01D     fake_argc
;   argv      $F01E    $F01F-$F020     fake_argv

; Vector table: (port_target_addr, fake_handler_addr) for each vector
tr_vector_table:
  .word write_d,    fake_write_d
  .word exit,       fake_exit
  .word argc,       fake_argc
  .word argv,       fake_argv
tr_vector_table_end:
TR_VECTOR_ENTRIES = tr_vector_table_end - tr_vector_table >> 2
TR_ORIG_VECTORS_SIZE = TR_VECTOR_ENTRIES + TR_VECTOR_ENTRIES

tr_orig_vectors: .reserve TR_ORIG_VECTORS_SIZE

tr_vc_count: .byte 0

; Trampoline: JSR tr_call_action → JMP (tr_action_ptr) → action RTS back
tr_call_action:
  JMP (tr_action_ptr)
tr_action_ptr: .word 0

; Walk table, calling action for each entry
; On each call: TR_PTR16 = port target addr, X = orig_vectors index,
;               TR_ACTUAL_PTR16 = current table entry
tr_vector_walk:
  SET16 tr_vector_table, TR_ACTUAL_PTR16
  LDX #$00
  LDA #TR_VECTOR_ENTRIES
  STA tr_vc_count
.loop:
  ; Load port target address from table[0..1] into TR_PTR16
  LDY #$00
  CLC
  LDA (TR_ACTUAL_PTR16),Y
  ADC #1
  STA TR_PTR16
  INY
  LDA (TR_ACTUAL_PTR16),Y
  ADC #0
  STA TR_PTR16 + 1
  ; Call action
  JSR tr_call_action
  ; Advance X (orig_vectors index) and table pointer
  INX
  INX
  CLC
  LDA TR_ACTUAL_PTR16
  ADC #$04
  STA TR_ACTUAL_PTR16
  BCC .no_carry
  INC TR_ACTUAL_PTR16 + 1
.no_carry:
  DEC tr_vc_count
  BNE .loop
  RTS

; Public API — thin wrappers setting the action pointer
tr_save_vectors:
  SET16 tr_action_save, tr_action_ptr
  JMP tr_vector_walk

tr_patch_vectors:
  SET16 tr_action_patch, tr_action_ptr
  JMP tr_vector_walk

tr_restore_vectors:
  SET16 tr_action_restore, tr_action_ptr
  JMP tr_vector_walk

; Action: copy 2 bytes from (TR_PTR16) → tr_orig_vectors+X
tr_action_save:
  LDY #$00
  LDA (TR_PTR16),Y
  STA tr_orig_vectors,X
  INY
  LDA (TR_PTR16),Y
  STA tr_orig_vectors + 1,X
  RTS

; Action: copy fake handler addr from table[2..3] → (TR_PTR16)
tr_action_patch:
  LDY #$02
  LDA (TR_ACTUAL_PTR16),Y     ; fake lo
  PHA
  INY
  LDA (TR_ACTUAL_PTR16),Y     ; fake hi
  LDY #$01
  STA (TR_PTR16),Y               ; write hi
  PLA
  DEY
  STA (TR_PTR16),Y               ; write lo
  RTS

; Action: copy 2 bytes from tr_orig_vectors+X → (TR_PTR16)
tr_action_restore:
  LDY #$00
  LDA tr_orig_vectors,X
  STA (TR_PTR16),Y
  INY
  LDA tr_orig_vectors + 1,X
  STA (TR_PTR16),Y
  RTS


; ============================================================================
; FAKE HANDLERS
; ============================================================================

; fake_exit - Capture exit code and return control to test runner
; Called when assembler hits BRK → interrupt → JMP exit
; On entry: A = exit code
fake_exit:
  STA TR_EXIT_CODE        ; Save exit code
  LDX TR_SAVED_SP
  TXS                     ; Atomically unwind stack
  JMP tr_test_resume      ; Continue in test runner

; fake_argc - Return virtual argument count
; On entry: nothing
; On exit: A = argument count, X and Y preserved
fake_argc:
  LDA TR_ARGC
  RTS

; fake_argv - Return virtual argument pointer
; On entry: A = argument index
; On exit: A = low byte, X = high byte, Y preserved
fake_argv:
  STY tr_save_y           ; Save Y
  ASL                     ; index * 2 (word-sized entries)
  TAY
  LDX TR_ARGV_PTRS + 1,Y ; X = high byte
  LDA TR_ARGV_PTRS,Y     ; A = low byte
  LDY tr_save_y           ; Restore Y
  RTS

tr_save_y: .byte 0

; fake_write_d - Buffer stderr byte and optionally forward to real port
; On entry: A = byte to write
; On exit: A, X, Y preserved (matches real write_d contract)
; Caps buffer at 255 bytes (stops buffering, still forwards if verbose)
fake_write_d:
  PHA
  LDA TR_VERBOSE
  BNE .forward
  PLA
  JMP .buffer
.forward:
  PLA
  STA $F002               ; Forward to real stderr port
.buffer:
  STX tr_save_x           ; Save X
  LDX TR_STDERR_LEN
  CPX #$FF                ; Buffer full?
  BCS .skip               ; Don't buffer
  STA TR_STDERR_BUF,X     ; Buffer the byte
  INC TR_STDERR_LEN
.skip:
  LDX tr_save_x           ; Restore X
  RTS

tr_save_x: .byte 0
