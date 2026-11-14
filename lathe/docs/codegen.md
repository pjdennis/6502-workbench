# Lathe: code generation rules

Status (2026-11-13): the rules the compiler follows from stage 2 on. [`code-model.md`](code-model.md) says what the compiled program looks like from outside; this says how EXPR and GEN produce it. Where a rule here turns out wrong in practice, change the rule and the code together.

## Operands

Parsing an operand pushes a description on the operand stack. No code is emitted until something needs the value.

| Kind | Describes | How its byte *k* is reached |
|---|---|---|
| Constant | A number, typed or not yet typed. | Immediate. |
| Address | The address of a variable, slot, function or constant data, plus an offset. | Immediate low or high byte. |
| Variable | A slot, module-level variable or fixed address, plus a constant offset (a field, a constant index, `hi()`). | Absolute, or zero page when known. |
| Element | An array element with a variable index: a base as for Variable, and an index variable. | `LDX index`, then absolute,X. |
| Target | What a pointer points at: a pointer variable in zero page, and an index that is a constant or a variable. | `LDY` index, then `(pointer),Y`. |
| In A | A byte value now in A. | — |
| In A and X | A two-byte value: low in A, high in X. | — |
| Condition | A test now in the flags, with the flag state that means true, and two labels that earlier parts of the test already branch to: one for true, one for false. | — |

Rules for building them:

- **Constant index.** `a[3]` and `r.field` add to the offset of a Variable; nothing is emitted.
- **Column storage.** Byte *k* of element *i* of a column-stored array of *N* elements is at base + *k*·*N* + *i*. The index register is loaded once for all the bytes. An array of records is stored the same way, one column per byte of the record.
- **Fields.** A field is a constant offset times the stride, then a change of type, as a constant index is: `r.kind` adds the field's offset to the offset of a Variable, `syms[i].kind` adds it times *N* to the base of an Element (`LDX i` / `LDA syms+2*N,X`), and `p.kind` adds it to the offset of a Target, so it is `LDY #2` / `LDA (p),Y`. `p.field` is `p[0].field`. A variable index into an array field of a Target, `p.marks[i]`, is added to where the array is in a temporary that Y is loaded from.
- **Whole records** are copied byte by byte, as any value is, from whichever form the source and the target have.
- **Computed index.** If the index is not a constant or a plain variable, it is evaluated and stored in a byte temporary, which then serves as the index variable. A constant added to or subtracted from a variable index is folded into the base: `a[i + 1]` is `LDX i` / `LDA a+1,X`.
- **Pointers.** The pointer of a Target must be a zero page variable. A local or module-level pointer variable that is dereferenced becomes "must be in zero page". Any other pointer value (a field, an element, a call result, a variable of another module not declared `zp`) is first copied to a zero page temporary.
- **Arrays use X, pointers use Y.** Absolute,X exists for every instruction that takes memory, including `INC` and `ASL`; `(zp),Y` is the only practical indirect form.
- **One description for all three.** An Element and a Target are Variables with a mode (absolute,X or (zp),Y) and an index, which is itself a constant or a byte Variable. Byte *k* of a Variable is at its offset plus *k* times a stride: 1, or *N* for an element of an array stored by column. A constant index adds to the offset (for a Target, to the offset added to Y), so `grid[1][2]` and `hi(w[i])` are found the same way.
- **A pointer that is the target.** A value reached through the pointer it is stored in, `p = p.next`, is loaded into A and X before the store, or into a temporary if an operation on it is pending: storing the low byte would change the pointer.
- **Which index register.** X, except for `LDX`, which has only absolute,Y: a word element goes to A and X as `LDX i` / `LDA a,X` / `LDY i` / `LDX a+N,Y`. A word in A and X that is stored in an element goes through a temporary, because the element's index needs X. Only A is loaded from or stored through a pointer; `INC`, `DEC` and the shifts of what a pointer points at are done in A (`INC` as `CLC` / `ADC #1`). Byte *k* of a Target with a variable index is `LDY i` and *k* `INY`s.
- **Big arrays.** A variable index into a byte array of more than 256 elements, or into a `rows` array of elements larger than a byte, is shifted by the element size and added to the array's address, in a word temporary that becomes "must be in zero page"; the element is then a Target with Y = 0. A constant added to such an index is folded into the address as for small arrays.
- **Address.** `@x` is an Address, whose bytes are immediates with a low or high byte fix-up (`LDA #<x+3`). `@` of an element with a variable index adds the index to the Address, in the usual way.

## Never forcing zero page

**The compiler's choice of instruction never makes a variable "must be in zero page".** Only two things do: the program declares it `zp`, or the program dereferences it as a pointer, which the 6502 can only do through zero page.

- Every instruction the compiler emits on a variable has an absolute form, so the linker stays free to place the variable anywhere.
- `STX v,Y` and `STY v,X` exist only in zero page form. The compiler does not emit them, except on a variable that is already "must be in zero page" for one of the two reasons above.
- In an `asm` block the programmer chooses the instruction. Writing a zero-page-only form there, or an indirect mode, on a variable makes that variable "must be in zero page". That is the programmer's decision, visible in the source.

`lathe/tests/test_no_forced_zp.py` checks the recorded output of every snapshot case for this.

## Owning a register

At most one pending operand is "In A", one "In A and X", one Condition.

- Before the compiler emits anything that changes A while a pending operand is In A, it stores that operand in a temporary, and the operand becomes a Variable. The same holds for A and X together.
- A Condition is consumed at once by `if`, `while`, `until`, `and`, `or`, `not`, or a conditional branch. Anything else that receives a Condition first turns it into 0 or 1 in A.

Temporaries are slots of the current function, handed out and returned like a stack. Value temporaries are class "either"; pointer temporaries are "must be in zero page".

## Bytes

For `a OP b` with the result in A:

| Situation | Code |
|---|---|
| `b` can be addressed directly (Constant, Variable, Element, Target) | Load `a` into A; apply `OP` with `b` as the instruction's operand. |
| `b` had to be computed into A, `a` can be addressed, `OP` commutes (`+ & \| ^`) | Apply `OP` with `a` as the operand. |
| `b` was computed into A, `OP` does not commute | Store `b` in a temporary; load `a`; apply `OP` with the temporary. |
| Both were computed | `a` was stored in a temporary when `b` needed A; then as the rows above. |

- `+` is `CLC` / `ADC`; `-` is `SEC` / `SBC`; `& | ^` are `AND`, `ORA`, `EOR`.
- Adding or subtracting the constant 1 to a Variable or Element that is also the destination is `INC` or `DEC` on memory. Operations whose constant operand changes nothing (`+ 0`, `| 0`, `& $FF`, `^ 0`) emit nothing.
- A shift by a constant is that many `ASL A` or `LSR A`, or `ASL`/`LSR` on memory when the destination is the left operand. A shift by a variable is a counted loop.
- `*`, `/` and `mod` by a constant power of two are shifts and masks. Otherwise they are calls to the run-time module `rt_math`.
- Unary `-` is `EOR #$FF` / `CLC` / `ADC #1`; `~` is `EOR #$FF`.

## Words

A two-byte operation needs somewhere to put its low byte while it computes the high one, so it is always given a destination.

- **Assignment** passes its left side as the destination: `x = y + z` is `CLC` / `LDA y` / `ADC z` / `STA x` / `LDA y+1` / `ADC z+1` / `STA x+1`.
- **An argument** passes the callee's parameter slot as the destination.
- **`return`** and anything else with no memory destination uses A and X, holding the low byte in Y meanwhile: `… ADC z` / `TAY` / `LDA y+1` / `ADC z+1` / `TAX` / `TYA`.
- **An operand of a larger expression** uses a word temporary as the destination.
- `w += 1` is `INC w` / `BNE` / `INC w+1`. `w += b` with `b` a byte is an 8-bit add and `BCC` / `INC w+1`. `w -= 1` is `LDA w` / `BNE` / `DEC w+1` / `DEC w`.
- A `byte` operand in a word operation has a high byte of constant 0, and operations with a zero operand byte are simplified as for bytes.
- Shifts are `ASL lo` / `ROL hi` and `LSR hi` / `ROR lo`, in memory. A shift by 8 to 15 places, except a signed shift right, moves a byte instead: `w << 8` is `LDA w` / `STA` hi / `LDA #0` / `STA` lo, `w >> 8` the mirror image, and each place beyond 8 is one `ASL A` or `LSR A` on the byte that moves (`lathe/tests/cases/snap/shift_bytes.lth`).

## Comparisons and conditions

| Comparison | Code | True when |
|---|---|---|
| byte `==` `!=` | `LDA a` / `CMP b` | Z set / Z clear |
| unsigned byte `<` `>=` | `LDA a` / `CMP b` | C clear / C set |
| unsigned byte `>` `<=` | operands swapped, then as `<` `>=` | |
| `x == 0`, `x != 0` just after `x` was loaded | no `CMP` | Z |
| word `==` `!=` | `LDA a` / `CMP b` / `BNE` false-or-true label / `LDA a+1` / `CMP b+1` | Z |
| unsigned word `<` `>=` | `LDA a` / `CMP b` / `LDA a+1` / `SBC b+1` | C |
| signed `<` `>=` | subtract as above, then `BVC` over `EOR #$80` | N set / N clear |

- `and` and `or` evaluate the right side only when needed. `a and b` branches to the false label if `a` is false, then evaluates `b`. `or` is the mirror image. `not` swaps the true and false labels and the flag state.
- A `bool` variable used as a condition is `LDA v` and "true when Z clear".
- A Condition becomes a value as `LDA #0` / `ROL A` when it is "C set", and otherwise as a branch over `LDA #1` to `LDA #0`.
- A `bool` result returned from a function is put in the carry flag: a comparison that already leaves it there costs nothing more.

## Statements

| Statement | Shape |
|---|---|
| `if` | Branch on false to the next `elif`/`else`/`end`; `JMP` to the end after each part but the last. |
| `while` | Label; test; branch on false to the exit; body; `JMP` to the label. |
| `loop … end` | Label; body; `JMP` to the label. |
| `loop … until c` | Label; body; test; branch on false to the label. |
| `for i = a to b` | `i = a`; unless the test is known, skip the loop if `a > b`, with `a` the constant if it is one (`for i = 0 to n` needs no test); label; body; the point `continue` goes to; if `i == limit` exit; `INC i`; `JMP` label. The limit is copied to a temporary unless it is a constant or a plain variable, which is read at each test: a body that changes it changes the loop (this costs nothing, where a copy costs a store and a temporary in every loop). The way back is a `BNE` instead of the `JMP` where the step cannot give 0: an unsigned count up (`i` is below the limit, so never 255 or $FFFF), and a byte count down to a constant from 1 to 127. A word counts up as `INC i` / `BNE` label / `INC i+1` / `BNE` (or `JMP`) label. `downto` mirrors this with `DEC`; `downto 0` on a byte is `LDA i` / `BEQ` exit / `DEC i` / `JMP` label, and `DEC i` / `BPL` would be wrong for values above 127. |
| `break`, `continue` | A `PLP` for each `critical` block inside the loop that it leaves; `JMP` to the exit or to the point where the next pass begins. A branch around nothing but a `JMP` is fused into one branch. |
| `case` | The selector is loaded into A (stored in a temporary first unless it is a variable; a variable at a fixed address is copied too, since it may be a device, and so is an element, which the register memory cannot remember in A). For each `of`: `CMP #c` / `BEQ body` for each constant but the last, `CMP #c` / `BNE next` for the last; body; `JMP` end, left out after the last `of` when there is no `else`. Every way into a body and into `next` has the selector in A, so the register memory knows it there (by the rule for labels that only forward branches reach) and it is reloaded only where the body before changed A. `CMP #0` just after the load is left out. |
| `critical` | `PHP` / `SEI`; body; `PLP`. After a `PLP` nothing is known about the flags. |
| `return` | Result into A, A and X, or carry; a `PLP` for each `critical` block it is inside; then `RTS`, or a `JMP` to the function's exit code if it has any. `return f(…)` with matching results is `JMP f`, except inside `critical`. A status cannot be returned from inside `critical`: the `PLP` would change the carry. |

A `JSR` followed directly by `RTS`, with no label between them, becomes a `JMP`. When the function ends, a `JMP` to a label whose next instruction is an `RTS` becomes that `RTS` (a branch to one stays a branch; a `JMP` an `asm` block wrote stays as written). Threading a `JMP` to a `JMP` was tried and saved nothing on `lextest`.

## Calls

1. Each argument is evaluated with the callee's parameter slot as its destination, in order.
2. While arguments are pending, any other call records the outer callee in its `CALL` record ([`object-format.md`](object-format.md)).
3. `JSR`. Everything known about the registers is forgotten.
4. The result is an operand: In A, In A and X, or a Condition "C set".

For `extern` and `asm` functions the arguments go in registers: each argument is evaluated; one that is not a Constant or Variable is stored in a temporary; then Y, X and A are loaded, in that order.

For a call between `recursive` functions the caller's frame is pushed first, the arguments are computed into temporaries and then moved, and the frame is popped after the call with the result registers preserved (stage 5).

## Remembering register contents

- After a load or store, the compiler remembers that A, X or Y holds a given constant or a copy of a given Variable, and that the N and Z flags reflect A.
- A load of what a register already holds is skipped. If another register holds it, a transfer (`TAX`, `TAY`, `TXA`, `TYA`) is used.
- A store remembers too: after `STA v`, A holds `v`. What usually spoils this is the next byte: a word copied from memory to memory goes through A twice, so its low byte is gone by the time it is used again. So the high byte of such a copy goes through X (`LDA y` / `STA x` / `LDX y+1` / `STX x+1`) when no operand is in the registers: A and X then hold the whole word, as an argument or a result wants it.
- A store to a variable forgets every register that held a copy of a variable that might be the same memory: the same variable at an overlapping offset, any Element of the same array, and, after a store through a pointer, everything except constants.
- What an Element or a Target holds is never remembered, but its index is: `a[i] = b[i]` loads X once, and an index that A holds is moved by `TAX` or `TAY`.
- Everything is forgotten at a call, and at a label that a later branch will reach (the top of a loop).
- **At a label that only forward branches reach**, the compiler has seen every way in when it places the label. Each branch or `JMP` to a label still to be placed keeps what the registers hold at that point, as one of a few saved states (eight); a second branch to the same label keeps only what the two agree on, and so does joining two labels. At the label, what is known is what the saved state and the code falling in from above agree on, or the saved state alone if the code above ends in a jump or return. Only constants and copies held on every way in survive; the flags are forgotten. With no saved state free, nothing is known at that label. The common case: `CMP #$28` / `BNE` .L1 / `LDA #$05` / `RTS` / .L1: A still holds what it was compared from, so it is not loaded again. Only REG adds branches, jumps and joins outside `asm` blocks, so no way in is missed (`lathe/tests/test_reg.py`).

## Weights

Every use of a slot or module-level variable in an instruction adds to its weight: 1 outside loops, 4 inside one loop, 16 inside two, 64 inside three or more. The weight stops at 255.

## Initial values

A module-level or `static` variable with an initialiser is recorded as it is declared (the variable and its constant value, or the constant data to copy for an array). At the end of the module the compiler writes the function `module.$init` from that list: `LDA #` / `STA` for scalars, with the usual register memory so that equal values are loaded once, and a copy loop from constant data for arrays. If the list fills up, the compiler writes what it has as `module.$init` part functions and chains them.

The copy loop moves whole pages with `LDX #0` / `LDA data,X` / `STA var,X` (one pair per page) / `INX` / `BNE`, then the rest with `LDX #n` / `LDA data+p-1,X` / `STA var+p-1,X` / `DEX` / `BNE`. A local array with an initialiser gets the same loop on every entry to its function. The constant data is a `DATA` record laid out as the array is (by column if its elements are larger than a byte), and so is a constant table: `DFIX` entries fill in the elements that are addresses.

## Naming

String literals and other anonymous constant data are symbols `module.$1`, `module.$2`, … in order of appearance. A `static var` in a function is the module-level symbol `module.function.name`.
