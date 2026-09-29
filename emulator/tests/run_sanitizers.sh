#!/bin/sh
# Rebuild every greatest C test under AddressSanitizer + UndefinedBehaviorSanitizer
# + LeakSanitizer and run each one. Mirrors the per-test source lists in the
# Makefile -- when adding a new C test, add it here too.
#
# Output binaries live in emulator/tests/out/san/ so the optimized regular
# .out files aren't disturbed. ASan halts on the first error and dumps a
# stack trace; the post-exit leak report fires automatically as long as
# detect_leaks=1 (default on Linux gcc; explicit for clarity).

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

OUT="emulator/tests/out/san"
mkdir -p "$OUT"

CC="${CC:-gcc}"
# No -Werror here: san mode is about catching memory + UB issues, not
# pedantic warnings (which already gate the regular make test build).
SAN_CFLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer -O1 -g -Wall"

# Linker pulls in the sanitizer runtimes. UBSan is a sub-runtime of ASan
# at link time so we only need one -fsanitize spec on the command line.
SAN_LDFLAGS="-fsanitize=address,undefined"

# Same Linux deps as the main binary for any test that pulls in audio.c.
case "$(uname -s)" in
    Darwin) AUDIO_LDLIBS="-lm -lpthread -framework CoreFoundation -framework CoreAudio -framework AudioUnit" ;;
    Linux)  AUDIO_LDLIBS="-lm -lpthread -ldl" ;;
    *)      AUDIO_LDLIBS="-lm -lpthread" ;;
esac

# Each entry: NAME|SRCS|EXTRA_LDLIBS
#
# NAME is the test-source basename without .c (e.g. test_chip_lcd). EXTRA_LDLIBS
# is appended after the standard san link flags; mostly empty, only audio-linked
# tests need miniaudio's deps.
TESTS="
test_smoke|emulator/tests/test_smoke.c|
test_file_io|emulator/tests/test_file_io.c emulator/file_io.c|
test_console|emulator/tests/test_console.c emulator/console.c|
test_trace|emulator/tests/test_trace.c emulator/trace.c|
test_cli|emulator/tests/test_cli.c emulator/cli.c|
test_emu_run|emulator/tests/test_emu_run.c emulator/emu_run.c emulator/cli.c emulator/trace.c|
test_bus|emulator/tests/test_bus.c emulator/bus.c|
test_cpu_variant|emulator/tests/test_cpu_variant.c emulator/cpu_core.c|-Wno-unused-function
test_cpu_65c02_fixes|emulator/tests/test_cpu_65c02_fixes.c emulator/cpu_core.c|-Wno-unused-function
test_cpu_65c02_group_a|emulator/tests/test_cpu_65c02_group_a.c emulator/cpu_core.c|-Wno-unused-function
test_cpu_65c02_group_b|emulator/tests/test_cpu_65c02_group_b.c emulator/cpu_core.c|-Wno-unused-function
test_cpu_65c02_bit_ops|emulator/tests/test_cpu_65c02_bit_ops.c emulator/cpu_core.c|-Wno-unused-function
test_cpu_65c02_wai_stp|emulator/tests/test_cpu_65c02_wai_stp.c emulator/cpu_core.c|-Wno-unused-function
test_cpu_bus_tap|emulator/tests/test_cpu_bus_tap.c emulator/cpu_core.c|-Wno-unused-function
test_dormann|emulator/tests/test_dormann.c emulator/cpu_core.c|-Wno-unused-function
test_machine_dispatch|emulator/tests/test_machine_dispatch.c emulator/cli.c|
test_chip_osc|emulator/tests/test_chip_osc.c emulator/chips/osc.c emulator/bus.c|
test_chip_clock|emulator/tests/test_chip_clock.c emulator/chips/clock_22v10.c emulator/bus.c|
test_chip_rom|emulator/tests/test_chip_rom.c emulator/chips/rom_28c256.c emulator/chips/clock_22v10.c emulator/bus.c|
test_chip_ram|emulator/tests/test_chip_ram.c emulator/chips/ram_628128.c emulator/chips/clock_22v10.c emulator/bus.c|
test_chip_cpu_65c02|emulator/tests/test_chip_cpu_65c02.c emulator/chips/cpu_65c02.c emulator/chips/syscall_ports.c emulator/emu_wendy2c.c emulator/lcd_report.c emulator/pace.c emulator/cli.c emulator/cpu_core.c emulator/bus.c emulator/tty_alt_screen.c emulator/wendy2c_web.c emulator/web_json.c emulator/chips/clock_22v10.c emulator/chips/rom_28c256.c emulator/chips/ram_628128.c emulator/chips/via_6522.c emulator/chips/lcd_hd44780.c emulator/chips/serial_usb.c emulator/chips/led_buttons.c|-Wno-unused-function
test_chip_via|emulator/tests/test_chip_via.c emulator/chips/via_6522.c emulator/bus.c|
test_direct_io|emulator/tests/test_direct_io.c emulator/direct_io.c|
test_ps2_keys|emulator/tests/test_ps2_keys.c emulator/ps2_keys.c|
test_chip_lcd|emulator/tests/test_chip_lcd.c emulator/chips/lcd_hd44780.c emulator/chips/via_6522.c emulator/bus.c|
test_chip_serial_usb|emulator/tests/test_chip_serial_usb.c emulator/chips/serial_usb.c emulator/chips/via_6522.c emulator/bus.c|
test_chip_led_buttons|emulator/tests/test_chip_led_buttons.c emulator/chips/led_buttons.c emulator/chips/via_6522.c emulator/bus.c|
test_audio|emulator/tests/test_audio.c emulator/audio.c|$AUDIO_LDLIBS
test_web_json|emulator/tests/test_web_json.c emulator/web_json.c|
test_web_smoke|emulator/tests/test_web_smoke.c emulator/wendy2c_web.c emulator/web_json.c|
"

# ASan + UBSan options. detect_leaks is on by default on Linux; explicit
# halt_on_error gives a clean non-zero exit so the loop below picks up
# the failure. abort_on_error=1 would dump a core; we prefer the clean
# exit so the script can keep reporting.
export ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=1:halt_on_error=1:strict_string_checks=1:detect_stack_use_after_return=1}"
export UBSAN_OPTIONS="${UBSAN_OPTIONS:-halt_on_error=1:print_stacktrace=1}"
export LSAN_OPTIONS="${LSAN_OPTIONS:-suppressions=$REPO_ROOT/emulator/tests/lsan_suppressions.txt:print_suppressions=0}"

# A few benign leaks live in third-party code we vendor (miniaudio loads
# ALSA/PulseAudio via dlopen and leaks one fd-set each at startup). The
# suppressions file lets us skip those without hiding our own leaks.
if [ ! -f "$REPO_ROOT/emulator/tests/lsan_suppressions.txt" ]; then
    cat > "$REPO_ROOT/emulator/tests/lsan_suppressions.txt" <<'EOF'
# Third-party / system leaks we don't intend to chase. Any leak whose
# stack contains one of these substrings is silenced.
leak:libasound
leak:libpulse
leak:libpipewire
leak:_dl_init
leak:ma_dlopen
EOF
fi

ok_count=0
fail_count=0
fail_names=""

echo "Building tests under -fsanitize=address,undefined..."
echo "$TESTS" | while IFS='|' read -r name srcs extra; do
    [ -z "$name" ] && continue
    out="$OUT/$name.out"
    # shellcheck disable=SC2086
    if ! $CC $SAN_CFLAGS -o "$out" $srcs $SAN_LDFLAGS $extra 2>"$OUT/$name.build.log"; then
        echo "  BUILD FAIL $name (see $OUT/$name.build.log)"
        echo "FAIL $name BUILD" >> "$OUT/.results"
        continue
    fi
    echo "BUILT $name" >> "$OUT/.results"
done

# Run each binary.
rm -f "$OUT/.runresults"
: > "$OUT/.runresults"
echo
echo "Running tests under ASan..."
echo "$TESTS" | while IFS='|' read -r name srcs extra; do
    [ -z "$name" ] && continue
    out="$OUT/$name.out"
    [ -x "$out" ] || { echo "  SKIP $name (binary missing)"; continue; }
    if "$out" >"$OUT/$name.runlog" 2>&1; then
        echo "  PASS $name"
        echo "PASS $name" >> "$OUT/.runresults"
    else
        echo "  FAIL $name (see $OUT/$name.runlog)"
        echo "FAIL $name" >> "$OUT/.runresults"
    fi
done

# Aggregate. The shell loops above ran in subshells (pipelines), so we
# read the side-effect files for counts. grep -c exits 1 with no matches,
# which would propagate up under `set -e`; tolerate that with `|| true`
# and a fallback to 0.
pass=$(grep -c '^PASS ' "$OUT/.runresults" 2>/dev/null || true)
fail=$(grep -c '^FAIL ' "$OUT/.runresults" 2>/dev/null || true)
pass=${pass:-0}
fail=${fail:-0}
echo
echo "Sanitizer summary: $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
