#!/bin/bash
# ATTIC NOTE: parked. The 22/, 23/ and editor/ paths below are from the old assembler2/ layout (now asm/NN/ and editor/). See attic/assembler2/README.md.
# Check that all .asm and .txt files in the assembler/editor source tree
# contain only ASCII characters (bytes 0x00-0x7F).
# Scans: 22/, 23/, editor/ (excluding Python scripts and output directories)
#
# Usage: check_ascii.sh [--fix]
#   --fix  Replace known Unicode characters with ASCII equivalents:
#            em dash (—) → dash (-)
#            left arrow (←) → <-
#            right arrow (→) → ->
#            times (×) → x
#          Other non-ASCII characters are reported but left alone.

fix_mode=0
if [ "$1" = "--fix" ]; then
    fix_mode=1
fi

found=0

while IFS= read -r file; do
    # grep for any byte with high bit set (0x80-0xFF)
    matches=$(grep -Pn '[^\x00-\x7F]' "$file")
    if [ -n "$matches" ]; then
        if [ "$fix_mode" -eq 1 ]; then
            # Apply known substitutions
            sed -i \
                -e $'s/\xe2\x80\x94/-/g' \
                -e $'s/\xe2\x86\x90/<-/g' \
                -e $'s/\xe2\x86\x92/->/g' \
                -e $'s/\xc3\x97/x/g' \
                "$file"

            # Check if any non-ASCII remains after fixes
            remaining=$(grep -Pn '[^\x00-\x7F]' "$file")
            if [ -n "$remaining" ]; then
                echo "=== $file === (unfixable non-ASCII remains)"
                echo "$remaining"
                echo
                found=1
            else
                echo "Fixed: $file"
            fi
        else
            echo "=== $file ==="
            echo "$matches"
            echo
            found=1
        fi
    fi
done < <(find 22 23 editor -type f '(' -name '*.asm' -o -name '*.txt' ')' -not -path '*/out/*')

if [ "$fix_mode" -eq 0 ] && [ "$found" -eq 0 ]; then
    echo "All files are ASCII-clean."
elif [ "$fix_mode" -eq 1 ] && [ "$found" -eq 0 ]; then
    echo "All files are now ASCII-clean."
fi
