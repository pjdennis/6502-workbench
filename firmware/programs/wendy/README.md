# Wendy programs

Programs for Wendy (v1), most from 2020-21, including blink and hello, 4-bit and banked-RAM LCD variants, timer/interrupt/shift-register tests, serial and upload tests, multitasking demos (`*_multitasking_test*.s`, `wendy_multitasking_test.s`), the mini graphic display tests (`mini_display_*`) and `keyboard.s`. `template.s` is a starting point.

They include `base_config_v1.inc` (or an older variant) and libraries from `firmware/lib/`. Some 2020-21 programs no longer assemble against the current libraries; `firmware/manifest.txt` records these as `FAIL`.

Upload to RAM with `tools/upload/compile_and_upload_wendy.sh <program.s>`; the `hello_ram*` programs are the ones written for the RAM loader. Of those, `hello_ram_2000.s`, `hello_ram_3000.s` and `hello_ram_minimal.s` still assemble; `hello_ram.s`, `hello_ram2.s` and `hello_ram_smaller.s` are `FAIL`.
