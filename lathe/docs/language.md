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

- **Character set.** Source is 7-bit ASCII. Upper-case letters are folded to lower case outside string and character literals, so keywords and names are not case sensitive. Only `|` and `~` fall outside the range `$20`–`$5F` (see the open questions in [`goals.md`](goals.md)).
- **Comments** run from `;` to the end of the line.
- **Names** start with a letter and continue with letters, digits and `_`. The first 31 characters are significant.
- **Numbers.** Decimal `123`, hexadecimal `$7F`, binary `%1010`, character `'A'`. A number literal has no type of its own; it takes the type its context needs, and it is an error if it does not fit.
- **Strings.** `"TEXT"` is a zero-terminated sequence of bytes. Escapes: `\n`, `\r`, `\t`, `\0`, `\\`, `\"`, `\'`, `\xHH`. Adjacent strings are joined into one: `"abc" "def"` is `"abcdef"`, and so is a string at the end of a line followed by one at the start of the next, with only blanks, comments and blank lines between, so a long text can be written in pieces, one per line. A string holds at most 2048 bytes, as much as a constant table (error 7, and error 87 for a table); one in the body of an `inline` function at most 255.
- **Statements end at the end of the line.** A line continues onto the next when it ends with a binary operator or a comma, or while a `(` or `[` is open. This rule is applied by the lexer alone.
- **Keywords**: `and asm at bool break byte case const continue critical do downto elif else end enum extern for forward func if import in inline int interrupt loop mod module not nozp of or pub record recursive return rows sbyte static then to type until var while word zp`. Reserved for later: `long`.

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
| `record … end` | sum of fields | Fields in order, no padding. Written only in a `type` declaration. |
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

### Named types, records and enumerations

- **Another name for a type is that type.** After `type SymPtr = ^Sym`, `SymPtr` and `^Sym` can be used for each other, and so can two names for one type: names of types are structural.
- **A record or an enumeration is a type of its own.** Each declaration makes a new type, different from every other even if their fields or constants are the same. Another module's is the same type wherever it is used: it is known by its module and its name.
- **A record** is declared only in a `type` declaration, so it always has a name. Its fields are in order with no padding, and each has a type declared before, or a pointer to the record itself (`next: ^Link`); the record cannot contain itself or an array of itself. It has at least one field.
- **What a record can do.** `r.field` and `p.field` (through a pointer) are variables of the field's type, which can be another record, an array or a pointer: `s.pos.x`, `s.marks[i]`, `syms[i].name`. A whole record can be assigned to a record of the same type, which copies it byte by byte. Records cannot be compared, converted or used in arithmetic, and are not parameters or results: pass a pointer. A record has no initial value yet. Like an array, a record variable is never in zero page unless it is declared `zp`.
- **An enumeration** is a type of one byte, and its constants are its values: the first is 0 unless it is given one (`= constExpr`), and each other is one more than the one before. Every value must fit a byte; two constants may have the same value.
- **What an enumeration can do.** It can be assigned, passed and returned, and compared, `==` and `!=` and the ordering comparisons, with a value of the same enumeration only. It is not a number: no arithmetic, and a number or a `byte` is not an enumeration. `byte(k)` gives its value, so `table[byte(k)]` indexes a table by it, and `Kind(b)` gives the enumeration whose value is `b`. A `case` on an enumeration takes its constants after `of`.
- **`pub`** on a `type` or an `enum` exports the name; `pub enum` exports its constants too.

### Type rules

- **A `byte` operation gives a `byte`** and wraps. `a + b` on two bytes is an 8-bit add.
- **Widening is implicit, narrowing is not.** A `byte` becomes a `word` wherever a `word` is needed, with a zero high byte. Going the other way needs `byte(x)`, `lo(x)` or `hi(x)`.
- **A number without a type takes the type of what it is used with**, which it must fit (error 43), with two allowances. If it is combined with a `byte` and does not fit a byte, the byte is widened to a `word`, as the rule above allows, and the operation is a word one: `$FFFF - digit` is a word, and `b + 300` is a word too. And a number below zero that `~` or unary `-` made of a number without a type fits an unsigned type by its bits, if it is at least -256 for a byte: `b = ~$20` stores `$DF`, `b & ~BIT` clears a bit, `w = -1` stores `$FFFF`. The mark is kept by `+`, `-`, `*`, `&`, `|`, `^` and `<<` of two such numbers (`~$20 & ~$40` is `$9F` as a byte), and dropped by `/`, `mod` and `>>`, whose low bits depend on the high ones. Everything else stays exact and is an error where it does not fit: `b = 0 - 1`, `b = ~$100`, `s = s + $FF` on an `sbyte` (a signed byte is not widened by itself). A constant declared without a type keeps its exact value, so `const MASK = ~$20` is -33 and no byte; `const MASK: byte = ~$20` is `$DF`.
- **Signed and unsigned do not mix** without a conversion. Signed comparisons cost more code than unsigned ones; the type makes that visible.
- **Conditions are `bool`.** There is no "non-zero is true": write `if n != 0 then`.
- **Conversions** are written as a call of the type name: `byte(w)`, `word(b)`, `int(w)`, a named pointer type such as `SymPtr(w)`, or an enumeration, `Kind(b)`. A record cannot be converted.
- **Built-ins:** `lo(x)`, `hi(x)`, `sizeof(T)`, `len(array)`. `lo(x)` and `hi(x)` of a variable can also be assigned to: `hi(w) = 0`.

### Arrays and their layout

- **An array of at most 256 elements is indexed by a `byte`.** A `word` index on such an array is an error.
- **Elements larger than one byte are stored by column.** An array of words is stored as all the low bytes, then all the high bytes. An array of records is stored as one byte array per byte of the record. `syms[i].kind` and `table[i]` are then single indexed loads with no multiply.
- **A column-stored element has no address.** `@syms[i]` is an error, and assigning a whole element copies it field by field.
- **`rows` keeps elements together**, as in C: `var nodes: [1000]Node rows`. It is required for arrays of more than 256 elements larger than a byte. The element size must then be a power of two, so the index is scaled by shifts; any other size is an error, to be fixed by padding the record. `rows` is part of the array's type: `[1000]word rows` and `[1000]word` are different types.
- **A byte array of more than 256 elements is indexed by a `word`** (a `byte` is widened). Such an array, and any `rows` array of elements larger than a byte, is reached through a pointer the compiler works out in zero page, so a variable index costs an addition.
- **Arrays of arrays.** `[3][4]byte` is three elements of `[4]byte`; stored by column, element `i`'s byte `j` is at `j * 3 + i`. Only one index of an element can be a variable, and only the first one, unless the array is declared `rows`: `grid[i][2]` and `grid[1][2]` are allowed, `grid[1][j]` is not.
- **A constant index must be inside the array**, `0` to `N - 1`; there is no element one past the end.
- **An array is not a value.** Assigning a whole array, passing it as an argument or returning it is an error: pass a pointer, or copy it with a loop.
- **Initial values.** `var a: [8]byte = [1, 2, 3]` gives the first elements; the others are 0. A string fills a byte array, followed by a zero if there is room: `const DIGITS: [16]byte = "0123456789ABCDEF"` has none. `const NAME = "text"` without a type is a `[5]byte`. A variable's initial value is copied from constant data as long as the whole array.

### Pointers

- `@x` is the address of a variable, an element of an array of bytes or a `rows` array, or a function. The address of an array is a pointer to its first element: `@a` of a `[10]byte` is a `^byte`, and `@grid[1]` of a `[3][4]byte rows` is a `^byte` too. An array stored by column has no such pointer: `@words` of a `[10]word` is an error, like `@words[i]`.
- `p.field` is a field of the record `p` points to, to read or to assign: `p.field` is `p[0].field`. `p.next.value` reads `p.next` into a zero page pointer first. An array field takes a variable index: `p.marks[i]`.
- `p[i]` is element `i` after the address in `p`, with a `byte` index. For a `^byte` this is the 6502's `(zp),Y` addressing and costs the same as an array access. For a larger element the size must be 2, 4 or 8, the index is scaled by shifts, and the scaled index must stay below 256. `p[0]` is what `p` points to, for any type.
- Pointer arithmetic is in bytes and written out: `p + sizeof(Sym)`. A pointer plus or minus an integer is a pointer; the difference of two pointers is a `word`. Pointers compare as unsigned numbers.
- `nil` is the pointer with value 0 and fits any pointer type. `^T(x)` converts a number to a pointer.
- A record field may be a pointer to the record being declared: `next: ^Link`.
- A string literal used as a value is a `^byte` to a constant. A constant table is not a value: `p = @NAME`.
- **The pointer of `p[i]` must be in zero page.** A pointer variable of this module, a parameter or a local that is dereferenced becomes "must be in zero page" ([`code-model.md`](code-model.md)); any other (declared `nozp`, another module's not declared `zp`, an element, a call result) is copied to a zero page temporary first.
- Only identical pointer types can be assigned to each other, and `nil` to any of them. `word(p)` and `^T(w)` convert.

## Declarations

```
const MAX = 40                         ; constant: no storage
const DIGITS: [16]byte = "0123456789ABCDEF"   ; constant table: read-only data

var count: byte                        ; variable: the linker chooses the address
var line: [128]byte
var cursor: ^byte zp                   ; must be in zero page (arrays too, if asked)
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
- A function returns nothing, one value, or **one value and a `bool` status**: `func next(): byte, bool`. The caller writes `ch, ok = next()`.
- **A `bool` result travels in the carry flag**, whether it is the only result or the status beside a value. This is the 6502's usual way to report "found" or "end of input", and a test of it is one branch.
- **Testing a status directly.** In a condition, `next() -> ch` calls the function, stores the value in `ch` and gives the status: `while next() -> ch do … end`.
- **Passing results on.** `return f(…)` is allowed when `f` has the same results as the function returning; both results pass through, and the call becomes a jump.
- **A status may be ignored.** A call of a function that gives a value and a status, used as a value, gives the value and drops the status: `v = next()`, `next() + 1`, `put(next())`. A call used as a statement may ignore both results. Only `return f()` passes both on, and only `ch, ok = f()` and `f() -> ch` take the status.
- **The end of a function that has a result must not be reachable** (error 180, reported at its `end`): every way through the body ends in a `return`, or in a `loop … end` that only `return` leaves. A body whose last statement is an `asm` block counts as returning: the block must end in its own `RTS` with the result in A, or A and X, as the functions of `rt_math` do. The test is on the code: an `if` without `else` after which nothing returns, a `case` without `else`, or a loop with a `break` can reach the end.
- A name must be declared before use. For functions that call each other, declare one first: `forward func expr(): byte`. A forward declaration of a `recursive` function says so too, `forward recursive func expr(): byte`, so that the calls made before its body are compiled as calls of a recursive function.

### Function attributes

| Attribute | Meaning |
|---|---|
| `inline` | The body is expanded at each call ([`code-model.md`](code-model.md), "Inline functions"). It cannot be recursive and its address cannot be taken. |
| `recursive` | The function may be active more than once. Calls between `recursive` functions save and restore the caller's storage. A cycle of calls through any function not marked `recursive` is a link error. Only a function with a body in Lathe can be `recursive`, and its `forward` declaration says so too. |
| `interrupt` | An interrupt handler: no parameters, no result. It saves the registers and returns with `RTI`. Everything it calls gets storage separate from the main program's. It cannot be called: `@name` is its address, a `^byte`, to be stored in the board's vector. |
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

- A function type is written only in a `type` declaration, so it always has a name. It lists parameters with names, like a function header. `@f` can be assigned wherever a function type with `f`'s exact signature is expected: assigned, passed, returned, as an initial value or an element of a constant table (`const KEYS: [3]Handler = [@beep, @flash, @beep]`), or compared. Exact means the same number of parameters and results with the same types, in order; the names do not matter.
- **Values of a function type** are two bytes, and can be variables, parameters, results, record fields and array elements. They can be assigned, passed and returned, compared with `==` and `!=` with each other and with `nil`, which fits every function type, and converted to a number, `word(h)`. There is no arithmetic on them and no conversion to them: a function type's value always comes from `@f`, which is what makes `f` a member of its class. Calling `nil` is the programmer's error.
- **`@f` on its own** has no type until it is given to something of a function type. `word(@f)` is the function's address as a number, which is what an interrupt vector needs. `@f` of an `extern` function is the number its `at` gives. An `asm` function has its parameters in registers and cannot be given to a function type.
- **A call through a pointer** is written as a call: `on_key(3, 500)`, `handlers[i](3, 500)`, `p.visit(n)`, with every form of result a direct call has (`ok = h(x)`, `v, ok = h(x)`, `h(x) -> v`, `return h(x)`).
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
loop … until cond                    ; test at the bottom: the body runs at least once
for i = first to last do … end       ; also downto; i is a declared variable
for i = first until limit do … end   ; first up to limit - 1; not at all if first >= limit
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

- `for` evaluates `last` once, unless it is a plain variable: that is read at each test, so a body that changes it changes the loop. The loop variable is a `byte`, `sbyte`, `word` or `int` declared beforehand. The body runs for every value from `first` to `last` inclusive, and not at all if `first` is already past `last`. The test is at the bottom, so a loop to 255 or down to 0 ends correctly. A loop that runs to its end leaves the variable equal to `last`; one that does not run at all leaves it equal to `first`. `continue` goes to the test at the bottom. Counting `downto 0` gives the shortest loop.
- `for i = first until limit` runs the body for every value from `first` up to but not including `limit`, and not at all when `first >= limit`: `for i = 0 until n` runs `n` times, also when `n` is 0, where `for i = 0 to n - 1` would run 256 times. The test, `i < limit`, is at the top, before each pass; the limit is evaluated as `to`'s is (once, unless it is a constant or a plain variable), and `continue` goes to the step before the test. A loop that runs leaves the variable equal to the limit, unless `break` left it; one that does not run leaves it equal to `first`. There is no downward form.
- `loop … until` is the tightest loop on a 6502: one branch per pass.
- `case` takes a selector of one byte (`byte`, `sbyte` or `bool`; a `word` selector is an error for now), evaluated once. The constants after `of` take its type, and each may appear only once in a `case`. With no `else`, a value that no `of` names does nothing. The compiler makes a chain of compares; with dense constants it may later make a jump table.
- `critical` saves the interrupt flag, disables interrupts, and restores the flag at `end`. Use it around any access to a multi-byte variable shared with an interrupt handler. A `break`, `continue` or `return` that leaves the block restores the flag on its way out. A `return` that gives a status (a `bool` result) cannot be inside `critical`, because restoring the flags would change the carry that holds it: keep the status in a variable and return after `end`.

### Inline assembly

- Instructions use asm17's syntax.
- Operands can name any Lathe variable, constant or function in scope. Fields and elements are written as offsets: `LDA sym+2`.
- Labels are local to the block and start with `.`. Branches must stay inside the block.
- A, X and Y are free to use and hold nothing useful on entry. The stack must be left as it was found.
- An indirect mode, or an instruction that has only a zero page form (`STX v,Y`, `STY v,X`), on a variable makes that variable "must be in zero page", as declaring it `zp` would. Compiled code never does this on its own. A variable declared `nozp`, or one of another module that was not declared `zp` there, cannot be made so: that is an error.
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

- `*`, `/` and `mod`, unless one operand is a constant power of two (for `/` and `mod`, the right one, and only on unsigned types: a shift would round a negative number the wrong way). The library is linked by itself, without an `import`. Division by zero is an error (59) only in a constant expression, two constants divided by the constant 0; anything else gives a quotient of all ones and the dividend as the remainder ([`code-model.md`](code-model.md), "Run-time arithmetic").
- `<<` and `>>` by an amount that is not a constant (a loop is generated in line for bytes).

Constant expressions are evaluated by the compiler wherever a constant is required, and folded elsewhere.

## Modules

```
module symtab          ; first line of the file

import host            ; use host's exported names as host.name
import strings
```

- One module per source file. The module name is the file name.
- Compiling a module writes its object file and an **interface file** listing what it exports. `import` reads the interface file, not the source. The interface holds every record and enumeration the module declares, `pub` or not, so that what it exports can use them; one that is not `pub` cannot be named by an importer.
- **The modules whose types an interface uses are imported first.** If `geometry` exports `func area(b: ^shapes.Box): word`, a module that imports `geometry` imports `shapes` before it, even if it does not name `shapes` itself.
- Imports cannot form a cycle. A module is compiled after the modules it imports.
- Imported names are always written with the module name: `strings.equal(a, b)`.
- The program starts at `pub func main()` in the module named when linking.
- An exported `inline` function carries its body in the interface file. Its body can use only what its module exports, and the modules its module imports, which an importer need not import itself.

## Conditional compilation

```
#if cpu_65c02
  …
#else
  …
#end
```

The condition is a constant expression over the constants declared before it. It is true if it is a `bool` that is true or a number that is not 0. Constants such as `cpu_65c02` come from the environment description ([`architecture.md`](architecture.md)): the compiler predeclares `cpu_65c02`, a `bool`, from its `cpu` entry, and a constant for each `define` entry, the `bool` `true` for `define NAME` and a number for `define NAME VALUE`. A name the condition uses must be declared, so a setting that only some environments want is given a value by all of them: `define FAST 0` in the others, tested as `#if FAST`.

`#error "text"` in a part that is compiled stops the compiler with error 181 at the `#`, followed by `: text` (the string may be left out). In a part that is skipped it is a line like any other, so a configuration that cannot work says so:

```
#if BOARD == 0
#error "no board: build with --env michael or --env wendy2"
#end
```

`error` is not a keyword; it has this meaning only after `#`. The skipped lines are not compiled and not even read as tokens, so they may hold anything, names that do not exist in this configuration included. The lexer only looks for lines that start with `#`, to match `#if` inside them with their `#end`. A directive stands at the start of a line, blanks before it allowed, with nothing but a comment after it. `#if` can start any line where a declaration, an `import` or a statement can start, in a module or in a function; `#else` and `#end` can start any line. Inside an `asm` block a line is assembly, so directives are not recognised there.

## Banked data

A variable can be placed in a named memory region from the environment description with `in REGION`. If the region is a bank, the program must have that bank switched in when it uses the variable; the run-time library provides the call. The linker rejects a function that uses a banked variable if the function's own code is placed in the same window. See [`code-model.md`](code-model.md).

## Grammar

`NL` is the end of a line. `{ x }` is zero or more, `[ x ]` is optional.

```
unit        = "module" name NL { "import" name NL } { declaration } .

declaration = [ "pub" ] ( constDecl | typeDecl | enumDecl | varDecl | funcDecl | externDecl )
            | "forward" [ "recursive" ] funcHead NL .

constDecl   = "const" name [ ":" type ] "=" initialiser NL .
enumDecl    = "enum" name NL { name [ "=" constExpr ] NL } "end" NL .
varDecl     = [ "static" ] "var" name ":" type { placement } [ "=" initialiser ] NL .
placement   = "zp" | "nozp" | "rows" | "at" constExpr | "in" name .
initialiser = constExpr | "[" constExpr { "," constExpr } "]" .
constExpr   = expression .

typeDecl    = "type" name "=" ( type | recordType | funcType ) NL .
recordType  = "record" NL { name ":" type NL } "end" .
funcType    = [ "recursive" ] "func" "(" [ param { "," param } ] ")" [ ":" type [ "," "bool" ] ] .
type        = typeKw
            | name [ "." name ]
            | "^" type
            | "[" constExpr "]" type .
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
            | "loop" NL body ( "end" | "until" expression ) NL
            | "for" name "=" expression ( "to" | "downto" | "until" ) expression "do" NL body "end" NL
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
            | "^" type "(" expression ")"
            | designator [ arguments [ "->" designator ] ] .
designator  = name { "." name | "[" expression "]" } .
arguments   = "(" [ expression { "," expression } ] ")" .
call        = designator arguments .
```

Notes on the grammar:

- A statement that starts with a name is an assignment, a two-result call or a plain call; the token after the designator decides.
- A conversion to a named type, such as `SymPtr(w)`, is parsed as a call. The symbol table says whether the name is a type.
- In `type` the name is a named type, a record or an enumeration, of this module or, after a ".", of an imported one.
- A designator whose value is of a function type, followed by `arguments`, is a call through that pointer.
- `true`, `false` and `nil` are predeclared constants, and `lo`, `hi`, `len` and `sizeof` are predeclared functions; none are keywords. `sizeof` takes a type as its argument.
- A `constExpr` is an expression the compiler can evaluate; anything else is an error.
- `#if`, `#else`, `#end` and `#error` are handled by the lexer and do not appear in the grammar. (The parser works out the condition of `#if` where a declaration, `import` or statement can start, and tells the lexer what to skip.)
- Inside an `asm` block the lexer passes whole lines through. The block ends at a line whose first word is `end`.

## A larger example

A symbol table of the kind the compiler itself needs. It shows column-stored records, an enumeration, a status result and a `case`.

```
module symtab

import strings

const MAX_SYMS = 200

pub enum Kind                 ; pub: the callers of add need its constants
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
