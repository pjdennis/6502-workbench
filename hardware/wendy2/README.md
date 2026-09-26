# Wendy 2

A 65C02 breadboard computer with GAL22V10 glue logic. It went through three revisions in April 2022. The current hardware is **revision c**, which is why the firmware and emulator use the name `wendy2c`.

| Revision | Commit | Date | What changed |
|---|---|---|---|
| Wendy 2 | `6be57cd` | 2022-04-10 | 65C02, 4 MHz, VIA at `$F000`, 4-bit LCD. No RAM banking. |
| 2b | `14951d4` | 2022-04-23 | Banking added: 4 bank-select lines on PORTB, "2 banks of 32K". |
| **2c** | `ae2865b` | 2022-04-30 | New memory map "designed for a 512K RAM chip". A 5th bank line (PB4) and the 22V10 PLD ([`22V10-wendy2c.pld`](22V10-wendy2c.pld)) with a dual-speed clock (ROM accesses at half speed). 15 lower banks at `$0000–$3FFF` for multitasking, fixed RAM at `$4000–$7FFF`, and 8 upper 32K banks. |

Within rev c:
- `e1d6a90` and `bfdce80` (2022-05/06): PLD updates.
- `ba13b19` (2022-06-02): crystal swapped to 9.72 MHz.
- `2b57f7d` (2022-07-22): 2b-specific code removed.
- 2026-05: the emulator's board model (`emulator/chips/`) generates its decode logic straight from the `.pld`.
- `8a8eb82` (2026-05-14) made config `$18` upper RAM. `17e4a78` (2026-09-23) restored it: **cfg `$18` = upper ROM, with lower bank 2**. That is the owner's decision, and the emulator's config-map tests enforce it.
- The graphic display pins PA1/PA2 are reused for CONTROL_BUTTON/CONTROL_LED, so the graphic display is disabled in `base_config_wendy2c.inc`.

`pin-mappings.txt` records the RAM address-line pin mapping (A15, R15–R18). The per-configuration memory map is documented in [`emulator/README.md`](../../emulator/README.md).

Program the AFT22V10C using:

minipro --no-write-protect --device 'ATF22V10C(UES)' --write 22V10-wendy2c.jed
