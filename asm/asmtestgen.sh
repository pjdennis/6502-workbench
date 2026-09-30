#!/bin/bash

set -e
shopt -s extglob

# Run tests for a version
run_version_tests() {
    local ver=$1
    if [ ! -d "${ver}/tests" ]; then
        echo "ERROR: Test directory ${ver}/tests not found" >&2
        exit 1
    fi
    echo "--- Test asm${ver} ---"
    if [ -d "${ver}/tests/asm" ]; then
        # Modular test structure (v17+)
        ./run_tests.py --version "$ver" -q
    else
        ./run_tests.py --version "$ver" -q "${ver}/tests/asm_tests.txt"
    fi
}

mkdir -p out
rm -f out/*.out out/*.asm.out
rm -rf {00..99}/out
make --quiet
echo "--- Version 00 ---"
(cd 00 && out/asm_c.out asm.asm out/asm.out)
echo "--- Version 01 ---"
(cd 01 && mkdir -p out && ../../emulator/emulator.out ../00/out/asm.out --load 2000 --input asm.asm --output out/asm.out)
echo "--- Version 02 ---"
(cd 02 && mkdir -p out && ../../emulator/emulator.out ../01/out/asm.out --load 2000 --input asm.asm --output out/asm.out)
echo "--- Version 03 ---"
(cd 03 && mkdir -p out && ../../emulator/emulator.out ../02/out/asm.out --load 2000 --input asm.asm --output out/asm.out)
run_version_tests 03
echo "--- Version 04 ---"
(cd 04 && mkdir -p out && ../../emulator/emulator.out ../03/out/asm.out --load 2000 --input asm.asm --output out/asm.out)
echo "--- Version 05 ---"
(cd 05 && mkdir -p out && ../../emulator/emulator.out ../04/out/asm.out --load 2000 --input asm.asm --output out/asm.out)
echo "--- Version 06 ---"
(cd 06 && mkdir -p out &&
  ../../emulator/emulator.out ../05/out/asm.out --load 2000 --input instgen.asm --output out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  cat out/inst.asm.out asm.asm > out/asmc.asm.out &&
  ../../emulator/emulator.out ../05/out/asm.out --load 2000 --input out/asmc.asm.out --output out/asmc.out)
echo "--- Version 07 ---"
(cd 07 && mkdir -p out &&
  ../../emulator/emulator.out ../06/out/asmc.out --load 2000 --input instgen.asm --output out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  cat out/inst.asm.out asm.asm > out/asmc.asm.out &&
  ../../emulator/emulator.out ../06/out/asmc.out --load 2000 --input out/asmc.asm.out --output out/asmc.out)
run_version_tests 07
echo "--- Version 08 ---"
(cd 08 && mkdir -p out &&
  ../../emulator/emulator.out ../07/out/asmc.out --load 2000 --input instgen.asm --output out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  cat out/inst.asm.out asm.asm > out/asmc.asm.out &&
  ../../emulator/emulator.out ../07/out/asmc.out --load 2000 --input out/asmc.asm.out --output out/asmc.out)
run_version_tests 08
echo "--- Version 09 ---"
(cd 09 && mkdir -p out &&
  ../../emulator/emulator.out ../08/out/asmc.out --input instgen.asm --output out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  ../../emulator/emulator.out ../08/out/asmc.out --input asm.asm --output out/asm.out)
run_version_tests 09
echo "--- Version 10 ---"
(cd 10 && mkdir -p out &&
  ../../emulator/emulator.out ../09/out/asm.out instgen.asm out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  ../../emulator/emulator.out ../09/out/asm.out asm.asm out/asm.out)
run_version_tests 10
echo "--- Version 11 ---"
(cd 11 && mkdir -p out &&
  ../../emulator/emulator.out ../10/out/asm.out instgen.asm out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  ../../emulator/emulator.out ../10/out/asm.out asm.asm out/asm.out)
run_version_tests 11
echo "--- Version 12 ---"
(cd 12 && mkdir -p out &&
  ../../emulator/emulator.out ../11/out/asm.out instgen.asm out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  ../../emulator/emulator.out ../11/out/asm.out asm.asm out/asm.out)
run_version_tests 12
# cmp (not diff of hexdump output): hexdump may be missing from the
# environment, and a failure inside a process substitution doesn't
# propagate through set -e -- the diff would silently compare two empty
# streams and pass.
cmp 11/out/asm.out 12/out/asm.out
echo "--- Version 13 ---"
(cd 13 && mkdir -p out &&
  ../../emulator/emulator.out ../12/out/asm.out instgen.asm out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  ../../emulator/emulator.out ../12/out/asm.out asm.asm out/asm.out)
run_version_tests 13
echo "--- Version 14 ---"
(cd 14 && mkdir -p out &&
  ../../emulator/emulator.out ../13/out/asm.out instgen.asm out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  ../../emulator/emulator.out ../13/out/asm.out asm.asm out/asm.out)
run_version_tests 14
echo "--- Version 15 ---"
(cd 15 && mkdir -p out &&
  ../../emulator/emulator.out ../14/out/asm.out instgen.asm out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  ../../emulator/emulator.out ../14/out/asm.out asm.asm out/asm.out &&
  ../../emulator/emulator.out ../14/out/asm.out asm.asm out/asm_debug.out define:enable_debug)
run_version_tests 15
echo "--- Version 16 ---"
(cd 16 && mkdir -p out &&
  ../../emulator/emulator.out ../15/out/asm_debug.out tests/file_stack_test.asm out/file_stack_test.out &&
  ../../emulator/emulator.out ../15/out/asm_debug.out instgen.asm out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  ../../emulator/emulator.out ../15/out/asm_debug.out asm.asm out/asm.out &&
  ../../emulator/emulator.out ../15/out/asm_debug.out asm.asm out/asm_debug.out define:enable_debug)
run_version_tests 16
echo "--- Version 17 ---"
(cd 17 && mkdir -p out &&
  ../../emulator/emulator.out ../16/out/asm_debug.out tests/source_stack/source_stack_test.asm out/source_stack_test.out &&
  ../../emulator/emulator.out ../16/out/asm_debug.out tests/opendir/opendir_test.asm out/opendir_test.out &&
  ../../emulator/emulator.out ../16/out/asm_debug.out instgen.asm out/instgen.out &&
  ../../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  ../../emulator/emulator.out ../16/out/asm_debug.out asm.asm out/asm.out &&
  ../../emulator/emulator.out ../16/out/asm_debug.out asm.asm out/asm_debug.out define:enable_debug)
run_version_tests 17
echo "--- opendir tests ---"
python3 17/tests/opendir/test_opendir.py
echo "--- Self-assembly test ---"
# Self-assembly test (without debug - smaller)
(cd 17 && ../../emulator/emulator.out out/asm.out asm.asm out/asm_2.out)
cmp 17/out/asm.out 17/out/asm_2.out
# Self-assembly test (with debug)
(cd 17 && ../../emulator/emulator.out out/asm_debug.out asm.asm out/asm_debug_2.out define:enable_debug)
cmp 17/out/asm_debug.out 17/out/asm_debug_2.out
echo "--- Self-hosted tests ---"
(cd 17 && ../../emulator/emulator.out out/asm.out asm.asm out/test_runner.out define:enable_test_runner define:enable_debug)
(cd 17/tests/asm && ../../../../emulator/emulator.out ../../out/test_runner.out -q)
python3 17/tests/test_runner/test_runner_dir.py -q

echo "Build chain completed OK"

# Show actual code size difference
# File covers $2000-$FFFF, vectors at end. Scan backwards from just before vectors.
echo "Code size comparison:"
SIZE1=$(perl -e 'open(F,"<","17/out/asm.out");binmode(F);read(F,$d,0xE000);for($i=0xDFFB;$i>=0;$i--){last if ord(substr($d,$i,1))!=0}print $i+1')
SIZE2=$(perl -e 'open(F,"<","17/out/asm_debug.out");binmode(F);read(F,$d,0xE000);for($i=0xDFFB;$i>=0;$i--){last if ord(substr($d,$i,1))!=0}print $i+1')
echo "  asm.out (no debug):     $SIZE1 bytes"
echo "  asm_debug.out:          $SIZE2 bytes"
echo "  Difference:             $((SIZE2 - SIZE1)) bytes"
