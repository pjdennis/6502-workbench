#!/bin/bash

set -e

./asmtestgen.sh && python3 editor/tests/ansi_screen.py && editor/tests/editor_tests.py -q && ../../emulator/tests/terminal_tests.py
