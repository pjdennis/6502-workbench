# Lathe: how a compiled program runs

Status (2026-11-13): proposal. This document describes the run-time model: where variables live, how functions are called, and what code the compiler should produce. The code listings show what the design aims for; none of it has been generated yet.

## Terms

- **Slot**: the storage for one parameter, local variable or compiler temporary.
- **Frame**: all the slots of one function. A frame is a fixed set of addresses, not an area on a stack.
- **Context**: the main program, or one interrupt handler, together with everything each can call.
- **Fixed memory**: memory that is always mapped. **Window**: an address range whose contents change with the selected bank or the loaded overlay.

## Storage

Every variable has a fixed address, chosen by the linker.

| Kind | Lifetime | Shared with other functions? |
|---|---|---|
| Module-level variable | whole program | no |
| `static var` in a function | whole program | no |
| Parameter, local, temporary | one call | yes, with functions never active at the same time |

### Sharing frames

Two functions can use the same addresses if neither is ever active while the other is. The linker works this out from the call graph:

1. Each function's frame starts just above the frames of everything that could be active when it is called. That is the largest "end of frame" among its callers.
2. A function with no callers (the entry point) starts at the bottom.
3. Functions that are not reachable from an entry point are dropped. Taking a function's address, in code that is kept or in constant data, makes it reachable: if nothing else reaches it, it is an entry point of the main program.

For a program whose call chain is `main → parse → lookup → hash`, plus `main → emit`, the frames of `parse` and `emit` start at the same address, and `emit` reuses what `lookup` and `hash` used. The storage needed is that of the deepest chain, not the sum of all functions.

This is done twice, once for zero page and once for main memory, because each function's slots are divided between the two.

### What goes in zero page

Each slot is in one of three classes.

| Class | Rule | Examples |
|---|---|---|
| Must be in zero page | The 6502 needs it there. | A pointer that is dereferenced; anything declared `zp`. |
| Either | The linker decides. | Bytes, words, pointers that are only copied or compared. |
| Never in zero page | Too large or excluded. | Arrays, records, anything declared `nozp`. |

The compiler gives every "either" slot a weight: the number of places it is used, with uses inside loops counting more. The linker first places all "must" slots. If they do not fit, linking fails and the message names the call chain that needs the most. It then moves "either" slots into what is left, heaviest first, as long as the deepest chain still fits.

A pointer declared `nozp` can still be dereferenced: the compiler copies it to a zero page temporary first, at a visible cost of several instructions each time.

The exact rule for choosing among "either" slots is the subject of a spike ([`spikes.md`](spikes.md), L2).

### Temporaries

Temporaries for expression evaluation are slots in the frame of the function that needs them. There are no global scratch locations. This is what makes interrupt handlers safe without saving anything.

## Calls

### Convention

| Item | Where |
|---|---|
| Arguments | The caller stores each one directly into the callee's parameter slot. |
| `byte`, `sbyte` result | A. |
| `word`, `int`, pointer result | A (low byte) and X (high byte). |
| `bool` result, alone or as a status | The carry flag: set for `true`. |
| A, X, Y and the flags | Not preserved across a call. |

The pair A and X matches the host interface in `asm/17/environment.asm`, which passes pointers the same way.

A call is a `JSR`. There is no entry or exit code in an ordinary function, and no stack frame to build. A call whose results are returned unchanged (`return f(…)`, or a call as the last statement) is a `JMP`.

### Example

```
func sum(p: ^byte, n: byte): word
  var total: word
  var i: byte
  total = 0
  i = 0
  while i < n do
    total += p[i]
    i += 1
  end
  return total
end
```

The code to aim for, with `sum.p` in zero page. Slot names are shown as `sum.total` for reading; in asm17 text they are written `sum__total`.

```
sum:    LDA #$00
        STA sum.total
        STA sum.total+1     ; A is known to hold 0
        STA sum.i
.loop:  LDA sum.i
        CMP sum.n
        BCS .done
        TAY                 ; A is known to hold i
        LDA (sum.p),Y
        CLC
        ADC sum.total
        STA sum.total
        BCC .next
        INC sum.total+1
.next:  INC sum.i
        JMP .loop
.done:  LDA sum.total
        LDX sum.total+1
        RTS
```

A call `t = sum(@buf, 10)`:

```
        LDA #<buf
        STA sum.p
        LDA #>buf
        STA sum.p+1
        LDA #10
        STA sum.n
        JSR sum
        STA t
        STX t+1
```

### Calls inside arguments

In `g(a + 1, h(b))`, the first argument is already stored in `g`'s slot when `h` runs. If `h` shared storage with `g`, it would destroy that argument. The compiler therefore records that `h` was called while `g`'s arguments were pending, and the linker treats this as if `g` called `h`: `h`'s frame is placed above `g`'s. If `h` can itself reach `g`, that is a cycle, and the linker reports it like any other recursion. A call of `g` itself inside `g`'s arguments, as in `g(a, g(b, c))`, would overwrite the arguments already stored, so the compiler reports it as an error: the inner result must go through a variable.

### Functions called through a pointer

The caller does not know which function it is calling, but the linker chooses every address, so it makes the question unnecessary: **all functions in a pointer class have their parameters at the same addresses.** (Classes are defined in [`language.md`](language.md).)

- The linker allocates one block of parameter slots per class. Each member's parameters are names for that block.
- A call through a pointer stores its arguments into the block with ordinary instructions and costs the same as a direct call. The callee has no entry code.
- A function whose address is never taken joins no class, and nothing changes for it.

```
        LDA #3
        STA Handler.code      ; the same address as beep.code, flash.code, ...
        LDA #<500
        STA Handler.arg
        LDA #>500
        STA Handler.arg+1
        JSR .call             ; .call: JMP (on_key)
        STA ok
```

In the call graph the block is one extra node. Every caller of any member, direct or through a pointer, calls the block; the block calls every member. The ordinary rule for sharing frames then places the block above everything that can be active when a member is called, and each member's locals above the block.

Consequences:

- **Members calling members.** If one member calls another, the callee's arguments would overwrite the caller's parameters. In the graph this is a cycle through the block, so the linker's cycle check reports it, and the remedy is the one for recursion. If this proves common, the linker can instead give such a function a small entry stub that copies the block into slots of its own.
- **Slot classes.** A block slot takes the strictest zero page class any member needs, and the sum of the members' weights.
- **The call itself.** The 6502 has no indirect `JSR`. The call is a `JSR` to a three-byte `JMP (pointer)`, which works because the pointer variable has a fixed address. On an NMOS 6502 the linker keeps such a variable from straddling a page boundary. A pointer taken from a table is copied to a temporary first.

### Register arguments for ordinary calls

Passing one argument in A would save a store at each call and cost one in each function. `p1`'s notes measured this on its own source at about 300 bytes saved in 58 KB. It is left out of the first version and listed as a measurement to repeat ([`spikes.md`](spikes.md), L1).

## Recursion

A function marked `recursive` may be active more than once. The cost is paid only on calls between `recursive` functions:

1. The caller pushes its whole frame onto a recursion stack kept by the run-time library.
2. It computes the arguments into temporaries, then moves them into the callee's slots. Two steps are needed because the callee's slots may be the caller's own.
3. It calls the function.
4. It pops its frame back, keeping the result in the registers.

Calls into a `recursive` function from outside, and everything inside its body, are unchanged: variables keep their fixed addresses and fast addressing.

Rules that follow:

- **Through a pointer** the compiler cannot see the callee, so the function type decides. A call through a type marked `recursive`, made from a `recursive` function, saves the caller's frame, including its parameters if they are in a class block. A call through an unmarked type never saves. A recursive tree walker can therefore call a plain callback at no extra cost, as long as the callbacks never call back into the walker; if one does, the cycle check below reports it.
- `recursive` functions that can call each other do not share storage.
- The linker checks every cycle in the call graph. A cycle through a function not marked `recursive` is an error.
- A pointer to a local of a `recursive` function points at the slot, not at one activation. Passing such a pointer down a recursive call is an error the compiler cannot always catch; this is documented, as it was for Turbo Pascal.

The compiler's own expression parser is the main user of this feature.

## Interrupts

An `interrupt` function is the root of its own context.

- **Storage.** The linker places the frames of an interrupt context above everything the main program uses, and above any other interrupt context. A handler therefore never touches a slot the interrupted code was using, and saves nothing but the registers.
- **Functions used by two contexts.** A function reachable from both the main program and a handler, or from two handlers, is linked once per context, each copy with its own frame. The map file lists the copies. This covers the run-time library: a handler that multiplies gets its own multiply routine.
- **Entry and exit.** The handler saves A, X and Y on the stack and returns with `RTI`.
- **Pointer calls.** A pointer class may be called through pointers from one context only. `@f` then means that context's copy of `f`, and the class's parameter block is in that context's storage. Other contexts can still call `f` directly and get their own copy. A class called through pointers from two contexts is a link error naming both calls. The pointer variable is shared data like any other.
- **Shared variables.** A module-level variable used by a handler and by the main program is the programmer's responsibility. A single byte needs no care. Anything longer must be read and written inside `critical … end` in the main program, which is `PHP` / `SEI` … `PLP`: the flag is as it was before the block after its end and after any `break`, `continue` or `return` that leaves it.
- **Placement.** Code in an interrupt context is always placed in fixed memory, never in a window.
- **Vectors.** Installing a handler is done by the environment module for the machine, using `@handler`.

Ordinary calls pay nothing for any of this.

## Inline functions

At a call of an `inline` function the compiler replays the function's saved tokens.

- Each parameter becomes a slot in the caller's frame, assigned from the argument. Where the argument is a constant or a plain variable and the function never assigns to the parameter, the parameter is replaced by the argument and no slot is used.
- The function's locals become slots in the caller's frame.
- `return` becomes a jump to the end of the expansion.

## Segments, banking and overlays

The compiler places everything it emits in one of four segments.

| Segment | Contents | In a ROM system |
|---|---|---|
| code | instructions | ROM |
| constants | `const` tables and string literals | ROM |
| variables | all variables and frames | RAM |
| zero page | whatever the linker placed there | RAM |

**Initial values are set by code.** A variable declared with an initial value is assigned by a function the compiler writes for each module and the start-up code calls before `main`. There is no initialised-data segment to copy, so the output is ROMable as it stands, and a variable with an initial value can be placed anywhere, zero page included. Whether a program links never depends on a placement the linker chose. For a large table that never changes, use `const`, which costs no start-up code.

Where each segment of each module goes is decided by the environment description and the link configuration ([`architecture.md`](architecture.md)), not by the source.

### Code in windows

A module's code can be assigned to a bank or to an overlay. The compiler emits an ordinary `JSR` for every call. The linker knows where both ends are:

- If the callee is in fixed memory, or in the same bank or overlay as the caller, the `JSR` stays as it is.
- Otherwise the linker points the `JSR` at a small stub in fixed memory. The stub loads the target's bank or overlay number and address and jumps to the run-time routine for far calls. That routine makes the target available, calls it, restores what was mapped before, and returns with the result registers intact.

With banks, "make available" writes a bank register. With overlays, it loads a file into the window if it is not already there. The program and the linker see no difference; only the run-time routine and its speed differ. Arguments cross without help because slots are always in fixed memory.

### Data in windows

Frames and ordinary variables are always in fixed memory. A variable declared `in REGION` is placed in that region; if the region is a bank, the program switches it in with a run-time call before use. Two checks are made at link time:

- A function that uses a banked variable must not have its code in the same window.
- Interrupt contexts must not use banked variables.

This is the arrangement `p1` reached on Wendy 2: code in fixed memory, symbol tables in a bank.

## The run-time library

Written in Lathe with assembly where needed, and linked function by function like any other code.

| Area | Routines |
|---|---|
| Arithmetic | multiply, divide and remainder for 8 and 16 bits; variable shifts for 16 bits (`lathe/rt/rt_math.lth`, below) |
| Recursion | push and pop of a frame |
| Far calls | one routine per banking or overlay scheme, supplied by the environment module |
| Start-up | set the stack, copy initialised data, call `main`, exit |
| Environment | a module per machine wrapping its console, file and banking services |

### Run-time arithmetic

The module `rt_math` (`lathe/rt/rt_math.lth`). Its functions are ordinary exported Lathe functions: arguments in their parameter slots, results in A or in A and X, temporaries in their own slots, so an interrupt handler that divides gets its own copy like any other function. Each stands alone, except that the signed divides call the unsigned ones, so a program links only what it uses. Bytes are code with every slot in zero page; cycles are from `JSR` to the end of `RTS`, a typical call being the mean over random operands (for the shifts, counts 0 to 15; for the divides, divisors not 0).

| Function | Gives | Bytes | Cycles: typical, worst |
|---|---|---|---|
| `mul8(a: byte, b: byte): byte` | the low 8 bits of a × b, signed or unsigned | 16 | 139, 168 |
| `mul8x8(a: byte, b: byte): word` | the whole unsigned product | 21 | 159, 175 |
| `mul16(a: word, b: word): word` | the low 16 bits of a × b, signed or unsigned | 43 | 562, 697 (b < 256: at most 368) |
| `div8(a: byte, b: byte): byte` | a / b unsigned; leaves a mod b in `remainder` | 25 | 171, 222 |
| `mod8(a: byte, b: byte): byte` | a mod b unsigned | 19 | 162, 213 |
| `div16(a: word, b: word): word` | a / b unsigned; leaves a mod b in `remainder` | 52 | 687, 931 |
| `mod16(a: word, b: word): word` | a mod b unsigned | 44 | 674, 919 |
| `sdiv8(a: sbyte, b: sbyte): sbyte` | a / b signed; leaves \|a\| mod \|b\| in `remainder` | 54 | 238, 289 |
| `smod8(a: sbyte, b: sbyte): sbyte` | a mod b signed | 50 | 224, 278 |
| `sdiv16(a: int, b: int): int` | a / b signed; leaves \|a\| mod \|b\| in `remainder` | 83 | 782, 1021 |
| `smod16(a: int, b: int): int` | a mod b signed | 79 | 761, 1017 |
| `shl16(w: word, n: byte): word` | w << n | 23 | 121, 227 |
| `shr16(w: word, n: byte): word` | w >> n, unsigned | 23 | 128, 227 |
| `sar16(w: int, n: byte): int` | w >> n, keeping the sign | 25 | 144, 259 |

- **Division by zero** gives a quotient of all ones and a remainder equal to the dividend: what the shift-and-subtract loop gives with no test. The signed divides divide the magnitudes by that rule, so a signed quotient by zero is -1 for a dividend of 0 or more and 1 for a negative one, and the signed remainder is the dividend.
- **Signed division truncates toward zero, and the remainder takes the sign of the dividend**, as in C: -7 / 2 = -3, -7 mod 2 = -1, 7 / -2 = -3, 7 mod -2 = 1, so a = (a / b) × b + a mod b. -128 / -1 and -32768 / -1 wrap to themselves.
- **Shifts** by 16 or more give 0, or all sign bits for `sar16`.
- **The remainder.** `div8`, `div16`, `sdiv8` and `sdiv16` also leave a remainder in the exported word `remainder` (`div8` with a high byte of 0; the signed ones that of the magnitudes, to be given the sign of the dividend), so a program that needs a quotient and its remainder divides once. `mod8` and `mod16` do not go through `remainder`: each has its own copy of the loop and keeps everything in its own slots. `remainder` is one variable for the whole program, so a remainder passed through it could be changed by an interrupt handler that divides between the store and the load; the operator `mod` must not have that hole, and the copy costs only a program that uses both `/` and `mod` (19 or 44 bytes), nothing in one that uses one of them. A program that reads `remainder` while a handler divides reads it inside the `critical` block that holds the divide.
- **Speed.** `mul16` takes 8 passes instead of 16 when its second operand is below 256, so a caller with one small or constant operand passes it second. Every other routine's time depends only on its operand values, never on where they come from.

Measured against `lathe/src/num.lth`, the stand-in the Lathe-written lexer uses: `lextest` built with `num.mul`, `num.div` and `num.rem` replaced by `rt_math.mul16`, `div16` and `mod16` is 86 bytes smaller (139 bytes of arithmetic instead of 225), and lexing every `.lth` file in `lathe/` takes 4.7% fewer cycles (38% fewer on a file of 2000 lines of numbers).

## Generating the code

The compiler has no syntax tree and no optimiser pass. Code quality comes from five techniques that all work in one pass.

1. **Lazy operands.** Parsing an operand produces a description, not code: a constant, a variable at an address, a value now in A, a value in A and X, a condition held in the flags, an indexed element. Code is emitted only when an operator needs its operands somewhere. Constant folding, `INC` for `x += 1`, compare-and-branch for conditions and indexed addressing all fall out of this. It is the method of Wirth's one-pass compilers.
2. **Destination passing.** An assignment parses its left side first, so the right side knows where its result goes. A 16-bit `x = y + z` adds the low bytes into `x` and then the high bytes into `x+1`, never loading the pair into registers.
3. **Register tracking.** Within straight-line code the compiler remembers what A, X and Y hold, as a constant or a copy of a variable, and skips loads that would change nothing. The memory is cleared at every call and loop head; at a label that only forward branches reach it keeps what every way in agrees on.
4. **Operand order.** When the left operand is simple and the right is not, the right is evaluated first and the left used as a memory operand. When both are complex, the left is saved in a frame temporary.
5. **Short branches first.** A function's code is held in a buffer until the function ends. Forward branches are emitted short, and only those that turn out not to reach are widened to a reversed branch around a `JMP`. `p8c` widened every one.

Spike S3 hand-compiled four existing routines by these rules and got 1.47 times the size of the hand-written originals, with inner loops between 1.1 and 1.85 times the cycles. It also named the refinements worth adding once the basics work, in order of gain:

- Keep register knowledge across a label reached only by forward branches, by keeping what every incoming branch agreed on. (Done: `codegen.md`, "Remembering register contents".)
- Remember that A holds an indexed element such as `a[i]` while its index register is unchanged.
- Turn a loop tested at the top into one tested at the bottom.
- Keep a loop counter in X or Y when the body allows.

The 65C02's extra instructions (`STZ`, `BRA`, `INC A`, `PHX` and the rest) are used when the environment says the CPU has them.

## Known costs

- An argument stored into a slot and then loaded again by the callee costs more than a register would for tiny functions. `inline` is the remedy. What registers would save over a whole program is measured in [`spikes.md`](spikes.md) ("Result of L4").
- Calls between `recursive` functions copy a frame each way.
- A function used from two contexts is linked twice.
- Two functions in one pointer class cannot call each other without the cost of recursion.
- A variable's value is lost between calls unless it is `static`. This is a rule to learn, not a run-time cost.
