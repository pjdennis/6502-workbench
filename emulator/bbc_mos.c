/* The bbcbplus machine: the CPU on the B+ memory map, the MOS's host traps, its calls in C, and the checks (see bbc_mos.h). */
#include "bbc_mos.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "cpu_core.h"
#include "bbc_mos_rom_generated.h"

#define FLAG_C 0x01
#define FLAG_V 0x40

#define ZP_ROMCOPY 0xF4
#define ZP_ESCAPE 0xFF
#define LANGUAGE 0x028C

static struct bbc_machine *active;

/* ---- memory ---- */

int bbc_in_mos(uint16_t addr) {
    return addr >= 0xC000 && !(addr >= 0xFC00 && addr < 0xFF00);
}

int bbc_mos_owned(uint16_t addr, uint16_t page) {
    if (addr < 0x0100)
        return addr >= 0x90 && addr != ZP_ROMCOPY && addr != 0xF6 && addr != 0xF7 && !(addr >= 0xA8 && addr <= 0xAF);
    if (addr >= 0x0200 && addr < 0x0400)
        return addr >= 0x0236 && !(addr >= 0x02A1 && addr <= 0x02B0);
    return addr >= 0x0800 && addr < page;
}

static uint8_t bus_rd(struct bbc_machine *m, uint16_t addr) {
    m->bus.addr = addr;
    m->bus.rwb = 1;
    bbc_memory_decode(&m->bus, m->mem);
    uint8_t d = m->mem->open_bus;
    bus_read(&m->bus, addr, &d);
    return d;
}

static void bus_wr(struct bbc_machine *m, uint16_t addr, uint8_t v) {
    m->bus.addr = addr;
    m->bus.rwb = 0;
    bbc_memory_decode(&m->bus, m->mem);
    bus_write(&m->bus, addr, v);
}

uint8_t bbc_peek(struct bbc_machine *m, uint16_t addr) { return bus_rd(m, addr); }
void bbc_poke(struct bbc_machine *m, uint16_t addr, uint8_t v) { bus_wr(m, addr, v); }

static uint16_t peek16(struct bbc_machine *m, uint16_t addr) {
    return (uint16_t)(bus_rd(m, addr) | bus_rd(m, (uint16_t)(addr + 1)) << 8);
}

static uint32_t peek32(struct bbc_machine *m, uint16_t addr) {
    uint32_t v = 0;
    for (int i = 3; i >= 0; i--) v = v << 8 | bus_rd(m, (uint16_t)(addr + i));
    return v;
}

static void poke32(struct bbc_machine *m, uint16_t addr, uint32_t v) {
    for (int i = 0; i < 4; i++) bus_wr(m, (uint16_t)(addr + i), (uint8_t)(v >> (8 * i)));
}

/* The byte at addr as the CPU would fetch it, without a fetch's effects
 * (the module's bank stays) */
static uint8_t quiet_peek(struct bbc_machine *m, uint16_t addr) {
    struct bbc_memory_state *mem = m->mem;
    if (m->module && addr >= 0x8000 && addr < 0xC000) {
        m->bus.addr = addr;
        bbc_memory_decode(&m->bus, mem);
        if (m->bus.romcs)
            return m->module->data[(uint32_t)m->module->bank * BBC_MODULE_BANK_SIZE + (addr - 0x8000)];
    }
    return bus_rd(m, addr);
}

static void note(struct bbc_violation *list, uint64_t count, uint16_t addr, uint16_t at) {
    if (count <= BBC_MAX_REPORTED) list[count - 1] = (struct bbc_violation){ addr, at };
}

static uint8_t cpu_read_hook(uint16_t addr) {
    struct bbc_machine *m = active;
    uint8_t d = bus_rd(m, addr);
    m->mem->open_bus = d;
    return d;
}

static void cpu_write_hook(uint16_t addr, uint8_t v) {
    struct bbc_machine *m = active;
    if (!bbc_in_mos(m->cur_pc) && bbc_mos_owned(addr, m->cfg.page)) {
        m->mos_writes++;
        note(m->first_writes, m->mos_writes, addr, m->cur_pc);
        if (m->cfg.strict && m->end == BBC_RUNNING) {
            static char msg[96];
            snprintf(msg, sizeof msg, "write to MOS memory $%04X by code at $%04X", addr, m->cur_pc);
            m->fault = msg;
            m->end = BBC_END_STRICT;
        }
    }
    bus_wr(m, addr, v);
    m->mem->open_bus = v;
}

long bbc_load_into(struct bbc_machine *m, const char *path, uint16_t addr) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    long n = 0;
    int c;
    while ((c = fgetc(f)) != EOF) bus_wr(m, (uint16_t)(addr + n++), (uint8_t)c);
    fclose(f);
    return n;
}

/* ---- the CPU's state ---- */

static void push(struct bbc_machine *m, uint8_t v) {
    bus_wr(m, (uint16_t)(0x0100 + sp), v);
    sp--;
}

/* Enter code at addr as if called by JSR from just before ret */
static void call(struct bbc_machine *m, uint16_t addr, uint16_t ret) {
    uint16_t r = (uint16_t)(ret - 1);
    push(m, (uint8_t)(r >> 8));
    push(m, (uint8_t)r);
    pc = addr;
}

static void set_c(int on) { status = on ? (uint8_t)(status | FLAG_C) : (uint8_t)(status & ~FLAG_C); }
static void raise(uint16_t error_block) { pc = error_block; }
static uint16_t xy(void) { return (uint16_t)(x | y << 8); }

/* ---- the filing system: the --disk directory ---- */

/* A file name at addr: leading spaces skipped, ended by CR, space or 0.
 * Used as given, except that "/" and ".." are refused, and that a leading
 * "./" (or several) names the --disk directory itself and is dropped: a
 * tool that joins a directory and a name, as the Lathe compiler does with
 * its directory ".", reaches the files there. Returns the address after
 * it, or 0 for a bad name. */
static uint16_t read_name(struct bbc_machine *m, uint16_t addr, char *name, size_t size) {
    while (bus_rd(m, addr) == ' ') addr++;
    size_t n = 0;
    for (uint8_t c; (c = bus_rd(m, addr)) != 0x0D && c != ' ' && c != 0; addr++) {
        if (n + 1 >= size || c < 0x20 || c == 0x7F) return 0;
        name[n++] = (char)c;
    }
    name[n] = 0;
    size_t skip = 0;
    while (name[skip] == '.' && name[skip + 1] == '/') skip += 2;
    if (skip) memmove(name, name + skip, n - skip + 1);
    n -= skip;
    if (!n || strchr(name, '/') || strstr(name, "..")) return 0;
    return addr;
}

/* The host path of a name; 0 if there is no --disk (an error is raised) */
static int host_path(struct bbc_machine *m, const char *name, const char *suffix, char *path, size_t size) {
    if (!m->cfg.disk_dir) {
        raise(BBC_MOS_E_NO_DISK);
        return 0;
    }
    snprintf(path, size, "%s/%s%s", m->cfg.disk_dir, name, suffix);
    return 1;
}

/* The .inf beside a file: "NAME LOAD EXEC [LENGTH]", in hex */
static void read_inf(const char *path, uint32_t *load, uint32_t *exec) {
    char inf[1100];
    snprintf(inf, sizeof inf, "%s.inf", path);
    *load = *exec = 0;
    FILE *f = fopen(inf, "r");
    if (!f) return;
    char name[256];
    unsigned long l, e;
    if (fscanf(f, "%255s %lx %lx", name, &l, &e) == 3) {
        *load = (uint32_t)l;
        *exec = (uint32_t)e;
    }
    fclose(f);
}

static int write_inf(const char *path, const char *name, uint32_t load, uint32_t exec, uint32_t length) {
    char inf[1100];
    snprintf(inf, sizeof inf, "%s.inf", path);
    FILE *f = fopen(inf, "w");
    if (!f) return -1;
    fprintf(f, "%s %08X %08X %08X\n", name, (unsigned)load, (unsigned)exec, (unsigned)length);
    return fclose(f);
}

/* 0 none, 1 file, 2 directory */
static int object_type(const char *path, uint32_t *length) {
    struct stat st;
    if (stat(path, &st) != 0) return 0;
    if (length) *length = (uint32_t)st.st_size;
    return S_ISDIR(st.st_mode) ? 2 : 1;
}

/* Load a file at its own load address (or at addr if use_addr). Raises
 * the error and returns -1 when it can't. */
static int load_file(struct bbc_machine *m, const char *name, int use_addr, uint32_t addr,
                     uint32_t *load, uint32_t *exec, uint32_t *length) {
    char path[1024];
    if (!host_path(m, name, "", path, sizeof path)) return -1;
    if (object_type(path, NULL) != 1) {
        raise(BBC_MOS_E_FILE_NOT_FOUND);
        return -1;
    }
    read_inf(path, load, exec);
    long n = bbc_load_into(m, path, (uint16_t)(use_addr ? addr : *load));
    if (n < 0) {
        raise(BBC_MOS_E_DISC_FAULT);
        return -1;
    }
    *length = (uint32_t)n;
    return 0;
}

static int save_file(struct bbc_machine *m, const char *name, uint32_t load, uint32_t exec,
                     uint32_t start, uint32_t end) {
    char path[1024];
    if (!host_path(m, name, "", path, sizeof path)) return -1;
    if (end < start) {
        raise(BBC_MOS_E_BAD_ADDRESS);
        return -1;
    }
    FILE *f = fopen(path, "wb");
    if (!f) {
        raise(BBC_MOS_E_DISC_FAULT);
        return -1;
    }
    for (uint32_t a = start; a < end; a++) fputc(bus_rd(m, (uint16_t)a), f);
    if (fclose(f) != 0 || write_inf(path, name, load, exec, end - start) != 0) {
        raise(BBC_MOS_E_DISC_FAULT);
        return -1;
    }
    return 0;
}

static struct bbc_file *handle_file(struct bbc_machine *m, uint8_t h) {
    if (h < BBC_FIRST_HANDLE || h >= BBC_FIRST_HANDLE + BBC_MAX_FILES) return NULL;
    struct bbc_file *bf = &m->files[h - BBC_FIRST_HANDLE];
    return bf->f ? bf : NULL;
}

/* stdio wants a seek between reading and writing a stream */
static void turn(struct bbc_file *bf, int op) {
    if (bf->last_op && bf->last_op != op) fseek(bf->f, ftell(bf->f), SEEK_SET);
    bf->last_op = (int8_t)op;
}

static long file_ext(struct bbc_file *bf) {
    long at = ftell(bf->f);
    fseek(bf->f, 0, SEEK_END);
    long ext = ftell(bf->f);
    fseek(bf->f, at, SEEK_SET);
    bf->last_op = 0;
    return ext;
}

static void file_seek(struct bbc_file *bf, uint32_t ptr) {
    fseek(bf->f, (long)ptr, SEEK_SET);
    bf->last_op = 0;
    bf->eof_hit = 0;
}

static void close_file(struct bbc_file *bf) {
    if (bf->f) fclose(bf->f);
    memset(bf, 0, sizeof *bf);
}

void bbc_machine_close(struct bbc_machine *m) {
    for (int i = 0; i < BBC_MAX_FILES; i++) close_file(&m->files[i]);
}

/* OSFIND: A = 0 close Y (0: all); $40 input, $80 output, $C0 update, XY the name */
static void os_find(struct bbc_machine *m) {
    if (a == 0) {
        if (y == 0) {
            bbc_machine_close(m);
            return;
        }
        struct bbc_file *bf = handle_file(m, y);
        if (!bf) raise(BBC_MOS_E_CHANNEL);
        else close_file(bf);
        return;
    }
    char name[256], path[1024];
    if (!read_name(m, xy(), name, sizeof name)) {
        raise(BBC_MOS_E_BAD_NAME);
        return;
    }
    if (!host_path(m, name, "", path, sizeof path)) return;
    int slot = 0;
    while (slot < BBC_MAX_FILES && m->files[slot].f) slot++;
    if (slot == BBC_MAX_FILES) {
        raise(BBC_MOS_E_TOO_MANY_OPEN);
        return;
    }
    uint8_t mode = a & 0xC0;
    FILE *f = NULL;
    if (object_type(path, NULL) != 2)
        f = fopen(path, mode == 0x40 ? "rb" : mode == 0x80 ? "w+b" : "r+b");
    if (!f) {
        a = 0;   /* not found: A = 0, no error */
        return;
    }
    m->files[slot] = (struct bbc_file){ f, mode, 0, 0 };
    m->files_opened++;
    a = (uint8_t)(BBC_FIRST_HANDLE + slot);
}

/* OSBGET: Y the handle; A the byte, C set at the end of the file (A = $FE),
 * the error EOF when read again there */
static void os_bget(struct bbc_machine *m) {
    struct bbc_file *bf = handle_file(m, y);
    if (!bf) {
        raise(BBC_MOS_E_CHANNEL);
        return;
    }
    turn(bf, 1);
    int c = fgetc(bf->f);
    if (c == EOF) {
        if (bf->eof_hit) {
            raise(BBC_MOS_E_EOF);
            return;
        }
        bf->eof_hit = 1;
        a = 0xFE;
        set_c(1);
        return;
    }
    a = (uint8_t)c;
    m->bytes_read++;
    set_c(0);
}

/* OSBPUT: Y the handle, A the byte */
static void os_bput(struct bbc_machine *m) {
    struct bbc_file *bf = handle_file(m, y);
    if (!bf) {
        raise(BBC_MOS_E_CHANNEL);
        return;
    }
    if (bf->mode == 0x40) {
        raise(BBC_MOS_E_READ_ONLY);
        return;
    }
    turn(bf, 2);
    if (fputc(a, bf->f) == EOF) raise(BBC_MOS_E_DISC_FAULT);
    else m->bytes_written++;
    bf->eof_hit = 0;
}

/* OSARGS: Y = 0: A = 0 the filing system (4, the DFS), 1 the command line
 * tail into X..X+3, $FF flush all. Y a handle: A = 0 read PTR, 1 write
 * PTR, 2 read EXT, $FF flush; the value in zero page X..X+3. */
static void os_args(struct bbc_machine *m) {
    uint16_t zp = x;
    if (y == 0) {
        if (a == 0) a = 4;
        else if (a == 1) poke32(m, zp, m->tail);
        else if (a == 0xFF) for (int i = 0; i < BBC_MAX_FILES; i++) if (m->files[i].f) fflush(m->files[i].f);
        return;
    }
    struct bbc_file *bf = handle_file(m, y);
    if (!bf) {
        raise(BBC_MOS_E_CHANNEL);
        return;
    }
    switch (a) {
    case 0: poke32(m, zp, (uint32_t)ftell(bf->f)); break;
    case 1: file_seek(bf, peek32(m, zp)); break;
    case 2: poke32(m, zp, (uint32_t)file_ext(bf)); break;
    case 0xFF: fflush(bf->f); break;
    default: break;
    }
}

/* OSGBPB 1-4: the block at XY: +0 handle, +1 data address, +5 count, +9 PTR.
 * 1 and 3 use the PTR given, 2 and 4 the current one; 1 and 2 write, 3
 * and 4 read. On exit the address has moved on, the count is what was not
 * transferred, PTR is the new one, C is set if not all was; A = 0. */
static void os_gbpb(struct bbc_machine *m) {
    uint16_t blk = xy();
    if (a < 1 || a > 4) return;
    struct bbc_file *bf = handle_file(m, bus_rd(m, blk));
    if (!bf) {
        raise(BBC_MOS_E_CHANNEL);
        return;
    }
    int writing = a <= 2;
    if (writing && bf->mode == 0x40) {
        raise(BBC_MOS_E_READ_ONLY);
        return;
    }
    if (a == 1 || a == 3) file_seek(bf, peek32(m, (uint16_t)(blk + 9)));
    uint32_t addr = peek32(m, (uint16_t)(blk + 1)), count = peek32(m, (uint16_t)(blk + 5));
    turn(bf, writing ? 2 : 1);
    while (count) {
        if (writing) {
            if (fputc(bus_rd(m, (uint16_t)addr), bf->f) == EOF) break;
            m->bytes_written++;
        } else {
            int c = fgetc(bf->f);
            if (c == EOF) break;
            bus_wr(m, (uint16_t)addr, (uint8_t)c);
            m->bytes_read++;
        }
        addr++;
        count--;
    }
    poke32(m, (uint16_t)(blk + 1), addr);
    poke32(m, (uint16_t)(blk + 5), count);
    poke32(m, (uint16_t)(blk + 9), (uint32_t)ftell(bf->f));
    set_c(count != 0);
    a = 0;
}

/* OSFILE: the block at XY: +0 the name's address, +2 load, +6 exec, +10
 * start or length, +14 end or attributes. */
static void os_file(struct bbc_machine *m) {
    uint16_t blk = xy();
    char name[256], path[1024];
    if (!read_name(m, peek16(m, blk), name, sizeof name)) {
        raise(BBC_MOS_E_BAD_NAME);
        return;
    }
    if (!host_path(m, name, "", path, sizeof path)) return;
    uint32_t load, exec, length = 0;
    switch (a) {
    case 0xFF:   /* load: at +2 if the low byte of +6 is 0, else at the file's own address */
        if (load_file(m, name, bus_rd(m, (uint16_t)(blk + 6)) == 0, peek32(m, (uint16_t)(blk + 2)),
                      &load, &exec, &length) != 0) return;
        break;
    case 0x00:   /* save +10 to +14, with +2 and +6 as its addresses */
        load = peek32(m, (uint16_t)(blk + 2));
        exec = peek32(m, (uint16_t)(blk + 6));
        if (save_file(m, name, load, exec, peek32(m, (uint16_t)(blk + 10)), peek32(m, (uint16_t)(blk + 14))) != 0)
            return;
        object_type(path, &length);
        break;
    case 1: case 2: case 3: case 4: case 5: case 6: {
        int type = object_type(path, &length);
        read_inf(path, &load, &exec);
        if (type == 1 && a >= 1 && a <= 3) {
            if (a != 3) load = peek32(m, (uint16_t)(blk + 2));
            if (a != 2) exec = peek32(m, (uint16_t)(blk + 6));
            if (write_inf(path, name, load, exec, length) != 0) {
                raise(BBC_MOS_E_DISC_FAULT);
                return;
            }
        }
        if (a == 6 && type == 1) {
            char inf[1100];
            snprintf(inf, sizeof inf, "%s.inf", path);
            remove(path);
            remove(inf);
        }
        if (type == 0) {
            a = 0;
            return;
        }
        if (a <= 4) {   /* calls 1-4 return the type and leave the block */
            a = (uint8_t)type;
            return;
        }
        a = (uint8_t)type;
        if (type == 2) load = exec = length = 0;
        poke32(m, (uint16_t)(blk + 2), load);
        poke32(m, (uint16_t)(blk + 6), exec);
        poke32(m, (uint16_t)(blk + 10), length);
        poke32(m, (uint16_t)(blk + 14), 0);
        return;
    }
    default:
        return;
    }
    a = 1;
    poke32(m, (uint16_t)(blk + 2), load);
    poke32(m, (uint16_t)(blk + 6), exec);
    poke32(m, (uint16_t)(blk + 10), length);
    poke32(m, (uint16_t)(blk + 14), 0);
}

/* ---- OSCLI ---- */

static uint16_t skip_spaces(struct bbc_machine *m, uint16_t addr) {
    while (bus_rd(m, addr) == ' ') addr++;
    return addr;
}

/* A hex number at *addr (after spaces); returns 0 if there is none */
static int read_hex(struct bbc_machine *m, uint16_t *addr, uint32_t *v) {
    uint16_t p = skip_spaces(m, *addr);
    int digits = 0;
    *v = 0;
    for (uint8_t c; isxdigit(c = bus_rd(m, p)); p++, digits++)
        *v = *v << 4 | (uint32_t)(isdigit(c) ? c - '0' : toupper(c) - 'A' + 10);
    *addr = p;
    return digits > 0;
}

/* *RUN name, a "/" command or *name: load at its load address and enter its execution
 * address (the code's RTS returns to OSCLI's caller) */
static void run_file(struct bbc_machine *m, const char *name, uint16_t after) {
    uint32_t load, exec, length;
    if (load_file(m, name, 0, 0, &load, &exec, &length) != 0) return;
    m->tail = skip_spaces(m, after);
    pc = (uint16_t)exec;
}

/* The command word at p (letters), matched against a built-in */
static int command_is(struct bbc_machine *m, uint16_t p, const char *word, uint16_t *after) {
    size_t n = strlen(word);
    for (size_t i = 0; i < n; i++)
        if (toupper(bus_rd(m, (uint16_t)(p + i))) != word[i]) return 0;
    uint8_t next = bus_rd(m, (uint16_t)(p + n));
    if (next != ' ' && next != 0x0D) return 0;
    *after = (uint16_t)(p + n);
    return 1;
}

static uint16_t command_start(struct bbc_machine *m, uint16_t line) {
    uint16_t p = line;
    for (uint8_t c; (c = bus_rd(m, p)) == ' ' || c == '*'; p++) {}
    return p;
}

static void os_cli(struct bbc_machine *m) {
    uint16_t line = xy(), p = command_start(m, line), after;
    uint8_t first = bus_rd(m, p);
    char name[256];
    if (first == 0x0D || first == '|') return;
    int slash = first == '/';
    if (slash || command_is(m, p, "RUN", &after)) {
        uint16_t end = read_name(m, slash ? (uint16_t)(p + 1) : after, name, sizeof name);
        if (!end) raise(BBC_MOS_E_BAD_NAME);
        else run_file(m, name, end);
    } else if (command_is(m, p, "HELP", &after)) {
        y = (uint8_t)(skip_spaces(m, after) - line);   /* service call 9, Y at its argument */
        pc = BBC_MOS_CLI_HELP;
    } else if (command_is(m, p, "LOAD", &after)) {
        uint16_t end = read_name(m, after, name, sizeof name);
        uint32_t addr, load, exec, length;
        if (!end) {
            raise(BBC_MOS_E_BAD_NAME);
            return;
        }
        int given = read_hex(m, &end, &addr);
        load_file(m, name, given, addr, &load, &exec, &length);
    } else if (command_is(m, p, "SAVE", &after)) {
        /* *SAVE name start end|+length [exec [reload]] */
        uint16_t q = read_name(m, after, name, sizeof name);
        uint32_t start, end, exec, reload;
        if (!q) {
            raise(BBC_MOS_E_BAD_NAME);
            return;
        }
        if (!read_hex(m, &q, &start)) {
            raise(BBC_MOS_E_BAD_ADDRESS);
            return;
        }
        q = skip_spaces(m, q);
        int plus = bus_rd(m, q) == '+';
        if (plus) q++;
        if (!read_hex(m, &q, &end)) {
            raise(BBC_MOS_E_BAD_ADDRESS);
            return;
        }
        if (plus) end += start;
        if (!read_hex(m, &q, &exec)) exec = start;
        if (!read_hex(m, &q, &reload)) reload = start;
        save_file(m, name, reload, exec, start, end);
    } else {
        y = (uint8_t)(p - line);   /* service call 4, Y the offset from ($F2) */
        pc = BBC_MOS_CLI_SVC;
    }
}

/* No ROM claimed the command: a file of that name is run, else Bad command */
static void os_cli_file(struct bbc_machine *m) {
    uint16_t p = command_start(m, peek16(m, 0xF2));
    char name[256], path[1024];
    uint16_t end = read_name(m, p, name, sizeof name);
    if (end && m->cfg.disk_dir) {
        host_path(m, name, "", path, sizeof path);
        if (object_type(path, NULL) == 1) {
            run_file(m, name, end);
            return;
        }
    }
    raise(BBC_MOS_E_BAD_COMMAND);
}

/* ---- OSBYTE, OSWORD ---- */

/* OSBYTE 142: an empty slot (type 0 in the table) has no effect; a ROM
 * without a language entry is the error "This is not a language" */
static void enter_language(struct bbc_machine *m, uint8_t slot) {
    slot &= 0x0F;
    uint8_t type = bus_rd(m, (uint16_t)(BBC_MOS_ROMTAB + slot));
    if (type == 0) return;
    if (!(type & 0x40)) {
        raise(BBC_MOS_E_NOT_LANGUAGE);
        return;
    }
    bus_wr(m, LANGUAGE, slot);
    bus_wr(m, ZP_ROMCOPY, slot);
    bus_wr(m, BBC_ROMSEL, slot);
    /* A language never returns on a real machine; here an RTS from it ends the run */
    sp = 0xFF;
    a = 1;
    call(m, BBC_MOS_BYTE_LANG, BBC_MOS_EXIT_RET);
}

static void os_byte(struct bbc_machine *m) {
    switch (a) {
    case 0:     /* the OS version: an error for X = 0, else X = 2 (OS 2.00, the B+) */
        if (x == 0) raise(BBC_MOS_E_OS);
        else x = 2;
        break;
    case 126: { /* acknowledge Escape */
        uint8_t flag = bus_rd(m, ZP_ESCAPE);
        bus_wr(m, ZP_ESCAPE, flag & 0x7F);
        x = (flag & 0x80) ? 0xFF : 0;
        break;
    }
    case 127: { /* the end of file X? */
        struct bbc_file *bf = handle_file(m, x);
        if (!bf) {
            raise(BBC_MOS_E_CHANNEL);
            break;
        }
        x = ftell(bf->f) >= file_ext(bf) ? 0xFF : 0;
        break;
    }
    case 130:   /* the high order address: the I/O processor */
        x = y = 0xFF;
        break;
    case 131:   /* OSHWM, PAGE */
        x = (uint8_t)m->cfg.page;
        y = (uint8_t)(m->cfg.page >> 8);
        break;
    case 132:   /* HIMEM */
        x = 0;
        y = m->cfg.shadow ? 0x80 : 0x7C;
        break;
    case 142:   /* enter the language ROM in slot X */
        enter_language(m, x);
        break;
    case 143:   /* a service call to the ROMs */
        pc = BBC_MOS_BYTE_SVC;
        break;
    case 252: { /* the current language ROM, $028C: X the old value, Y the next variable's */
        uint8_t old = bus_rd(m, LANGUAGE);
        bus_wr(m, LANGUAGE, (uint8_t)((old & y) ^ x));
        x = old;
        y = bus_rd(m, LANGUAGE + 1);
        break;
    }
    case 170:   /* the address of the ROM type table */
        x = (uint8_t)BBC_MOS_ROMTAB;
        y = (uint8_t)(BBC_MOS_ROMTAB >> 8);
        break;
    default:
        pc = BBC_MOS_BYTE_UNKNOWN;
        break;
    }
}

static uint64_t centiseconds(struct bbc_machine *m) {
    return (uint64_t)((int64_t)(clockticks6502 / 20000) + m->clock_offset);   /* 2 MHz */
}

/* OSWORD 0: the block at XY: +0 the buffer, +2 the most characters, +3
 * and +4 the lowest and highest accepted. The line from standard input,
 * ended by CR (a host newline is one), without echo; DEL removes a
 * character; at the end of input with nothing read, Escape (C set). */
static void read_line(struct bbc_machine *m) {
    uint16_t blk = xy(), buf = peek16(m, blk);
    uint8_t max = bus_rd(m, (uint16_t)(blk + 2)), lo = bus_rd(m, (uint16_t)(blk + 3)), hi = bus_rd(m, (uint16_t)(blk + 4));
    int n = 0, c;
    for (;;) {
        c = fgetc(m->cfg.in);
        if (c == EOF && n == 0) {
            bus_wr(m, ZP_ESCAPE, bus_rd(m, ZP_ESCAPE) | 0x80);
            y = 0;
            set_c(1);
            return;
        }
        if (c == EOF || c == '\n' || c == '\r') break;
        if (c == 0x7F || c == 0x08) {
            if (n) n--;
            continue;
        }
        if (c < lo || c > hi || n >= max) continue;
        bus_wr(m, (uint16_t)(buf + n++), (uint8_t)c);
    }
    bus_wr(m, (uint16_t)(buf + n), 0x0D);
    y = (uint8_t)n;
    set_c(0);
}

static void os_word(struct bbc_machine *m) {
    uint16_t blk = xy();
    switch (a) {
    case 0:
        read_line(m);
        break;
    case 1: {   /* read the clock: five bytes, centiseconds, low byte first */
        uint64_t cs = centiseconds(m);
        for (int i = 0; i < 5; i++) bus_wr(m, (uint16_t)(blk + i), (uint8_t)(cs >> (8 * i)));
        break;
    }
    case 2: {   /* write the clock */
        uint64_t cs = 0;
        for (int i = 4; i >= 0; i--) cs = cs << 8 | bus_rd(m, (uint16_t)(blk + i));
        m->clock_offset = (int64_t)cs - (int64_t)(clockticks6502 / 20000);
        break;
    }
    default:
        pc = BBC_MOS_WORD_UNKNOWN;
        break;
    }
}

/* ---- reset ---- */

/* A slot holds a ROM if the copyright offset at $8007 points at "\0(C)" */
static int slot_is_rom(struct bbc_machine *m, int slot, uint8_t *type) {
    uint8_t saved = m->mem->romsel;
    m->mem->romsel = (uint8_t)slot;
    uint16_t c = (uint16_t)(0x8000 + bus_rd(m, 0x8007));
    int rom = bus_rd(m, c) == 0 && bus_rd(m, (uint16_t)(c + 1)) == '(' && bus_rd(m, (uint16_t)(c + 2)) == 'C'
           && bus_rd(m, (uint16_t)(c + 3)) == ')';
    *type = bus_rd(m, 0x8006);
    m->mem->romsel = saved;
    return rom;
}

/* A command line put at $0700 (at most 254 bytes and the CR) and passed to OSCLI, with the
 * run's end as its return address */
static void start_command(struct bbc_machine *m, const char *text) {
    size_t n = strlen(text);
    if (n > 254) n = 254;
    for (size_t i = 0; i < n; i++) bus_wr(m, (uint16_t)(BBC_COMMAND_BUFFER + i), (uint8_t)text[i]);
    bus_wr(m, (uint16_t)(BBC_COMMAND_BUFFER + n), 0x0D);
    x = (uint8_t)BBC_COMMAND_BUFFER;
    y = (uint8_t)(BBC_COMMAND_BUFFER >> 8);
    call(m, BBC_MOS_OSCLI, BBC_MOS_EXIT_RET);
}

static void mos_reset(struct bbc_machine *m) {
    int language = -1;
    for (int slot = 0; slot < BBC_SLOTS; slot++) {
        uint8_t type;
        if (!slot_is_rom(m, slot, &type)) type = 0;
        bus_wr(m, (uint16_t)(BBC_MOS_ROMTAB + slot), type);
        if (type & 0x40) language = slot;
    }
    uint8_t current = (uint8_t)(language >= 0 ? language : 15);
    bus_wr(m, LANGUAGE, current);
    bus_wr(m, ZP_ROMCOPY, current);
    bus_wr(m, BBC_ROMSEL, current);
    bus_wr(m, ZP_ESCAPE, 0);
    if (m->cfg.command) start_command(m, m->cfg.command);
    else call(m, (uint16_t)m->cfg.entry, BBC_MOS_EXIT_RET);
}

/* The command or program returned: the next command, if there is one, from $0700 with the
 * stack reset, as a language's prompt would pass a line typed after the last one returned;
 * otherwise the run ends with status 0 */
static void command_returned(struct bbc_machine *m) {
    if (m->next_command < m->cfg.more_count) {
        sp = 0xFF;
        start_command(m, m->cfg.more_commands[m->next_command++]);
        return;
    }
    m->end = BBC_END_RETURNED;
}

/* The default BRKV handler: the message after the error number at ($FD).
 * By now the MOS has selected the language ROM again; an error block in
 * the sideways window is read from the ROM that raised it ($024A). */
static void report_error(struct bbc_machine *m) {
    uint16_t p = peek16(m, 0xFD);
    uint8_t romsel = m->mem->romsel;
    if (p >= 0x8000 && p < 0xC000) m->mem->romsel = bus_rd(m, 0x024A);
    fflush(m->cfg.out);
    for (int i = 1; i < 256; i++) {
        uint8_t c = bus_rd(m, (uint16_t)(p + i));
        if (!c) break;
        fputc(c, m->cfg.err);
    }
    fputc('\n', m->cfg.err);
    m->mem->romsel = romsel;
    m->end = BBC_END_ERROR;
}

/* ---- the traps ---- */

static void trap(struct bbc_machine *m, uint16_t at) {
    m->mos_calls++;
    switch (at) {
    case BBC_MOS_T_RESET: mos_reset(m); break;
    case BBC_MOS_T_EXIT:  command_returned(m); break;
    case BBC_MOS_T_BRK:   report_error(m); break;
    case BBC_MOS_T_CLI:   os_cli(m); break;
    case BBC_MOS_T_CLI_FILE: os_cli_file(m); break;
    case BBC_MOS_T_BYTE:  os_byte(m); break;
    case BBC_MOS_T_WORD:  os_word(m); break;
    case BBC_MOS_T_WRCH:  fputc(a, m->cfg.out); break;
    case BBC_MOS_T_RDCH: {
        int c = fgetc(m->cfg.in);
        if (c == EOF) {
            bus_wr(m, ZP_ESCAPE, bus_rd(m, ZP_ESCAPE) | 0x80);
            a = 0x1B;
            set_c(1);
        } else {
            a = (uint8_t)c;
            set_c(0);
        }
        break;
    }
    case BBC_MOS_T_FILE:  os_file(m); break;
    case BBC_MOS_T_ARGS:  os_args(m); break;
    case BBC_MOS_T_BGET:  os_bget(m); break;
    case BBC_MOS_T_BPUT:  os_bput(m); break;
    case BBC_MOS_T_GBPB:  os_gbpb(m); break;
    case BBC_MOS_T_FIND:  os_find(m); break;
    default: break;
    }
}

static int is_trap(uint16_t at) {
    for (int i = 0; i < BBC_MOS_TRAP_COUNT; i++) if (bbc_mos_traps[i] == at) return 1;
    return 0;
}

static int is_entry(uint16_t at) {
    if (at >= BBC_MOS_OSRDRM_ENTRY && at <= BBC_MOS_OSRDCH) return (at - BBC_MOS_OSRDRM_ENTRY) % 3 == 0;
    return at == BBC_MOS_OSASCI || at == BBC_MOS_OSNEWL || at == BBC_MOS_OSWRCH || at == BBC_MOS_OSWORD
        || at == BBC_MOS_OSBYTE || at == BBC_MOS_OSCLI;
}

/* The NMOS opcodes that halt the CPU */
static int is_jam(uint8_t op) {
    return (op & 0x0F) == 0x02 && op != 0xA2 && (op & 0xF0) != 0x80 && op != 0xC2 && op != 0xE2;
}

static char fault_text[128];

static void fault(struct bbc_machine *m, enum bbc_end end, const char *fmt, unsigned a1, unsigned a2) {
    snprintf(fault_text, sizeof fault_text, fmt, a1, a2);
    m->fault = fault_text;
    m->end = end;
}

void bbc_machine_init(struct bbc_machine *m, const struct bbc_config *cfg,
                      struct bbc_memory_state *mem, struct bbc_module_state *module) {
    memset(m, 0, sizeof *m);
    m->cfg = *cfg;
    if (!m->cfg.out) m->cfg.out = stdout;
    if (!m->cfg.in) m->cfg.in = stdin;
    if (!m->cfg.err) m->cfg.err = stderr;
    if (!m->cfg.page) m->cfg.page = 0x1900;
    m->mem = mem;
    m->module = module;
    memcpy(mem->mos, bbc_mos_rom, sizeof mem->mos);
    bus_init(&m->bus);
    if (module) {   /* ahead of the memory map: it answers what the decode gives it */
        bbc_module_chip(&m->module_chip, module);
        bus_add_chip(&m->bus, &m->module_chip);
    }
    bbc_memory_chip(&m->mem_chip, mem);
    bus_add_chip(&m->bus, &m->mem_chip);
}

int bbc_machine_run(struct bbc_machine *m, uint64_t cap) {
    active = m;
    cpu_variant = CPU_NMOS;
    cpu_external_read = cpu_read_hook;
    cpu_external_write = cpu_write_hook;
    clockticks6502 = clockgoal6502 = 0;
    status = 0x24;
    reset6502();
    m->prev_pc = m->cur_pc = pc;
    m->end = BBC_RUNNING;
    while (m->end == BBC_RUNNING) {
        if (clockticks6502 >= cap) {
            m->end = BBC_END_CAP;
            break;
        }
        uint16_t at = pc;
        if (at >= 0xC000 && is_trap(at)) {
            if (m->prev_pc != (uint16_t)(at - 1)) {
                fault(m, BBC_END_FAULT, "the MOS trap at $%04X reached from $%04X, not through the MOS", at, m->prev_pc);
                break;
            }
            m->prev_pc = at;
            pc = (uint16_t)(at + 1);
            clockticks6502 += 2;
            trap(m, at);
            continue;
        }
        if (at >= 0xFF00 && is_entry(at) && !bbc_in_mos(m->prev_pc)) {
            uint8_t copy = m->mem->ram[ZP_ROMCOPY];
            if (copy != m->mem->romsel) {
                m->romsel_mismatches++;
                note(m->first_mismatches, m->romsel_mismatches, at, m->prev_pc);
                if (m->cfg.strict) {
                    fault(m, BBC_END_STRICT, "ROMSEL differs from its copy at $F4 on a call to $%04X from $%04X",
                          at, m->prev_pc);
                    break;
                }
            }
        }
        if (is_jam(quiet_peek(m, at))) {
            fault(m, BBC_END_FAULT, "the CPU jammed on opcode $%02X at $%04X", quiet_peek(m, at), at);
            break;
        }
        m->cur_pc = at;
        step6502();
        m->prev_pc = at;
    }
    m->end_pc = pc;
    fflush(m->cfg.out);
    cpu_external_read = NULL;
    cpu_external_write = NULL;
    active = NULL;
    switch (m->end) {
    case BBC_END_RETURNED: return 0;
    case BBC_END_CAP: return 2;
    default: return 1;
    }
}

const char *bbc_end_name(enum bbc_end end) {
    switch (end) {
    case BBC_END_RETURNED: return "returned";
    case BBC_END_ERROR: return "error";
    case BBC_END_FAULT: return "fault";
    case BBC_END_STRICT: return "strict";
    case BBC_END_CAP: return "cycle cap";
    default: return "running";
    }
}
