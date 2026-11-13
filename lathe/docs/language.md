# Lathe: proposed language

Status (2026-11-13): proposal. Nothing here is implemented. Syntax is the cheapest thing to change, so treat every spelling as a first offer. The reasons behind the rules are in [`code-model.md`](code-model.md).

## A first look

```
; count the bytes of a zero-terminated string that are spaces
module demo

import host

const SPACE = ' '

func spaces(s: ^byte): byte
  var n: byte
  var i: byte
  n = 0
  i = 0
  while s[i] != 0 do
    if s[i] == SPACE then
      n += 1
    end
    i += 1
  end
  return n
end

pub func main()
  host.put_byte('0' + spaces("A B C"))
end
```

## Design rules

- **Every construct has an obvious 6502 translation.** If a feature needs a hidden multiply, a hidden copy or a hidden call, it is either left out or spelled so the cost shows.
- **Declare before use.** The compiler makes one pass, so a name must be declared above its first use. `forward` exists for functions that call each other.
- **The grammar is LL(1).** One token of lookahead decides every choice, with no backtracking.
- **A program is a set of modules** compiled one at a time.

## Lexical rules

- **Character set.** Source is 7-bit ASCII. Lower-case letters are folded to upper case outside string and character literals, so keywords and names are not case sensitive. Only `|` and `~` fall outside the range `$20`–`$5F` (see the open questions in [`goals.md`](goals.md)).
- **Comments** run from `;` to the end of the line.
- **Names** start with a letter and continue with letters, digits and `_`. The first 31 characters are significant.
- **Numbers.** Decimal `123`, hexadecimal `$7F`, binary `%1010`, character `'A'`. A number literal has no type of its own; it takes the type its context needs, and it is an error if it does not fit.
- **Strings.** `"TEXT"` is a zero-terminated sequence of bytes. Escapes: `\n`, `\r`, `\t`, `\0`, `\\`, `\"`, `\'`, `\xHH`.
- **Statements end at the end of the line.** A line continues onto the next when it ends with a binary operator or a comma, or while a `(` or `[` is open. This rule is applied by the lexer alone.
- **Keywords**: `and asm at bool break byte case const continue critical do downto elif else end enum extern for forward func if import in inline int interrupt loop mod module not nozp of or pub record recursive return rows sbyte static then to type var while word zp`. Reserved for later: `long`.

## Types

| Type | Size | Meaning |
|---|---|---|
| `byte` | 1 | Unsigned, 0 to 255. |
| `sbyte` | 1 | Signed, -128 to 127. |
| `word` | 2 | Unsigned, 0 to 65535. Low byte first. |
| `int` | 2 | Signed, -32768 to 32767. |
| `bool` | 1 | `true` or `false`, stored as 1 or 0. |
| `^T` | 2 | Pointer to a `T`. |
| `[N]T` | N × size of T | Array of `N` elements, indexed from 0. `N` is a constant. |
| `record … end` | sum of fields | Fields in order, no padding. |
| `func(…): T` | 2 | Pointer to a function (see Function pointers). |

Named types are introduced with `type`. An enumeration introduces a `byte`-sized type and its constants:

```
type Sym = record
  name:  ^byte
  kind:  byte
  value: word
end

enum Kind
  K_CONST
  K_VAR
  K_FUNC
end
```

### Type rules

- **A `byte` operation gives a `byte`** and wraps. `a + b` on two bytes is an 8-bit add.
- **Widening is implicit, narrowing is not.** A `byte` becomes a `word` wherever a `word` is needed, with a zero high byte. Going the other way needs `byte(x)`, `lo(x)` or `hi(x)`.
- **Signed and unsigned do not mix** without a conversion. Signed comparisons cost more code than unsigned ones; the type makes that visible.
- **Conditions are `bool`.** There is no "non-zero is true": write `if n != 0 then`.
- **Conversions** are written as a call of the type name: `byte(w)`, `word(b)`, `int(w)`, or a named pointer type such as `SymPtr(w)`.
- **Built-ins:** `lo(x)`, `hi(x)`, `sizeof(T)`, `len(array)`.

### Arrays and their layout

- **An array of at most 256 elements is indexed by a `byte`.** A `word` index on such an array is an error.
- **Elements larger than one byte are stored by column.** An array of words is stored as all the low bytes, then all the high bytes. An array of records is stored as one byte array per byte of the record. `syms[i].kind` and `table[i]` are then single indexed loads with no multiply.
- **A column-stored element has no address.** `@syms[i]` is an error, and assigning a whole element copies it field by field.
- **`rows` keeps elements together**, as in C: `var nodes: [1000]Node rows`. It is required for arrays of more than 256 elements. The element size must then be a power of two, so the index is scaled by shifts; any other size is an error, to be fixed by padding the record.

### Pointers

- `@x` is the address of a variable, a `rows` array element or a function.
- `p.field` reads a field of the record `p` points to.
- `p[i]` reads byte `i` after the address in `p`, for a `^byte` and a `byte` index. This is the 6502's `(zp),Y` addressing and costs the same as an array access. `p[0]` is the byte `p` points to.
- Pointer arithmetic is in bytes and written out: `p + sizeof(Sym)`.
- A string literal used as a value is a `^byte` to a constant.

## Declarations

```
const MAX = 40                         ; constant: no storage
const DIGITS: [16]byte = "0123456789ABCDEF"   ; constant table: read-only data

var count: byte                        ; variable: the linker chooses the address
var line: [128]byte
var cursor: ^byte zp                   ; must be in zero page
var big: [512]byte nozp                ; must not be in zero page
var border: byte at $D020              ; fixed address, never cached in a register
var total: word = 0                    ; initialised when the program starts
var nodes: [1000]Node rows in SYMBANK  ; in a named memory region (see banking)
```

- **Module-level variables** live for the whole program.
- **Variables declared in a function** belong to that function. Their values are **not kept between calls**: the linker reuses the storage for other functions. An initialiser on a local is an assignment made on every entry.
- **`static var`** in a function keeps its value between calls and is never shared.
- **`pub`** in front of a declaration exports it from the module.

## Functions

```
func max(a: byte, b: byte): byte
  if a > b then
    return a
  end
  return b
end
```

- Parameters are ordinary local variables that the caller fills in. They can be assigned to.
- A function returns nothing, one value, or **one value and a `bool` status**: `func next(): byte, bool`. The status travels in the carry flag, the 6502's usual way to report "end of input" or "failed". The caller writes `ch, ok = next()`.
- A name must be declared before use. For functions that call each other, declare one first: `forward func expr(): byte`.

### Function attributes

| Attribute | Meaning |
|---|---|
| `inline` | The body is expanded at each call. It cannot be recursive and its address cannot be taken. |
| `recursive` | The function may be active more than once. Calls between `recursive` functions save and restore the caller's storage. A cycle of calls through any function not marked `recursive` is a link error. |
| `interrupt` | An interrupt handler: no parameters, no result. It saves the registers and returns with `RTI`. Everything it calls gets storage separate from the main program's. |
| `extern … at` | A routine at a fixed address, with parameters and results in named registers. |
| `asm` | A function whose whole body is assembly, with parameters and results in named registers. |

```
; services of the emulator's host interface (asm/17/environment.asm)
pub extern func read_byte(): byte in a, bool in c       at $F006
pub extern func put_byte(ch: byte in a)                  at $F009
pub extern func open(name: ^byte in ax): byte in a       at $F012

asm func swap_nibbles(v: byte in a): byte in a
  ASL A
  ADC #$80
  ROL A
  ASL A
  ADC #$80
  ROL A
end
```

Register names are `a`, `x`, `y`, the pairs `ax`, `ay` and `xy` (low byte in the first), and `c` for a `bool` in the carry flag.

### Function pointers

```
type Handler = func(code: byte, arg: word): bool

var on_key: Handler

on_key = @beep            ; beep must have exactly Handler's parameters and result
ok = on_key(3, 500)       ; call through the pointer
```

- A function type is written only in a `type` declaration, so it always has a name. It lists parameters with names, like a function header. `@f` can be assigned wherever a function type with `f`'s exact signature is expected.
- **Class.** Each function type is a class of its own. A function joins a class when its address is used as that type. A function used as two types makes the linker merge those classes.
- **Any number of parameters.** All functions in a class have their parameters at the same addresses, chosen by the linker, so a call through a pointer stores its arguments exactly as a direct call does ([`code-model.md`](code-model.md)).
- **What the linker assumes.** A call through a pointer may reach every function in the pointer's class. Named types keep that assumption narrow.
- **Members calling members.** Two functions in one class share parameter storage, so one calling the other, directly or through a pointer, counts as recursion.
- **`recursive` function types.** `type Visit = recursive func(n: ^Node)` accepts only `recursive` functions. A call through it from a `recursive` function saves the caller's storage. A call through an unmarked type never saves.
- **One context per class.** A class can be called through pointers from the main program or from one interrupt handler, not both. Use two named types to have the same signature in both.

## Statements

```
x = expr                 ; assignment
x += expr                ; also -= &= |= ^= <<= >>=
f(a, b)                  ; call
v, ok = f()              ; call returning a value and a status

if cond then … elif cond then … else … end
while cond do … end
loop … end                           ; forever; leave with break or return
for i = first to last do … end       ; also downto; i is a declared variable
break                                ; leave the nearest loop
continue                             ; next iteration of the nearest loop
return [expr [, status]]

case kind                            ; byte value against constants
of K_CONST, K_VAR
  …
of K_FUNC
  …
else
  …
end

critical … end                       ; interrupts disabled inside, restored after

asm                                  ; inline assembly
  LDA count
  STA $D020
end
```

- `for` evaluates `last` once. The loop variable is a `byte` or `word` declared beforehand. Counting `downto 0` gives the shortest loop.
- `case` with dense constants becomes a jump table; otherwise a chain of compares.
- `critical` saves the interrupt flag, disables interrupts, and restores the flag at `end`. Use it around any access to a multi-byte variable shared with an interrupt handler.

### Inline assembly

- Instructions use asm17's syntax.
- Operands can name any Lathe variable, constant or function in scope. Fields and elements are written as offsets: `LDA sym+2`.
- Labels are local to the block and start with `.`. Branches must stay inside the block.
- A, X and Y are free to use and hold nothing useful on entry. The stack must be left as it was found.
- The decimal flag must be clear on exit.

## Expressions

Precedence, from lowest to highest. Operators on one row associate left to right.

| Level | Operators | Notes |
|---|---|---|
| 1 | `or` | `bool` only; the right side is evaluated only if needed |
| 2 | `and` | `bool` only; the right side is evaluated only if needed |
| 3 | `not` | `bool` only |
| 4 | `==` `!=` `<` `<=` `>` `>=` | give `bool`; do not chain |
| 5 | `+` `-` `\|` `^` | add, subtract, bitwise or, bitwise exclusive or |
| 6 | `*` `/` `mod` `&` `<<` `>>` | multiply, divide, remainder, bitwise and, shifts |
| 7 | unary `-` `~` `@` | negate, bitwise not, address of |
| 8 | `f(…)` `a[i]` `r.field` | call, index, field |

Bitwise operators bind tighter than comparisons, so `flags & MASK != 0` means what it says.

**Operators that call the run-time library.** These are the only ones:

- `*`, `/` and `mod`, unless one operand is a constant power of two.
- `<<` and `>>` by an amount that is not a constant (a loop is generated in line for bytes).

Constant expressions are evaluated by the compiler wherever a constant is required, and folded elsewhere.

## Modules

```
module symtab          ; first line of the file

import host            ; use host's exported names as host.name
import strings
```

- One module per source file. The module name is the file name.
- Compiling a module writes its object file and an **interface file** listing what it exports. `import` reads the interface file, not the source.
- Imports cannot form a cycle. A module is compiled after the modules it imports.
- Imported names are always written with the module name: `strings.equal(a, b)`.
- The program starts at `pub func main()` in the module named when linking.
- An exported `inline` function carries its body in the interface file.

## Conditional compilation

```
#if CPU_65C02
  …
#else
  …
#end
```

The condition is a constant expression. Constants such as `CPU_65C02` come from the environment description. The skipped lines are not compiled, so they may use names that do not exist in this configuration.

## Banked data

A variable can be placed in a named memory region from the environment description with `in REGION`. If the region is a bank, the program must have that bank switched in when it uses the variable; the run-time library provides the call. The linker rejects a function that uses a banked variable if the function's own code is placed in the same window. See [`code-model.md`](code-model.md).

## Grammar

`NL` is the end of a line. `{ x }` is zero or more, `[ x ]` is optional.

```
unit        = "module" name NL { "import" name NL } { declaration } .

declaration = [ "pub" ] ( constDecl | typeDecl | enumDecl | varDecl | funcDecl | externDecl )
            | "forward" funcHead NL .

constDecl   = "const" name [ ":" type ] "=" initialiser NL .
enumDecl    = "enum" name NL { name [ "=" constExpr ] NL } "end" NL .
varDecl     = [ "static" ] "var" name ":" type { placement } [ "=" initialiser ] NL .
placement   = "zp" | "nozp" | "rows" | "at" constExpr | "in" name .
initialiser = constExpr | "[" constExpr { "," constExpr } "]" .
constExpr   = expression .

typeDecl    = "type" name "=" ( type | funcType ) NL .
funcType    = [ "recursive" ] "func" "(" [ param { "," param } ] ")" [ ":" type [ "," "bool" ] ] .
type        = typeKw
            | name [ "." name ]
            | "^" type
            | "[" constExpr "]" type
            | "record" NL { name ":" type NL } "end" .
typeKw      = "byte" | "sbyte" | "word" | "int" | "bool" .

funcDecl    = { "inline" | "recursive" | "interrupt" } funcHead NL body "end" NL
            | "asm" regHead NL { asmLine NL } "end" NL .
funcHead    = "func" name "(" [ param { "," param } ] ")" [ ":" type [ "," "bool" ] ] .
param       = name ":" type .
externDecl  = "extern" regHead "at" constExpr NL .
regHead     = "func" name "(" [ regParam { "," regParam } ] ")" [ ":" regResult [ "," regResult ] ] .
regParam    = name ":" type "in" register .
regResult   = type "in" register .
register    = "a" | "x" | "y" | "ax" | "ay" | "xy" | "c" .

body        = { varDecl | statement } .
statement   = designator ( assignOp expression | "," designator "=" call | arguments ) NL
            | "if" expression "then" NL body
                 { "elif" expression "then" NL body } [ "else" NL body ] "end" NL
            | "while" expression "do" NL body "end" NL
            | "loop" NL body "end" NL
            | "for" name "=" expression ( "to" | "downto" ) expression "do" NL body "end" NL
            | "case" expression NL { "of" constExpr { "," constExpr } NL body }
                 [ "else" NL body ] "end" NL
            | "critical" NL body "end" NL
            | "asm" NL { asmLine NL } "end" NL
            | "break" NL | "continue" NL
            | "return" [ expression [ "," expression ] ] NL .
assignOp    = "=" | "+=" | "-=" | "&=" | "|=" | "^=" | "<<=" | ">>=" .

expression  = andExpr { "or" andExpr } .
andExpr     = notExpr { "and" notExpr } .
notExpr     = "not" notExpr | relation .
relation    = sum [ ( "==" | "!=" | "<" | "<=" | ">" | ">=" ) sum ] .
sum         = term { ( "+" | "-" | "|" | "^" ) term } .
term        = factor { ( "*" | "/" | "mod" | "&" | "<<" | ">>" ) factor } .
factor      = ( "-" | "~" ) factor | "@" designator | primary .
primary     = number | string | "(" expression ")"
            | typeKw "(" expression ")"
            | designator [ arguments ] .
designator  = name { "." name | "[" expression "]" } .
arguments   = "(" [ expression { "," expression } ] ")" .
call        = designator arguments .
```

Notes on the grammar:

- A statement that starts with a name is an assignment, a two-result call or a plain call; the token after the designator decides.
- A conversion to a named type, such as `SymPtr(w)`, is parsed as a call. The symbol table says whether the name is a type.
- `true` and `false` are predeclared constants, and `lo`, `hi`, `len` and `sizeof` are predeclared functions; none are keywords. `sizeof` takes a type as its argument.
- A `constExpr` is an expression the compiler can evaluate; anything else is an error.
- `#if`, `#else` and `#end` are handled by the lexer and do not appear in the grammar.
- Inside an `asm` block the lexer passes whole lines through. The block ends at a line whose first word is `end`.

## A larger example

A symbol table of the kind the compiler itself needs. It shows column-stored records, an enumeration, a status result and a `case`.

```
module symtab

import strings

const MAX_SYMS = 200

enum Kind
  K_CONST
  K_VAR
  K_FUNC
end

type Sym = record
  name:  ^byte
  kind:  Kind
  value: word
end

var syms: [MAX_SYMS]Sym        ; five byte columns of 200 bytes each
var used: byte

; index of the symbol called name; status false if there is none
pub func find(name: ^byte): byte, bool
  var i: byte
  i = used
  while i != 0 do
    i -= 1
    if strings.equal(syms[i].name, name) then
      return i, true
    end
  end
  return 0, false
end

pub func add(name: ^byte, kind: Kind, value: word): bool
  if used == MAX_SYMS then
    return false
  end
  syms[used].name = name
  syms[used].kind = kind
  syms[used].value = value
  used += 1
  return true
end

; size in bytes of the storage a symbol needs
pub func storage(i: byte): byte
  case syms[i].kind
  of K_CONST
    return 0
  of K_VAR
    return lo(syms[i].value)
  else
    return 2
  end
end
```

## Left for later

- 32-bit `long`.
- Alternate spellings for `|` and `~`.
- A register hint for loop variables. The compiler's tracking of register contents may make it unnecessary.
- Whether column storage should be the default or asked for. It is the default here because it is the cheaper form on a 6502.
