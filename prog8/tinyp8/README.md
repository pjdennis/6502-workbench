# tinyp8 — 6502-native compiler proof-of-concept

A deliberately tiny compiler **written in 6502 assembly** that runs
inside the emulator on the nmos-default machine. It reads a `.tp8`
source file via the emulator's file-I/O ABI (`open` `$F012`, `read`
`$F018`), emits 6502 machine code into another file (`openout` `$F021`,
`write` `$F024`), and exits cleanly. The compiled output is itself
a 6502 program; running it on the emulator produces the expected
stdout.

This isn't the real Prog8 compiler -- it accepts a trivially small
fragment of the language. Its purpose is to **prove the on-target
compilation concept** before we sink Phases 2-4 into preparing the
host-side `p8c` for self-hosting.

## Language (v0)

```
print "string literal"     ; emit one (lda + jsr write_b) per char + \n
print_ub $XX               ; emit code that prints byte $XX as 2 hex chars + \n
end                        ; emit (lda #0 ; jsr exit)
; comments to end of line; blank lines allowed
```

One statement per line. The compiler is forgiving: unknown lines are
skipped, malformed `print_ub` cleanly aborts compilation.

## What it proves

* A compiler can run on the 6502 (well, the emulator's 6502 — same ISA).
* The runtime-I/O model -- source-in-via-file, code-out-via-file --
  works, including the cleanup pattern (close handles before exit).
* The wrap-as-runnable step (body + reset vector) gives us a way to
  *execute* the compiler's output for end-to-end verification.
* The test harness ("compile via emulator → run output via emulator →
  diff captured stdout") is a real, repeatable verification path.

## What it doesn't prove

* That the *real* p8c (Phase 5) fits in 32 KiB.
* That a Prog8-language-complete compiler is feasible -- tinyp8 is
  not even a tokenizer in the usual sense, just a line dispatcher.
* That this compiles itself -- tinyp8 is hand-written asm; the
  source-level self-host comes from a real p8c written in real Prog8.

## Layout

    tinyp8/
        tinyp8.s            # the compiler -- assembled by vasm
        __main__.py         # Python driver: build, run, wrap, run-out
        out/tinyp8.bin      # cached vasm output
        tests/
            test_e2e.py     # discovers goldens/*.tp8 and runs them
            goldens/
                01_hello.tp8 + .expected.stdout
                02_multi.tp8 + .expected.stdout
                03_bytes.tp8 + .expected.stdout
                04_mixed.tp8 + .expected.stdout

## Use

    # one-shot: compile via emulator, wrap, run, print captured stdout
    python3 -m tinyp8 hello.tp8 --run-out

    # compile only (leaves hello.body next to the source)
    python3 -m tinyp8 hello.tp8

    # run the test suite
    make -C toolchain/prog8 tinyp8-test
