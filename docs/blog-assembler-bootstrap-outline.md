# Blog post outline: the bootstrapped assembler

An outline for a long-form post about [`asm/`](../asm/). Second draft, 2026-11-12, revised after the author's first review.

How to read it:

- Plain text is proposed content. Numbers were measured on the current tree unless noted.
- **[You]** marks what only the author can supply.
- **[Check]** marks claims to verify before publishing.
- **(optional)** marks sections meant to be collapsed by default (see "Format").

## Working titles

1. *Bootstrapping a 6502 assembler the way it could have been done in 1980*
2. *From 129 bytes to a macro assembler: eighteen assemblers, each built by the last*
3. *An assembler that never met another assembler*

Title 1 now matches the stated motive. Avoid "from nothing" in a headline; section 11 says why.

## Format

- **One post for two audiences.** The main line is the story, readable without 6502 knowledge. Technical detail goes in collapsed sections the reader can open: the HTML `<details>` element does this with no scripting, and works on GitHub Pages, most static site generators and in GitHub's own Markdown.
- **Collapsed by default:** the full stage table, each stage's detail, stage 17's internals, the memory map, the related-work notes.
- **Length:** about 3,000 words for the main line; perhaps as much again inside the collapsed sections.
- **Follow-up posts**, if this one lands: stage 17's internals; the editor; running the chain on a real board (section 13).
- **Hacker News** is a link aggregator: the post lives on your own site (or GitHub Pages) and you submit its URL. "Show HN" is for things readers can try, which this is, since the repository builds with one command. 6502.org's forum and r/beneater take links the same way.

## Reader and promise

- **Reader:** programmers curious about how tools get built; retro-computing readers second.
- **Promise:** the reader sees how a tool can be grown from a seed too small to be useful, why each step is the size it is, and how AI assistance changed what one person could attempt.

## 1. Opening hook

The first lines of stage 00, an assembler written as hex because nothing yet exists that can read mnemonics:

```
DATA $20 $06 $F0  ; 2000: JSR read
DATA $90 $03      ; 2003: BCC $2008
DATA $4C $80 $20  ; 2005: JMP eof ($2080)
```

Then a few lines of stage 17: ordinary assembly with local labels, macros and includes. Between them, one sentence: every step from the first to the second was assembled by the step before it, and all eighteen are still in the repository.

## 2. Why do this

The author's motive, to be written in the first person:

- **The question.** How could someone with an 8-bit machine in about 1980, and no assembler, have got to a good one? The post replays that process, using an emulator and a modern PC for convenience but keeping each step something the period machine could have done.
- **Keep every step.** In the 1980s the intermediate tools would have been overwritten as soon as the next one worked. Here the whole chain is kept and rebuilt on every change, as a permanent record of the route.
- **It started in the middle.** The work began in 2022 with an assembler written against an existing one (vasm) and already able to read mnemonics. The earlier, cruder steps were filled in afterwards to give an honest starting point. Say this in two or three sentences and move on. The repository shows it: the first commit of the present chain (2026-01-06) is a copy of the older chain; the hex seed arrived two days later, and the last use of the outside assembler was removed the day after that.
- **Inspiration.** A web page presenting a series of languages of increasing power, each editable and runnable in the browser. **[You]** My best candidate is Ben Lynn's *Compiler Quest* (<https://crypto.stanford.edu/~blynn/compiler/quest.html>), which builds a Haskell compiler through a chain of ever more capable compilers and, as I recall, has in-browser editors. **[Check]** I found the page by search but did not open it; confirm it is the one you remember. Another possibility is Edmund Grimley Evans's *bcompiler* (HEX1 to HEX5 and beyond), though that one is not browser-based.
- **What it is not:** a competitor to vasm or ca65.

## 3. The rules of the game

These followed from the motive; present them that way.

1. **No outside assembler.** 
2. **Each stage is assembled by the previous stage's binary.**
3. **A stage's source may only use what the previous stage understands.** A new feature cannot be used in the stage that introduces it.
4. **Everything runs on a 6502 with 64K**, reading its source as a stream of characters and writing bytes, as a machine with tape or disk would.
5. **Stages are frozen** once the next one works, with their tests.
6. **The last stage must reassemble itself byte for byte.**

## 4. The machine it runs on

- An emulated 6502 with a small table of host calls: read a byte, write a byte, and later open and close files and read arguments. Stage 00 uses two of them.
- The emulator stands in for a 1980 machine with a keyboard and a disk drive. It is a convenience, and section 11 is direct about that.
- A period touch worth stating: assembling stage 17 with itself takes 41.7 million CPU cycles, which is about 21 seconds on a 2 MHz 6502 before any disk time. **[Check]** One run of the debug build.

## 5. The seed

- **What it is.** Stage 00: 92 lines of source, 129 bytes of code. It reads lines of `DATA $XX` and writes the bytes. No labels, no mnemonics.
- **The C program is a stand-in for fingers.** `00/asm.c` turns stage 00's hex source into a binary. It does nothing a person at a hex keypad could not do: it transcribes the hex digits already written in the source. Say so plainly, since it answers the obvious objection.
- **How the seed was really written.** Honest and interesting: the original hand-made starting point (2022) was written with instructions and hand-calculated addresses in the margin, and working out branch offsets by hand was painful. The 129-byte seed in the repository was written later by an AI model, to the specification "the smallest assembler that can assemble itself", and was right first time. **[Check]** The log shows one fix the next day (a comment-handling bug found when stage 01 was added), so "nearly right first time" may be more exact.
- Show the old hand-annotated listing beside the new seed: `JSR F006 ; 2000 read_b` against `DATA $20 $06 $F0 ; 2000: JSR read`.

## 6. The climb

Tell it in acts: what hurt, what the stage added, what that made possible. The full table is collapsed.

### Act 1: getting out of hex (stages 01–04)

- **01** adds mnemonics, labels and strings, but is still written in hex. Its instruction table is spelled out byte by byte.
- **02** adds nothing. It is stage 01 rewritten in the mnemonics stage 01 understands, and the two binaries are identical (744 bytes). First appearance of the pattern to name: **teach, then use**.
- The early mnemonics carry the addressing mode in the name (`LDA#`, `LDAZ`, `LDA(),Y`), so the assembler needs no operand parser yet.
- **03** byte selectors, assignments, origin. **04** two passes, so labels can be used before they are defined: the end of hand-counted branch offsets.

### Act 2: growing up (stages 05–10)

- **05** hash tables. **06** the instruction table moves into a generator program built by the chain. **07** error messages with line numbers.
- **08** `.include`. In the 1980 framing this is the day the machine gets a disk drive: before it, one source stream (tape); after it, named files.
- **09** sections and arguments. **10** local labels and a heap.

### Act 3: the syntax migration (stages 11–12)

- **11** learns standard 6502 syntax but is written in the old one. **12** is the same assembler in the new syntax, with an identical binary.
- The rewrite was done by AI (the author recalls it writing a script for the conversion). The identical-binary check is what made a mechanical rewrite of the whole source safe to accept.

### Act 4: features that earn their keep (stages 13–16)

- **13** expressions. **14** conditional assembly. **15** macros. **16** `.byte`, `.word`, `.asciiz`, decimal numbers.
- Each feature is used by the next stage, so nothing was added on speculation.

### Act 5: the live assembler (stage 17)

- Stage 17 removes nothing. It adds `.ifndef` and `.else`, is rewritten in the final dialect that stage 16 taught, and is where development now happens: 8,345 lines in 29 files against stage 16's 5,086 in 12, with a test runner that runs on the 6502 itself.
- It is the fixed point the build checks on every change, in both its plain and debug builds.

### Which stages can assemble themselves (optional)

A correction to the usual telling, measured by having each stage's binary assemble its own source:

- **Fourteen of the eighteen stages self-host**, from stage 00 on. Self-hosting is the normal state of the chain, not something reached at the end.
- **Four do not: 04, 11, 13 and 16.** Each one changes the language in a way its own source has not caught up with:
  - 04 drops two instructions its own source still uses.
  - 11 takes only standard syntax, and is written in the old one.
  - 13 rejects an older form of data declaration its source still uses. **[Check]** The exact construct.
  - 16 replaces `.data` with `.byte`, and its generated instruction table still uses `.data`.
- So the pattern is: a stage that *replaces* syntax cannot build itself, and the next stage is the rewrite. A stage that only *adds* can.

### The chain in numbers (optional)

| Stage | Adds | Source lines | Binary (bytes) | Assembles itself |
|---|---|---|---|---|
| 00 | `DATA` only | 92 | 131 | yes |
| 01 | mnemonics, labels | 338 | 744 | yes |
| 02 | source in mnemonics | 376 | 744 (same as 01) | yes |
| 03 | selectors, assignments, origin | 507 | 942 | yes |
| 04 | two passes | 574 | 1,050 | no |
| 05 | hash tables | 823 | 1,564 | yes |
| 06 | instruction table generator | 1,498 | 17,959 | yes |
| 07 | diagnostics | 1,875 | 29,138 | yes |
| 08 | `.include` | 2,095 | 33,747 | yes |
| 09 | sections, arguments | 2,007 | image | yes |
| 10 | local labels, heap | 2,358 | image | yes |
| 11 | standard syntax | 3,373 | image | no |
| 12 | source in standard syntax | 3,395 | image (same as 11) | yes |
| 13 | expressions | 3,278 | image | no |
| 14 | conditional assembly | 3,547 | image | yes |
| 15 | macros | 4,532 | image | yes |
| 16 | data directives, decimal | 5,086 | image | no |
| 17 | `.ifndef`/`.else`, final dialect | 8,345 | image | yes |

From stage 09 the output is a fixed 57,344-byte memory image, so its size says nothing. Stage 17's code and tables are about 7.4 KB of it. The whole chain builds and checks itself in about 10 seconds on a current PC **[Check]**.

## 7. Trusting trust

- Ken Thompson's *Reflections on Trusting Trust*: a compiler can carry something its source does not show, passed on each time it compiles itself. The usual defence is to be able to rebuild the tool from something small enough to inspect.
- This chain is a small, complete example of that defence. Nothing in it is a binary handed down from an earlier build: every stage is rebuilt from source each time, starting from 129 bytes a person can read in an afternoon.
- **Be exact about what it settles.** It answers the question for the assembler's own lineage. It moves the trust to what lies underneath: the C compiler and emulator today, or on a real board the hardware and whatever lets the first bytes be keyed in. So it shows the remedy at small scale; it does not dispose of the problem.
- Related work to name briefly **[Check]**: the bootstrappable-builds community and its hex-seed projects (stage0), and David A. Wheeler's "diverse double-compiling".

## 8. Keeping it honest

- **The chain is its own test.** Any change that breaks an early stage breaks everything after it, at once and visibly.
- **Frozen tests per stage.** Stages 03 and 07 to 17 have their own test suites, and all of them run every time the chain is built, in CI on every push. Stage 17's suite, 515 tests today, is the definition of the dialect, and the assembler can run it on the 6502 itself.
- **A second implementation.** `pyasm.py` is a Python work-alike of the last stage, added on 2026-02-08. Its commit says what it is for: an independent implementation that passes the same tests and assembles the assembler's source to identical bytes, and so cross-checks it; it is also a way into the chain without the emulator.
- **Every stage must earn its keep.** The chain was once 24 stages and was cut to 18 on 2026-02-13, to make each step a real one and the whole presentable to others.
- **Backports.** Now and then a feature was added to an earlier frozen stage where that made more sense than a new stage. **[You]** One example and its reasoning would be enough.

## 9. Working with an AI

To be written candidly; this is the part many readers will come for.

- **By hand (2022–2025):** the original starting point with hand-calculated addresses, and the first chain up to a self-hosting assembler with hash tables and includes. **[You]** Confirm where the hand-written line ends; you said about the new-syntax stage.
- **With AI (from January 2026):** the hex seed, written retroactively; the conversion of the source to standard syntax; and much of the code from there on: expressions, conditional assembly, macros, the test runner. The author's part became design: discussing implementation approaches and optimisations, reviewing, and deciding what each stage should be.
- **What it changed:** ambition. Standard syntax, expressions and macros are the features that turn a bootstrap exercise into an assembler one can write a 10,000-line editor in, and they are the ones that would have taken longest alone.
- **Why it could be trusted:** the byte-identical check (the AI's suggestion) and the frozen tests. A rewrite either reproduces the binary or it does not. This is the general lesson: mechanical checks that cannot be argued with are what make generated code acceptable.
- The repository is open about it: commit messages carry co-author lines from the first day of the new chain.
- **[You]** One thing the AI got wrong or that needed steering would add balance.

## 10. Inside stage 17 (optional)

- Two passes; a hash table for labels and one for instructions.
- **Memory map figure:** [`images/asm17-memory-map.svg`](images/asm17-memory-map.svg). A heap growing up and a source stack growing down, sharing about 45 KB. Assembling itself, the assembler uses 14.6 KB of heap.
- Includes and macro calls are frames on the one source stack.
- A 6502 wrinkle: a forward reference to a zero-page variable costs a byte, so the editor declares all of them first. The assembler reports the count (23 in its own source).

## 11. Honest limits

- The seed is transcribed by a C program and the chain runs in an emulator written in C. The claim is "no outside assembler", and "nothing a 1980 machine could not do".
- It does not yet run on a real board (section 13).
- It targets the NMOS 6502 instruction set. **[Check]**
- **A hex loader would be the more honest seed.** Explain the difference in two sentences: `asm.c` runs on the PC and writes a file; a hex loader is a few dozen bytes on the 6502 itself (in ROM, or entered on switches) that takes hex digits from a keypad and puts them in memory, as the KIM-1's monitor and the Apple 1's did. Stage 00 is already close to one: it reads hex and writes bytes.

## 12. What it made possible

- The vi-like editor: about 10,700 lines in this dialect, built by stage 17, running in the emulator and on a real breadboard computer. One photo.
- The same pattern reused for a Prog8 compiler that compiles itself (a link).

## 13. What's next: the bring-up on a real board

A closing section that sets up a follow-up post. Ideas to choose from:

- **Run the last stage on a board.** It needs files. Michael is close, through storage on its FPGA bus. The assembler's only contact with the outside is its table of host calls (open, read, write, close), so the board needs those few calls implemented, and the assembler does not change.
- **Memory.** Code, heap and low memory come to about 24 KB when the assembler builds itself, more than Michael's 16 KB of RAM. Wendy 2 has room. **[You]** Which board?
- **Replay the whole climb on hardware.** Enter the seed on a hex keypad, then grow an editor in step with the assembler: a line-entry program first, a line editor once labels exist, the screen editor at the end. The need to type source text is what forces the editor to exist, which is a good story.
- **Period storage.** What the design asks of a disk is small: named files read from start to end, several open at once (one per level of include), and one output file. No seeking within a file.
  - Tape gives one stream, which is all stages 00 to 07 need.
  - A floppy with a simple sequential file system is enough from stage 08 on. A period controller chip (the WD1770 family) can be driven by a 2 MHz 6502, as the BBC Micro did.
  - Size matters: stage 17's source is 237 KB, more than a 140 KB Apple II disk, so a 1980 author would have used two drives or terser comments. It fits a 360 KB disk.

## 14. Closing

Return to the two excerpts. End with how to try it:

```bash
git clone https://github.com/pjdennis/6502-workbench
cd 6502-workbench/asm && ./asmtestgen.sh
```

## Figures and excerpts to prepare

1. Stage 00 source, first ten lines.
2. The 2022 hand-annotated listing beside the stage 00 seed.
3. Stage 01's hex-encoded instruction table beside stage 02's readable one.
4. The same routine in stage 10 and stage 12 syntax.
5. The chain as a diagram, with the four stages that cannot build themselves marked and the two identical pairs joined.
6. Source lines per stage, as a chart.
7. Stage 17's memory map (drawn: [`images/asm17-memory-map.svg`](images/asm17-memory-map.svg)).
8. The editor on screen and on Michael.

## Questions still open

1. Is *Compiler Quest* the page you remember?
2. Where exactly does the hand-written work end and the AI-assisted work begin: which stage, in today's numbering?
3. Should `asm.c` be replaced before the post goes out (for example by a small hex loader run in the emulator), or described as a stand-in and replaced later?
4. Which board is the target for running the assembler: Michael with more RAM, or Wendy 2?
5. Where will the post be hosted? That decides whether collapsible sections and an in-browser demo are easy.
6. An example each of a backport and of the AI needing correction.
