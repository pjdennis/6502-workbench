#!/bin/bash
# ATTIC NOTE: parked alternate of asmtestgen.sh for the old assembler2/ layout (stages 06-17 paths, ../emulator/emulator.out). Live chain: asm/asmtestgen.sh, asm/verify.sh.

set -e
shopt -s extglob

# --- Helper functions ---

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

# Assemble using old --load/--input/--output flags (versions 01-05)
build_early() {
    local ver=$1 prev=$2
    echo "--- Version $ver ---"
    (cd "$ver" && mkdir -p out &&
      ../emulator/emulator.out ../"$prev"/out/asm.out --load 2000 --input asm.asm --output out/asm.out)
}

# Build instgen with cat-based inclusion (versions 06-08)
build_cat_instgen() {
    local ver=$1 prev_asm=$2
    echo "--- Version $ver ---"
    (cd "$ver" && mkdir -p out &&
      ../emulator/emulator.out "$prev_asm" --load 2000 --input instgen.asm --output out/instgen.out &&
      ../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
      cat out/inst.asm.out asm.asm > out/asmc.asm.out &&
      ../emulator/emulator.out "$prev_asm" --load 2000 --input out/asmc.asm.out --output out/asmc.out)
}

# Build with instgen and .include (versions 10+)
build_standard() {
    local ver=$1 prev_asm=$2
    echo "--- Version $ver ---"
    (cd "$ver" && mkdir -p out &&
      ../emulator/emulator.out "$prev_asm" instgen.asm out/instgen.out &&
      ../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
      ../emulator/emulator.out "$prev_asm" asm.asm out/asm.out)
}

# Build standard + debug variant (versions 15+)
build_with_debug() {
    local ver=$1 prev_asm=$2
    build_standard "$ver" "$prev_asm"
    (cd "$ver" && ../emulator/emulator.out "$prev_asm" asm.asm out/asm_debug.out define:enable_debug)
}

# Verify two binary files match
verify_match() {
    diff <(hexdump -C "$1") <(hexdump -C "$2")
}

# --- Build chain ---

mkdir -p out
rm -f out/*.out out/*.asm.out
rm -rf {00..99}/out
make --quiet

# Version 00: C bootstrap
echo "--- Version 00 ---"
(cd 00 && out/asm_c.out asm.asm out/asm.out)

# Versions 01-05: early bootstrap
build_early 01 00
build_early 02 01
build_early 03 02
run_version_tests 03
build_early 04 03
build_early 05 04

# Versions 06-08: instgen with cat-based inclusion
build_cat_instgen 06 ../05/out/asm.out
build_cat_instgen 07 ../06/out/asmc.out
run_version_tests 07
build_cat_instgen 08 ../07/out/asmc.out
run_version_tests 08

# Version 09: transitional (old flags for instgen, new arg style for asm)
echo "--- Version 09 ---"
(cd 09 && mkdir -p out &&
  ../emulator/emulator.out ../08/out/asmc.out --input instgen.asm --output out/instgen.out &&
  ../emulator/emulator.out out/instgen.out --load 2000 --output out/inst.asm.out &&
  ../emulator/emulator.out ../08/out/asmc.out --input asm.asm --output out/asm.out)
run_version_tests 09

# Versions 10-14: standard build
build_standard 10 ../09/out/asm.out
run_version_tests 10
build_standard 11 ../10/out/asm.out
run_version_tests 11
build_standard 12 ../11/out/asm.out
run_version_tests 12
verify_match 11/out/asm.out 12/out/asm.out
build_standard 13 ../12/out/asm.out
run_version_tests 13
build_standard 14 ../13/out/asm.out
run_version_tests 14

# Versions 15-17: standard build + debug variant
build_with_debug 15 ../14/out/asm.out
run_version_tests 15
build_with_debug 16 ../15/out/asm_debug.out
(cd 16 && ../emulator/emulator.out ../15/out/asm_debug.out tests/file_stack_test.asm out/file_stack_test.out)
run_version_tests 16
build_with_debug 17 ../16/out/asm_debug.out
(cd 17 &&
  ../emulator/emulator.out ../16/out/asm_debug.out tests/file_stack/file_stack_test.asm out/file_stack_test.out &&
  ../emulator/emulator.out ../16/out/asm_debug.out tests/opendir/opendir_test.asm out/opendir_test.out)
run_version_tests 17

# Additional tests
echo "--- opendir tests ---"
python3 17/tests/opendir/test_opendir.py
echo "--- Self-assembly test ---"
(cd 17 && ../emulator/emulator.out out/asm.out asm.asm out/asm_2.out)
verify_match 17/out/asm.out 17/out/asm_2.out
(cd 17 && ../emulator/emulator.out out/asm_debug.out asm.asm out/asm_debug_2.out define:enable_debug)
verify_match 17/out/asm_debug.out 17/out/asm_debug_2.out
echo "--- Self-hosted tests ---"
(cd 17 && ../emulator/emulator.out out/asm.out asm.asm out/test_runner.out define:enable_test_runner)
(cd 17/tests/asm && ../../../emulator/emulator.out ../../out/test_runner.out)
echo "--- Test runner directory mode tests ---"
python3 17/tests/test_runner/test_runner_dir.py

echo "Build chain completed OK"

# Show actual code size difference
# File covers $2000-$FFFF, vectors at end. Scan backwards from just before vectors.
echo "Code size comparison:"
SIZE1=$(perl -e 'open(F,"<","17/out/asm.out");binmode(F);read(F,$d,0xE000);for($i=0xDFFB;$i>=0;$i--){last if ord(substr($d,$i,1))!=0}print $i+1')
SIZE2=$(perl -e 'open(F,"<","17/out/asm_debug.out");binmode(F);read(F,$d,0xE000);for($i=0xDFFB;$i>=0;$i--){last if ord(substr($d,$i,1))!=0}print $i+1')
echo "  asm.out (no debug):     $SIZE1 bytes"
echo "  asm_debug.out:          $SIZE2 bytes"
echo "  Difference:             $((SIZE2 - SIZE1)) bytes"
