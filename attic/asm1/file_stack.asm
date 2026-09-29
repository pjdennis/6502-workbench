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

FS_PL   DATA $00 ; Pointer to the current location in the file stack
FS_PH   DATA $00 ; "
FS_TEMP DATA $00 ; Temporary location for use in calculations

  .code


file_stack_init
  LDA# <FILE_STACK
  STAZ FS_PL
  LDA# >FILE_STACK
  STAZ FS_PH
  RTS


; On exit Z is set if file stack empty, clear otherwise
file_stack_empty
  LDAZ FS_PL
  CMP# <FILE_STACK
  BNE fse_done
  LDAZ FS_PH
  CMP# >FILE_STACK
fse_done
  RTS


; On entry FS_FILENAME contains the file name of the new file to open
;            and push on stack
;          FS_CURR_LINEL;FS_CURR_LINEH contains the current line
;            number of the current file
;          FS_CURR_FILE contains the current file handle
; On exit X is preserved
push_file_stack
  LDY# $FF
pfs_len_loop
; A <- len(FS_FILENAME) 
  INY
  LDA,Y FS_FILENAME
  BNE pfs_len_loop
; Decrease file stack pointer by len(FS_FILENAME) + 4
; (null terminator + handle + 2-byte line number)
  TYA
  CLC
  ADC# $04
  STAZ FS_TEMP
  SEC
  LDAZ FS_PL
  SBCZ FS_TEMP
  STAZ FS_PL
  LDAZ FS_PH
  SBC# $00
  STAZ FS_PH
  LDY# $FF
pfs_copy_loop
  INY
  LDA,Y FS_FILENAME
  STAZ(),Y FS_PL
  BNE pfs_copy_loop
  ; Store file handle
  INY
  LDA FS_CURR_FILE
  STAZ(),Y FS_PL
  INY
  ; Store line number
  LDA FS_CURR_LINEL
  STAZ(),Y FS_PL
  INY
  LDA FS_CURR_LINEH
  STAZ(),Y FS_PL
  INY
; Reset line number and open new file
  LDA# $00
  STAZ FS_CURR_LINEL
  STAZ FS_CURR_LINEH

  TXA
  PHA
  LDA# <FS_FILENAME
  LDX# >FS_FILENAME
  JSR open
  STAZ FS_CURR_FILE
  PLA
  TAX

  RTS


; On exit FS_CURR_FILE contains the previous file handle
;         FS_CURR_LINEL;FS_CURR_LINEH contains the previous line number
pop_file_stack
; Close currnet file and restore from filestack
  LDAZ FS_CURR_FILE
  JSR close
; Pop the filename
  LDY# $FF
rc_pop_loop
  INY
  LDAZ(),Y FS_PL
  BNE rc_pop_loop
; Pop the file handle
  INY
  LDAZ(),Y FS_PL
  STAZ FS_CURR_FILE
; Pop the line number
  INY
  LDAZ(),Y FS_PL
  STAZ FS_CURR_LINEL
  INY
  LDAZ(),Y FS_PL
  STAZ FS_CURR_LINEH
; Adjust stack pointer
  TYA
  SEC  ; +1
  ADCZ FS_PL
  STAZ FS_PL
  LDA# $00
  ADCZ FS_PH
  STAZ FS_PH
  RTS
