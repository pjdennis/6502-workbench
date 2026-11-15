#ifndef EMULATOR_BBC_MOS_H
#define EMULATOR_BBC_MOS_H

#include <stdint.h>
#include <stdio.h>

#include "bus.h"
#include "chips/bbc_memory.h"
#include "chips/bbc_module.h"

/* The BBC Model B+128 machine (--machine bbcbplus): an NMOS 6502 on the
 * B+ memory map (chips/bbc_memory.h), the banked module in one slot
 * (chips/bbc_module.h), and the emulator's own MOS: a 6502 ROM
 * (bbc_mos_rom.asm) whose default handlers end in host traps that this
 * file serves.
 *
 * A trap is the byte $02 at one of the ROM's trap sites
 * (bbc_mos_traps[]), acted on only when the instruction just run was the
 * NOP in front of it. That NOP is only ever reached by falling into it
 * from the MOS's own handler, or by entering that handler from its
 * vector. Reaching a trap site in any other way ends the run as a fault,
 * as does a JAM opcode (which halts a real NMOS 6502). A trap's C work
 * takes no emulated time beyond the two cycles counted for the trap. */

#define BBC_MAX_FILES 15
#define BBC_FIRST_HANDLE 0x11
#define BBC_COMMAND_BUFFER 0x0700   /* where --bbc-command's text is put */
#define BBC_MAX_REPORTED 8

enum bbc_end {
    BBC_RUNNING,
    BBC_END_RETURNED,   /* the command or program returned: status 0 */
    BBC_END_ERROR,      /* the default BRKV handler: an error, status 1 */
    BBC_END_FAULT,      /* a jump into a trap or a JAM opcode: status 1 */
    BBC_END_STRICT,     /* --bbc-strict and a check failed: status 1 */
    BBC_END_CAP,        /* --cycle-cap: status 2 */
};

struct bbc_config {
    const char *disk_dir;   /* --disk: the host directory of the filing system, or NULL */
    uint16_t page;          /* OSBYTE 131: OSHWM ($1900) */
    int shadow;             /* --bbc-shadow: OSBYTE 132 answers $8000 (else $7C00) */
    int strict;             /* --bbc-strict: a failed check ends the run */
    const char *command;    /* --bbc-command: passed to OSCLI after reset, or NULL */
    const char *const *more_commands;   /* further --bbc-command lines, each passed to OSCLI from
                                         * $0700 when the one before it returns */
    int more_count;
    long entry;             /* without a command: the program entered after reset, or -1 */
    FILE *out, *in, *err;   /* OSWRCH, OSRDCH/OSWORD 0, error messages */
};

struct bbc_file {
    FILE *f;
    uint8_t mode;           /* $40 input, $80 output, $C0 update */
    uint8_t eof_hit;        /* OSBGET has reported EOF once */
    int8_t last_op;         /* 1 read, 2 write: stdio needs a seek between them */
};

struct bbc_violation {
    uint16_t addr, pc;
};

struct bbc_machine {
    struct bus bus;
    struct chip mem_chip, module_chip;
    struct bbc_memory_state *mem;
    struct bbc_module_state *module;   /* NULL without a module */
    struct bbc_config cfg;

    enum bbc_end end;
    const char *fault;                 /* what ended a BBC_END_FAULT or BBC_END_STRICT run */
    uint16_t prev_pc, cur_pc;          /* the previous and the current instruction */
    uint16_t end_pc;

    /* the checks */
    uint64_t mos_writes;               /* writes to MOS memory by code outside the MOS */
    struct bbc_violation first_writes[BBC_MAX_REPORTED];
    uint64_t romsel_mismatches;        /* ROMSEL != $F4 when a MOS entry point was called */
    struct bbc_violation first_mismatches[BBC_MAX_REPORTED];

    struct bbc_file files[BBC_MAX_FILES];
    uint16_t tail;                     /* OSARGS 1: the command line tail of *RUN */
    int64_t clock_offset;              /* OSWORD 2 */
    uint64_t mos_calls;                /* traps served */
    int next_command;                  /* the next of cfg.more_commands to run */
};

/* Wire the machine: mem and module (NULL for none) are the caller's,
 * already loaded (mem->kind[], ROM images, the module image). The MOS
 * ROM goes into mem->mos. */
void bbc_machine_init(struct bbc_machine *m, const struct bbc_config *cfg,
                      struct bbc_memory_state *mem, struct bbc_module_state *module);

/* Reset and run until the run ends or clockticks6502 reaches cap.
 * Returns the exit status (see enum bbc_end). */
int bbc_machine_run(struct bbc_machine *m, uint64_t cap);

/* Close the files the program left open. */
void bbc_machine_close(struct bbc_machine *m);

/* The MOS's own memory accesses, through the bus as the CPU's are (a
 * read of the module's zone switches its bank), but not checked. */
uint8_t bbc_peek(struct bbc_machine *m, uint16_t addr);
void bbc_poke(struct bbc_machine *m, uint16_t addr, uint8_t v);

/* Load a host file into memory through bbc_poke. Returns its length, or -1. */
long bbc_load_into(struct bbc_machine *m, const char *path, uint16_t addr);

/* Whether code at pc is the MOS's: $C000-$FBFF and $FF00-$FFFF. */
int bbc_in_mos(uint16_t pc);

/* Whether a write there by code outside the MOS is checked: zero page
 * $90-$FF except $F4, $F6/$F7 (OSRDRM's pointer) and $A8-$AF (workspace
 * for * commands); $0200-$03FF except the vectors ($0200-$0235) and the
 * ROM type table ($02A1-$02B0); $0800 up to PAGE. */
int bbc_mos_owned(uint16_t addr, uint16_t page);

const char *bbc_end_name(enum bbc_end end);

#endif
