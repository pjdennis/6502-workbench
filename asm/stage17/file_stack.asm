; Requires:
;   FILE_STACK     - 1 past the highest address from which the stack grows down
;   FS_FILENAME    - filename buffer
;   FS_ERR_NO_FILE - error handler for read_char when no file is open
;   err_file_not_found - error handler for when open returns 0
;   open, close, read - file I/O functions

; The file stack grows downwards. Unified frame format (from low to high address):
;
;   name\0         - Source name (null-terminated)
;   curr_type      - Type of THIS source: 0=file, 1=memory
;   prev_type      - Type we're RETURNING to: 0=file, 1=memory
;   prev_line_L    - Line number in parent (low byte)
;   prev_line_H    - Line number in parent (high byte)
;   <prev_data>    - Depends on prev_type:
;                    If prev_type=0 (file):   prev_handle (1 byte)
;                    If prev_type=1 (memory): prev_ptr_L, prev_ptr_H (2 bytes, zero-terminated)
;
; Frame sizes: name_len + 1 (null) + 1 (curr) + 1 (prev) + 2 (line) + prev_data
;   = name_len + 6 if returning to file
;   = name_len + 7 if returning to memory

  .zeropage

FS_CURR_CHAR:   .data $00   ; The last character read
FS_CURR_FILE:   .data $00   ; The current file handle
FS_CURR_LINE16: .data $0000 ; The current line number
FS_P16:         .data $0000 ; Pointer to the current location in the file stack
FS_TEMP16:      .data $0000 ; Temporary location for use in calculations

; Memory source support (zero-terminated buffers)
FS_SRC_TYPE:   .data $00   ; Source type: 0=file, 1=memory
FS_MEM_PTR16:  .data $0000 ; Current read position in memory

  .code


file_stack_init:
  SET16 FILE_STACK FS_P16
  LDA #$00
  STA FS_SRC_TYPE
  STA FS_CURR_FILE
  RTS


; On exit Z is set if file stack empty, clear otherwise
file_stack_empty:
  CMPI16 FS_P16 FILE_STACK
  RTS


; Internal: Build a stack frame for a new source
; On entry: A = curr_type (0=file, 1=memory)
;           FS_FILENAME contains the source name
; On exit: Frame built with name, curr_type, prev_type, prev_line, prev_data
;          FS_CURR_LINE16 reset to 0
;          A, X, Y clobbered
push_source_frame:
  PHA                   ; Save curr_type for later
  ; Calculate name length
  LDY #$FF
.len_loop:
  INY
  LDA FS_FILENAME,Y
  BNE .len_loop
  ; Y = name length (without null)
  ; Calculate frame size: name_len + 1 (null) + 1 (curr) + 1 (prev) + 2 (line) + prev_data
  ; prev_data is 1 byte if prev_type=0 (file), 2 bytes if prev_type=1 (memory ptr only)
  TYA
  CLC
  ADC #$06              ; Base: name + null + curr_type + prev_type + line + handle
  LDX FS_SRC_TYPE
  BEQ .size_done
  ADC #$01              ; Add 1 more for memory (2 bytes ptr - 1 already counted)
.size_done:
  STA FS_TEMP16
  ; Decrease stack pointer by frame size
  SEC
  LDA FS_P16
  SBC FS_TEMP16
  STA FS_TEMP16
  LDA FS_P16+$01
  SBC #$00
  STA FS_TEMP16+$01

  ; Check for collision with heap before committing
  CHECK_FOR_OUT_OF_MEMORY FS_TEMP16

  ; Commit new stack pointer
  CP16 FS_TEMP16 FS_P16
  ; Copy name to stack
  LDY #$FF
.copy_loop:
  INY
  LDA FS_FILENAME,Y
  STA (FS_P16),Y
  BNE .copy_loop
  ; Store curr_type (saved on 6502 stack)
  INY
  PLA                   ; Get curr_type
  STA (FS_P16),Y
  ; Store prev_type
  INY
  LDA FS_SRC_TYPE
  STA (FS_P16),Y
  PHA                   ; Save prev_type for later
  ; Store prev_line
  INY
  LDA FS_CURR_LINE16
  STA (FS_P16),Y
  INY
  LDA FS_CURR_LINE16+$01
  STA (FS_P16),Y
  ; Store prev_data based on prev_type
  PLA                   ; Restore prev_type
  BNE .save_memory_state
  ; prev_type=0: save file handle
  INY
  LDA FS_CURR_FILE
  STA (FS_P16),Y
  JMP .reset_line
.save_memory_state:
  ; prev_type=1: save memory pointer (zero-terminated, no end needed)
  INY
  LDA FS_MEM_PTR16
  STA (FS_P16),Y
  INY
  LDA FS_MEM_PTR16+$01
  STA (FS_P16),Y
.reset_line:
  ; Reset line number for new source
  LDA #$00
  STA_LH16 FS_CURR_LINE16
  RTS


; Push a file source onto the stack
; On entry: FS_FILENAME contains the file name to open
;           FS_CURR_LINE16 contains the current line number
;           FS_CURR_FILE contains the current file handle
; On exit: X is preserved, new file is open and ready to read
push_file_stack:
  TXA
  PHA                   ; Save X
  ; Open file before pushing frame so error reports parent context
  LDA #<FS_FILENAME
  LDX #>FS_FILENAME
  JSR open
  CMP #$00
  BNE .file_ok
  JMP err_file_not_found
.file_ok:
  PHA                   ; Save new file handle
  LDA #$00              ; curr_type = file
  JSR push_source_frame
  LDA #$00
  STA FS_SRC_TYPE       ; Now a file source
  PLA
  STA FS_CURR_FILE      ; Set new file handle
  PLA
  TAX                   ; Restore X
  RTS


; Push a memory source onto the stack
; On entry: FS_FILENAME = name for this memory source (e.g., macro name)
;           FS_MEM_PTR16 = start of zero-terminated memory buffer
; On exit: X is preserved, reading will continue from memory buffer
push_memory_source:
  TXA
  PHA                   ; Save X
  LDA #$01              ; curr_type = memory
  JSR push_source_frame
  ; Set up memory source (pointers already set by caller)
  LDA #$01
  STA FS_SRC_TYPE       ; Now a memory source
  PLA
  TAX                   ; Restore X
  RTS


; Unified pop function - handles both file and memory sources
; On exit: Previous state restored (FS_CURR_FILE or FS_MEM_PTR)
;          FS_SRC_TYPE restored to prev_type
;          FS_CURR_LINE16 restored to prev_line
pop_source:
  ; Skip past name to find null terminator
  LDY #$FF
.skip_name:
  INY
  LDA (FS_P16),Y
  BNE .skip_name
  ; Y points at null, curr_type is at Y+1
  INY
  LDA (FS_P16),Y
  BEQ .was_file_source
  ; curr_type=1: was memory source - pop label scope if hook defined
  .ifdef FS_POP_MEMORY_HOOK
  TYA
  PHA                   ; Save Y (frame offset) before hook
  JSR FS_POP_MEMORY_HOOK
  PLA
  TAY                   ; Restore Y
  .endif
  JMP .restore_prev
.was_file_source:
  ; curr_type=0: close the current file (if open)
  LDA FS_CURR_FILE
  BEQ .restore_prev     ; Handle 0 = no file to close
  JSR close
.restore_prev:
  ; Read prev_type
  INY
  LDA (FS_P16),Y
  STA FS_SRC_TYPE       ; Restore source type
  PHA                   ; Save for later
  ; Read prev_line
  INY
  LDA (FS_P16),Y
  STA FS_CURR_LINE16
  INY
  LDA (FS_P16),Y
  STA FS_CURR_LINE16+$01
  ; Restore prev_data based on prev_type
  PLA
  BNE .restore_memory
  ; prev_type=0: restore file handle
  INY
  LDA (FS_P16),Y
  STA FS_CURR_FILE
  JMP .adjust_stack
.restore_memory:
  ; prev_type=1: restore memory pointer (zero-terminated, no end needed)
  INY
  LDA (FS_P16),Y
  STA FS_MEM_PTR16
  INY
  LDA (FS_P16),Y
  STA FS_MEM_PTR16+$01
.adjust_stack:
  ; Y points to last byte read, add Y+1 to stack pointer
  TYA
  SEC                   ; +1
  ADCA16 FS_P16 FS_P16 
  RTS

; Legacy names for compatibility
pop_file_stack = pop_source


; Read character from current source (file or memory)
; On exit: A = character (also stored in FS_CURR_CHAR)
;          C = 0 if char read, C = 1 if all sources exhausted
;          X is preserved
;          Y is not preserved
file_stack_read_char:
  LDA FS_SRC_TYPE
  BNE .read_memory
  ; Type 0 = file source
  LDA FS_CURR_FILE
  .ifdef enable_debug 
  BEQ .no_source
  .endif
  JSR read
  BCS .source_exhausted
  ; Got character
  STA FS_CURR_CHAR
  ; Carry is clear
  RTS
.read_memory:
  ; Type 1 = memory source (zero-terminated)
  ; Read byte from memory pointer
  LDY #$00
  LDA (FS_MEM_PTR16),Y
  BEQ .source_exhausted     ; $00 = end of memory source
  ; Increment memory pointer
  INC16 FS_MEM_PTR16     ; Preserves A
  STA FS_CURR_CHAR
  CLC
  RTS
.source_exhausted:
  ; Source exhausted - pop and try previous source
  JSR pop_source
  ; Check if stack is empty
  JSR file_stack_empty
  ; Continue reading from previous source
  BNE file_stack_read_char
.all_done:
  SEC
  RTS
  .ifdef enable_debug
.no_source:
  JMP FS_ERR_NO_FILE
  .endif
