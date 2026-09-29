# 6502 Assembly Syntax Highlighting (asm17)

VS Code syntax highlighting for the asm17 6502 assembler dialect.

## Features

- All 56 standard 6502 mnemonics (case-insensitive)
- Directives: `.byte`, `.word`, `.asciiz`, `.include`, `.reserve`, `.macro`, `.endmacro`, `.zeropage`, `.code`, `.ifdef`, `.ifndef`, `.else`, `.endif`
- Global and local label definitions
- Hex (`$FF`) and decimal number literals
- Character (`'A'`) and string (`"text"`) literals with escape sequences
- Expression operators (`+`, `-`, `<<`, `>>`) and byte selectors (`<`, `>`)
- `;` line comments
- Comment toggling via `Ctrl+/`

## Installation

Create a symlink from your VS Code extensions directory:

```bash
ln -s /path/to/toolchain/asm2/vscode-asm6502 ~/.vscode/extensions/asm6502
```

Then reload VS Code. All `.asm` files will use the `6502 Assembly` language mode.
