# Prog8 compiler work: host p8c, tinyp8, p1, and the upstream prog8c targets.
# The emulator is built by the repository-level Makefile.

test: prog8-test tinyp8-test p1-test

emu:
	@$(MAKE) -s -C ../.. emulator/emulator.out

# Prog8 host compiler (Phase 1 walking skeleton) test suite. Includes
# lexer / parser / sema / codegen unit tests, .s snapshot tests, and an
# end-to-end golden that compiles the demo .p8, runs it through vasm
# and the emulator, and asserts on the resulting LCD frame. SKIPs the
# end-to-end golden if vasm6502_oldstyle or the emulator binary are
# missing.
prog8-test: emu
	@python3 -m unittest discover -s tests -v

# wendy2: the custom external prog8 target with upper-window memory banking.
# Compiles the demos with upstream prog8c (-target wendy2.properties), runs
# them on the wendy2c emulator via the boot-ROM upload path, and diffs the
# LCD frame against goldens. Skips cleanly if prog8c.jar / 64tass /
# vasm6502_oldstyle / the emulator are missing. See
# WENDY2_BANKING_TARGET_PLAN.md.
wendy2-test: emu
	@cd upstream && python3 tests/test_wendy2.py && python3 tests/test_wendy2_disk.py && python3 tests/test_wendy2_monitor.py

# tinyp8: the 6502-native compiler proof-of-concept. Two tests:
#   * test_e2e        -- the hand-written tinyp8.s compiles each .tp8
#                        and the resulting binary's stdout matches a
#                        golden. Proves: on-target compilation works.
#   * test_self_host  -- additionally, tinyp8.p8 (the SAME compiler
#                        rewritten in Prog8 and compiled by our host
#                        p8c) produces byte-identical output for the
#                        same inputs. Proves: a useful compiler can be
#                        written in our language and compiled by us.
# SKIPs cleanly if vasm6502_oldstyle or the emulator binary are
# missing.
tinyp8-test: emu
	@python3 -m unittest tinyp8.tests.test_e2e tinyp8.tests.test_self_host tinyp8.tests.test_v2 -v

# p1: the Prog8 parser port (Phase 6, step 5). M1 is the on-target lexer
# (p1/lexer.p8): built with host p8c + vasm, run on the emulator over a
# corpus, its token-stream dump diffed byte-for-byte against the Python
# oracle (p8c --dump-tokens). SKIPs cleanly if vasm or the emulator are
# missing.
p1-test: emu
	@python3 -m unittest p1.tests.test_lexer p1.tests.test_expr p1.tests.test_p1 -v

.PHONY: test emu prog8-test wendy2-test tinyp8-test p1-test
