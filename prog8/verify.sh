#!/bin/bash
# Self-host gate for the Prog8 pipeline.
#
# The pipeline is two passes -- p1/p1_pass1_sh.p8 (parse -> binary dump) and
# p1/p1_pass2_sh.p8 (dump -> 6502 asm) -- each written in upstream-legal Prog8
# (a `main { sub start() {...} }` block; NO lenient `main { <statements> }`,
# which is not upstream syntax). Build both passes with the host p8c, then run
# the pipeline on EACH pass's OWN source and diff the emitted asm against p8c's
# output for that source. PASS = the on-target pipeline reproduces p8c byte-for-
# byte for the files that make up the pipeline (true self-hosting).
#
# (The old monolith p1/p1.p8 is NOT a pipeline input: it combines both passes'
# globals -- >780 module symbols -- and overflows pass1's on-target arenas. That
# is exactly why the compiler was split into two passes. p1.p8 is kept only as a
# large p8c-compilation sanity check below.)
set -e
cd "$(dirname "$0")"
EMU=../../emulator/emulator.out
CAP=30000000000

python3 -m p8c --target nmos p1/p1_pass1_sh.p8 -o /tmp/_p1.s >/dev/null 2>&1
O1=$(../../firmware/vasm -Fbin -dotdir -ignore-mult-inc -esc -wfail -o /tmp/p1.bin /tmp/_p1.s 2>&1) \
   || { echo "PASS1 VASM FAIL"; echo "$O1" | grep -i error; exit 1; }
python3 -m p8c --target nmos p1/p1_pass2_sh.p8 -o /tmp/_p2.s >/dev/null 2>&1
O2=$(../../firmware/vasm -Fbin -dotdir -ignore-mult-inc -esc -wfail -o /tmp/p2.bin /tmp/_p2.s 2>&1) \
   || { echo "PASS2 VASM FAIL"; echo "$O2" | grep -iE 'error|overlap'; exit 1; }
s1=$(echo "$O1" | grep 'org0001' | grep -oE '[0-9]+ bytes' | grep -oE '[0-9]+')
s2=$(echo "$O2" | grep 'org0001' | grep -oE '[0-9]+ bytes' | grep -oE '[0-9]+')
python3 -c "print(f'pass1 top \${0x200+$s1:04X} ({0xF000-0x200-$s1} B free)  pass2 top \${0x200+$s2:04X} ({0xF000-0x200-$s2} B free)')"

fail=0
for f in p1_pass1_sh p1_pass2_sh; do
  $EMU /tmp/p1.bin --cycle-cap $CAP p1/$f.p8 /tmp/${f}_dump.bin >/dev/null 2>&1 \
     || { echo "$f: PASS1 RUN FAIL"; fail=1; continue; }
  $EMU /tmp/p2.bin --cycle-cap $CAP --no-dump /tmp/${f}_dump.bin /tmp/${f}_out.s >/dev/null 2>&1 \
     || { echo "$f: PASS2 RUN FAIL"; fail=1; continue; }
  python3 -m p8c --target nmos p1/$f.p8 -o /tmp/${f}_oracle.s >/dev/null 2>&1
  n=$(diff <(sed 's/^; source:.*/X/' /tmp/${f}_out.s) <(sed 's/^; source:.*/X/' /tmp/${f}_oracle.s) | wc -l)
  if [ "$n" -eq 0 ]; then echo "$f: SELF-HOST diff=0 PASS"; else echo "$f: SELF-HOST diff=$n FAIL"; fail=1; fi
done

# p8c sanity: the monolith still compiles with the host p8c (upstream-legal form).
if python3 -m p8c --target nmos p1/p1.p8 -o /tmp/p1_oracle.s >/dev/null 2>&1; then
  echo "p1.p8: p8c compiles OK"
else
  echo "p1.p8: p8c FAIL"; fail=1
fi

[ "$fail" -eq 0 ] && echo "PASS: pipeline self-hosts byte-identically on both _sh passes."
exit $fail
