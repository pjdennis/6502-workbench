/* emu_run_bbcbplus: the BBC Model B+128 from the command line -- slots, module, program, the run and --exit-report (see emu_bbcbplus.h). */
#include "emu_bbcbplus.h"

#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

#include "bbc_mos.h"
#include "cpu_core.h"
#include "chips/bbc_memory.h"
#include "chips/bbc_module.h"

static void report(const struct bbc_machine *m, const struct emu_opts *opts) {
    fprintf(stderr, "bbcbplus: exit  cpu_cycles=%llu  pc=$%04X  (%s)\n",
            (unsigned long long)clockticks6502, m->end_pc, bbc_end_name(m->end));
    if (m->fault) fprintf(stderr, "bbcbplus: %s\n", m->fault);
    fprintf(stderr, "bbcbplus: romsel=$%02X  $F4=$%02X  mos-calls=%llu\n", m->mem->romsel, m->mem->ram[0xF4],
            (unsigned long long)m->mos_calls);
    if (m->module)
        fprintf(stderr, "bbcbplus: module: slot %d, %s %s, bank %d, bank switches %llu\n", opts->bbc_module_slot,
                m->module->scheme == BBC_MODULE_DIRECT16 ? "direct16" : "cc128", m->module->ram ? "RAM" : "ROM",
                m->module->bank, (unsigned long long)m->module->switches);
    fprintf(stderr, "bbcbplus: files: opened=%llu  bytes-read=%llu  bytes-written=%llu\n",
            (unsigned long long)m->files_opened, (unsigned long long)m->bytes_read,
            (unsigned long long)m->bytes_written);
    if (m->cfg.dfs)
        fprintf(stderr, "bbcbplus: dfs: most-open=%llu  most-writing=%llu\n", (unsigned long long)m->most_open,
                (unsigned long long)m->most_writing);
    fprintf(stderr, "bbcbplus: checks: mos-memory-writes=%llu  romsel-mismatches=%llu\n",
            (unsigned long long)m->mos_writes, (unsigned long long)m->romsel_mismatches);
    for (uint64_t i = 0; i < m->mos_writes && i < BBC_MAX_REPORTED; i++)
        fprintf(stderr, "bbcbplus:   write to $%04X by code at $%04X\n", m->first_writes[i].addr, m->first_writes[i].pc);
    for (uint64_t i = 0; i < m->romsel_mismatches && i < BBC_MAX_REPORTED; i++)
        fprintf(stderr, "bbcbplus:   call to $%04X from $%04X with ROMSEL unlike $F4\n", m->first_mismatches[i].addr,
                m->first_mismatches[i].pc);
}

int emu_run_bbcbplus(const struct emu_opts *opts) {
    static struct bbc_memory_state mem;
    static struct bbc_module_state module;
    static struct bbc_machine m;
    struct chip mem_chip, module_chip;

    bbc_memory_init(&mem_chip, &mem);
    unsigned ram = 0;
    bbc_slot_list(opts->bbc_sideways_ram, &ram);   /* cli.c checked it */
    for (int s = 0; s < BBC_SLOTS; s++)
        if (ram & (1u << s)) mem.kind[s] = BBC_SLOT_RAM;
    for (int s = 0; s < BBC_SLOTS; s++) {
        if (!opts->bbc_roms[s]) continue;
        int rc = bbc_memory_load_rom(&mem, s, opts->bbc_roms[s]);
        if (rc != 0) {
            fprintf(stderr, "bbcbplus: %s %s\n", rc == -2 ? "larger than 16 KB:" : "could not read --bbc-rom",
                    opts->bbc_roms[s]);
            return 1;
        }
    }
    int has_module = opts->bbc_module_filename || opts->bbc_module_ram;
    if (has_module) {
        enum bbc_module_scheme scheme = opts->bbc_module_scheme == BBC_SCHEME_DIRECT16 ? BBC_MODULE_DIRECT16
                                                                                       : BBC_MODULE_CC128;
        bbc_module_init(&module_chip, &module, scheme, opts->bbc_module_ram, opts->bbc_module_bank);
        if (opts->bbc_module_filename) {
            long n = bbc_module_load(&module, opts->bbc_module_filename);
            if (n < 0) {
                fprintf(stderr, n == -2 ? "bbcbplus: --bbc-module %s is larger than %d bytes\n"
                                        : "bbcbplus: could not read --bbc-module %s\n",
                        opts->bbc_module_filename, bbc_module_banks(scheme) * BBC_MODULE_BANK_SIZE);
                return 1;
            }
        }
        mem.kind[opts->bbc_module_slot] = BBC_SLOT_MODULE;
    }

    struct bbc_config cfg = {
        .disk_dir = opts->disk_dir,
        .page = (uint16_t)(opts->bbc_page >= 0 ? opts->bbc_page : 0x1900),
        .shadow = opts->bbc_shadow,
        .strict = opts->bbc_strict,
        .dfs = opts->bbc_dfs,
        .command = opts->bbc_command,
        .more_commands = opts->bbc_more_commands,
        .more_count = opts->bbc_more_count,
        .entry = opts->load_address,
    };
    bbc_machine_init(&m, &cfg, &mem, has_module ? &module : NULL);
    if (opts->code_filename) {
        struct stat st;
        if (stat(opts->code_filename, &st) != 0) {
            fprintf(stderr, "bbcbplus: could not open %s\n", opts->code_filename);
            return 1;
        }
        if (opts->load_address + (long)st.st_size > 0x8000) {
            fprintf(stderr, "bbcbplus: %s does not fit in main RAM at $%04lX\n", opts->code_filename,
                    opts->load_address);
            return 1;
        }
        if (bbc_load_into(&m, opts->code_filename, (uint16_t)opts->load_address) < 0) {
            fprintf(stderr, "bbcbplus: could not open %s\n", opts->code_filename);
            return 1;
        }
    }

    int status = bbc_machine_run(&m, opts->cycle_cap);
    if ((m.end == BBC_END_FAULT || m.end == BBC_END_STRICT) && !opts->exit_report)
        fprintf(stderr, "bbcbplus: %s\n", m.fault);
    if (m.end == BBC_END_CAP && !opts->exit_report)
        fprintf(stderr, "bbcbplus: the cycle cap (%llu) ended the run at $%04X\n",
                (unsigned long long)opts->cycle_cap, m.end_pc);
    if (opts->exit_report) report(&m, opts);
    bbc_machine_close(&m);
    return status;
}
