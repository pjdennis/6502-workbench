; Requires:
;   FILE_STACK    - 1 past the highest address from which the stack grows down
;   FS_FILENAME   - filename buffer
;   FS_CURR_FILE  - zero page location of the current file handle
;   FS_CURR_LINEL - zero page location of the current line number (low byte)
;   FS_CURR_LINEH - zero page location of the current line number (high byte)
;   FS_NEXT_CHAR  - zero page location to store last character read
;   open, close, read - file I/O functions
;
; Optional:
;   FS_ERR_NO_FILE - error handler for read_char when no file is open
;                    If not defined, read_char returns SEC like normal EOF

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

FS_PL   .data $00 ; Pointer to the current location in the file stack
FS_PH   .data $00 ; "
FS_TEMP .data $00 ; Temporary location for use in calculations

; Memory source support (zero-terminated buffers)
FS_SRC_TYPE   .data $00 ; Source type: 0=file, 1=memory
FS_MEM_PTR_L  .data $00 ; Current read position in memory (low)
FS_MEM_PTR_H  .data $00 ; Current read position in memory (high)

  .code


file_stack_init
  LDA #<FILE_STACK
  STA FS_PL
  LDA #>FILE_STACK
  STA FS_PH
  LDA #$00
  STA FS_SRC_TYPE
  RTS


; On exit Z is set if file stack empty, clear otherwise
file_stack_empty
  LDA FS_PL
  CMP #<FILE_STACK
  BNE .done
  LDA FS_PH
  CMP #>FILE_STACK
.done
  RTS


; Internal: Build a stack frame for a new source
; On entry: A = curr_type (0=file, 1=memory)
;           FS_FILENAME contains the source name
; On exit: Frame built with name, curr_type, prev_type, prev_line, prev_data
;          FS_CURR_LINEL/H reset to 0
;          A, X, Y clobbered
push_source_frame
  PHA                   ; Save curr_type for later
  ; Calculate name length
  LDY #$FF
.len_loop
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
.size_done
  STA FS_TEMP
  ; Decrease stack pointer by frame size
  SEC
  LDA FS_PL
  SBC FS_TEMP
  STA FS_PL
  LDA FS_PH
  SBC #$00
  STA FS_PH
  ; Copy name to stack
  LDY #$FF
.copy_loop
  INY
  LDA FS_FILENAME,Y
  STA (FS_PL),Y
  BNE .copy_loop
  ; Store curr_type (saved on 6502 stack)
  INY
  PLA                   ; Get curr_type
  STA (FS_PL),Y
  ; Store prev_type
  INY
  LDA FS_SRC_TYPE
  STA (FS_PL),Y
  PHA                   ; Save prev_type for later
  ; Store prev_line
  INY
  LDA FS_CURR_LINEL
  STA (FS_PL),Y
  INY
  LDA FS_CURR_LINEH
  STA (FS_PL),Y
  ; Store prev_data based on prev_type
  PLA                   ; Restore prev_type
  BNE .save_memory_state
  ; prev_type=0: save file handle
  INY
  LDA FS_CURR_FILE
  STA (FS_PL),Y
  JMP .reset_line
.save_memory_state
  ; prev_type=1: save memory pointer (zero-terminated, no end needed)
  INY
  LDA FS_MEM_PTR_L
  STA (FS_PL),Y
  INY
  LDA FS_MEM_PTR_H
  STA (FS_PL),Y
.reset_line
  ; Reset line number for new source
  LDA #$00
  STA FS_CURR_LINEL
  STA FS_CURR_LINEH
  RTS


; Push a file source onto the stack
; On entry: FS_FILENAME contains the file name to open
;           FS_CURR_LINEL;FS_CURR_LINEH contains the current line number
;           FS_CURR_FILE contains the current file handle
; On exit: X is preserved, new file is open and ready to read
push_file_stack
  TXA
  PHA                   ; Save X
  LDA #$00              ; curr_type = file
  JSR push_source_frame
  ; Open new file
  LDA #$00
  STA FS_SRC_TYPE       ; Now a file source
  LDA #<FS_FILENAME
  LDX #>FS_FILENAME
  JSR open
  STA FS_CURR_FILE
  PLA
  TAX                   ; Restore X
  RTS


; Push a memory source onto the stack
; On entry: FS_FILENAME = name for this memory source (e.g., macro name)
;           FS_MEM_PTR_L/H = start of zero-terminated memory buffer
; On exit: X is preserved, reading will continue from memory buffer
push_memory_source
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
;          FS_CURR_LINEL/H restored to prev_line
pop_source
  ; Skip past name to find null terminator
  LDY #$FF
.skip_name
  INY
  LDA (FS_PL),Y
  BNE .skip_name
  ; Y points at null, curr_type is at Y+1
  INY
  LDA (FS_PL),Y
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
.was_file_source
  ; curr_type=0: close the current file
  LDA FS_CURR_FILE
  JSR close
.restore_prev
  ; Read prev_type
  INY
  LDA (FS_PL),Y
  STA FS_SRC_TYPE       ; Restore source type
  PHA                   ; Save for later
  ; Read prev_line
  INY
  LDA (FS_PL),Y
  STA FS_CURR_LINEL
  INY
  LDA (FS_PL),Y
  STA FS_CURR_LINEH
  ; Restore prev_data based on prev_type
  PLA
  BNE .restore_memory
  ; prev_type=0: restore file handle
  INY
  LDA (FS_PL),Y
  STA FS_CURR_FILE
  JMP .adjust_stack
.restore_memory
  ; prev_type=1: restore memory pointer (zero-terminated, no end needed)
  INY
  LDA (FS_PL),Y
  STA FS_MEM_PTR_L
  INY
  LDA (FS_PL),Y
  STA FS_MEM_PTR_H
.adjust_stack
  ; Y points to last byte read, add Y+1 to stack pointer
  TYA
  SEC                   ; +1
  ADC FS_PL
  STA FS_PL
  LDA #$00
  ADC FS_PH
  STA FS_PH
  RTS

; Legacy names for compatibility
pop_file_stack = pop_source
pop_memory_source = pop_source


; Read character from current source (file or memory)
; On exit: A = character (also stored in FS_NEXT_CHAR)
;          C = 0 if char read, C = 1 if all sources exhausted
file_stack_read_char
  LDA FS_SRC_TYPE
  BNE .read_memory
  ; Type 0 = file source
  LDA FS_CURR_FILE
  BEQ .no_source
  JSR read
  BCC .got_char
  ; EOF on current file - pop and try previous source
  JSR pop_source
  ; Check if stack is empty
  JSR file_stack_empty
  BEQ .all_done
  ; Continue reading from previous source (could be file or memory)
  JMP file_stack_read_char
.read_memory
  ; Type 1 = memory source (zero-terminated)
  ; Read byte from memory pointer
  LDY #$00
  LDA (FS_MEM_PTR_L),Y
  BEQ .mem_exhausted     ; $00 = end of memory source
  ; Increment memory pointer
  INC FS_MEM_PTR_L
  BNE .got_char
  INC FS_MEM_PTR_H
.got_char
  STA FS_NEXT_CHAR
  CLC
  RTS
.mem_exhausted
  ; Memory source exhausted - pop and try previous source
  JSR pop_source
  ; Check if stack is empty
  JSR file_stack_empty
  BEQ .all_done
  ; Continue reading from previous source
  JMP file_stack_read_char
.no_source
  .ifdef FS_ERR_NO_FILE
  JMP FS_ERR_NO_FILE
  .endif
.all_done
  SEC
  RTS
