#!/usr/bin/env python3
"""
Python work-alike of the v17 6502 assembler.

Usage: python3 pyasm.py <input> <output> [debug] [define:LABEL ...]

Replicates the exact behavior of the 6502 assembler including:
- Two-pass assembly
- Forward reference tracking for ZP/ABS mode selection
- Macro expansion with parameter substitution
- Conditional assembly (.ifdef/.endif)
- Expression evaluation with +, -, <<, >>
- Byte selectors < and >
- Local labels scoped by global label
- Include file support
"""

import os
import sys


# ============================================================================
# INSTRUCTION TABLE
# ============================================================================

# Addressing mode constants (matching common.asm)
MODE_NONE = 0   # Implied
MODE_IMM  = 1   # Immediate
MODE_ZP   = 2   # Zero page
MODE_ZPX  = 3   # Zero page, X
MODE_ZPY  = 4   # Zero page, Y
MODE_ABS  = 5   # Absolute
MODE_ABSX = 6   # Absolute, X
MODE_ABSY = 7   # Absolute, Y
MODE_INDX = 8   # Indirect, X
MODE_INDY = 9   # Indirect, Y
MODE_REL  = 10  # Relative
MODE_IND  = 11  # Indirect

# Operand byte counts per mode
OPERAND_BYTES = {
    MODE_NONE: 0,
    MODE_IMM: 1, MODE_ZP: 1, MODE_ZPX: 1, MODE_ZPY: 1,
    MODE_INDX: 1, MODE_INDY: 1, MODE_REL: 1,
    MODE_ABS: 2, MODE_ABSX: 2, MODE_ABSY: 2, MODE_IND: 2,
}

# ZP to ABS mode mapping
ZP_TO_ABS = {MODE_ZP: MODE_ABS, MODE_ZPX: MODE_ABSX, MODE_ZPY: MODE_ABSY}

# Full 6502 instruction table: mnemonic -> list of (mode, opcode)
INSTRUCTIONS = {
    # Load/Store
    "LDA": [(MODE_IMM, 0xA9), (MODE_ZP, 0xA5), (MODE_ZPX, 0xB5), (MODE_ABS, 0xAD),
            (MODE_ABSX, 0xBD), (MODE_ABSY, 0xB9), (MODE_INDX, 0xA1), (MODE_INDY, 0xB1)],
    "LDX": [(MODE_IMM, 0xA2), (MODE_ZP, 0xA6), (MODE_ZPY, 0xB6),
            (MODE_ABS, 0xAE), (MODE_ABSY, 0xBE)],
    "LDY": [(MODE_IMM, 0xA0), (MODE_ZP, 0xA4), (MODE_ZPX, 0xB4),
            (MODE_ABS, 0xAC), (MODE_ABSX, 0xBC)],
    "STA": [(MODE_ZP, 0x85), (MODE_ZPX, 0x95), (MODE_ABS, 0x8D), (MODE_ABSX, 0x9D),
            (MODE_ABSY, 0x99), (MODE_INDX, 0x81), (MODE_INDY, 0x91)],
    "STX": [(MODE_ZP, 0x86), (MODE_ZPY, 0x96), (MODE_ABS, 0x8E)],
    "STY": [(MODE_ZP, 0x84), (MODE_ZPX, 0x94), (MODE_ABS, 0x8C)],
    # Arithmetic
    "ADC": [(MODE_IMM, 0x69), (MODE_ZP, 0x65), (MODE_ZPX, 0x75), (MODE_ABS, 0x6D),
            (MODE_ABSX, 0x7D), (MODE_ABSY, 0x79), (MODE_INDX, 0x61), (MODE_INDY, 0x71)],
    "SBC": [(MODE_IMM, 0xE9), (MODE_ZP, 0xE5), (MODE_ZPX, 0xF5), (MODE_ABS, 0xED),
            (MODE_ABSX, 0xFD), (MODE_ABSY, 0xF9), (MODE_INDX, 0xE1), (MODE_INDY, 0xF1)],
    # Logical
    "AND": [(MODE_IMM, 0x29), (MODE_ZP, 0x25), (MODE_ZPX, 0x35), (MODE_ABS, 0x2D),
            (MODE_ABSX, 0x3D), (MODE_ABSY, 0x39), (MODE_INDX, 0x21), (MODE_INDY, 0x31)],
    "ORA": [(MODE_IMM, 0x09), (MODE_ZP, 0x05), (MODE_ZPX, 0x15), (MODE_ABS, 0x0D),
            (MODE_ABSX, 0x1D), (MODE_ABSY, 0x19), (MODE_INDX, 0x01), (MODE_INDY, 0x11)],
    "EOR": [(MODE_IMM, 0x49), (MODE_ZP, 0x45), (MODE_ZPX, 0x55), (MODE_ABS, 0x4D),
            (MODE_ABSX, 0x5D), (MODE_ABSY, 0x59), (MODE_INDX, 0x41), (MODE_INDY, 0x51)],
    # Compare
    "CMP": [(MODE_IMM, 0xC9), (MODE_ZP, 0xC5), (MODE_ZPX, 0xD5), (MODE_ABS, 0xCD),
            (MODE_ABSX, 0xDD), (MODE_ABSY, 0xD9), (MODE_INDX, 0xC1), (MODE_INDY, 0xD1)],
    "CPX": [(MODE_IMM, 0xE0), (MODE_ZP, 0xE4), (MODE_ABS, 0xEC)],
    "CPY": [(MODE_IMM, 0xC0), (MODE_ZP, 0xC4), (MODE_ABS, 0xCC)],
    # Bit test
    "BIT": [(MODE_ZP, 0x24), (MODE_ABS, 0x2C)],
    # Increment/Decrement
    "INC": [(MODE_ZP, 0xE6), (MODE_ZPX, 0xF6), (MODE_ABS, 0xEE), (MODE_ABSX, 0xFE)],
    "DEC": [(MODE_ZP, 0xC6), (MODE_ZPX, 0xD6), (MODE_ABS, 0xCE), (MODE_ABSX, 0xDE)],
    "INX": [(MODE_NONE, 0xE8)],
    "INY": [(MODE_NONE, 0xC8)],
    "DEX": [(MODE_NONE, 0xCA)],
    "DEY": [(MODE_NONE, 0x88)],
    # Shift/Rotate
    "ASL": [(MODE_NONE, 0x0A), (MODE_ZP, 0x06), (MODE_ZPX, 0x16), (MODE_ABS, 0x0E), (MODE_ABSX, 0x1E)],
    "LSR": [(MODE_NONE, 0x4A), (MODE_ZP, 0x46), (MODE_ZPX, 0x56), (MODE_ABS, 0x4E), (MODE_ABSX, 0x5E)],
    "ROL": [(MODE_NONE, 0x2A), (MODE_ZP, 0x26), (MODE_ZPX, 0x36), (MODE_ABS, 0x2E), (MODE_ABSX, 0x3E)],
    "ROR": [(MODE_NONE, 0x6A), (MODE_ZP, 0x66), (MODE_ZPX, 0x76), (MODE_ABS, 0x6E), (MODE_ABSX, 0x7E)],
    # Branch
    "BCC": [(MODE_REL, 0x90)],
    "BCS": [(MODE_REL, 0xB0)],
    "BEQ": [(MODE_REL, 0xF0)],
    "BMI": [(MODE_REL, 0x30)],
    "BNE": [(MODE_REL, 0xD0)],
    "BPL": [(MODE_REL, 0x10)],
    "BVC": [(MODE_REL, 0x50)],
    "BVS": [(MODE_REL, 0x70)],
    # Jump
    "JMP": [(MODE_ABS, 0x4C), (MODE_IND, 0x6C)],
    "JSR": [(MODE_ABS, 0x20)],
    # Stack
    "PHA": [(MODE_NONE, 0x48)],
    "PHP": [(MODE_NONE, 0x08)],
    "PLA": [(MODE_NONE, 0x68)],
    "PLP": [(MODE_NONE, 0x28)],
    # Transfer
    "TAX": [(MODE_NONE, 0xAA)],
    "TAY": [(MODE_NONE, 0xA8)],
    "TSX": [(MODE_NONE, 0xBA)],
    "TXA": [(MODE_NONE, 0x8A)],
    "TXS": [(MODE_NONE, 0x9A)],
    "TYA": [(MODE_NONE, 0x98)],
    # Flags
    "CLC": [(MODE_NONE, 0x18)],
    "CLD": [(MODE_NONE, 0xD8)],
    "CLI": [(MODE_NONE, 0x58)],
    "CLV": [(MODE_NONE, 0xB8)],
    "SEC": [(MODE_NONE, 0x38)],
    "SED": [(MODE_NONE, 0xF8)],
    "SEI": [(MODE_NONE, 0x78)],
    # Other
    "BRK": [(MODE_NONE, 0x00)],
    "NOP": [(MODE_NONE, 0xEA)],
    "RTI": [(MODE_NONE, 0x40)],
    "RTS": [(MODE_NONE, 0x60)],
}


# ============================================================================
# ERROR MESSAGES
# ============================================================================

ERROR_MESSAGES = {
    1:   "Label not found",
    2:   "Duplicate label",
    3:   "No global label for local",
    4:   "Label expected",
    5:   "Opcode not found",
    6:   "Value out of range",
    7:   "Invalid hex",
    8:   "Branch out of range",
    9:   "Invalid operand",
    10:  "Unexpected text after operand",
    11:  "Expected << or >>",
    12:  "Invalid character literal",
    13:  "Invalid addressing mode",
    14:  "Unknown directive",
    15:  "PC value expected",
    16:  "Cannot move PC backwards",
    17:  "Filename expected",
    18:  "Closing quote not found",
    19:  ".endif without .ifdef",
    20:  "Unclosed .ifdef",
    21:  "Too many .ifdef directives",
    22:  "Macro name expected",
    23:  "Macro name shadows instruction",
    24:  "Duplicate macro definition",
    25:  ".endmacro without .macro",
    26:  "Unclosed .macro",
    27:  "Nested macro definition",
    28:  "Recursive macro invocation",
    29:  "Too few macro arguments",
    30:  "Too many macro arguments",
    31:  "Macro nesting too deep",
    32:  "Out of memory",
    33:  "Token too long",
    34:  "Too many forward references",
    35:  "Zero page overflow",
    36:  "File not found",
    37:  "Comma expected",
    38:  ".asciiz not allowed in .zeropage",
    39:  "Operand not allowed on .byte/.word in .zeropage",
    240: "Usage: <assembler> <input> <output> [debug]",
    241: "Invalid argument",
}


# ============================================================================
# ASSEMBLER ERROR
# ============================================================================

class AsmError(Exception):
    """Raised when an assembly error occurs."""
    def __init__(self, code):
        self.code = code
        super().__init__(ERROR_MESSAGES.get(code, f"Unknown error {code}"))


# ============================================================================
# SOURCE STACK (file stack equivalent)
# ============================================================================

class SourceEntry:
    """A single entry in the source stack."""
    __slots__ = ('name', 'src_type', 'line_num', 'handle', 'mem_ptr', 'mem_data')

    def __init__(self, name, src_type, line_num, handle=None, mem_ptr=None, mem_data=None):
        self.name = name
        self.src_type = src_type  # 0=file, 1=memory
        self.line_num = line_num
        self.handle = handle      # file handle for file sources
        self.mem_ptr = mem_ptr    # read position for memory sources
        self.mem_data = mem_data  # memory buffer for memory sources


class SourceStack:
    """Manages the input source stack (files and macro expansions)."""

    def __init__(self):
        self.stack = []  # list of SourceEntry (saved parent state)
        self.curr_char = ''
        self.curr_file = None    # current file object
        self.curr_line = 0
        self.src_type = 0        # 0=file, 1=memory
        self.mem_ptr = 0         # position in memory source
        self.mem_data = ''       # memory source data
        self.curr_name = ''      # name of current source
        self.base_dir = ''       # base directory for resolving includes

    def push_file(self, filename):
        """Push current state and open a new file source."""
        # Resolve path relative to CWD (matching 6502 assembler behavior)
        filepath = filename

        # Try to open the file before pushing state
        try:
            fh = open(filepath, 'r')
        except (FileNotFoundError, OSError):
            raise AsmError(36)

        # Save current state
        if self.curr_name or self.curr_file is not None:
            entry = SourceEntry(
                name=self.curr_name,
                src_type=self.src_type,
                line_num=self.curr_line,
                handle=self.curr_file,
                mem_ptr=self.mem_ptr,
                mem_data=self.mem_data,
            )
            self.stack.append(entry)

        self.curr_name = filepath
        self.src_type = 0
        self.curr_file = fh
        self.curr_line = 0
        self.mem_ptr = 0
        self.mem_data = ''

    def push_memory(self, name, data, pop_hook=None):
        """Push current state and start reading from memory."""
        self.pop_hook = pop_hook
        entry = SourceEntry(
            name=self.curr_name,
            src_type=self.src_type,
            line_num=self.curr_line,
            handle=self.curr_file,
            mem_ptr=self.mem_ptr,
            mem_data=self.mem_data,
        )
        self.stack.append(entry)

        self.curr_name = name
        self.src_type = 1
        self.curr_file = None
        self.curr_line = 0
        self.mem_ptr = 0
        self.mem_data = data

    def pop(self):
        """Pop the current source and restore previous state."""
        if self.src_type == 0 and self.curr_file is not None:
            self.curr_file.close()
            self.curr_file = None

        if not self.stack:
            return False

        was_memory = (self.src_type == 1)
        entry = self.stack.pop()
        self.curr_name = entry.name
        self.src_type = entry.src_type
        self.curr_line = entry.line_num
        self.curr_file = entry.handle
        self.mem_ptr = entry.mem_ptr
        self.mem_data = entry.mem_data

        if was_memory and hasattr(self, 'pop_hook') and self.pop_hook:
            self.pop_hook()

        return True

    def read_char(self):
        """Read one character. Returns (char, eof).
        Returns (char, False) on success, ('', True) when all sources exhausted."""
        while True:
            if self.src_type == 0:
                # File source
                if self.curr_file is None:
                    return ('', True)
                ch = self.curr_file.read(1)
                if ch:
                    self.curr_char = ch
                    return (ch, False)
                # Source exhausted
            else:
                # Memory source
                if self.mem_ptr < len(self.mem_data):
                    ch = self.mem_data[self.mem_ptr]
                    self.mem_ptr += 1
                    self.curr_char = ch
                    return (ch, False)
                # Source exhausted

            if not self.pop():
                return ('', True)

    def is_empty(self):
        """Check if stack is empty (no saved entries)."""
        return len(self.stack) == 0

    def get_location(self):
        """Get current file/line for error reporting."""
        return self.curr_name, self.curr_line, self.src_type

    def get_traceback(self):
        """Get include/expansion traceback for error reporting."""
        # Build traceback from stack
        entries = []
        for entry in reversed(self.stack):
            entries.append((entry.name, entry.line_num, entry.src_type))
        return entries


# ============================================================================
# ASSEMBLER
# ============================================================================

class Assembler:
    def __init__(self, input_file, output_file, debug=False, defines=None,
                 show_macros=False):
        self.input_file = input_file
        self.output_file = output_file
        self.debug = debug
        self.show_macros = show_macros
        self.defines = defines or []

        # Symbol table: maps label key -> value (16-bit)
        # Global labels: ("global", name) -> value
        # Local labels: ("local", scope, name) -> value
        # Macro params: ("macro", expansion_id, name) -> value
        # Macro-local labels: ("macro_local", expansion_id, name) -> value
        self.symbols = {}

        # Macro table: name -> (params, body)
        # params: list of parameter names
        # body: string of captured macro body
        self.macros = {}

        # Instruction table with macros merged in during assembly
        # name -> ("instruction", modes) or ("macro", params, body)
        self.inst_table = {}
        for mnemonic, modes in INSTRUCTIONS.items():
            self.inst_table[mnemonic] = ("instruction", {m: op for m, op in modes})

        # Pass state
        self.pass_num = 0  # 0 = pass 1, 1 = pass 2
        self.pc = 0
        self.pc_save = 0
        self.in_zeropage = False
        self.started = False  # Has the first * = been seen?
        self.output = bytearray()

        # Source stack
        self.source = SourceStack()

        # Current character
        self.curr_char = ''

        # Forward reference list
        self.fwdref_list = []
        self.fwdref_ptr = 0

        # Forward reference flag for current expression
        self.is_fwdref = False

        # Label scoping
        self.label_scope = None      # Current global label key (for local labels)
        self.label_scope_type = 0    # 0=global, 1=local, 2=macro, 3=macro_local

        # Macro expansion state
        self.expansion_id = 0
        self.scope_stack = []  # list of (label_scope, expansion_id, macro_entry_name)
        self.scope_depth = 0

        # Conditional assembly
        self.cond_depth = 0
        self.skip_depth = 0
        self.ifdef_decisions = []
        self.ifdef_index = 0

        # Macro definition capture
        self.in_macro_def = False
        self.macro_def_name = ''
        self.macro_def_params = []
        self.macro_def_body = ''

        # Output file handle
        self.out_fh = None

        # Base directory for includes
        self.base_dir = os.path.dirname(os.path.abspath(input_file))

    def run(self):
        """Run the full two-pass assembly."""
        # Process define: labels
        for label in self.defines:
            self.symbols[("global", label)] = 1

        # Pass 1
        self.pass_num = 0
        self._open_input()
        self._assemble()
        self.fwdref_list.append(0xFFFF)  # Terminator

        # Pass 2
        self.pass_num = 1
        self.fwdref_ptr = 0
        self.expansion_id = 0
        self.scope_stack = []
        self.scope_depth = 0
        self._open_input()
        self._assemble()

        # Write output
        with open(self.output_file, 'wb') as f:
            f.write(self.output)

        # Debug output
        if self.debug:
            # Count forward references (excluding the terminator)
            fwdref_count = len(self.fwdref_list) - 1  # Subtract the 0xFFFF terminator
            sys.stderr.write(f"Forward references forced to absolute: {fwdref_count}\n")

    def _open_input(self):
        """Open the input file for a pass."""
        self.source = SourceStack()
        self.source.base_dir = self.base_dir
        self.source.pop_hook = None
        try:
            self.source.push_file(self.input_file)
        except AsmError:
            self._error(36)

    def _read_char(self):
        """Read one character from the source stack.
        Returns True if a character was read, False on EOF.
        Sets self.curr_char."""
        ch, eof = self.source.read_char()
        if eof:
            self.curr_char = ''
            return False
        self.curr_char = ch
        return True

    def _assemble(self):
        """Main assembly loop for one pass."""
        self.started = False
        self.in_zeropage = False
        self.pc = 0
        self.pc_save = 0
        self.label_scope = None
        self.label_scope_type = 0
        self.cond_depth = 0
        self.skip_depth = 0
        self.in_macro_def = False
        self.ifdef_index = 0
        self.output = bytearray()

        while True:
            if not self._read_char():
                # EOF
                if self.cond_depth:
                    self._error(20)
                if self.in_macro_def:
                    self._error(26)
                return

            self.source.curr_line += 1

            # Check if we're capturing macro body
            if self.in_macro_def:
                self._capture_macro_line()
                continue

            # Check if we're skipping (conditional assembly)
            if self.skip_depth:
                self._process_skipped_line()
                continue

            # Normal processing
            ch = self.curr_char
            if ch == ' ':
                # Line starts with space - skip to opcode
                if self._check_for_end_of_line():
                    continue
                # Fall through to check for opcode
            elif ch == '\n' or ch == ';':
                if ch == ';':
                    self._skip_rest_of_line()
                continue
            else:
                # Line starts with non-space - it's a label
                self._capture_label()
                if self._at_end_of_line:
                    continue

            # Check for directive or opcode
            ch = self.curr_char
            if ch == '.':
                self._read_char()
                self._process_directive()
                continue

            # Must be an opcode or macro
            self._process_opcode()

    # ==== Character Classification ====

    def _is_token_char(self, ch):
        """Check if ch is a valid token character [0-9A-Za-z_]."""
        return ch.isalnum() or ch == '_'

    # ==== Tokenizer ====

    def _skip_spaces(self):
        """Skip space characters, stopping at the first non-space."""
        while self.curr_char == ' ':
            if not self._read_char():
                return

    def _skip_rest_of_line(self):
        """Read and discard characters until newline."""
        while self.curr_char != '\n':
            if not self._read_char():
                return

    def _check_for_end_of_line(self):
        """Skip spaces, check for end of line or comment.
        Returns True if at end of line, False if more content.
        Sets self._at_end_of_line as well."""
        self._skip_spaces()
        if self.curr_char == ';':
            self._skip_rest_of_line()
            self._at_end_of_line = True
            return True
        if self.curr_char == '\n' or self.curr_char == '':
            self._at_end_of_line = True
            return True
        self._at_end_of_line = False
        return False

    def _read_token(self):
        """Read a token (word) into self.token.
        On entry curr_char is the first character of the token.
        On exit curr_char is the character after the token."""
        chars = []
        while self._is_token_char(self.curr_char):
            chars.append(self.curr_char)
            if len(chars) > 127:
                self._error(33)
            if not self._read_char():
                break
        self.token = ''.join(chars)

    def _skip_token(self):
        """Skip characters that are token characters."""
        while True:
            if not self._read_char():
                return
            if not self._is_token_char(self.curr_char):
                return

    def _read_filename(self):
        """Read a filename into self.token.
        Filename is terminated by space or newline."""
        chars = []
        while self.curr_char != ' ' and self.curr_char != '\n' and self.curr_char != '':
            chars.append(self.curr_char)
            if len(chars) > 127:
                self._error(33)
            if not self._read_char():
                break
        self.token = ''.join(chars)

    # ==== Hex Reading ====

    def _convert_hex_char(self, ch):
        """Convert a hex character to its value (0-15)."""
        if '0' <= ch <= '9':
            return ord(ch) - ord('0')
        if 'A' <= ch <= 'F':
            return ord(ch) - ord('A') + 10
        self._error(7)

    def _read_hex_byte(self):
        """Read a 2-character hex byte. curr_char has first char."""
        hi = self._convert_hex_char(self.curr_char)
        self._read_char()
        lo = self._convert_hex_char(self.curr_char)
        return (hi << 4) | lo

    def _read_hex_byte_or_word(self):
        """Read a 2 or 4 character hex value.
        On entry curr_char is first hex char (after $).
        Returns the value."""
        byte1 = self._read_hex_byte()
        self._read_char()
        if not self._is_token_char(self.curr_char):
            return byte1
        byte2 = self._read_hex_byte()
        self._read_char()
        return (byte1 << 8) | byte2

    # ==== Escape Sequences ====

    def _decode_escape(self, ch):
        """Decode an escape character. Returns (value, recognized)."""
        escapes = {'n': 0x0A, 'b': 0x08, 't': 0x09, 'r': 0x0D,
                   '\\': 0x5C, "'": 0x27, '"': 0x22}
        if ch in escapes:
            return escapes[ch], True
        return 0, False

    # ==== Decimal Reading ====

    def _from_decimal(self):
        """Read decimal number. curr_char has first digit.
        Returns value (0-65535)."""
        value = 0
        while '0' <= self.curr_char <= '9':
            value = value * 10 + (ord(self.curr_char) - ord('0'))
            if value > 65535:
                self._error(6)
            if not self._read_char():
                break
        return value

    # ==== Expression Evaluation ====

    def _parse_char_literal(self):
        """Parse character literal 'x' or escape sequence.
        On entry curr_char is the opening quote.
        Returns value."""
        self._read_char()  # skip opening quote
        if self.curr_char == "'":
            self._error(12)  # empty literal
        if self.curr_char == '\n':
            self._error(12)
        if self.curr_char == '\\':
            self._read_char()
            val, ok = self._decode_escape(self.curr_char)
            if not ok:
                self._error(12)
        else:
            val = ord(self.curr_char)
        self._read_char()  # should be closing quote
        if self.curr_char != "'":
            self._error(12)
        self._read_char()  # read past closing quote
        return val

    def _parse_term(self):
        """Parse a single term: $hex, 'char', .local, decimal, or label.
        Returns value. Sets self.is_fwdref for labels."""
        ch = self.curr_char
        if ch == '$':
            self._read_char()
            return self._read_hex_byte_or_word()
        if ch == "'":
            return self._parse_char_literal()
        if ch == '.':
            # Local label reference
            return self._parse_local_ref()
        if '0' <= ch <= '9':
            return self._from_decimal()
        # Global label
        if not self._is_token_char(ch):
            self._error(4)
        self._read_token()
        name = self.token

        # If in macro expansion, try macro-scoped lookup first (parameter shadowing)
        if self.scope_depth > 0:
            key = ("macro", self._get_current_expansion_id(), name)
            if key in self.symbols:
                self.is_fwdref = False
                return self.symbols[key]

        key = ("global", name)
        if key in self.symbols:
            self.is_fwdref = False
            return self.symbols[key]

        # Label not found
        if self.pass_num == 1:
            self._error(1)

        # Pass 1 - forward reference
        self.is_fwdref = True
        return 0

    def _parse_local_ref(self):
        """Parse a local label reference (.name).
        Returns value."""
        self._read_char()  # skip dot
        self._read_token()
        name = self.token

        if self.label_scope is None:
            self._error(3)

        # Determine local label type based on scope depth
        if self.scope_depth > 0:
            key = ("macro_local", self._get_current_expansion_id(), name)
        else:
            key = ("local", self.label_scope, name)

        if key in self.symbols:
            self.is_fwdref = False
            return self.symbols[key]

        if self.pass_num == 1:
            self._error(1)

        # Pass 1 forward reference
        self.is_fwdref = True
        return 0

    def _get_current_expansion_id(self):
        """Get the current macro expansion ID from the label scope."""
        if self.label_scope and isinstance(self.label_scope, tuple) and self.label_scope[0] == "expansion":
            return self.label_scope[1]
        return self.expansion_id

    def _parse_term_with_selector(self):
        """Parse a term with optional byte selector prefix.
        Used for shift counts."""
        ch = self.curr_char
        if ch == '<':
            self._read_char()
            self._skip_spaces()
            val = self._parse_term()
            self.is_fwdref = False
            return val & 0xFF
        if ch == '>':
            self._read_char()
            self._skip_spaces()
            val = self._parse_term()
            self.is_fwdref = False
            return (val >> 8) & 0xFF
        return self._parse_term()

    def _parse_expression(self):
        """Parse expression: term [op term]*
        Operators: +, -, <<, >>
        Left-to-right evaluation, no precedence."""
        result = self._parse_term()
        fwdref = self.is_fwdref

        while True:
            ch = self.curr_char
            # Check << and >> before skipping spaces
            if ch == '<':
                self._read_char()
                if self.curr_char != '<':
                    self._error(11)
                self._read_char()
                self._skip_spaces()
                rhs = self._parse_term_with_selector()
                fwdref = fwdref or self.is_fwdref
                if rhs >= 16:
                    result = 0
                else:
                    result = (result << rhs) & 0xFFFF
                continue
            if ch == '>':
                self._read_char()
                if self.curr_char != '>':
                    self._error(11)
                self._read_char()
                self._skip_spaces()
                rhs = self._parse_term_with_selector()
                fwdref = fwdref or self.is_fwdref
                if rhs >= 16:
                    result = 0
                else:
                    result = result >> rhs
                continue

            # Check +, - after skipping spaces
            self._skip_spaces()
            ch = self.curr_char
            if ch == '+':
                self._read_char()
                self._skip_spaces()
                rhs = self._parse_term_with_selector()
                fwdref = fwdref or self.is_fwdref
                result = (result + rhs) & 0xFFFF
            elif ch == '-':
                self._read_char()
                self._skip_spaces()
                rhs = self._parse_term_with_selector()
                fwdref = fwdref or self.is_fwdref
                result = (result - rhs) & 0xFFFF
            elif ch == '<':
                self._read_char()
                if self.curr_char != '<':
                    self._error(11)
                self._read_char()
                self._skip_spaces()
                rhs = self._parse_term_with_selector()
                fwdref = fwdref or self.is_fwdref
                if rhs >= 16:
                    result = 0
                else:
                    result = (result << rhs) & 0xFFFF
            elif ch == '>':
                self._read_char()
                if self.curr_char != '>':
                    self._error(11)
                self._read_char()
                self._skip_spaces()
                rhs = self._parse_term_with_selector()
                fwdref = fwdref or self.is_fwdref
                if rhs >= 16:
                    result = 0
                else:
                    result = result >> rhs
            else:
                break

        self.is_fwdref = fwdref
        return result

    def _parse_value(self):
        """Parse a value with optional byte selector prefix.
        Returns value. Sets self.is_fwdref."""
        ch = self.curr_char
        if ch == '<':
            self._read_char()
            self._skip_spaces()
            val = self._parse_expression()
            self.is_fwdref = False
            return val & 0xFF
        if ch == '>':
            self._read_char()
            self._skip_spaces()
            val = self._parse_expression()
            self.is_fwdref = False
            return (val >> 8) & 0xFF
        return self._parse_expression()

    # ==== Label Management ====

    def _capture_label(self):
        """Process a label at the start of a line.
        Sets self._at_end_of_line."""
        ch = self.curr_char
        if ch == '*':
            # Set PC
            self._read_char()  # skip *
            self._skip_spaces()
            if self.curr_char != '=':
                self._error(15)
            self._read_char()  # skip =
            self._skip_spaces()
            val = self._parse_value()
            if not self._check_for_end_of_line():
                self._error(10)
            self._update_pc(val)
            return

        if ch == '.':
            # Local label
            self._read_char()
            self._read_token()
            name = self.token
            if self.label_scope is None:
                self._error(3)
            if self.scope_depth > 0:
                label_type = "macro_local"
                scope = self._get_current_expansion_id()
            else:
                label_type = "local"
                scope = self.label_scope
        else:
            # Global label
            self._read_token()
            name = self.token
            label_type = "global"
            scope = None

        # Check for optional trailing colon
        if self.curr_char == ':':
            self._read_char()

        # Check for assignment
        self._skip_spaces()
        if self.curr_char == '=':
            # Value assignment
            self._read_char()
            self._skip_spaces()
            val = self._parse_value()

            if self.pass_num == 0:
                if label_type == "global":
                    key = ("global", name)
                elif label_type == "local":
                    key = ("local", scope, name)
                elif label_type == "macro_local":
                    key = ("macro_local", scope, name)
                else:
                    key = ("global", name)
                if key in self.symbols:
                    self._error(2)
                self.symbols[key] = val

            if not self._check_for_end_of_line():
                self._error(10)
            return
        else:
            # No assignment - use PC as value
            val = self.pc
            if self.pass_num == 0:
                if label_type == "global":
                    key = ("global", name)
                    if key in self.symbols:
                        self._error(2)
                    self.symbols[key] = val
                    self.label_scope = key
                elif label_type == "local":
                    key = ("local", scope, name)
                    if key in self.symbols:
                        self._error(2)
                    self.symbols[key] = val
                elif label_type == "macro_local":
                    key = ("macro_local", scope, name)
                    if key in self.symbols:
                        self._error(2)
                    self.symbols[key] = val
            else:
                # Pass 2 - update label_scope for global labels (don't store values)
                if label_type == "global":
                    key = ("global", name)
                    self.label_scope = key
                # For local/macro_local labels in pass 2, update scope but don't re-add
                # (they were already defined in pass 1)

            self._check_for_end_of_line()

    # ==== Output / PC Management ====

    def _emit(self, byte):
        """Emit a byte (pass 2 only) and increment PC."""
        byte = byte & 0xFF
        if self.in_zeropage:
            if self.pc > 0xFF:
                self._error(35)
            self.pc += 1
            return
        self.pc = (self.pc + 1) & 0xFFFF
        if self.pass_num == 1:
            self.output.append(byte)

    def _update_pc(self, new_pc):
        """Set the program counter to a new value."""
        if self.in_zeropage:
            self.pc = new_pc
            return
        if not self.started:
            self.started = True
            self.pc = new_pc
            return
        if new_pc < self.pc:
            self._error(16)
        self._advance_pc_to(new_pc)

    def _advance_pc_to(self, target):
        """Advance PC to target, zero-filling in pass 2."""
        if self.in_zeropage:
            if target > 0xFF and (target >> 8) != 0:
                self._error(35)
            self.pc = target
            return
        if self.pass_num == 1:
            while self.pc < target:
                self.output.append(0)
                self.pc += 1
        else:
            self.pc = target

    # ==== Forward Reference Tracking ====

    def _add_forward_ref(self):
        """Add current PC to forward reference list (pass 1 only)."""
        self.fwdref_list.append(self.pc)

    def _check_forward_ref(self):
        """Check if current PC is in forward reference list (pass 2).
        Returns True if found."""
        if self.fwdref_ptr < len(self.fwdref_list):
            if self.fwdref_list[self.fwdref_ptr] == self.pc:
                self.fwdref_ptr += 1
                return True
        return False

    # ==== Instruction Handling ====

    def _find_opcode(self, modes, mode):
        """Find opcode for addressing mode. Returns opcode or None."""
        return modes.get(mode)

    def _handle_fwdref_mode(self, modes, zp_mode):
        """Handle forward reference mode selection.
        Returns True if must use ABS variant."""
        # Check if ZP mode is available for this instruction
        if self._find_opcode(modes, zp_mode) is None:
            return True  # No ZP mode, must use ABS

        if self.pass_num == 0:
            # Pass 1 - check forward reference
            if self.is_fwdref:
                self._add_forward_ref()
                return True
        else:
            # Pass 2 - check the list
            if self._check_forward_ref():
                return True

        # Check if value requires absolute (>= $100)
        if self.operand > 0xFF:
            return True
        return False

    def _process_opcode(self):
        """Process an opcode (instruction or macro invocation)."""
        ch = self.curr_char
        self._read_token()
        mnemonic = self.token

        entry = self.inst_table.get(mnemonic)
        if entry is None:
            self._error(5)

        if entry[0] == "macro":
            # Macro invocation
            _, params, body = entry
            self._expand_macro(mnemonic, params, body)
            return

        # Instruction
        _, modes = entry
        self._parse_operand(modes)
        self._emit_instruction(modes)

        # Check for garbage after instruction
        if not self._check_for_end_of_line():
            self._error(10)

    def _parse_operand(self, modes):
        """Parse instruction operand and determine addressing mode.
        Sets self.addr_mode and self.operand."""
        if self._check_for_end_of_line():
            # Implied mode
            self.addr_mode = MODE_NONE
            self.operand = 0
            return

        ch = self.curr_char
        if ch == '#':
            # Immediate mode
            self._read_char()
            self.operand = self._parse_value()
            self.addr_mode = MODE_IMM
            return

        if ch == '(':
            # Indirect modes
            self._read_char()
            self.operand = self._parse_value()
            ch = self.curr_char
            if ch == ',':
                # ($xx,X)
                self._read_char()
                if self.curr_char != 'X':
                    self._error(13)
                self._read_char()
                if self.curr_char != ')':
                    self._error(13)
                self._read_char()
                self.addr_mode = MODE_INDX
                return
            if ch != ')':
                self._error(9)
            self._read_char()
            if self.curr_char == ',':
                # ($xx),Y
                self._read_char()
                if self.curr_char != 'Y':
                    self._error(13)
                self._read_char()
                self.addr_mode = MODE_INDY
                return
            # ($xxxx) - indirect
            self.addr_mode = MODE_IND
            return

        # Direct operand: value, value,X, or value,Y
        self.operand = self._parse_value()

        # Check if this is a branch instruction
        if self._find_opcode(modes, MODE_REL) is not None:
            self.addr_mode = MODE_REL
            return

        # Check for indexed mode
        if self.curr_char == ',':
            self._read_char()
            if self.curr_char == 'X':
                self._read_char()
                zp_mode = MODE_ZPX
                abs_mode = MODE_ABSX
            elif self.curr_char == 'Y':
                self._read_char()
                zp_mode = MODE_ZPY
                abs_mode = MODE_ABSY
            else:
                self._error(13)

            if self._handle_fwdref_mode(modes, zp_mode):
                self.addr_mode = abs_mode
            else:
                self.addr_mode = zp_mode
            return

        # Non-indexed: ZP or ABS
        if self._handle_fwdref_mode(modes, MODE_ZP):
            self.addr_mode = MODE_ABS
        else:
            self.addr_mode = MODE_ZP

    def _emit_instruction(self, modes):
        """Emit instruction bytes based on addressing mode."""
        opcode = self._find_opcode(modes, self.addr_mode)
        if opcode is None:
            self._error(13)

        self._emit(opcode)

        if self.addr_mode == MODE_NONE:
            return

        if self.addr_mode == MODE_REL:
            # Relative branch
            if self.pass_num == 1:
                # Calculate offset: target - PC - 1
                # PC is now pointing at the offset byte (opcode already emitted)
                offset = self.operand - self.pc - 1
                # Convert to signed byte
                if offset < -128 or offset > 127:
                    self._error(8)
                self._emit(offset & 0xFF)
            else:
                self._emit(self.operand & 0xFF)
            return

        nbytes = OPERAND_BYTES[self.addr_mode]
        if nbytes == 1:
            if self.pass_num == 1 and self.operand > 0xFF:
                self._error(6)
            self._emit(self.operand & 0xFF)
        elif nbytes == 2:
            self._emit(self.operand & 0xFF)
            self._emit((self.operand >> 8) & 0xFF)

    # ==== Directive Handling ====

    def _process_directive(self):
        """Process a directive. curr_char is first char of directive name."""
        self._read_token()
        directive = self.token

        if directive == "include":
            self._directive_include()
        elif directive == "zeropage":
            self._directive_zeropage()
        elif directive == "code":
            self._directive_code()
        elif directive == "byte":
            self._directive_byte()
        elif directive == "word":
            self._directive_word()
        elif directive == "asciiz":
            self._directive_asciiz()
        elif directive == "reserve":
            self._directive_reserve()
        elif directive == "ifdef":
            self._process_ifdef()
        elif directive == "endif":
            self._process_endif()
        elif directive == "macro":
            self._process_macro()
        elif directive == "endmacro":
            self._error(25)  # .endmacro without .macro
        else:
            self._error(14)

    def _directive_include(self):
        """Process .include directive."""
        if self._check_for_end_of_line():
            self._error(17)
        self._read_filename()
        self._skip_rest_of_line()
        try:
            self.source.push_file(self.token)
        except AsmError:
            self._error(36)

    def _directive_zeropage(self):
        """Process .zeropage directive."""
        if not self.in_zeropage:
            self.in_zeropage = True
            self.pc, self.pc_save = self.pc_save, self.pc
        self._skip_rest_of_line()

    def _directive_code(self):
        """Process .code directive."""
        if self.in_zeropage:
            self.in_zeropage = False
            self.pc, self.pc_save = self.pc_save, self.pc
        self._skip_rest_of_line()

    def _directive_byte(self):
        """Process .byte directive."""
        if self.in_zeropage:
            if not self._check_for_end_of_line():
                self._error(39)
            self._emit(0)
            return
        self._data_parameters(1)

    def _directive_word(self):
        """Process .word directive."""
        if self.in_zeropage:
            if not self._check_for_end_of_line():
                self._error(39)
            self._emit(0)
            self._emit(0)
            return
        self._data_parameters(2)

    def _directive_asciiz(self):
        """Process .asciiz directive."""
        if self.in_zeropage:
            self._error(38)
        self._data_parameters(3)

    def _directive_reserve(self):
        """Process .reserve directive."""
        self._skip_spaces()
        val = self._parse_value()
        target = self.pc + val
        self._advance_pc_to(target)
        self._skip_rest_of_line()

    def _data_parameters(self, mode):
        """Process data parameters for .byte, .word, .asciiz.
        mode: 1=byte, 2=word, 3=asciiz"""
        while True:
            if self._check_for_end_of_line():
                break

            if self.curr_char == '"':
                # Quoted string
                self._read_char()
                self._emit_quoted()
                # Check for more data
                if self._check_for_end_of_line():
                    break
                if self.curr_char != ',':
                    self._error(37)
                self._read_char()
                continue

            # Expression value
            val = self._parse_value()
            if mode == 2:
                # .word: emit 2 bytes
                self._emit(val & 0xFF)
                self._emit((val >> 8) & 0xFF)
            else:
                # .byte or .asciiz: emit 1 byte
                if self.pass_num == 1 and (val > 0xFF and val < 0xFF00):
                    self._error(6)
                self._emit(val & 0xFF)

            if self._check_for_end_of_line():
                break
            if self.curr_char != ',':
                self._error(37)
            self._read_char()

        # Null terminator for .asciiz
        if mode == 3:
            self._emit(0)

    def _emit_quoted(self):
        """Emit a quoted string. curr_char is first char inside quotes."""
        while True:
            ch = self.curr_char
            if ch == '\n':
                self._error(18)
            if ch == '"':
                self._read_char()
                return
            if ch == '\\':
                self._read_char()
                if self.curr_char == '\n':
                    self._error(18)
                val, ok = self._decode_escape(self.curr_char)
                if ok:
                    self._emit(val)
                else:
                    self._emit(ord(self.curr_char))
            else:
                self._emit(ord(ch))
            self._read_char()

    # ==== Conditional Assembly ====

    def _process_ifdef(self):
        """Process .ifdef directive."""
        self.cond_depth += 1

        if self.skip_depth:
            # Already skipping
            self._skip_rest_of_line()
            return

        if self._check_for_end_of_line():
            self._error(4)

        self._read_token()
        name = self.token

        if self.pass_num == 0:
            # Pass 1: evaluate and store decision
            # Match 6502: INC wraps 255→0, overflow on 256th ifdef (index 255)
            if self.ifdef_index >= 255:
                self._error(21)
            defined = ("global", name) in self.symbols
            self.ifdef_decisions.append(defined)
            self.ifdef_index += 1
        else:
            # Pass 2: replay stored decision
            defined = self.ifdef_decisions[self.ifdef_index]
            self.ifdef_index += 1

        if not defined:
            self.skip_depth = self.cond_depth

        self._skip_rest_of_line()

    def _process_endif(self):
        """Process .endif directive."""
        if self.cond_depth == 0:
            self._error(19)

        self.cond_depth -= 1

        if self.skip_depth:
            if self.cond_depth < self.skip_depth:
                self.skip_depth = 0

        self._skip_rest_of_line()

    def _process_skipped_line(self):
        """Process a line while in skip mode (conditional assembly)."""
        ch = self.curr_char
        if ch == ' ':
            if self._check_for_end_of_line():
                return
        elif ch == '\n' or ch == ';':
            if ch == ';':
                self._skip_rest_of_line()
            return
        else:
            if ch == '\n' or ch == ';':
                if ch == ';':
                    self._skip_rest_of_line()
                return
            # Skip label
            self._skip_token()
            if self._check_for_end_of_line():
                return

        # Check for directive
        if self.curr_char != '.':
            self._skip_rest_of_line()
            return

        self._read_char()
        self._read_token()

        # Only process ifdef/endif
        if self.token == "ifdef":
            self._process_ifdef()
        elif self.token == "endif":
            self._process_endif()
        else:
            self._skip_rest_of_line()

    # ==== Macro System ====

    def _process_macro(self):
        """Process .macro directive."""
        if self._check_for_end_of_line():
            self._error(22)

        self._read_token()
        macro_name = self.token

        # Check for instruction collision
        if macro_name in INSTRUCTIONS:
            self._error(23)

        if self.pass_num == 1:
            # Pass 2: just set flag to skip body capture
            if macro_name in self.macros:
                self.in_macro_def = True
                self.macro_def_name = macro_name
                self._skip_rest_of_line()
                return
            self._error(24)  # Should not happen in pass 2

        # Check for duplicate macro
        if macro_name in self.macros:
            self._error(24)

        # Read parameters
        params = []
        while True:
            if self._check_for_end_of_line():
                break
            self._read_token()
            params.append(self.token)
            if self._check_for_end_of_line():
                break
            if self.curr_char != ',':
                self._error(37)
            self._read_char()

        self.in_macro_def = True
        self.macro_def_name = macro_name
        self.macro_def_params = params
        self.macro_def_body = ''

    def _capture_macro_line(self):
        """Capture a line during macro definition."""
        if self.pass_num == 1:
            # Pass 2: just scan for .endmacro
            self._p2_scan_for_endmacro()
            return

        # Pass 1: capture with compression
        line = self._capture_compressed_line()

        # Check if the line is .endmacro or .macro
        stripped = line.lstrip(' ')
        if stripped.startswith('.'):
            rest = stripped[1:]
            # Check for .endmacro
            if self._match_directive(rest, "endmacro"):
                # End of macro definition
                self.in_macro_def = False
                body = self.macro_def_body
                self.macros[self.macro_def_name] = (self.macro_def_params, body)
                # Register in instruction table
                self.inst_table[self.macro_def_name] = ("macro", self.macro_def_params, body)
                # Show captured macro if requested
                if self.show_macros:
                    params_str = ', '.join(self.macro_def_params)
                    if params_str:
                        sys.stderr.write(f"Macro: {self.macro_def_name} {params_str}\n")
                    else:
                        sys.stderr.write(f"Macro: {self.macro_def_name}\n")
                    sys.stderr.write(body)
                self._skip_rest_of_line()
                return
            if self._match_directive(rest, "macro"):
                self._error(27)

        # Keep the line in the macro body
        self.macro_def_body += line + '\n'

    def _match_directive(self, text, directive):
        """Check if text starts with directive name followed by non-token char."""
        if not text.startswith(directive):
            return False
        if len(text) == len(directive):
            return True
        return not self._is_token_char(text[len(directive)])

    def _capture_compressed_line(self):
        """Capture current line with comment stripping and space compression."""
        result = []
        last_space = False
        in_string = False
        in_char = False

        ch = self.curr_char
        while ch != '\n' and ch != '':
            if in_string:
                result.append(ch)
                if ch == '\\':
                    if not self._read_char():
                        self._error(26)
                    result.append(self.curr_char)
                elif ch == '"':
                    in_string = False
                if not self._read_char():
                    self._error(26)
                ch = self.curr_char
                continue

            if in_char:
                result.append(ch)
                if ch == '\\':
                    if not self._read_char():
                        self._error(26)
                    result.append(self.curr_char)
                    if not self._read_char():
                        self._error(26)
                    ch = self.curr_char
                    # Should be closing quote
                    if ch != "'":
                        self._error(12)
                    result.append(ch)
                    in_char = False
                    if not self._read_char():
                        self._error(26)
                    ch = self.curr_char
                    continue
                else:
                    # Regular char - next should be closing quote
                    if not self._read_char():
                        self._error(26)
                    ch = self.curr_char
                    if ch != "'":
                        self._error(12)
                    result.append(ch)
                    in_char = False
                    if not self._read_char():
                        self._error(26)
                    ch = self.curr_char
                    continue

            if ch == ';':
                # Comment - skip rest of line
                while ch != '\n' and ch != '':
                    if not self._read_char():
                        self._error(26)
                    ch = self.curr_char
                break
            elif ch == '"':
                in_string = True
                last_space = False
                result.append(ch)
            elif ch == "'":
                in_char = True
                last_space = False
                result.append(ch)
            elif ch == ' ':
                if not last_space:
                    last_space = True
                    result.append(ch)
                # Skip consecutive spaces
            else:
                last_space = False
                result.append(ch)

            if not self._read_char():
                self._error(26)
            ch = self.curr_char

        return ''.join(result)

    def _p2_scan_for_endmacro(self):
        """In pass 2, scan for .endmacro without capturing."""
        ch = self.curr_char
        # Skip leading spaces
        while ch == ' ':
            if not self._read_char():
                self._error(26)
            ch = self.curr_char

        if ch == '\n':
            return

        if ch != '.':
            self._skip_rest_of_line()
            return

        self._read_char()
        self._read_token()
        if self.token == "endmacro":
            self.in_macro_def = False
        self._skip_rest_of_line()

    def _expand_macro(self, name, params, body):
        """Expand a macro invocation."""
        # Check for recursion
        for saved_scope, saved_exp_id, saved_name in self.scope_stack:
            if saved_name == name:
                self._error(28)

        # Parse arguments using parent scope
        # Match 6502 buffer limit: 256 bytes / 3 bytes per arg = 85 max
        MAX_MACRO_ARGS = 85
        arg_values = []
        arg_fwdrefs = []
        param_idx = 0
        for i, param in enumerate(params):
            if i >= MAX_MACRO_ARGS:
                self._error(30)
            if self._check_for_end_of_line():
                self._error(29)
            val = self._parse_expression()
            arg_values.append(val)
            arg_fwdrefs.append(self.is_fwdref)
            param_idx += 1

            if i < len(params) - 1:
                # More params expected
                if self._check_for_end_of_line():
                    self._error(29)
                if self.curr_char != ',':
                    self._error(37)
                self._read_char()

        # Check no extra arguments
        if not self._check_for_end_of_line():
            self._error(30)

        # Check scope depth limit
        if self.scope_depth >= 51:  # ~256/5 entries
            self._error(31)

        # Push label scope
        self.scope_stack.append((self.label_scope, self.expansion_id, name))
        self.scope_depth += 1
        self.expansion_id += 1
        exp_id = self.expansion_id
        self.label_scope = ("expansion", exp_id)

        # Add parameters to symbol table
        for i, param in enumerate(params):
            if arg_fwdrefs[i] and self.pass_num == 0:
                continue  # Skip forward refs in pass 1
            key = ("macro", exp_id, param)
            self.symbols[key] = arg_values[i]

        # Push memory source for macro body
        self.source.push_memory(name, body, pop_hook=self._pop_label_scope)

    def _pop_label_scope(self):
        """Pop label scope when macro expansion ends."""
        if self.scope_stack:
            saved_scope, saved_exp_id, saved_name = self.scope_stack.pop()
            self.label_scope = saved_scope
            self.scope_depth -= 1

    # ==== Error Handling ====

    def _error(self, code):
        """Raise an assembly error with location info."""
        msg = ERROR_MESSAGES.get(code, f"Unknown error {code}")
        name, line, src_type = self.source.get_location()

        # Format error message
        parts = [f"Error {code}"]
        if name:
            if src_type == 1:
                parts.append(f" in macro {name}")
            else:
                parts.append(f" in file {name}")
            parts.append(f" at line {line}")
        parts.append(f": {msg}")

        # Add traceback
        traceback_entries = self.source.get_traceback()
        traceback_lines = []
        prev_src_type = src_type
        for t_name, t_line, t_src_type in traceback_entries:
            if not t_name:
                continue
            if prev_src_type == 1:
                verb = "expanded from"
            else:
                verb = "included from"
            prefix = ""
            if t_src_type == 1:
                prefix = "macro "
            traceback_lines.append(f"  {verb} {prefix}{t_name}:{t_line}")
            prev_src_type = t_src_type

        error_text = ''.join(parts)
        if traceback_lines:
            error_text += '\n' + '\n'.join(traceback_lines)
        error_text += '\n'

        # Write to stderr and exit
        sys.stderr.write(error_text)

        # Close output file if open
        if self.out_fh:
            self.out_fh.close()
            self.out_fh = None

        sys.exit(code)


# ============================================================================
# MAIN
# ============================================================================

def main():
    if len(sys.argv) < 3:
        sys.stderr.write(f"Error 240: {ERROR_MESSAGES[240]}\n")
        sys.exit(240)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    debug = False
    show_macros = False
    defines = []

    for arg in sys.argv[3:]:
        if arg == "debug":
            debug = True
        elif arg.startswith("define:"):
            defines.append(arg[7:])
        elif arg == "small_heap":
            pass  # Not applicable to Python
        elif arg == "show_captured_macros":
            show_macros = True
        else:
            sys.stderr.write(f"Error 241: {ERROR_MESSAGES[241]}\n")
            sys.exit(241)

    asm = Assembler(input_file, output_file, debug=debug, defines=defines,
                    show_macros=show_macros)
    asm.run()


if __name__ == "__main__":
    main()
