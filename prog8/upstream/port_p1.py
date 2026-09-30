#!/usr/bin/env python3
"""Shared helper for the upstream-Prog8 pipeline porter (port_pipeline.py) and
the slab baker (bake_slabs.py).

Historically this module also transformed p1/p1.p8 (our p8c model) into upstream
source: a structural `main`/`start` wrap, byte-index casts, truthy `!= 0`, the
out_text long-literal split, and the I/O `%asm`-string -> register-ABI asmsub
rewrite. Every one of those is now BAKED into the source itself -- p1.p8 and the
pipeline `_sh` files are authored in the one converged dialect both p8c and
upstream Prog8 accept -- so the transform pipeline is gone. All that remains is
the comment-splitting utility the porter + slab baker still share."""


def _split_comment(line):
    """Split a line into (code, comment) at the first `;` outside a string."""
    instr = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"' and not (i and line[i - 1] == "\\"):
            instr = not instr
        elif c == ";" and not instr:
            return line[:i], line[i:]
        i += 1
    return line, ""
