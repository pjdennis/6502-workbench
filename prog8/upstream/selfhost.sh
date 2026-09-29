#!/bin/bash
# Upstream-bootstrap self-host FIXPOINT.
#
# Build the two-pass pipeline (p1/p1_pass1_sh.p8 + p1/p1_pass2_sh.p8) with the
# UPSTREAM Prog8 compiler (prog8c), DIRECTLY from the committed sources -- no
# preprocessing. The only thing upstream needs beyond a stock `nmos` target is
# the `%memtop $XXXX` directive each source already carries, which tells the
# upstream allocator to keep its code/data/BSS below the baked peek/poke slab
# region. (port_pipeline.py is retired; the sources are one converged dialect.)
#
# Then demonstrate the classic self-hosting fixpoint on the pipeline's OWN two
# sources:
#   gen1 = upstream-prog8c(source)                 (upstream codegen)
#   gen2 = vasm(gen1 run on source -> asm)         (the pipeline's own codegen)
#   gen3 = vasm(gen2 run on source -> asm)
# and assert gen2 == gen3 byte-for-byte: once built, the pipeline compiles its
# own source to a bit-identical copy of itself, and every generation's emitted
# asm matches the p8c host oracle.
#
# Prereqs: /tmp/prog8c.jar (upstream prog8c), vasm6502_oldstyle, the emulator.
set -e
cd "$(dirname "$0")/.."                       # .../toolchain/prog8
EMU=../../emulator/emulator.out
JAR=${PROG8C:-/tmp/prog8c.jar}
CAP=30000000000
W=/tmp/sh_fixpoint; rm -rf "$W"; mkdir -p "$W"
VASM="../../firmware/vasm -Fbin -dotdir -ignore-mult-inc -esc -wfail"
PASSES="p1_pass1_sh p1_pass2_sh"

# run the two-pass pipeline (pass1 img $1, pass2 img $2) on source $3 -> asm $4
run_pipeline() {
    $EMU "$1" --cycle-cap $CAP "$3" "$W/d.bin"           >/dev/null 2>&1 || return 1
    $EMU "$2" --cycle-cap $CAP --no-dump "$W/d.bin" "$4" >/dev/null 2>&1 || return 1
}

fail=0

echo "gen1: build pipeline with upstream prog8c, DIRECTLY from source (no preprocessing)"
for f in $PASSES; do
    ( cd upstream && java -jar "$JAR" -target nmos.properties -out "$W" "../p1/$f.p8" ) \
        >"$W/$f.build.log" 2>&1 || { echo "  FAIL: upstream rejected $f"; grep -iE 'error|exception' "$W/$f.build.log"|head -3; exit 1; }
    python3 upstream/mkimage.py "$W/$f.bin" "$W/$f.gen1.img" >/dev/null
    echo "  $f: upstream compiled OK"
done

echo "gen1 -> asm (must match p8c oracle); assemble -> gen2"
for f in $PASSES; do
    run_pipeline "$W/p1_pass1_sh.gen1.img" "$W/p1_pass2_sh.gen1.img" "p1/$f.p8" "$W/$f.gen1.s" \
        || { echo "  $f: gen1 RUN FAIL"; fail=1; continue; }
    python3 -m p8c --target nmos "p1/$f.p8" -o "$W/$f.oracle.s" >/dev/null 2>&1
    n=$(diff <(sed 's/^; source:.*/X/' "$W/$f.gen1.s") <(sed 's/^; source:.*/X/' "$W/$f.oracle.s") | wc -l)
    if [ "$n" -eq 0 ]; then echo "  $f: gen1 asm == p8c oracle (diff=0)"; else echo "  $f: gen1 asm DIFF=$n"; fail=1; fi
    $VASM -o "$W/$f.gen2.bin" "$W/$f.gen1.s" >/dev/null 2>&1
done

echo "gen2 -> asm; assemble -> gen3; assert gen2 == gen3 (binary fixpoint)"
for f in $PASSES; do
    run_pipeline "$W/p1_pass1_sh.gen2.bin" "$W/p1_pass2_sh.gen2.bin" "p1/$f.p8" "$W/$f.gen2.s" \
        || { echo "  $f: gen2 RUN FAIL"; fail=1; continue; }
    $VASM -o "$W/$f.gen3.bin" "$W/$f.gen2.s" >/dev/null 2>&1
    if cmp -s "$W/$f.gen2.bin" "$W/$f.gen3.bin"; then
        echo "  $f: gen2.bin == gen3.bin ($(wc -c <"$W/$f.gen2.bin") B) -- FIXPOINT"
    else
        echo "  $f: gen2.bin != gen3.bin"; fail=1
    fi
done

[ "$fail" -eq 0 ] \
    && echo "PASS: upstream-built pipeline self-hosts its own sources to a stable, p8c-identical fixpoint." \
    || echo "FAIL: upstream-bootstrap fixpoint broken."
exit $fail
