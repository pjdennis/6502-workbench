# Repository-level Makefile. Run from the repository root:
#   make            build the emulator (emulator/emulator.out)
#   make test       emulator C unit tests + wendy2c end-to-end goldens
# The assembler bootstrap lives in asm/Makefile, prog8 in prog8/Makefile.
# Emulator tests open paths like emulator/web and emulator/tests/... relative
# to the current directory, so they must run from the repository root.

all: emulator/emulator.out

clean:
	rm -f emulator/emulator.out
	rm -rf emulator/tests/out

.PHONY: all clean test michael-goldens wendy2c-goldens wendy2c-lcd-trace wendy2c-merge-sort wendy2c-serial-link wendy2c-live-sigint michael-web wendy2c-web wendy2c-lcd5x10 web-machine-switch web-audio-buffer timer2-cycles

EMU_SRCS = emulator/emulator.c emulator/direct_io.c emulator/file_io.c emulator/console.c emulator/cpu_core.c emulator/stubs.c emulator/trace.c emulator/cli.c emulator/emu_run.c emulator/bus.c emulator/emu_wendy2c.c emulator/emu_michael.c emulator/ps2_keys.c emulator/lcd_report.c emulator/pace.c emulator/tty_alt_screen.c emulator/audio.c emulator/web_server.c emulator/web_run.c emulator/web_json.c emulator/serial_link.c emulator/chips/osc.c emulator/chips/clock_22v10.c emulator/chips/rom_28c256.c emulator/chips/ram_628128.c emulator/chips/via_6522.c emulator/chips/lcd_hd44780.c emulator/chips/glue_michael.c emulator/chips/ps2_keyboard_board.c emulator/chips/serial_usb.c emulator/chips/led_buttons.c emulator/chips/fpga_bus.c emulator/chips/fpga_text.c emulator/chips/cpu_65c02.c emulator/chips/syscall_ports.c
EMU_HDRS = emulator/direct_io.h emulator/file_io.h emulator/console.h emulator/cpu_core.h emulator/stubs.h emulator/trace.h emulator/cli.h emulator/emu_run.h emulator/bus.h emulator/emu_wendy2c.h emulator/emu_michael.h emulator/ps2_keys.h emulator/lcd_report.h emulator/pace.h emulator/tty_alt_screen.h emulator/audio.h emulator/web_server.h emulator/web_run.h emulator/web_json.h emulator/serial_link.h emulator/chips/osc.h emulator/chips/clock_22v10.h emulator/chips/clock_22v10_pld_generated.h emulator/chips/rom_28c256.h emulator/chips/ram_628128.h emulator/chips/via_6522.h emulator/chips/lcd_hd44780.h emulator/chips/glue_michael.h emulator/chips/ps2_keyboard_board.h emulator/chips/serial_usb.h emulator/chips/led_buttons.h emulator/chips/fpga_bus.h emulator/chips/fpga_text.h emulator/chips/cpu_65c02.h

# Path to the .pld source whose equations define the wendy2c memory
# map. clock_22v10_pld_generated.h is rebuilt by pld_to_c.py whenever
# either the .pld or the generator script changes.
WENDY2C_PLD = hardware/wendy2/22V10-wendy2c.pld

emulator/chips/clock_22v10_pld_generated.h: $(WENDY2C_PLD) emulator/pld_to_c.py
	emulator/pld_to_c.py $(WENDY2C_PLD) -o $@

# miniaudio (vendored, used by emulator/audio.c) needs math, pthreads,
# and dynamic loading for runtime backend probing (ALSA/PulseAudio on
# Linux). macOS picks CoreAudio frameworks; Windows links built-in libs
# automatically.
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
  AUDIO_LDLIBS = -lm -lpthread -framework CoreFoundation -framework CoreAudio -framework AudioUnit
else ifeq ($(UNAME_S),Linux)
  AUDIO_LDLIBS = -lm -lpthread -ldl
else
  AUDIO_LDLIBS = -lm -lpthread
endif

emulator/emulator.out: $(EMU_SRCS) $(EMU_HDRS) emulator/vendor/miniaudio.h
	gcc -O2 -march=native -flto=auto -DNDEBUG -o emulator/emulator.out $(EMU_SRCS) $(AUDIO_LDLIBS)

# C unit tests
C_TESTS = emulator/tests/out/test_smoke.out emulator/tests/out/test_file_io.out emulator/tests/out/test_console.out emulator/tests/out/test_trace.out emulator/tests/out/test_cli.out emulator/tests/out/test_stubs.out emulator/tests/out/test_emu_run.out emulator/tests/out/test_bus.out emulator/tests/out/test_cpu_variant.out emulator/tests/out/test_cpu_65c02_fixes.out emulator/tests/out/test_cpu_65c02_group_a.out emulator/tests/out/test_cpu_65c02_group_b.out emulator/tests/out/test_cpu_65c02_bit_ops.out emulator/tests/out/test_cpu_65c02_wai_stp.out emulator/tests/out/test_cpu_bus_tap.out emulator/tests/out/test_dormann.out emulator/tests/out/test_machine_dispatch.out emulator/tests/out/test_chip_osc.out emulator/tests/out/test_chip_clock.out emulator/tests/out/test_chip_rom.out emulator/tests/out/test_chip_ram.out emulator/tests/out/test_chip_cpu_65c02.out emulator/tests/out/test_chip_via.out emulator/tests/out/test_pld_literal.out emulator/tests/out/test_pld_config_map.out emulator/tests/out/test_serial_link.out emulator/tests/out/test_chip_lcd.out emulator/tests/out/test_hd44780_font.out emulator/tests/out/test_chip_serial_usb.out emulator/tests/out/test_chip_led_buttons.out emulator/tests/out/test_chip_fpga_bus.out emulator/tests/out/test_audio.out emulator/tests/out/test_web_json.out emulator/tests/out/test_web_smoke.out emulator/tests/out/test_ps2_keys.out emulator/tests/out/test_direct_io.out

# Must follow the C_TESTS definition: make expands prerequisites when it
# reads the rule.
test: $(C_TESTS) michael-goldens michael-web wendy2c-goldens wendy2c-lcd-trace wendy2c-merge-sort wendy2c-serial-link wendy2c-live-sigint wendy2c-web wendy2c-lcd5x10 web-machine-switch web-audio-buffer timer2-cycles
	@for t in $(C_TESTS); do ./$$t || exit 1; done

# End-to-end Michael golden-LCD tests. Same vasm-skip pattern as the
# wendy2c goldens below.
michael-goldens: emulator/emulator.out
	@emulator/tests/michael_goldens.sh

# Playwright test of michael's --web page: the 20x4 LCD, keys typed on
# the page reaching the PS/2 keyboard, reset and the PA2 LED. SKIPs if
# vasm or playwright are missing.
michael-web: emulator/emulator.out
	@python3 emulator/tests/michael_web_playwright_test.py

# End-to-end wendy2c golden-LCD tests. Requires vasm6502_oldstyle on
# PATH; the script SKIPs (exits 0) if vasm is missing. Depends on the
# emulator binary -- chained behind it to ensure it's built fresh.
wendy2c-goldens: emulator/emulator.out
	@emulator/tests/wendy2c_goldens.sh

# End-to-end test for --lcd-trace: builds hello_ram_4000_wendy2c.s,
# runs the emulator with trace enabled, asserts the trace file contains
# a sequence of LCD frames. Same vasm-skip pattern as the goldens.
wendy2c-lcd-trace: emulator/emulator.out
	@emulator/tests/lcd_trace_test.sh

# End-to-end goldens for the wendy2 merge-sort demo. Uses --lcd-trace
# to assert on intermediate LCD frames (init -> fill -> sort -> verify
# -> final), not just the closing frame. Same vasm-skip pattern.
wendy2c-merge-sort: emulator/emulator.out
	@emulator/tests/merge_sort_goldens.sh

# End-to-end test of the host-driven --serial-link transport: a Python
# client uploads a framed payload bit-by-bit over the Unix socket, the
# boot ROM receives it, and we check the final LCD frame. Same
# vasm-skip pattern as the goldens.
wendy2c-serial-link: emulator/emulator.out
	@emulator/tests/wendy2c_serial_link_test.sh

# Python PTY test: confirms --live restores the terminal cleanly when
# Ctrl-C arrives mid-render. Same vasm-skip pattern as the goldens.
wendy2c-live-sigint: emulator/emulator.out
	@python3 emulator/tests/live_sigint_test.py

# Playwright test: drives the --web HTTP+WS server with headless
# Chromium, verifies the LCD canvas renders CGRAM custom characters
# pixel-by-pixel, that state + audio frames flow over the WS, and that
# button clicks round-trip. SKIPs if vasm or playwright are missing.
wendy2c-web: emulator/emulator.out
	@python3 emulator/tests/web_playwright_test.py

# Playwright test focused on HD44780 5x10 mode: loads the 5x10 demo
# payload, verifies the snapshot reports f5x10=1, and that the LCD
# canvas grew to the 11-row-per-cell size. SKIPs same as wendy2c-web.
wendy2c-lcd5x10: emulator/emulator.out
	@python3 emulator/tests/lcd_5x10_playwright_test.py

# Playwright test: one open page follows the emulator on its port from
# wendy2c to michael and back. SKIPs same as wendy2c-web.
web-machine-switch: emulator/emulator.out
	@python3 emulator/tests/web_machine_switch_playwright_test.py

# The web page's audio jitter buffer (web/audio_buffer.js) in headless
# Chromium, with simulated time. SKIPs if playwright is missing.
web-audio-buffer:
	@python3 emulator/tests/web_audio_buffer_test.py

# michael_timer2_test2.s's T2 ticks, timed on the CPU and VIA chips by
# via_t2_runner. Requires vasm6502_oldstyle on PATH.
timer2-cycles: emulator/tests/out/via_t2_runner.out
	@python3 emulator/tests/timer2_cycles_test.py

emulator/tests/out/via_t2_runner.out: emulator/tests/via_t2_runner.c emulator/cpu_core.c emulator/cpu_core.h emulator/chips/cpu_65c02.c emulator/chips/cpu_65c02.h emulator/chips/via_6522.c emulator/chips/via_6522.h emulator/bus.c emulator/bus.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/via_t2_runner.c emulator/cpu_core.c emulator/chips/cpu_65c02.c emulator/chips/via_6522.c emulator/bus.c

emulator/tests/out/test_direct_io.out: emulator/tests/test_direct_io.c emulator/direct_io.c emulator/direct_io.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_direct_io.c emulator/direct_io.c

emulator/tests/out/test_ps2_keys.out: emulator/tests/test_ps2_keys.c emulator/ps2_keys.c emulator/ps2_keys.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_ps2_keys.c emulator/ps2_keys.c

emulator/tests/out/test_smoke.out: emulator/tests/test_smoke.c emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -o $@ $<

emulator/tests/out/test_file_io.out: emulator/tests/test_file_io.c emulator/file_io.c emulator/file_io.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -o $@ emulator/tests/test_file_io.c emulator/file_io.c

emulator/tests/out/test_console.out: emulator/tests/test_console.c emulator/console.c emulator/console.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -o $@ emulator/tests/test_console.c emulator/console.c

emulator/tests/out/test_trace.out: emulator/tests/test_trace.c emulator/trace.c emulator/trace.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_trace.c emulator/trace.c

emulator/tests/out/test_cli.out: emulator/tests/test_cli.c emulator/cli.c emulator/cli.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_cli.c emulator/cli.c

emulator/tests/out/test_stubs.out: emulator/tests/test_stubs.c emulator/stubs.c emulator/stubs.h emulator/direct_io.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_stubs.c emulator/stubs.c

emulator/tests/out/test_emu_run.out: emulator/tests/test_emu_run.c emulator/emu_run.c emulator/emu_run.h emulator/cli.c emulator/cli.h emulator/trace.c emulator/trace.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_emu_run.c emulator/emu_run.c emulator/cli.c emulator/trace.c

emulator/tests/out/test_bus.out: emulator/tests/test_bus.c emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_bus.c emulator/bus.c

emulator/tests/out/test_cpu_variant.out: emulator/tests/test_cpu_variant.c emulator/cpu_core.c emulator/cpu_core.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/test_cpu_variant.c emulator/cpu_core.c

emulator/tests/out/test_cpu_65c02_fixes.out: emulator/tests/test_cpu_65c02_fixes.c emulator/cpu_core.c emulator/cpu_core.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/test_cpu_65c02_fixes.c emulator/cpu_core.c

emulator/tests/out/test_cpu_65c02_group_a.out: emulator/tests/test_cpu_65c02_group_a.c emulator/cpu_core.c emulator/cpu_core.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/test_cpu_65c02_group_a.c emulator/cpu_core.c

emulator/tests/out/test_cpu_65c02_group_b.out: emulator/tests/test_cpu_65c02_group_b.c emulator/cpu_core.c emulator/cpu_core.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/test_cpu_65c02_group_b.c emulator/cpu_core.c

emulator/tests/out/test_cpu_65c02_bit_ops.out: emulator/tests/test_cpu_65c02_bit_ops.c emulator/cpu_core.c emulator/cpu_core.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/test_cpu_65c02_bit_ops.c emulator/cpu_core.c

emulator/tests/out/test_cpu_65c02_wai_stp.out: emulator/tests/test_cpu_65c02_wai_stp.c emulator/cpu_core.c emulator/cpu_core.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/test_cpu_65c02_wai_stp.c emulator/cpu_core.c

emulator/tests/out/test_cpu_bus_tap.out: emulator/tests/test_cpu_bus_tap.c emulator/cpu_core.c emulator/cpu_core.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/test_cpu_bus_tap.c emulator/cpu_core.c

emulator/tests/out/test_dormann.out: emulator/tests/test_dormann.c emulator/cpu_core.c emulator/cpu_core.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/test_dormann.c emulator/cpu_core.c

emulator/tests/out/test_machine_dispatch.out: emulator/tests/test_machine_dispatch.c emulator/cli.c emulator/cli.h emulator/cpu_core.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_machine_dispatch.c emulator/cli.c

emulator/tests/out/test_chip_osc.out: emulator/tests/test_chip_osc.c emulator/chips/osc.c emulator/chips/osc.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_chip_osc.c emulator/chips/osc.c emulator/bus.c

emulator/tests/out/test_chip_clock.out: emulator/tests/test_chip_clock.c emulator/chips/clock_22v10.c emulator/chips/clock_22v10.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_chip_clock.c emulator/chips/clock_22v10.c emulator/bus.c

emulator/tests/out/test_chip_rom.out: emulator/tests/test_chip_rom.c emulator/chips/rom_28c256.c emulator/chips/rom_28c256.h emulator/chips/clock_22v10.c emulator/chips/clock_22v10.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_chip_rom.c emulator/chips/rom_28c256.c emulator/chips/clock_22v10.c emulator/bus.c

emulator/tests/out/test_chip_ram.out: emulator/tests/test_chip_ram.c emulator/chips/ram_628128.c emulator/chips/ram_628128.h emulator/chips/clock_22v10.c emulator/chips/clock_22v10.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_chip_ram.c emulator/chips/ram_628128.c emulator/chips/clock_22v10.c emulator/bus.c

emulator/tests/out/test_chip_cpu_65c02.out: emulator/tests/test_chip_cpu_65c02.c emulator/chips/cpu_65c02.c emulator/chips/syscall_ports.c emulator/chips/cpu_65c02.h emulator/emu_wendy2c.c emulator/emu_wendy2c.h emulator/lcd_report.c emulator/lcd_report.h emulator/pace.c emulator/pace.h emulator/cli.c emulator/cli.h emulator/cpu_core.c emulator/cpu_core.h emulator/bus.c emulator/bus.h emulator/tty_alt_screen.c emulator/tty_alt_screen.h emulator/web_server.c emulator/web_server.h emulator/web_run.c emulator/web_run.h emulator/web_json.c emulator/web_json.h emulator/chips/clock_22v10.c emulator/chips/clock_22v10.h emulator/chips/rom_28c256.c emulator/chips/rom_28c256.h emulator/chips/ram_628128.c emulator/chips/ram_628128.h emulator/chips/via_6522.c emulator/chips/via_6522.h emulator/chips/lcd_hd44780.c emulator/chips/lcd_hd44780.h emulator/chips/serial_usb.c emulator/chips/serial_usb.h emulator/chips/led_buttons.c emulator/chips/led_buttons.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/test_chip_cpu_65c02.c emulator/chips/cpu_65c02.c emulator/chips/syscall_ports.c emulator/emu_wendy2c.c emulator/lcd_report.c emulator/pace.c emulator/cli.c emulator/cpu_core.c emulator/bus.c emulator/tty_alt_screen.c emulator/web_server.c emulator/web_run.c emulator/web_json.c emulator/chips/clock_22v10.c emulator/chips/rom_28c256.c emulator/chips/ram_628128.c emulator/chips/via_6522.c emulator/chips/lcd_hd44780.c emulator/chips/serial_usb.c emulator/chips/led_buttons.c

emulator/tests/out/test_chip_serial_usb.out: emulator/tests/test_chip_serial_usb.c emulator/chips/serial_usb.c emulator/chips/serial_usb.h emulator/chips/via_6522.c emulator/chips/via_6522.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_chip_serial_usb.c emulator/chips/serial_usb.c emulator/chips/via_6522.c emulator/bus.c

emulator/tests/out/test_chip_via.out: emulator/tests/test_chip_via.c emulator/chips/via_6522.c emulator/chips/via_6522.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_chip_via.c emulator/chips/via_6522.c emulator/bus.c

emulator/tests/out/test_pld_config_map.out: emulator/tests/test_pld_config_map.c emulator/chips/clock_22v10.c emulator/chips/clock_22v10.h emulator/chips/clock_22v10_pld_generated.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_pld_config_map.c emulator/chips/clock_22v10.c emulator/bus.c

emulator/tests/out/test_pld_literal.out: emulator/tests/test_pld_literal.c emulator/chips/clock_22v10.c emulator/chips/clock_22v10.h emulator/chips/clock_22v10_pld_generated.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_pld_literal.c emulator/chips/clock_22v10.c emulator/bus.c

emulator/tests/out/test_serial_link.out: emulator/tests/test_serial_link.c emulator/serial_link.c emulator/serial_link.h emulator/chips/via_6522.c emulator/chips/via_6522.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_serial_link.c emulator/serial_link.c emulator/chips/via_6522.c emulator/bus.c

emulator/tests/out/test_chip_lcd.out: emulator/tests/test_chip_lcd.c emulator/chips/lcd_hd44780.c emulator/chips/lcd_hd44780.h emulator/chips/via_6522.c emulator/chips/via_6522.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_chip_lcd.c emulator/chips/lcd_hd44780.c emulator/chips/via_6522.c emulator/bus.c

emulator/tests/out/test_hd44780_font.out: emulator/tests/test_hd44780_font.c emulator/chips/hd44780_a00_font.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_hd44780_font.c

emulator/tests/out/test_chip_led_buttons.out: emulator/tests/test_chip_led_buttons.c emulator/chips/led_buttons.c emulator/chips/led_buttons.h emulator/chips/via_6522.c emulator/chips/via_6522.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_chip_led_buttons.c emulator/chips/led_buttons.c emulator/chips/via_6522.c emulator/bus.c

emulator/tests/out/test_chip_fpga_bus.out: emulator/tests/test_chip_fpga_bus.c emulator/chips/fpga_bus.c emulator/chips/fpga_bus.h emulator/chips/fpga_text.c emulator/chips/fpga_text.h emulator/chips/via_6522.c emulator/chips/via_6522.h emulator/bus.c emulator/bus.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_chip_fpga_bus.c emulator/chips/fpga_bus.c emulator/chips/fpga_text.c emulator/chips/via_6522.c emulator/bus.c

# audio.c pulls in miniaudio (vendored); needs system audio libs even
# in the test, since miniaudio_init resolves backends at runtime.
emulator/tests/out/test_audio.out: emulator/tests/test_audio.c emulator/audio.c emulator/audio.h emulator/vendor/miniaudio.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_audio.c emulator/audio.c $(AUDIO_LDLIBS)

emulator/tests/out/test_web_json.out: emulator/tests/test_web_json.c emulator/web_json.c emulator/web_json.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_web_json.c emulator/web_json.c

emulator/tests/out/test_web_smoke.out: emulator/tests/test_web_smoke.c emulator/web_server.c emulator/web_server.h emulator/web_json.c emulator/web_json.h emulator/tests/greatest.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -o $@ emulator/tests/test_web_smoke.c emulator/web_server.c emulator/web_json.c

# Rebuild every C_TESTS binary with AddressSanitizer + UndefinedBehaviorSanitizer
# + LeakSanitizer and run them. Output binaries land in emulator/tests/out/san/
# so the regular optimized .out files stay intact. Asan flags slow the binaries
# by ~2x but catch leaks, use-after-free, double-free, OOB, signed-overflow
# and other UB. The shell script (run_sanitizers.sh) carries the source list
# rather than the Makefile -- the list mirrors C_TESTS by name + sources.
sanitizers: emulator/emulator.out
	@emulator/tests/run_sanitizers.sh

.PHONY: sanitizers

# Tom Harte ProcessorTests harness (phase 3h). Opt-in: requires
# `emulator/tests/harte/fetch.sh` to populate `emulator/tests/harte/data/`
# first. When data is missing, harte_runner.out prints a warning and
# exits 0 so this target is safe to wire into CI without the fetch.
harte: emulator/tests/out/harte_runner.out
	@./emulator/tests/out/harte_runner.out

emulator/tests/out/harte_runner.out: emulator/tests/harte_runner.c emulator/cpu_core.c emulator/cpu_core.h
	@mkdir -p emulator/tests/out
	gcc -Wall -Werror -Wno-unused-function -o $@ emulator/tests/harte_runner.c emulator/cpu_core.c

.PHONY: harte
