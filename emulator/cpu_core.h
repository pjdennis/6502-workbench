#ifndef CPU_CORE_H
#define CPU_CORE_H

#include <stdint.h>

// CPU variant selection. NMOS is the default; 65C02 picks an
// alternate dispatch table with the W65C02S differences and new opcodes.
#define CPU_NMOS  0
#define CPU_65C02 1
extern int cpu_variant;

// 6502 CPU registers
extern uint16_t pc;
extern uint8_t sp, a, x, y, status;

// Helper variables
extern uint32_t instructions;
extern uint64_t clockticks6502, clockgoal6502;

// CPU interface
void reset6502(void);
void exec6502(uint64_t tickcount);
void step6502(void);
void nmi6502(void);
void irq6502(void);
void hookexternal(void *funcptr);

// These must be provided by the host
extern uint8_t read6502(uint16_t address);
extern void write6502(uint16_t address, uint8_t value);

// Optional bus-transaction taps. When non-NULL, every read6502/write6502
// performed by the CPU dispatch is mirrored to the tap with the (addr,
// data) it observed. Used by the Harte harness
// (tests/harte_runner.c) and test_cpu_bus_tap.c. Default is NULL (no overhead
// beyond a per-access null-pointer check).
extern void (*cpu_bus_read_tap)(uint16_t addr, uint8_t data);
extern void (*cpu_bus_write_tap)(uint16_t addr, uint8_t data);

// Optional external memory hooks. When set, the CPU dispatch routes
// every memory access through these instead of the host's read6502 /
// write6502 (the bus-model machines install these so the CPU
// reads/writes go to the ROM/RAM/VIA chips on the bus).
extern uint8_t (*cpu_external_read)(uint16_t addr);
extern void    (*cpu_external_write)(uint16_t addr, uint8_t data);

// 65C02 WAI / STP pending state (read-only inspection from outside the
// core; the wendy2c run loop polls stp_pending to know when to exit).
extern int cpu_wai_pending(void);
extern int cpu_stp_pending(void);

// Clear the WAI-pending flag without dispatching an interrupt. The real
// W65C02S wakes from WAI on any IRQ or NMI regardless of the I mask --
// when the mask blocks the dispatch, WAI still completes and the CPU
// runs the next instruction with the interrupt staying pending in the
// peripheral. cpu_65c02_tick calls this on any asserted bus->irq /
// bus->nmi (in addition to the I-gated dispatch) to model that.
extern void cpu_clear_wai(void);

#endif
