"""p8c - the host-side Prog8 compiler for wendy2c.

This is the "p0" stage of the Prog8 bootstrap chain (see
plan-for-wendy2c-prog8-compiler in the conversation context).
Reads .p8 source, emits .s in a syntax that asm17 accepts (and
that vasm6502_oldstyle also assembles, by design, so we get fast
iteration during early phases).

The compiler is deliberately small:
  * recursive-descent parser, hand-written lexer, no PLY/lark deps;
  * typed AST that's been name-resolved and scope-flattened by sema;
  * direct emission of 6502 from the AST (no IR), per the upstream
    Prog8 backend's "skip the IR" pattern.

Run:
    python3 -m p8c source.p8 -o source.s
    python3 -m p8c source.p8 --run     # compile + assemble + emulate

Conventions:
  * Symbol prefixing matches upstream Prog8 (p8v_, p8s_, p8c_, p8l_).
  * Static allocation everywhere; subroutines are not reentrant.
  * Default load address is $4000 (the wendy2c serial-upload target);
    override with `%address $XXXX` in the source.
"""
