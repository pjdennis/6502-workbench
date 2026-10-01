# Harte known-deltas

Opcodes where our CPU implementation diverges from the
SingleStepTests/65x02 vectors. The runner reports each as FAIL; this
file documents *why* each one is acceptable for our purposes (or
flags it as a real bug to chase).

## Summary as of the first harness version (not re-measured since)

With `HARTE_LIMIT=200`:
- `6502/`: pass=229 fail=27
- `wdc65c02/`: pass=237 fail=17 skip=2 (`cb`/`db` are empty in upstream)

## NMOS undocumented opcodes

These are opcodes the 6502 chip executes via internal microcode
side effects; the documented Fake6502-derived implementation models
them only loosely (most as NOPs or with simple combined-op
semantics that don't match every flag combination). Acceptable
because no wendy2c program uses them and the assembler bootstrap
doesn't either.

| Op | Mnemonic | Notes |
|----|----------|-------|
| `0B` | `ANC #` | NOP in our impl |
| `2B` | `ANC #` | NOP in our impl |
| `4B` | `ASR #` (a.k.a. ALR) | NOP |
| `6B` | `ARR #` | NOP |
| `8B` | `XAA #` (highly unstable) | NOP |
| `93` | `SHA (zp),Y` | NOP |
| `9B` | `TAS abs,Y` | NOP |
| `9C` | `SHY abs,X` | NOP / addr-NOP |
| `9E` | `SHX abs,Y` | NOP |
| `9F` | `SHA abs,Y` | NOP |
| `AB` | `LAX #` | LAX in NMOS table but flag delta vs Harte |
| `BB` | `LAS abs,Y` | NOP / addr-NOP |
| `CB` | `AXS #` (a.k.a. SBX) | NOP |

## NMOS ADC/SBC BCD edge cases

The Harte vectors test ADC/SBC with arbitrary operands including
"invalid" BCD nibbles (`$0A..$0F`, `$A0..$F0`). The 6502 result on
those is documented as "undefined"; different chips give different
answers. Our implementation matches the most common reference but
diverges on ~1-2% of vectors per opcode. Acceptable -- on-target
wendy2c code never uses BCD ADC/SBC with invalid operands (in fact
it always `cld`s first so BCD is off entirely).

Affected NMOS opcodes (small-percentage failures):
`61, 63, 65, 67, 69, 6D, 6F, 71, 73, 75, 77, 7B, 7D, 7F` (ADC and
combined ADC undoc), `E1..FF` analogous SBC.

## 65C02 ADC/SBC BCD edge cases

Same root cause as the NMOS BCD edge cases. The W65C02S also
documents the result as undefined for invalid BCD operands. ~1-7%
of vectors per opcode mismatch.

Affected wdc65c02 opcodes:
`61, 65, 69, 71, 72, 75, 79, 7D` (ADC) and
`E1, E5, E9, ED, F1, F2, F5, F9, FD` (SBC).

## Empty (untested) opcodes

`wdc65c02/cb.json` (`WAI`) and `wdc65c02/db.json` (`STP`) are empty
in the upstream Tom Harte set: those instructions don't fit the
"single-step state transition" model, so they aren't tested. The
runner reports SKIP.
