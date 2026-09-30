#!/usr/bin/env python3
"""Bake the pipeline's >256-element arenas into peek/poke "slabs" IN PLACE.

This is the native (p8c-compilable) twin of port_pipeline.py's slab rewrite.
Each typed array decl with > 256 elements becomes a `const uword <name> =
$BASE` (a fixed RAM base address just below the $F000 I/O floor) and every
`<name>[idx]` access is rewritten to peek/poke:

    uword arena read   arr[i]      -> peekw($BASE + (i << 1))
    uword arena write  arr[i] = v  -> pokew($BASE + (i << 1), v)
    ubyte arena read   arr[i]      -> peek($BASE + (i))
    ubyte arena write  arr[i] = v  -> poke($BASE + (i), v)

The `<< 1` (rather than `*2`) offset form is used because p8c supports uword
`<<` but not `*`. p8c places code/data from $0200 upward and never allocates
storage for the slab addresses, so the arenas live at the fixed bases. After
this transform the source has NO arrays > 256 elements and no uword-indexed
arrays -- exactly upstream's array model.

Run once per pipeline pass; edits the file in place. Idempotent-ish: re-running
finds no `[\\d+]` arena decls (they are now consts) so it is a no-op.

Usage: bake_slabs.py <pipeline_pass.p8>
"""
import re
import sys
import port_p1   # only for _split_comment

IO_FLOOR = 0xF000
SLAB_THRESHOLD = 256

DECL = re.compile(r'(?m)^([ \t]*)(uword|ubyte)\[(\d+)\][ \t]+([A-Za-z_]\w*)(.*)$')

path = sys.argv[1]
src = open(path).read()

# ---- 1. discover slab arrays (typed array decls with > 256 elements) ----
slabs = {}          # name -> (esize, base)
order = []          # (name, esize, count) in declaration order
for m in DECL.finditer(src):
    etype, count, name = m.group(2), int(m.group(3)), m.group(4)
    if count > SLAB_THRESHOLD:
        esize = 2 if etype == "uword" else 1
        order.append((name, esize, count))

if not order:
    print("%s: no arenas > %d -- nothing to bake." % (path, SLAB_THRESHOLD))
    sys.exit(0)

# ---- 2. lay the slab region out just below $F000 ----
total = sum(esize * count for _, esize, count in order)
slab_base = IO_FLOOR - total
slab_base &= 0xFF00                       # page-align the base
addr = slab_base
for name, esize, count in order:
    slabs[name] = (esize, addr)
    addr += esize * count
assert addr <= IO_FLOOR, "slab region overruns the I/O floor"


def slab_read(name, inner):
    esize, base = slabs[name]
    if esize == 1:
        return "peek($%04x + (%s))" % (base, inner)
    return "peekw($%04x + ((%s) << 1))" % (base, inner)


def slab_write(name, inner, rhs):
    esize, base = slabs[name]
    if esize == 1:
        return "poke($%04x + (%s), %s)" % (base, inner, rhs)
    return "pokew($%04x + ((%s) << 1), %s)" % (base, inner, rhs)


def _balanced(s, j):
    depth = 0
    k = j
    while k < len(s):
        if s[k] == "[":
            depth += 1
        elif s[k] == "]":
            depth -= 1
            if depth == 0:
                return k
        k += 1
    return -1


def _balanced_paren(s, j):
    depth = 0
    k = j
    while k < len(s):
        if s[k] == "(":
            depth += 1
        elif s[k] == ")":
            depth -= 1
            if depth == 0:
                return k
        k += 1
    return len(s) - 1


def _str_spans(code):
    return re.split(r'("(?:[^"\\]|\\.)*")', code)


def _parse_primary(s, p):
    """End index of one primary at s[p] (a slab-write RHS is a single primary:
    literal, var, IDENT(args), or IDENT[idx] read, possibly nested)."""
    n = len(s)
    while p < n and s[p] in " \t&~-<>":
        p += 1
    if p >= n:
        return p
    c = s[p]
    if c == "(":
        return _balanced_paren(s, p) + 1
    if c == "'":
        q = p + 1
        while q < n and s[q] != "'":
            q += 2 if s[q] == "\\" else 1
        return q + 1
    if c.isdigit() or c == "$":
        q = p + 1
        while q < n and s[q].isalnum():
            q += 1
        return q
    m = re.match(r"[A-Za-z_]\w*(?:\.\w+)*", s[p:])
    if not m:
        return p
    q = p + m.end()
    if q < n and s[q] == "(":
        return _balanced_paren(s, q) + 1
    if q < n and s[q] == "[":
        return _balanced(s, q) + 1
    return q


def rewrite_code(s):
    out, i, n = [], 0, len(s)
    while i < n:
        m = re.match(r"[A-Za-z_]\w*", s[i:])
        if m and (i + m.end()) < n and s[i + m.end()] == "[":
            name = m.group()
            j = i + m.end()
            k = _balanced(s, j)
            if k < 0:
                out.append(s[i])
                i += 1
                continue
            idx = rewrite_code(s[j + 1:k])
            if name in slabs:
                am = re.match(r'\s*=\s*(?!=)', s[k + 1:])    # a write?
                if am:
                    after = k + 1 + am.end()
                    end = _parse_primary(s, after)
                    rhs = rewrite_code(s[after:end])
                    out.append(slab_write(name, idx, rhs))
                    i = end
                else:
                    out.append(slab_read(name, idx))
                    i = k + 1
            else:
                out.append(name + "[" + idx + "]")
                i = k + 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def slab_line(line):
    code, comment = port_p1._split_comment(line)
    parts = _str_spans(code)            # protect string literals
    for x in range(0, len(parts), 2):
        parts[x] = rewrite_code(parts[x])
    return "".join(parts) + comment


# ---- 3. apply the slab rewrite, then turn the decls into base consts ----
src = "".join(slab_line(l) for l in src.splitlines(keepends=True))


def _decl_to_const(m):
    name = m.group(4)
    if name in slabs:
        return "%sconst uword %s = $%04x%s" % (
            m.group(1), name, slabs[name][1], m.group(5))
    return m.group(0)


src = DECL.sub(_decl_to_const, src)
open(path, "w").write(src)

print("baked %s (%d slabs, %d B, base $%04x..$%04x)"
      % (path, len(slabs), total, slab_base, IO_FLOOR - 1))
for name, esize, count in order:
    print("    %-14s %s[%d]  base $%04x"
          % (name, "uword" if esize == 2 else "ubyte", count, slabs[name][1]))
