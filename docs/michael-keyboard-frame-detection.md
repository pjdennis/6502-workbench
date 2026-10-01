# Michael: PS/2 frame detection and fast keyboards

Findings from 2026-09-30. With some keyboards, Michael's keyboard board can't separate the bytes of a command's reply. The driver then never sees the ACK and `keyboard_send_command` hangs. This document records the measurements, the cause, the recommended hardware change and what is still to do.

## Symptom

`firmware/programs/michael/michael_keyboard_info.s` sends Read ID (`$F2`) and shows the reply:

| Keyboard | Result |
|---|---|
| Adesso EasyTouch mini | `ID AB 83` |
| Perixx PERIBOARD-409 Mini | `ID AB 83` |
| MC Saite MC-689 | hangs after showing `ID` |

The MC-689 works with every other test program, typing included. `michael_keyboard_diag.s` shows its arrow keys' four-byte sequences intact (`E0 12 E0 74 E0 F0 74 E0 F0 12` for Right Arrow with Num Lock on). With `$F2` added after start-up, the diagnostic ended `F2bcd[AB]`. The `$F2` went out, but the first byte back was `$AB`, not the ACK `$FA`, and `$83` never arrived.

## How the board finds the end of a byte

The keyboard board shifts each frame from the keyboard into 74HC595s. A frame detector drives the VIA's CA2. CA2 goes low when the keyboard clock starts and goes high again once the clock has been idle for a fixed time, which this document calls the **idle time**. The driver (`firmware/lib/keyboard/keyboard_driver.inc`) treats a falling CA2 edge as the start of a frame and a rising edge as its end. On the rising edge it reads the byte through SOEB.

The idle time was measured on the board at **about 92 µs** (183 T1 ticks of 0.5 µs; see [measurements](#measurements)). The emulator assumes 150 µs (`DETECT_IDLE_US` in `emulator/chips/ps2_keyboard_board.c`).

## Cause

If the keyboard starts its next frame less than the idle time after the previous one ends, CA2 never goes high between them. The driver sees one long frame and reads only the last byte. The shift register has already shifted the earlier one out.

- The Perixx leaves about 440 µs between the frames of its reply. Each frame is seen separately.
- The MC-689's `$FA` and `$AB` came as a single 1.74 ms burst, about 1.75 times the length of a single frame. The `$FA` was lost and the driver read `$AB`. It goes on waiting for an ACK that never comes.
- Then `$83` was lost too. This is inferred, not measured: the gap before it was probably just over the idle time. CA2 rose, but the next frame began before the interrupt handler had switched CA2 back to the falling edge (about 20 µs after the rising edge). The handler then misses that frame's start, and so its end too.

The MC-689 sends scan codes with wider gaps, so typing works. Only command replies come back to back.

PS/2 only requires a device to see the bus idle for 50 µs before it starts a frame. The clock's high phase can last up to 50 µs within a frame. An idle-time detector must outlast the high phase and still end before the next frame starts. So no RC value works with every keyboard. A value of about 40 µs might suit the MC-689, but with almost no margin.

## Recommended hardware change: count the clock pulses

End each frame on its **11th clock pulse** (start bit, 8 data bits, parity, stop bit) instead of after an idle time:

1. **Counter:** a 74HC161 (4-bit counter: asynchronous clear, synchronous load) clocked on the same clock edge the 74HC595s shift on.
2. **Frame complete:** decode a count of 11 (`1011`: Q3·Q1·Q0; 15 can't be reached) as *frame complete* and send it to CA2. It rises right after the 11th bit and stays high until the next frame's first clock. So every frame produces a rising edge, however short the gap.
3. **Back-to-back frames:** while the count is 11, hold the counter's LOAD active with the inputs set to 1. The next frame's first clock then loads 1 instead of counting to 12, so back-to-back frames stay aligned without an idle gap.
4. **Resync:** keep the existing RC idle detector, but use it to clear the counter (its asynchronous CLR) once the bus has been idle. That throws away partial frames (a transmission aborted by the host, a glitch, the host frame's 12th clock for the ACK bit). Its timing no longer decides where a frame ends.
5. **Latch the byte:** clock the 74HC595s' storage registers (RCLK) with *frame complete*, so the byte the CPU reads stays put while the next frame shifts in. The next frame can start 50 µs after the last one, which is less time than the interrupt handler takes to read it.

Another option uses no new chips: route the keyboard clock to a free VIA input (e.g. CB1) and count the bits in software. That costs one interrupt per bit (about 11 per byte, at 60–100 µs intervals). The board's spare pins and the cost in interrupt time would need checking.

### Software changes the hardware change needs

- **Driver:** each rising CA2 edge is one whole frame. Leave CA2 on the rising edge and drop the start/end toggling (`KEYBOARD_RECEIVING`). This also removes the race that lost `$83`.
- **Driver:** `keyboard_send_command` waits for CA2 to fall after pulling the clock low (trace step `b`). With the counter, CA2 no longer falls then, so it needs another way to time the hold, such as a fixed 100 µs delay.
- **ROM:** the driver is built into the Michael ROM (`firmware/boards/michael/michael_services.inc`). Rebuild `hardware/michael/michael_rom.bin` and reprogram the EEPROM.
- **Emulator:** update the frame detector model in `emulator/chips/ps2_keyboard_board.c` to match.

## Measurements

Both programs are in `firmware/programs/michael/`, and the emulator tests in `tools/tests/test_michael_keyboard.py` keep them building. Values are hex T1 ticks of 0.5 µs at 2 MHz. The board was measured with earlier versions of these programs. The committed versions are tidied, and the idle-time program's T1 read is fixed (see TODO).

**Idle time** (`michael_keyboard_frame_detector.s`): the program holds the clock low with SOLB, releases it, and times CA2's rising edge.

| | Readings | Idle time |
|---|---|---|
| Board | `00B7 00B7 01B7 FFB7 00B7 00B7 00B7 00B7` | 183 ticks = 92 µs |
| Emulator | `0133` × 8 | 150 µs plus polling |

`01B7` and `FFB7` were misreads: T1's high byte changed between reading the two halves. The committed program reads the high byte again and retries if it changed.

**Read ID exchange** (`michael_keyboard_frame_timing.s`): each entry is a type, a byte and the time since the previous entry. The types are `b` (clock pulled low), `c` (clock released + 300 µs), `h` (end of the host's frame), `s` (frame start), `a` (end of an ACK frame) and `r` (end of a frame with another byte).

| Keyboard | Log |
|---|---|
| Perixx | `b000000 c000465 h0014AB s00023B aFA07AC s00037C rAB07AB s000368 r8307AA` |
| MC-689 | `b000000 c000465 h0004E2 s000287 rAB0D93` |
| Emulator | `b000000 c000465 h000E01 s0006A6 aFA080C s0006A2 rAB080C s0006A4 r83080D` |

The Perixx takes `$7AC` (982 µs) from each frame's start to its end, including the idle time. The gaps until the next frame's start are 446 µs and 436 µs. On the MC-689, a single start (`s`) is followed by one end, `$D93` (1738 µs) later, carrying `$AB`. Nothing more arrived in the next second.

## TODO

- [ ] Run the committed `michael_keyboard_frame_detector.s` on the board and confirm about `00BC` (the earlier probe read `00B7`; the new T1 read adds a few cycles) with no misreads.
- [ ] Run the committed `michael_keyboard_frame_timing.s` with the MC-689 and the Perixx and confirm the logs above.
- [ ] Measure the MC-689's clock period and the gap between its reply bytes with a logic analyser or scope on the PS/2 clock and data lines. The estimate is a gap of about 50 µs, but it hasn't been measured.
- [ ] Check the board against "Bidirectional PS2 Keyboard Interface Schematic v1.0.pdf" (not in this repository): the RC values, which edge the 74HC595s shift on, and how their RCLK is driven today. Add the schematic, or its details, to `hardware/michael/`.
- [ ] Build the counter-based frame detector (above) and test it with all three keyboards.
- [ ] Driver, ROM and emulator changes for the new detector (above).
- [ ] Until then, consider a timeout on the ACK wait in `keyboard_send_command`, so a fast keyboard (or none) can't hang the board. `michael_keyboard_info.s` would then show `--` for the MC-689. The bytes would still be lost.
- [ ] Set the emulator's `DETECT_IDLE_US` to the measured 92 µs, and add a keyboard option that sends reply bytes 50 µs apart, so the hang can be reproduced in `tools/tests/test_michael_keyboard.py`.
