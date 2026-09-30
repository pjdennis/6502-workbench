#!/bin/bash
# HARD REQUIREMENT GATE: both pipeline passes MUST compile with the UPSTREAM
# Prog8 compiler (prog8c), DIRECTLY from the committed sources -- no
# preprocessing.
#
# The pipeline sources (p1/p1_pass1_sh.p8, p1/p1_pass2_sh.p8) are one converged
# dialect that BOTH compilers consume verbatim:
#   1. upstream prog8c (this gate; the reference build) -- needs only a stock
#      `nmos` target plus the `%memtop $XXXX` directive each source carries
#      (the allocator ceiling that keeps code/data/BSS below the baked slabs).
#   2. the in-repo p8c backend (the on-target self-hosting toolchain).
#
# p8c is more lenient than upstream, so it is EASY to introduce changes that p8c
# accepts but upstream rejects. Known traps (do NOT do these):
#   * Lenient `main { <statements> }` -- upstream needs `main { sub start() {} }`.
#   * Bare truthy conditions like `if some_call(...)` / `while arr[i]` --
#     upstream requires boolean conditions; write `... != 0` explicitly.
#   * Arrays > 256 elements / uword-indexed arrays -- bake them into peek/poke
#     slabs (upstream/bake_slabs.py) and bump %memtop accordingly.
#
# Run this after ANY edit to the _sh pipeline sources.
# Prereq: upstream prog8c jar at $PROG8C (default /tmp/prog8c.jar) + 64tass.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
JAR="${PROG8C:-/tmp/prog8c.jar}"
cd "$HERE"                       # so prog8c reads ./nmos.properties
mkdir -p /tmp/upchk
fail=0
for src in p1_pass1_sh p1_pass2_sh; do
  rm -f "/tmp/upchk/${src}.asm"
  if java -jar "$JAR" -target nmos.properties -out /tmp/upchk \
        "$HERE/../p1/$src.p8" >"/tmp/${src}_up.log" 2>&1 \
      && [ -f "/tmp/upchk/${src}.asm" ]; then
    echo "PASS: upstream prog8c compiles $src (directly, no preprocessing)"
  else
    echo "FAIL: upstream prog8c rejects $src --"
    grep -iE 'error|exception' "/tmp/${src}_up.log" | head -4
    fail=1
  fi
done
[ "$fail" -eq 0 ] && echo "OK: both passes compile DIRECTLY with upstream prog8c." \
                  || echo "BROKEN: upstream compatibility regression (hard requirement)."
exit $fail
