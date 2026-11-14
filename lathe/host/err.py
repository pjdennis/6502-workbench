"""Error numbers and reporting (part of the kernel).

Owns the list of error numbers with their texts, and the place in the source an error is
reported at. The compiler stops at the first error: fatal() writes
`FILE:LINE:COL: error N: text` to the error output and ends the program with status 1.
It never returns and nothing catches it.

MESSAGES has one line per error, `number text`, so the texts can move to a file of their own
when the compiler has to be smaller (docs/architecture.md, "Errors and debugging").

The numbers are grouped by what the error is about:

      1 to 19   characters and tokens
     20 to 39   syntax (39 is "not implemented yet")
     40 to 59   meaning: names, types, values, statements and functions
     60 to 69   the command line and files
     70 to 98   a capacity of the compiler that was exceeded
     99         a fault in the compiler itself
    100 to 139  meaning, continued: further errors about meaning go here
    140 to 159  `asm` blocks and `asm` functions

A number is never reused for another error; a new one takes the next free number of its group.
"""
import env

# Characters and tokens
E_BAD_CHAR = 1
E_BAD_NUMBER = 2
E_NUMBER_RANGE = 3
E_BAD_CHAR_CONST = 4
E_OPEN_STRING = 5
E_BAD_ESCAPE = 6
E_STRING_LONG = 7

# Syntax
E_SYNTAX = 20
E_NAME_EXPECTED = 21
E_NL_EXPECTED = 22
E_LPAREN_EXPECTED = 23
E_RPAREN_EXPECTED = 24
E_COLON_EXPECTED = 25
E_MODULE_EXPECTED = 26
E_FUNC_EXPECTED = 27
E_IN_EXPECTED = 28
E_AT_EXPECTED = 29
E_END_EXPECTED = 30
E_REGISTER_EXPECTED = 31
E_TYPE_EXPECTED = 32
E_DECL_EXPECTED = 33
E_STMT_EXPECTED = 34
E_EXPR_EXPECTED = 35
E_DOT_EXPECTED = 36
E_THEN_EXPECTED = 37
E_DO_EXPECTED = 38
E_UNSUPPORTED = 39

# Meaning
E_UNDEFINED = 40
E_DUPLICATE = 41
E_ARG_COUNT = 42
E_RANGE = 43
E_TYPE = 44
E_NOT_FUNC = 45
E_NOT_CONST = 46
E_REG_TYPE = 47
E_REG_USED = 48
E_MODULE_NAME = 49
E_NO_INTERFACE = 50
E_BAD_INTERFACE = 51
E_SELF_IMPORT = 52
E_NOT_VAR = 53
E_NEEDS_RT = 54
E_NO_LOOP = 55
E_RESULTS = 56
E_FORWARD = 57
E_NO_BODY = 58
E_DIV_ZERO = 59

# The command line and files
E_USAGE = 60
E_SOURCE_NAME = 61
E_OPEN_SOURCE = 62
E_CREATE = 63

# Capacities
E_NAMES_FULL = 70
E_SYMS_FULL = 71
E_MEMBERS_FULL = 72
E_MODULES_FULL = 73
E_TYPES_FULL = 74
E_FUNC_BIG = 75
E_LABELS_FULL = 76
E_FIXUPS_FULL = 77
E_CALLS_FULL = 78
E_OPERANDS_FULL = 79
E_STREAMS_FULL = 80
E_SOURCES_FULL = 81
E_TEXT_FULL = 82
E_PATH_LONG = 83
E_DIRS_FULL = 84
E_SLOTS_FULL = 85
E_INITS_FULL = 86
E_DATA_FULL = 87
E_INTERNAL = 99

# Meaning, continued (40 to 59 are full)
E_CALL_IN_ARGUMENTS = 100
E_TO_EXPECTED = 110
E_CASE_SELECTOR = 111
E_CASE_TWICE = 112
E_STATUS_IN_CRITICAL = 113
E_DIRECTIVE = 114
E_NO_IF = 115
E_IF_OPEN = 116
E_IF_DEEP = 117

# Arrays, strings and pointers
E_BYTE_INDEX = 120
E_ARRAY_VALUE = 121
E_NO_ADDRESS = 122
E_NEEDS_ROWS = 123
E_ELEMENT_SIZE = 124
E_TWO_INDEXES = 125
E_TOO_MANY = 126
E_NOT_INDEXED = 127

# asm blocks and asm functions
E_ASM_BRANCH = 140
E_ASM_LABEL_USE = 141
E_ASM_NO_LABEL = 142
E_ASM_RANGE = 143
E_ASM_MODE = 144
E_ASM_DIRECTIVE = 145
E_ASM_MNEMONIC = 146
E_ASM_NOT_ZP = 147

MESSAGES = (
    b"1 character not allowed here\n"
    b"2 digits expected\n"
    b"3 number above 65535\n"
    b"4 character constant not closed\n"
    b"5 string not closed\n"
    b"6 unknown escape\n"
    b"7 string too long\n"
    b"20 syntax error\n"
    b"21 name expected\n"
    b"22 end of line expected\n"
    b"23 \"(\" expected\n"
    b"24 \")\" expected\n"
    b"25 \":\" expected\n"
    b"26 \"module\" expected\n"
    b"27 \"func\" expected\n"
    b"28 \"in\" expected\n"
    b"29 \"at\" expected\n"
    b"30 \"end\" expected\n"
    b"31 register expected: a x y ax ay xy c\n"
    b"32 type expected\n"
    b"33 declaration expected\n"
    b"34 statement expected\n"
    b"35 expression expected\n"
    b"36 \".\" expected\n"
    b"37 \"then\" expected\n"
    b"38 \"do\" expected\n"
    b"39 not implemented yet\n"
    b"40 undefined name\n"
    b"41 name already declared\n"
    b"42 wrong number of arguments\n"
    b"43 value out of range\n"
    b"44 wrong type\n"
    b"45 not a function\n"
    b"46 constant expected\n"
    b"47 register does not suit the type\n"
    b"48 register used twice\n"
    b"49 module name differs from the file name\n"
    b"50 no interface file for this module\n"
    b"51 not an interface file of this version\n"
    b"52 a module cannot import itself\n"
    b"53 not a variable that can be assigned to\n"
    b"54 needs the run-time library, not available yet\n"
    b"55 not inside a loop\n"
    b"56 wrong number of results\n"
    b"57 differs from the forward declaration\n"
    b"58 function declared forward has no body\n"
    b"59 division by zero\n"
    b"60 usage: lathec [-c6502|-c65c02] [-dNAME[=NUMBER]]... SOURCE.lth OUTDIR [IMPORTDIR...]\n"
    b"61 source file must be called NAME.lth\n"
    b"62 cannot open the source file\n"
    b"63 cannot create the output file\n"
    b"70 too many names\n"
    b"71 too many symbols\n"
    b"72 too many parameters\n"
    b"73 too many imports\n"
    b"74 too many types\n"
    b"75 function too large\n"
    b"76 too many labels in one function\n"
    b"77 too many references in one function\n"
    b"78 too many calls in one function\n"
    b"79 expression too complex\n"
    b"80 too many open files\n"
    b"81 sources nested too deeply\n"
    b"82 arguments too long\n"
    b"83 file name too long\n"
    b"84 too many directories\n"
    b"85 too many variables in one function\n"
    b"86 too many initial values\n"
    b"87 too much constant data in one table\n"
    b"99 compiler error\n"
    b"100 a call of this function inside its own arguments: use a variable\n"
    b"110 \"to\" or \"downto\" expected\n"
    b"111 a case selector must be a byte, sbyte or bool\n"
    b"112 constant already used in this case\n"
    b"113 a status cannot be returned from inside critical: return after its end\n"
    b"114 #if, #else or #end expected at the start of a line\n"
    b"115 #else or #end without its #if\n"
    b"116 #if without #end\n"
    b"117 #if nested too deeply\n"
    b"120 an array of at most 256 elements, and a pointer, take a byte index\n"
    b"121 an array is not a value: use a pointer to it, or copy it with a loop\n"
    b"122 has no address: not a variable, or an element of an array stored by column\n"
    b"123 an array of more than 256 elements larger than a byte must be declared rows\n"
    b"124 element size must be a power of two here (1, 2, 4 or 8 through a pointer)\n"
    b"125 only one index can be a variable, and only the first unless the array is declared rows\n"
    b"126 more values than the array has elements\n"
    b"127 not an array or a pointer\n"
    b"140 a branch must go to a label of this asm block\n"
    b"141 a label of an asm block can only be the target of a branch or JMP\n"
    b"142 label not defined in this asm block\n"
    b"143 operand out of range\n"
    b"144 addressing mode not available for this instruction\n"
    b"145 directives such as .byte are not allowed in asm\n"
    b"146 unknown instruction\n"
    b"147 cannot be made to be in zero page: declared nozp, or another module's and not zp\n"
)
TOOL = b"lathec"
ERROR = b": error "

C_LF = 0x0A
C_SPACE = 0x20
C_ZERO = 0x30
C_COLON = 0x3A

MAX_DIGITS = 5
digits = bytearray(MAX_DIGITS)

file = 0        # pointer to the name of the file being read; 0 before there is one
line = 0        # where the error is: the token or character being looked at; 0 for nowhere
col = 0


def init():
    set_file(0)


def set_file(name):
    """Name the file errors are in from now on. `name` points to its zero-terminated name."""
    global file
    file = name
    position(0, 0)


def position(new_line, new_col):
    """Say where an error found from now on is."""
    global line, col
    line = new_line
    col = new_col


def put_decimal(n):
    count = 0
    while True:
        digits[count] = C_ZERO + n % 10
        count += 1
        n = n // 10
        if n == 0:
            break
    for i in range(count - 1, -1, -1):
        env.put_error(digits[i])


def put_place():
    if file == 0:
        for i in range(0, len(TOOL)):
            env.put_error(TOOL[i])
        return
    i = file
    while env.mem[i] != 0:
        env.put_error(env.mem[i])
        i += 1
    if line != 0:
        env.put_error(C_COLON)
        put_decimal(line)
        env.put_error(C_COLON)
        put_decimal(col)


def message_start(number):
    """Index in MESSAGES of the text of error `number`, or len(MESSAGES) if it has none."""
    i = 0
    while i < len(MESSAGES):
        n = 0
        while MESSAGES[i] != C_SPACE:
            n = n * 10 + MESSAGES[i] - C_ZERO
            i += 1
        i += 1
        if n == number:
            return i
        while MESSAGES[i] != C_LF:
            i += 1
        i += 1
    return i


def fatal(number):
    """Report error `number` at the current place and end the program."""
    put_place()
    for i in range(0, len(ERROR)):
        env.put_error(ERROR[i])
    put_decimal(number)
    env.put_error(C_COLON)
    env.put_error(C_SPACE)
    i = message_start(number)
    while i < len(MESSAGES) and MESSAGES[i] != C_LF:
        env.put_error(MESSAGES[i])
        i += 1
    env.put_error(C_LF)
    env.exit(1)
