#!/bin/bash

set -e

./asmtestgen.sh && python3 editor/tests/ansi_screen.py && editor/tests/editor_tests.py -q && editor/tests/editor_tests.py -q --direct-io && editor/tests/michael_tests.py && ../../emulator/tests/terminal_tests.py && ../../emulator/tests/emulator_tests.py
