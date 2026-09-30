; Requires:
;   FILE_STACK    - 1 past the highest address from which the stack grows down
;   FS_FILENAME   - filename
;   FS_CURR_FILE  - zero page location of the current file handle
;   FS_CURR_LINEL - zero page location of the current line
;   FS_CURR_LINEH - "
;   open, close   - functions to open and close a file

; The file stack grows downwards. Each entry includes (from low to high address)
; File name of current file (0-terminated)
; File handle of previous file (1 byte)
; Line number of previous file (2 bytes)

  .zeropage

FS_PL   .data $00 ; Pointer to the current location in the file stack
FS_PH   .data $00 ; "
FS_TEMP .data $00 ; Temporary location for use in calculations

  .code


file_stack_init
  LDA #<FILE_STACK
  STA FS_PL
  LDA #>FILE_STACK
  STA FS_PH
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


; On entry FS_FILENAME contains the file name of the new file to open
;            and push on stack
;          FS_CURR_LINEL;FS_CURR_LINEH contains the current line
;            number of the current file
;          FS_CURR_FILE contains the current file handle
; On exit X is preserved
push_file_stack
  LDY #$FF
.len_loop
; A <- len(FS_FILENAME)
  INY
  LDA FS_FILENAME,Y
  BNE .len_loop
; Decrease file stack pointer by len(FS_FILENAME) + 4
; (null terminator + handle + 2-byte line number)
  TYA
  CLC
  ADC #$04
  STA FS_TEMP
  SEC
  LDA FS_PL
  SBC FS_TEMP
  STA FS_PL
  LDA FS_PH
  SBC #$00
  STA FS_PH
  LDY #$FF
.copy_loop
  INY
  LDA FS_FILENAME,Y
  STA (FS_PL),Y
  BNE .copy_loop
  ; Store file handle
  INY
  LDA FS_CURR_FILE
  STA (FS_PL),Y
  INY
  ; Store line number
  LDA FS_CURR_LINEL
  STA (FS_PL),Y
  INY
  LDA FS_CURR_LINEH
  STA (FS_PL),Y
  INY
; Reset line number and open new file
  LDA #$00
  STA FS_CURR_LINEL
  STA FS_CURR_LINEH

  TXA
  PHA
  LDA #<FS_FILENAME
  LDX #>FS_FILENAME
  JSR open
  STA FS_CURR_FILE
  PLA
  TAX

  RTS


; On exit FS_CURR_FILE contains the previous file handle
;         FS_CURR_LINEL;FS_CURR_LINEH contains the previous line number
pop_file_stack
; Close currnet file and restore from filestack
  LDA FS_CURR_FILE
  JSR close
; Pop the filename
  LDY #$FF
.pop_loop
  INY
  LDA (FS_PL),Y
  BNE .pop_loop
; Pop the file handle
  INY
  LDA (FS_PL),Y
  STA FS_CURR_FILE
; Pop the line number
  INY
  LDA (FS_PL),Y
  STA FS_CURR_LINEL
  INY
  LDA (FS_PL),Y
  STA FS_CURR_LINEH
; Adjust stack pointer
  TYA
  SEC  ; +1
  ADC FS_PL
  STA FS_PL
  LDA #$00
  ADC FS_PH
  STA FS_PH
  RTS
