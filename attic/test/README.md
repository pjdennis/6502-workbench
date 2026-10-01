# test: early vasm experiments

What it is: scratch files from 2020-23, from when the repository root held everything: vasm syntax and macro experiments (`macro.s`, `macrotest.s`, `if_test.s`, `calc_test.s`, `constant_test.s`, `test_neg_const.s`, `test.s`), a C++ hello (`test.cpp`), and small Python binary-file generators (`makebin*.py`, `makefile.py`, `pause_test.py`).

Why it is parked: they are one-off experiments. Most of the `.s` files do not assemble now, because the include files they expect (root-level `base_config_*.inc` and friends) moved or were removed.

Live successor: `firmware/` (programs and libraries, tested by `tools/check_all.sh firmware`) and `tools/tests/`.
