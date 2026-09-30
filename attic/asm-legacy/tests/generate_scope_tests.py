#!/usr/bin/env python3
import os

os.makedirs("tests/scope", exist_ok=True)

# Generate files numbered downwards: s52 → s51 → ... → s02 → s01
# Each file defines a macro that calls the previous macro number
# This creates nested macro invocations without using .include
#
# s01 (bottom): defines M01 with NOP, invokes it
# s02: defines M02 that calls M01, invokes M02
# ...
# s51: defines M51 that calls M50, invokes M51 (positive test starts here)
# s52: defines M52 that calls M51, invokes M52 (negative test starts here)

for i in range(52, 0, -1):  # 52 down to 1
    with open(f"tests/scope/s{i:02d}.asm", "w") as f:
        f.write(f"M{i:02d}_macro:\n")  # Global label to avoid "no global label" error
        f.write(f"  .macro M{i:02d}\n")
        if i > 1:  # Not the bottom file
            # Include the next file down and invoke its macro
            f.write(f"  .include tests/scope/s{i-1:02d}.asm\n")
        else:  # Bottom file (s01)
            f.write("  NOP\n")
        f.write(f"  .endmacro\n")
        f.write(f"  M{i:02d}\n")

print("Generated test files:")
print("  tests/scope/s52.asm - triggers overflow (52 nested macros)")
print("  tests/scope/s51.asm - at limit (51 nested macros)")
print("  tests/scope/s50.asm through s01.asm - supporting files")
