" Vim syntax file for 6502 assembler (asm22 format)
" Language: 6502 Assembly
" Put this file in ~/.vim/syntax/asm6502.vim
" Add to ~/.vimrc:  autocmd BufRead,BufNewFile *.asm set filetype=asm6502

if exists("b:current_syntax")
  finish
endif

" Case insensitive matching for opcodes
syntax case ignore

" Comments - semicolon to end of line
syntax match asm6502Comment ";.*$"

" Strings
syntax region asm6502String start=+"+ end=+"+ contains=asm6502Escape
syntax match asm6502Escape "\\[n\\']" contained

" Character constants
syntax match asm6502Char "'\(\\.\|[^']\)'"

" Hex numbers
syntax match asm6502Hex "\$[0-9a-fA-F]\+"

" Decimal numbers (standalone, not part of identifier)
syntax match asm6502Decimal "\<[0-9]\+\>"

" Labels at start of line (global labels)
syntax match asm6502Label "^[a-zA-Z_][a-zA-Z0-9_]*"

" Local labels at start of line (start with .)
syntax match asm6502LocalLabel "^\.[a-zA-Z_][a-zA-Z0-9_]*"

" Directives (start with . but not at line start)
syntax match asm6502Directive "\s\+\.\(macro\|endmacro\|data\|include\|ifdef\|endif\|zeropage\)\>"

" 6502 Opcodes - Load/Store
syntax keyword asm6502Opcode LDA LDX LDY STA STX STY

" 6502 Opcodes - Transfer
syntax keyword asm6502Opcode TAX TAY TXA TYA TSX TXS

" 6502 Opcodes - Stack
syntax keyword asm6502Opcode PHA PHP PLA PLP

" 6502 Opcodes - Arithmetic
syntax keyword asm6502Opcode ADC SBC

" 6502 Opcodes - Increment/Decrement
syntax keyword asm6502Opcode INC INX INY DEC DEX DEY

" 6502 Opcodes - Logical
syntax keyword asm6502Opcode AND ORA EOR

" 6502 Opcodes - Shift/Rotate
syntax keyword asm6502Opcode ASL LSR ROL ROR

" 6502 Opcodes - Compare
syntax keyword asm6502Opcode CMP CPX CPY BIT

" 6502 Opcodes - Branch
syntax keyword asm6502Opcode BCC BCS BEQ BMI BNE BPL BVC BVS

" 6502 Opcodes - Jump/Call
syntax keyword asm6502Opcode JMP JSR RTS RTI

" 6502 Opcodes - Flag
syntax keyword asm6502Opcode CLC CLD CLI CLV SEC SED SEI

" 6502 Opcodes - Other
syntax keyword asm6502Opcode BRK NOP

" Operators
syntax match asm6502Operator "[+\-<>]"

" Immediate mode marker
syntax match asm6502Immediate "#"

" Assignment operator
syntax match asm6502Assign "="

" Define highlighting groups
highlight default link asm6502Comment Comment
highlight default link asm6502String String
highlight default link asm6502Char Character
highlight default link asm6502Escape SpecialChar
highlight default link asm6502Hex Number
highlight default link asm6502Decimal Number
highlight default link asm6502Label Function
highlight default link asm6502LocalLabel Identifier
highlight default link asm6502Directive PreProc
highlight default link asm6502Opcode Statement
highlight default link asm6502Operator Operator
highlight default link asm6502Immediate Special
highlight default link asm6502Assign Operator

let b:current_syntax = "asm6502"
