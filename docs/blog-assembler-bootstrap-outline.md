# Blog post outline: the bootstrapped assembler

An outline for a long-form post about [`asm/`](../asm/), for review. Draft of 2026-11-12.

How to read it:

- Plain text is proposed content, taken from the repository. Numbers were measured on the current tree unless noted.
- **[You]** marks places where only the author knows the answer: motives, what was hard, what it felt like. Several have guesses to react to.
- **[Check]** marks claims to verify before publishing.

## Working titles

1. *From 129 bytes to a macro assembler: bootstrapping a 6502 assembler that builds itself*
2. *An assembler that never met another assembler*
3. *Eighteen assemblers, each built by the last*

Title 1 says the most. Avoid "from nothing" in the headline: the seed is a C program and the chain runs on an emulator written in C, and readers will point that out (see section 10).

## Reader and promise

- **Reader:** programmers curious about how tools get built, including people who have never written 6502 code. Retro-computing readers are the second audience.
- **Promise:** by the end the reader understands how a tool can be grown from a seed too small to be useful, why each step is as small as it is, and what "self-hosting" proves.
- **Length:** 3,000–4,000 words, plus code excerpts and two tables.
- **Assumed knowledge:** what an assembler is, roughly. Explain two-pass assembly, forward references and zero page in a sentence each when they first appear.

## 1. Opening hook

Start with the first lines of stage 00's source, which is an assembler written as hex bytes because nothing exists yet that can read mnemonics:

```
DATA $20 $06 $F0  ; 2000: JSR read
DATA $90 $03      ; 2003: BCC $2008
DATA $4C $80 $20  ; 2005: JMP eof ($2080)
```

Then the last stage's source, which is ordinary assembly with local labels, macros and includes. One sentence between them: every step from the first to the second was assembled by the step before it.

## 2. Why do this

**[You]** This section needs your voice. Candidate motives, inferred from the repository; keep, cut or correct:

- **The first assembler had an asterisk.** asm1 (2022–2025) reached self-hosting on 2025-11-15, but it was seeded by a version written for vasm. It could build itself, yet it could not have existed without someone else's assembler. asm2 started seven weeks later. Was removing that dependency the trigger?
- **To understand the whole stack.** The boards came first (2020–2022): hardware you wired, firmware you wrote. The assembler was the one part of the toolchain you had not made.
- **A use for it.** The plan to write real software for the boards in your own dialect: the editor followed a month later and now runs on Michael.
- **The puzzle itself.** How small can the seed be, and what is the smallest useful next step?
- **[You]** Was there an outside inspiration (a bootstrapping project, a book, Ben Eater's approach of building up from parts)?
- **[You]** Why a second assembler from scratch rather than fixing asm1's seed?

Also worth one paragraph: what you did *not* set out to do (compete with vasm or ca65, target other CPUs).

## 3. The rules of the game

State these as a short list; the rest of the post leans on them.

1. **No outside assembler, ever.** The only host tools are a C compiler (for the seed and the emulator) and a shell script to run the stages in order.
2. **Each stage is assembled by the previous stage's binary.**
3. **A stage's source may only use syntax the previous stage understands.** This is the constraint that shapes everything: a new feature cannot be used in the stage that introduces it.
4. **The final stage must reassemble itself byte for byte.**
5. **Everything runs on a 6502** with 64K of memory.
6. **Stages are frozen** once the next one works. Only the last stage is developed.

**[You]** Were these rules set at the start, or did some emerge along the way?

## 4. The machine it runs on

Brief, so the reader knows what "runs on a 6502" means here.

- An emulated NMOS 6502 with a small table of host calls at `$F006` onward: read a byte, write a byte, write to the error stream, and later files and arguments.
- Stage 00 uses exactly two of them: read and write.
- **[Check]** Be direct that the assembler runs in the emulator, not yet on one of the boards. **[You]** Is running it on Michael or Wendy 2 a goal? What is missing (storage)?

## 5. The seed

- `00/asm.c`: a C program of about 130 lines that understands `DATA $XX`, quoted strings and comments. It exists only to turn stage 00's source into a binary.
- Stage 00's source: 92 lines, 129 bytes of code. Every instruction encoded by hand, every branch offset and address worked out by hand, with the intended instruction in a comment and a hand-drawn layout map at the top (`$2000: main (47b)`, `$202F: skip_sp (17b)` and so on).
- What it can do: read `DATA $XX` lines and emit the bytes. No labels, no mnemonics, no program counter. It is an assembler in the thinnest sense, and it is immediately able to assemble a copy of itself.
- **[You]** How was the hex produced: fully by hand, or with help from another tool and then checked? Readers will ask.
- **[You]** How long did the seed take? Any memorable bug from a miscounted branch offset?

## 6. The climb

The centre of the post. Group the 18 stages into acts and tell each as "what hurt, what the stage added, what that made possible". Don't walk every stage; the full table goes in a sidebar.

### Act 1: getting out of hex (stages 01–04)

- **01** adds mnemonics, labels and strings, but is itself still written in hex, because stage 00 can read nothing else. Its instruction table is spelled out byte by byte, with the text it means in a comment: `DATA $4C $44 $41 $23 $00 $00 $A9 ; DATA "LDA#" $00 $00 $A9`.
- **02** adds no features at all. It is stage 01 rewritten in the mnemonics stage 01 understands, and the two binaries are identical (both 744 bytes). This is the first appearance of a rhythm worth naming: **teach, then use**. One stage learns a syntax; the next is rewritten in it and must produce the same bytes, which proves the rewrite.
- The mnemonics are non-standard: `LDA#`, `LDAZ`, `LDA(),Y`. The addressing mode is part of the name, so the assembler needs no operand parser yet. A neat trick to explain.
- **03** byte selectors, assignments, setting the origin. **04** two passes, so a label can be used before it is defined.
- Payoff: by stage 04 the source reads like a program instead of a puzzle.

### Act 2: growing up (stages 05–10)

- **05** hash tables: linear search through labels was the first thing to stop scaling.
- **06** the instruction table moves into a generator program (`instgen`), itself built by the chain. The binary jumps from 1.5 KB to 18 KB here; explain why.
- **07** error messages with line numbers. **[You]** What was debugging like before this stage existed?
- **08** `.include` and a file stack. **09** zero-page and code sections, command-line arguments. **10** local labels and a heap.
- Payoff: the source splits into several files, and names stop colliding.

### Act 3: the syntax migration (stages 11–12)

- **11** learns standard 6502 syntax, all 13 addressing modes, but is written in the old syntax, so it cannot assemble itself.
- **12** is the same assembler rewritten in standard syntax. Teach, then use, again: the two binaries are identical.
- **[You]** Was the rewrite by hand or scripted? How long did it take, and did the identical-binary check catch mistakes?

### Act 4: conveniences that earn their keep (stages 13–16)

- **13** expressions. **14** conditional assembly. **15** macros and shift operators. **16** `.byte`, `.word`, `.asciiz`, decimal numbers, memory protection.
- Each is used by the following stage, so every feature had a customer before it was written. A good place for the theme: nothing was added on speculation.

### Act 5: closing the loop (stage 17)

- Stage 17 is assembled by stage 16, then assembles itself, and the result must match. It must also match in its debug build.
- Explain what this fixed point proves and what it doesn't (section 7).
- **[You]** The moment it first matched: when, and what was the last bug in the way?

### Sidebar: the chain in numbers

Source lines are for the stage's `.asm` files. Binary sizes from stage 09 on are a fixed 57,344-byte memory image, so they stop being informative; use source lines there.

| Stage | Adds | Source lines | Binary (bytes) |
|---|---|---|---|
| 00 | `DATA` only | 92 | 131 (129 of code and a 2-byte start address) |
| 01 | mnemonics, labels | 338 | 744 |
| 02 | source in mnemonics | 376 | 744 (identical to 01) |
| 03 | selectors, assignments, origin | 507 | 942 |
| 04 | two passes | 574 | 1,050 |
| 05 | hash tables | 823 | 1,564 |
| 06 | instruction table generator | 1,498 | 17,959 |
| 07 | diagnostics | 1,875 | 29,138 |
| 08 | `.include` | 2,095 | 33,747 |
| 09 | sections, arguments | 2,007 | image |
| 10 | local labels, heap | 2,358 | image |
| 11 | standard syntax | 3,373 | image |
| 12 | source in standard syntax | 3,395 | image (identical to 11) |
| 13 | expressions | 3,278 | image |
| 14 | conditional assembly | 3,547 | image |
| 15 | macros | 4,532 | image |
| 16 | data directives, decimal | 5,086 | image |
| 17 | self-hosting, `.ifndef`/`.else` | 8,345 | image |

The whole chain, seed to self-check, builds in about 10 seconds on a current PC. **[Check]** Measured once in a cloud container, emulator build included; re-time on your machine.

## 7. What self-hosting proves

- Assembling itself to identical bytes shows the assembler is a fixed point: it understands every feature its own source uses, and it is deterministic.
- It does not show the assembler is correct for programs unlike itself. That is what the test suite is for (section 8).
- Link to the wider idea of bootstrappable builds and "trusting trust" in two or three sentences, without overclaiming. **[Check]** Name related work accurately if you cite it (for example the stage0/hex0 projects); I have not verified details.

## 8. Keeping it honest

How the chain stays working, which is what makes this more than a one-off stunt.

- **Tests as the language definition.** The stage 17 test files are the specification of the dialect: 515 tests pass today. The assembler can also run them itself, on the 6502, when built with its test runner.
- **The whole chain is rebuilt and checked** on every push in CI.
- **A second implementation.** `pyasm.py` is a Python work-alike. **[You]** What is it for: cross-checking, speed, something else?
- **Renumbering.** The chain was once 24 stages (00–23) and was consolidated to 18 on 2026-02-13. Explain why some steps turned out to be too small, and how you merged frozen stages safely.
- **Changing a frozen stage.** The log shows at least one backport (`.reserve`). **[You]** What is the rule for when that is allowed?

## 9. Inside stage 17 (optional deep-dive)

For readers who want internals. Could be a separate follow-up post.

- Two passes, with a hash table for labels and one for instructions.
- Memory: a heap growing up from the end of the code and a source stack growing down from `$F000`, with an out-of-memory check where they would meet. Includes and macro expansions are both frames on that one stack.
- Macros: capture, parameters, local scope. The May 2026 rework unified the include stack and macro frames; `asm/docs/` has the design notes.
- A 6502-specific wrinkle worth showing: a forward reference to a zero-page variable is assembled as a longer absolute instruction, which is why the editor declares all its zero-page variables before any code.

## 10. Honest limits

Put these in the post yourself, before the comments do.

- The seed needs a C compiler, and the emulator is C. The claim is "no external *assembler*", not "no external software".
- It runs in an emulator with host calls for files, not on bare hardware.
- It targets the NMOS 6502 instruction set. **[Check]** Confirm 65C02 instructions are not supported.
- Stage 00 could in principle be typed in by hand, replacing `asm.c`. **[You]** Have you considered a hex loader as the true seed?

## 11. What it made possible

- The vi-like editor: about 10,700 lines in this dialect, built by stage 17, running in the emulator and on a real breadboard computer. One screenshot or photo here carries the point.
- The same bootstrap pattern reused for a Prog8 compiler that compiles itself (a link, not a digression).

## 12. Lessons

**[You]** Yours to write. Prompts:

- What surprised you about how small a useful step can be?
- "Teach, then use" as a general technique for changing a language under a program written in it.
- Which stage would you design differently now?
- AI assistance: the 2026 work used it. Say how, and what the byte-identical check and the tests meant for trusting generated changes. Readers will be interested and some will be sceptical; a concrete account is better than leaving it out.
- What is next: running on the board, 65C02 support, anything else.

## 13. Closing

Return to the two excerpts from the opening. End with how to try it:

```bash
git clone https://github.com/pjdennis/6502-workbench
cd 6502-workbench/asm && ./asmtestgen.sh
```

## Figures and excerpts to prepare

1. Stage 00 source, first ten lines (the hook).
2. Stage 01's hex-encoded instruction table next to stage 02's readable one.
3. The same routine in stage 10 syntax and stage 12 syntax, side by side.
4. A diagram of the chain: boxes 00–17 with arrows, and the "teach, then use" pairs (01–02, 11–12) highlighted.
5. A chart of source lines per stage.
6. Stage 17's memory map.
7. The editor running, on screen and on Michael.

## Open questions for you

1. Which audience first: general programmers (Hacker News style) or 6502 hobbyists? It changes how much section 9 belongs in the main post.
2. One post or a series (the story, then the internals)?
3. How much of asm1's history to include: a paragraph of motivation, or its own section?
4. Are you comfortable discussing the AI assistance in detail?
