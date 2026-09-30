" Vim syntax file
" Language: 6502 Assembler Test Format
" Maintainer: Your Name
" Latest Revision: 2026-01-13

if exists("b:current_syntax")
  finish
endif

" Test case separator
syn match asmtestSeparator /^---$/

" Comments
syn match asmtestComment /^#.*$/

" Section headers (comment lines with ===)
syn match asmtestSection /^#.*=\{3,}.*$/

" Keywords (field names)
syn match asmtestKeyword /^NAME:/
syn match asmtestKeyword /^DESCRIPTION:/
syn match asmtestKeyword /^INPUT:/
syn match asmtestKeyword /^EXPECT_HEX:/
syn match asmtestKeyword /^EXPECT_FWDREF:/
syn match asmtestKeyword /^EXPECT_ERROR:/
syn match asmtestKeyword /^EXPECT_LINE:/
syn match asmtestKeyword /^EXPECT_MSG:/
syn match asmtestKeyword /^EXPECT_STDERR:/
syn match asmtestKeyword /^FILE [^:]*:/
syn match asmtestKeyword /^MODE:/
syn match asmtestKeyword /^EXPECT_STDOUT:/

" Line number prefix in INPUT section
syn match asmtestLineNum /^\d\+:/

" Test name value (after NAME:)
syn match asmtestName /^NAME:\s*\zs.*$/

" Hex values in EXPECT_HEX
syn match asmtestHex /\<[0-9a-fA-F]\{2}\>/

" 6502 assembly within INPUT lines (after line number prefix)
" Instructions
syn match asm6502Inst /\<\(ADC\|AND\|ASL\|BCC\|BCS\|BEQ\|BIT\|BMI\|BNE\|BPL\|BRK\|BVC\|BVS\|CLC\|CLD\|CLI\|CLV\|CMP\|CPX\|CPY\|DEC\|DEX\|DEY\|EOR\|INC\|INX\|INY\|JMP\|JSR\|LDA\|LDX\|LDY\|LSR\|NOP\|ORA\|PHA\|PHP\|PLA\|PLP\|ROL\|ROR\|RTI\|RTS\|SBC\|SEC\|SED\|SEI\|STA\|STX\|STY\|TAX\|TAY\|TSX\|TXA\|TXS\|TYA\)\>/

" Assembler directives
syn match asm6502Dir /\.\(data\|code\|include\|macro\|endmacro\|ifdef\|ifndef\|else\|endif\|zeropage\)\>/

" Hex numbers
syn match asm6502Hex /\$[0-9a-fA-F]\+/

" Character literals
syn match asm6502Char /'[^']*'/
syn match asm6502Char /'\\[\\n']'/

" Labels (identifiers followed by optional colon or equals)
syn match asm6502Label /^\d\+:\s*\zs[a-zA-Z_][a-zA-Z0-9_]*/

" Local labels (starting with .)
syn match asm6502Local /\.[a-zA-Z_][a-zA-Z0-9_]*/

" Comments in assembly (after semicolon)
syn match asm6502Comment /;.*$/

" Program counter
syn match asm6502PC /\*/

" Define highlighting
hi def link asmtestSeparator Special
hi def link asmtestComment Comment
hi def link asmtestSection Title
hi def link asmtestKeyword Structure
hi def link asmtestLineNum LineNr
hi def link asmtestName Identifier
hi def link asmtestHex Number

hi def link asm6502Inst Statement
hi def link asm6502Dir Keyword
hi def link asm6502Hex Number
hi def link asm6502Char String
hi def link asm6502Label Function
hi def link asm6502Local Identifier
hi def link asm6502Comment Comment
hi def link asm6502PC Special

let b:current_syntax = "asmtest"
