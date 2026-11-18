/* The bbcbplus machine: the CPU on the B+ memory map, the MOS's host traps, its calls in C, and the checks (see bbc_mos.h). */
#include "bbc_mos.h"

#include <ctype.h>
#include <dirent.h>
#include <strings.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

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

uint16_t bbc_screen_start(int mode) {
    static const uint16_t start[8] = { 0x3000, 0x3000, 0x3000, 0x4000, 0x5800, 0x5800, 0x6000, 0x7C00 };
    return start[mode & 7];
}

static void cpu_write_hook(uint16_t addr, uint8_t v) {
    struct bbc_machine *m = active;
    if (!bbc_in_mos(m->cur_pc) && !m->cfg.shadow && addr >= m->cfg.screen && addr < 0x8000) {
        m->screen_writes++;
        note(m->first_screen_writes, m->screen_writes, addr, m->cur_pc);
        if (m->cfg.strict && m->end == BBC_RUNNING) {
            static char msg[96];
            snprintf(msg, sizeof msg, "write to the screen at $%04X by code at $%04X", addr, m->cur_pc);
            m->fault = msg;
            m->end = BBC_END_STRICT;
        }
    }
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
    if (m->cfg.dfs || m->cfg.adfs) return n ? addr : 0;   /* checked as the DFS or ADFS checks it, by file_path() */
    size_t skip = 0;
    while (name[skip] == '.' && name[skip + 1] == '/') skip += 2;
    if (skip) memmove(name, name + skip, n - skip + 1);
    n -= skip;
    if (!n || strchr(name, '/') || strstr(name, "..")) return 0;
    return addr;
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

/* --bbc-fs dfs. A name is [:D.][X.]NAME: the drive D 0 to 3, the directory X one
 * character ($ if none), NAME one to seven; a character is any from $21 to $7E but
 * . : " # * (BeebWiki, "Acorn DFS disc format") and, here only, /, which a host
 * file name cannot hold. Upper and lower case match. Drive 0 is the --disk
 * directory, drive N its subdirectory ":N"; the file X.NAME is the host file
 * "X.NAME", in the case it was created in, so that a file's host name is its full
 * DFS name, and its .inf file "X.NAME.inf". A drive's catalogue holds 31 files. */
static int dfs_char(int c) { return c > 0x20 && c < 0x7F && !strchr(".:\"#*/", c); }

static int dfs_base_ok(const char *s) {
    size_t n = 0;
    while (s[n] && dfs_char((unsigned char)s[n])) n++;
    return n >= 1 && n <= 7 && !s[n];
}

/* Whether a host file name is a DFS file's: X.NAME */
static int dfs_entry(const char *s) {
    return dfs_char((unsigned char)s[0]) && s[1] == '.' && dfs_base_ok(s + 2);
}

/* The drive, directory and name of a DFS name; 0, or the error to raise */
static uint16_t dfs_parse(const char *s, int *drive, char *dir, const char **base) {
    *drive = 0;
    *dir = '$';
    if (s[0] == ':') {
        if (s[1] < '0' || s[1] > '3') return BBC_MOS_E_BAD_DRIVE;
        if (s[2] != '.') return BBC_MOS_E_BAD_NAME;
        *drive = s[1] - '0';
        s += 3;
    }
    if (s[0] && s[1] == '.') {
        if (!dfs_char((unsigned char)s[0])) return BBC_MOS_E_BAD_NAME;
        *dir = s[0];
        s += 2;
    }
    if (!dfs_base_ok(s)) return BBC_MOS_E_BAD_NAME;
    *base = s;
    return 0;
}

/* ---- --bbc-fs adfs ----
 *
 * The rules are emulator/NOTES-bbcbplus.md's, "ADFS on the B+". A name is a path: [:D.][$.]PART
 * {.PART}, a part one to ten characters from $21 to $7E but # * . : $ & @ ^ " and, here only, /
 * (a host file name cannot hold it); # and * are Wild cards; ^ alone is the parent, @ alone the
 * CSD, $ (or &) first the root; :D. names a drive's root, D 0 (or 4, A, E) or 1 (5, B, F), and the
 * other drive numbers ADFS knows (2, 3, 6, 7, C, D, G, H) are Bad drive here. A name without $ or
 * a drive starts at the CSD (*DIR). Parts match host names without regard to case. Drive 0 is the
 * --disk directory, drive 1 its subdirectory ":1"; an ADFS directory is a host directory, a file
 * a host file (and its .inf beside it); host names that are not ADFS names are not entries.
 *
 * Space, per drive of adfs_sectors (an L disc, 2,560): the map and the root take sectors 0-6, a
 * directory 5, a file its length in whole sectors. OPENOUT of a new file reserves 256 sectors in
 * one run, or fails (Disc full if fewer are free, else Compaction required); of a file that is
 * there, the sectors it has. A file that outgrows what it has takes the sectors after it if they
 * are free, else moves whole to the first run that holds its new length (both held while it
 * moves), else Compaction required (or Disc full). Closed, it keeps its length in whole sectors and
 * the rest is free again. *SAVE and OSFILE 0 put a file in the first run that holds it. The map
 * holds 80 free spaces: what would leave more is Map full, and is not done. Looser than ADFS:
 * which run a file gets (the first; ADFS's choice was not found), how far a file grows at a time
 * (to the sector it needs), the release at close (inferred), and that each run starts on a
 * compacted disc (the layout is not kept between runs). */

static int adfs_char(int c) { return c > 0x20 && c < 0x7F && !strchr("#*.:$&@^\"/", c); }

/* A part of a path: 0, or the error */
static uint16_t adfs_part(const char *s, size_t n) {
    if (n == 0 || n > 10) return BBC_MOS_E_BAD_NAME;
    for (size_t i = 0; i < n; i++) {
        if (s[i] == '#' || s[i] == '*') return BBC_MOS_E_WILD_CARDS;
        if (!adfs_char((unsigned char)s[i])) return BBC_MOS_E_BAD_NAME;
    }
    return 0;
}

static int adfs_entry(const char *s) { return adfs_part(s, strlen(s)) == 0; }

static void adfs_folder(const struct bbc_machine *m, int drive, char *out, size_t size) {
    if (drive) snprintf(out, size, "%s/:%d", m->cfg.disk_dir, drive);
    else snprintf(out, size, "%s", m->cfg.disk_dir);
}

static void adfs_host(const struct bbc_machine *m, int drive, const char *rel, char *out, size_t size) {
    char folder[1024];
    adfs_folder(m, drive, folder, sizeof folder);
    if (rel[0]) snprintf(out, size, "%s/%s", folder, rel);
    else snprintf(out, size, "%s", folder);
}

/* The entry of dir called part, whatever its case: its type (1 file, 2 directory) and host
 * name in found, or 0; *entries the entries dir holds */
static int adfs_lookup(const char *dir, const char *part, char *found, int *entries) {
    int type = 0, n = 0;
    DIR *d = opendir(dir);
    if (!d) {
        if (entries) *entries = 0;
        return 0;
    }
    for (struct dirent *de; (de = readdir(d));) {
        if (!adfs_entry(de->d_name)) continue;
        char full[1100];
        snprintf(full, sizeof full, "%s/%.10s", dir, de->d_name);
        int t = object_type(full, NULL);
        if (!t) continue;
        n++;
        if (!type && strcasecmp(de->d_name, part) == 0) {
            type = t;
            if (found) snprintf(found, 16, "%.15s", de->d_name);
        }
    }
    closedir(d);
    if (entries) *entries = n;
    return type;
}

/* ---- the sectors of a drive ---- */

static uint32_t adfs_size(const struct bbc_machine *m) {
    return m->cfg.adfs_sectors ? m->cfg.adfs_sectors : BBC_ADFS_SECTORS;
}

static void adfs_mark(struct bbc_adfs *a, int drive, uint32_t start, uint32_t n, uint8_t v) {
    for (uint32_t i = start; i < start + n && i < a->sectors; i++) {
        if (a->used[drive][i] == v) continue;
        a->used[drive][i] = v;
        if (v) a->in_use[drive]++;
        else a->in_use[drive]--;
    }
    if (a->in_use[drive] > a->peak[drive]) a->peak[drive] = a->in_use[drive];
}

static int adfs_spaces(const struct bbc_adfs *a, int drive) {
    int n = 0;
    for (uint32_t i = 0; i < a->sectors; i++)
        if (!a->used[drive][i] && (i == 0 || a->used[drive][i - 1])) n++;
    return n;
}

int bbc_adfs_free_spaces(const struct bbc_machine *m, int drive) {
    if (drive < 0 || drive >= BBC_ADFS_DRIVES || !m->adfs.loaded[drive]) return -1;
    return adfs_spaces(&m->adfs, drive);
}

/* The first run of n free sectors, or -1 */
static long adfs_run(const struct bbc_adfs *a, int drive, uint32_t n) {
    uint32_t len = 0;
    for (uint32_t i = 0; i < a->sectors; i++) {
        len = a->used[drive][i] ? 0 : len + 1;
        if (len == n) return (long)(i + 1 - n);
    }
    return -1;
}

/* n sectors in one run: 0 and *start, or the error */
static uint16_t adfs_take(struct bbc_machine *m, int drive, uint32_t n, uint32_t *start) {
    struct bbc_adfs *a = &m->adfs;
    *start = 0;
    if (!n) return 0;
    long at = adfs_run(a, drive, n);
    if (at < 0) return a->sectors - a->in_use[drive] < n ? BBC_MOS_E_DISC_FULL : BBC_MOS_E_COMPACTION;
    adfs_mark(a, drive, (uint32_t)at, n, 1);
    *start = (uint32_t)at;
    return 0;
}

/* Give n sectors back: 0, or Map full (and they stay taken) */
static uint16_t adfs_give(struct bbc_machine *m, int drive, uint32_t start, uint32_t n) {
    struct bbc_adfs *a = &m->adfs;
    if (!n) return 0;
    adfs_mark(a, drive, start, n, 0);
    if (adfs_spaces(a, drive) > BBC_ADFS_MAP) {
        adfs_mark(a, drive, start, n, 1);
        return BBC_MOS_E_MAP_FULL;
    }
    return 0;
}

static int adfs_obj(const struct bbc_adfs *a, const char *path) {
    for (int i = 0; i < a->nobj; i++)
        if (a->obj[i].path && strcmp(a->obj[i].path, path) == 0) return i;
    return -1;
}

static int adfs_add(struct bbc_adfs *a, const char *path, int drive, uint32_t start, uint32_t len) {
    if (a->nobj == a->cap) {
        a->cap = a->cap ? 2 * a->cap : 64;
        a->obj = realloc(a->obj, (size_t)a->cap * sizeof *a->obj);
    }
    a->obj[a->nobj] = (struct bbc_adfs_object){ strdup(path), drive, start, len };
    return a->nobj++;
}

static int adfs_by_name(const void *x, const void *y) {
    return strcasecmp(*(char *const *)x, *(char *const *)y);
}

/* The layout of a directory and what is in it, as on a compacted disc */
static void adfs_lay_out(struct bbc_machine *m, int drive, const char *dir) {
    struct bbc_adfs *a = &m->adfs;
    DIR *d = opendir(dir);
    if (!d) return;
    char *names[BBC_ADFS_ENTRIES * 4];
    int n = 0;
    for (struct dirent *de; (de = readdir(d)) && n < (int)(sizeof names / sizeof *names);)
        if (adfs_entry(de->d_name)) names[n++] = strdup(de->d_name);
    closedir(d);
    qsort(names, (size_t)n, sizeof *names, adfs_by_name);
    uint64_t entries = 0;
    for (int i = 0; i < n; i++) {
        char full[1100];
        uint32_t length = 0, start;
        snprintf(full, sizeof full, "%s/%s", dir, names[i]);
        int t = object_type(full, &length);
        if (t) {
            uint32_t sectors = t == 2 ? BBC_ADFS_DIR_SECTORS : (length + 255) / 256;
            entries++;
            if (adfs_take(m, drive, sectors, &start))      /* more than the disc holds: it is full */
                adfs_mark(a, drive, 0, a->sectors, 1);
            adfs_add(a, full, drive, start, sectors);
            if (t == 2) adfs_lay_out(m, drive, full);
        }
        free(names[i]);
    }
    if (entries > a->most_entries) a->most_entries = entries;
}

static void adfs_load(struct bbc_machine *m, int drive) {
    struct bbc_adfs *a = &m->adfs;
    if (a->loaded[drive]) return;
    a->sectors = adfs_size(m);
    a->used[drive] = calloc(a->sectors, 1);
    a->loaded[drive] = 1;
    adfs_mark(a, drive, 0, BBC_ADFS_FIRST_FREE, 1);
    char folder[1024];
    adfs_folder(m, drive, folder, sizeof folder);
    adfs_lay_out(m, drive, folder);
}

static void adfs_free(struct bbc_adfs *a) {
    for (int i = 0; i < BBC_ADFS_DRIVES; i++) free(a->used[i]);
    for (int i = 0; i < a->nobj; i++) free(a->obj[i].path);
    free(a->obj);
}

/* ---- names ---- */

struct adfs_where {
    int drive;
    int type;               /* 0 none, 1 file, 2 directory */
    int missing;            /* a directory on the way is not there */
    int entries;            /* what the directory it is in holds */
    char dir[1024];         /* the host path of the directory it is in */
    char path[1100];        /* its host path */
    char rel[600];          /* its path below the drive's root, host names joined by "/" */
};

/* 0, 1 for drive 1, -1 a bad name, -2 a drive this machine does not have */
static int adfs_drive(int c) {
    c = toupper(c);
    if (c == '0' || c == '4' || c == 'A' || c == 'E') return 0;
    if (c == '1' || c == '5' || c == 'B' || c == 'F') return 1;
    if (strchr("2367CDGH", c) && c) return -2;
    return -1;
}

static void rel_up(char *rel) {
    char *slash = strrchr(rel, '/');
    if (slash) *slash = 0;
    else rel[0] = 0;
}

/* Where the name is. 0, or the error. A directory on the way that is not there is Not found,
 * unless reading (then w->missing, and type 0) */
static uint16_t adfs_where(struct bbc_machine *m, const char *name, int reading, struct adfs_where *w) {
    const char *s = name;
    memset(w, 0, sizeof *w);
    w->drive = m->adfs.csd_drive;
    snprintf(w->rel, sizeof w->rel, "%s", m->adfs.csd);
    if (s[0] == ':') {
        int d = adfs_drive((unsigned char)s[1]);
        if (d == -1 || (s[2] && s[2] != '.')) return BBC_MOS_E_BAD_NAME;
        if (d == -2) return BBC_MOS_E_BAD_DRIVE;
        w->drive = d;
        w->rel[0] = 0;
        s += 2;
        if (*s == '.') {
            s++;
            if (!*s) return BBC_MOS_E_BAD_NAME;
        }
    }
    if (!m->cfg.disk_dir) return BBC_MOS_E_NO_DISK;
    for (const char *p = s; *p;) {  /* the parts, before any is looked for */
        const char *dot = strchr(p, '.');
        size_t n = dot ? (size_t)(dot - p) : strlen(p);
        if (n == 1 && (p[0] == '$' || p[0] == '&' || p[0] == '@')) {
            if (p != s) return BBC_MOS_E_BAD_NAME;
        } else if (!(n == 1 && p[0] == '^')) {
            uint16_t e = adfs_part(p, n);
            if (e) return e;
        }
        if (dot && !dot[1]) return BBC_MOS_E_BAD_NAME;
        p += n + (dot != NULL);
    }
    adfs_load(m, w->drive);
    int first = 1, special = 1;     /* the name so far is a directory: a drive, $, ^ or @ */
    char leaf[16] = "";
    while (*s) {
        const char *dot = strchr(s, '.');
        size_t n = dot ? (size_t)(dot - s) : strlen(s);
        if (!special && w->type != 2) {     /* the part before this one must be a directory */
            if (!reading || w->type == 1) return BBC_MOS_E_NOT_FOUND;
            w->missing = 1;
            w->type = 0;
            snprintf(w->path, sizeof w->path, "%s/%s", w->dir, leaf);  /* not there */
            return 0;
        }
        if (n == 1 && (s[0] == '$' || s[0] == '&')) {
            w->rel[0] = 0;
        } else if (n == 1 && s[0] == '^') {
            if (!special) special = 1;      /* into the directory found, and out again */
            else rel_up(w->rel);
        } else if (n == 1 && s[0] == '@') {
            (void)first;                    /* the CSD: where a name starts anyway */
        } else {
            if (!special) {         /* step into the directory found */
                size_t l = strlen(w->rel);
                snprintf(w->rel + l, sizeof w->rel - l, "%s%s", l ? "/" : "", leaf);
            }
            char part[16];
            memcpy(part, s, n);
            part[n] = 0;
            adfs_host(m, w->drive, w->rel, w->dir, sizeof w->dir);
            char found[16];
            w->type = adfs_lookup(w->dir, part, found, &w->entries);
            snprintf(leaf, sizeof leaf, "%s", w->type ? found : part);
            special = 0;
        }
        first = 0;
        s += n;
        if (*s == '.') s++;
    }
    if (special) {                  /* the name is a directory of its own: $, a drive, ^, @ */
        w->type = 2;
        adfs_host(m, w->drive, w->rel, w->path, sizeof w->path);
        snprintf(w->dir, sizeof w->dir, "%.1023s", w->path);
        return 0;
    }
    snprintf(w->path, sizeof w->path, "%s/%s", w->dir, leaf);
    size_t l = strlen(w->rel);
    snprintf(w->rel + l, sizeof w->rel - l, "%s%s", l ? "/" : "", leaf);
    return 0;
}

/* Whether the file at path is open, other than for input with mode for input too */
static int adfs_open_already(const struct bbc_machine *m, const char *path, uint8_t mode) {
    int i = adfs_obj(&m->adfs, path);
    if (i < 0) return 0;
    for (int k = 0; k < BBC_ADFS_MAX_FILES; k++)
        if (m->files[k].f && m->files[k].obj == i + 1 && (mode != 0x40 || m->files[k].mode != 0x40)) return 1;
    return 0;
}

/* Before an object is created in w's directory: 0, or the error */
static uint16_t adfs_room(struct bbc_machine *m, struct adfs_where *w) {
    if (w->entries >= BBC_ADFS_ENTRIES) return BBC_MOS_E_DIR_FULL;
    if (w->drive) {
        char folder[1024];
        adfs_folder(m, w->drive, folder, sizeof folder);
        mkdir(folder, 0777);
    }
    return 0;
}

static void adfs_created(struct bbc_machine *m, struct adfs_where *w) {
    if ((uint64_t)w->entries + 1 > m->adfs.most_entries) m->adfs.most_entries = (uint64_t)w->entries + 1;
}

/* An open file is to hold `bytes`: 0, or the error */
static uint16_t adfs_grow(struct bbc_machine *m, struct bbc_file *bf, uint32_t bytes) {
    if (!bf->obj) return 0;
    struct bbc_adfs *a = &m->adfs;
    struct bbc_adfs_object *o = &a->obj[bf->obj - 1];
    uint32_t need = (bytes + 255) / 256;
    if (need <= o->len) return 0;
    uint32_t extra = need - o->len, start;
    if (o->len) {
        uint32_t i = o->start + o->len;
        while (i < o->start + need && i < a->sectors && !a->used[o->drive][i]) i++;
        if (i == o->start + need) {         /* the sectors after it are free */
            adfs_mark(a, o->drive, o->start + o->len, extra, 1);
            o->len = need;
            return 0;
        }
    }
    long at = adfs_run(a, o->drive, need);
    if (at < 0) return a->sectors - a->in_use[o->drive] < extra ? BBC_MOS_E_DISC_FULL : BBC_MOS_E_COMPACTION;
    adfs_mark(a, o->drive, (uint32_t)at, need, 1);
    start = (uint32_t)at;
    uint16_t e = adfs_give(m, o->drive, o->start, o->len);
    if (e) {
        adfs_mark(a, o->drive, start, need, 0);
        return e;
    }
    o->start = start;
    o->len = need;
    return 0;
}

static long file_ext(struct bbc_file *bf);

/* A file is closed: what it reserved beyond its length is free again */
static void adfs_closed(struct bbc_machine *m, struct bbc_file *bf) {
    if (!bf->obj || !bf->f) return;
    struct bbc_adfs_object *o = &m->adfs.obj[bf->obj - 1];
    uint32_t need = ((uint32_t)file_ext(bf) + 255) / 256;
    if (need < o->len && adfs_give(m, o->drive, o->start + need, o->len - need) == 0) o->len = need;
}

/* Delete the object at w: 0, or the error */
static uint16_t adfs_delete(struct bbc_machine *m, struct adfs_where *w) {
    if (adfs_open_already(m, w->path, 0x80)) return BBC_MOS_E_ALREADY_OPEN;
    if (w->type == 2) {
        int entries;
        adfs_lookup(w->path, "", NULL, &entries);
        if (entries) return BBC_MOS_E_DIR_NOT_EMPTY;
        if (!w->rel[0]) return BBC_MOS_E_BAD_NAME;      /* a root */
    }
    int i = adfs_obj(&m->adfs, w->path);
    if (i >= 0) {
        uint16_t e = adfs_give(m, w->drive, m->adfs.obj[i].start, m->adfs.obj[i].len);
        if (e) return e;
        free(m->adfs.obj[i].path);
        m->adfs.obj[i].path = NULL;
    }
    if (w->type == 2) rmdir(w->path);
    else {
        char inf[1200];
        snprintf(inf, sizeof inf, "%s.inf", w->path);
        remove(w->path);
        remove(inf);
    }
    return 0;
}

/* *CDIR name */
static void adfs_cdir(struct bbc_machine *m, const char *name) {
    struct adfs_where w;
    uint16_t e = adfs_where(m, name, 0, &w);
    if (!e && w.type) e = BBC_MOS_E_ALREADY_EXISTS;
    if (!e) e = adfs_room(m, &w);
    uint32_t start;
    if (!e) e = adfs_take(m, w.drive, BBC_ADFS_DIR_SECTORS, &start);
    if (!e && mkdir(w.path, 0777) != 0) {
        adfs_mark(&m->adfs, w.drive, start, BBC_ADFS_DIR_SECTORS, 0);
        e = BBC_MOS_E_DISC_FAULT;
    }
    if (e) {
        raise(e);
        return;
    }
    adfs_add(&m->adfs, w.path, w.drive, start, BBC_ADFS_DIR_SECTORS);
    adfs_created(m, &w);
}

/* *DIR [name] */
static void adfs_dir(struct bbc_machine *m, const char *name) {
    if (!name[0]) {
        m->adfs.csd[0] = 0;
        return;
    }
    struct adfs_where w;
    uint16_t e = adfs_where(m, name, 0, &w);
    if (!e && w.type != 2) e = BBC_MOS_E_NOT_FOUND;
    if (e) {
        raise(e);
        return;
    }
    m->adfs.csd_drive = w.drive;
    snprintf(m->adfs.csd, sizeof m->adfs.csd, "%.511s", w.rel);
}

/* *DELETE name */
static void adfs_delete_command(struct bbc_machine *m, const char *name) {
    struct adfs_where w;
    uint16_t e = adfs_where(m, name, 0, &w);
    if (!e && !w.type) e = BBC_MOS_E_NOT_FOUND;
    if (!e) e = adfs_delete(m, &w);
    if (e) raise(e);
}

/* The host path of a name the 6502 code gave, and the name its .inf file records. With
 * `creating` (a file about to be written), a DFS file that is not there must have room in
 * its drive's catalogue. Returns 0, or the error to raise. */
static uint16_t file_path(struct bbc_machine *m, const char *name, int creating, char *path, size_t size,
                          char *inf_name, size_t inf_size) {
    if (!m->cfg.disk_dir) return BBC_MOS_E_NO_DISK;
    if (m->cfg.adfs) {
        struct adfs_where w;
        uint16_t e = adfs_where(m, name, !creating, &w);
        if (!e && creating && !w.type) e = adfs_room(m, &w);
        if (e) return e;
        snprintf(path, size, "%s", w.path);
        snprintf(inf_name, inf_size, "%s", name);
        return 0;
    }
    if (!m->cfg.dfs) {
        snprintf(path, size, "%s/%s", m->cfg.disk_dir, name);
        snprintf(inf_name, inf_size, "%s", name);
        return 0;
    }
    int drive;
    char dir;
    const char *base;
    uint16_t e = dfs_parse(name, &drive, &dir, &base);
    if (e) return e;
    char folder[1024], want[16];
    if (drive) snprintf(folder, sizeof folder, "%s/:%d", m->cfg.disk_dir, drive);
    else snprintf(folder, sizeof folder, "%s", m->cfg.disk_dir);
    snprintf(want, sizeof want, "%c.%s", dir, base);
    int entries = 0, found = 0;
    DIR *d = opendir(folder);
    if (d) {
        for (struct dirent *de; (de = readdir(d));) {
            if (!dfs_entry(de->d_name)) continue;    /* at most 9 characters */
            char full[1100];
            snprintf(full, sizeof full, "%s/%.9s", folder, de->d_name);
            if (object_type(full, NULL) != 1) continue;
            entries++;
            if (!found && strcasecmp(de->d_name, want) == 0) {
                memcpy(want, de->d_name, strlen(de->d_name) + 1);
                found = 1;
            }
        }
        closedir(d);
    }
    if (creating && !found) {
        if (entries >= BBC_DFS_CATALOGUE) return BBC_MOS_E_CAT_FULL;
        if (drive) mkdir(folder, 0777);
    }
    snprintf(path, size, "%s/%s", folder, want);
    snprintf(inf_name, inf_size, "%s", want);
    return 0;
}

/* file_path(), raising its error: 0 if it raised one (no --disk, a bad name, ...) */
static int host_path(struct bbc_machine *m, const char *name, int creating, char *path, size_t size,
                     char *inf_name, size_t inf_size) {
    uint16_t e = file_path(m, name, creating, path, size, inf_name, inf_size);
    if (e) raise(e);
    return !e;
}

/* --bbc-fs adfs: the space for a file saved whole (*SAVE, OSFILE 0) of `bytes` at path, the
 * name's: the sectors of the file of that name before are given back and the first run that
 * holds it taken. Returns the file's object, or -1 if it raised an error. */
static int adfs_save_space(struct bbc_machine *m, const char *name, const char *path, uint32_t bytes,
                           uint32_t *start) {
    struct adfs_where w;
    uint16_t e = adfs_where(m, name, 0, &w);
    if (!e && w.type == 2) e = BBC_MOS_E_ALREADY_EXISTS;
    if (!e && adfs_open_already(m, path, 0x80)) e = BBC_MOS_E_ALREADY_OPEN;
    int i = e ? -1 : adfs_obj(&m->adfs, path);
    if (!e && i >= 0) adfs_mark(&m->adfs, w.drive, m->adfs.obj[i].start, m->adfs.obj[i].len, 0);
    if (!e) {
        e = adfs_take(m, w.drive, (bytes + 255) / 256, start);
        if (e && i >= 0) adfs_mark(&m->adfs, w.drive, m->adfs.obj[i].start, m->adfs.obj[i].len, 1);
    }
    if (e) {
        raise(e);
        return -1;
    }
    if (i < 0) {
        adfs_created(m, &w);
        i = adfs_add(&m->adfs, path, w.drive, 0, 0);
    }
    m->adfs.obj[i].start = *start;
    m->adfs.obj[i].len = (bytes + 255) / 256;
    return i;
}

/* Load a file at its own load address (or at addr if use_addr). Raises
 * the error and returns -1 when it can't. */
static int load_file(struct bbc_machine *m, const char *name, int use_addr, uint32_t addr,
                     uint32_t *load, uint32_t *exec, uint32_t *length) {
    char path[1024], inf_name[256];
    if (!host_path(m, name, 0, path, sizeof path, inf_name, sizeof inf_name)) return -1;
    if (object_type(path, NULL) != 1) {
        raise(m->cfg.adfs ? BBC_MOS_E_NOT_FOUND : BBC_MOS_E_FILE_NOT_FOUND);
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
    char path[1024], inf_name[256];
    if (end < start) {
        raise(BBC_MOS_E_BAD_ADDRESS);
        return -1;
    }
    if (!host_path(m, name, 1, path, sizeof path, inf_name, sizeof inf_name)) return -1;
    if (end < start) {
        raise(BBC_MOS_E_BAD_ADDRESS);
        return -1;
    }
    uint32_t place;
    if (m->cfg.adfs && adfs_save_space(m, name, path, end - start, &place) < 0) return -1;
    FILE *f = fopen(path, "wb");
    if (!f) {
        raise(BBC_MOS_E_DISC_FAULT);
        return -1;
    }
    for (uint32_t a = start; a < end; a++) fputc(bus_rd(m, (uint16_t)a), f);
    if (fclose(f) != 0 || write_inf(path, inf_name, load, exec, end - start) != 0) {
        raise(BBC_MOS_E_DISC_FAULT);
        return -1;
    }
    return 0;
}

static int first_handle(const struct bbc_machine *m) {
    return m->cfg.adfs ? BBC_ADFS_FIRST_HANDLE : BBC_FIRST_HANDLE;
}

static struct bbc_file *handle_file(struct bbc_machine *m, uint8_t h) {
    if (h < first_handle(m) || h >= first_handle(m) + BBC_MAX_FILES) return NULL;
    struct bbc_file *bf = &m->files[h - first_handle(m)];
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

static void close_all(struct bbc_machine *m) {
    for (int i = 0; i < BBC_MAX_FILES; i++) {
        adfs_closed(m, &m->files[i]);
        close_file(&m->files[i]);
    }
}

void bbc_machine_close(struct bbc_machine *m) { close_all(m); }

/* OSFIND: A = 0 close Y (0: all); $40 input, $80 output, $C0 update, XY the name */
static void os_find(struct bbc_machine *m) {
    if (a == 0) {
        if (y == 0) {
            close_all(m);
            return;
        }
        struct bbc_file *bf = handle_file(m, y);
        if (!bf) raise(BBC_MOS_E_CHANNEL);
        else {
            adfs_closed(m, bf);
            close_file(bf);
        }
        return;
    }
    char name[256], path[1024], inf_name[256];
    if (!read_name(m, xy(), name, sizeof name)) {
        raise(BBC_MOS_E_BAD_NAME);
        return;
    }
    uint8_t mode = a & 0xC0;
    if (!host_path(m, name, mode == 0x80, path, sizeof path, inf_name, sizeof inf_name)) return;
    int most = m->cfg.adfs ? BBC_ADFS_MAX_FILES : m->cfg.dfs ? BBC_DFS_MAX_FILES : BBC_MAX_FILES, slot = 0;
    while (slot < most && m->files[slot].f) slot++;
    if (slot == most) {
        raise(m->cfg.dfs ? BBC_MOS_E_DFS_TOO_MANY_OPEN : BBC_MOS_E_TOO_MANY_OPEN);
        return;
    }
    int obj = 0, type = object_type(path, NULL);
    if (m->cfg.adfs && type != 2) {     /* the file's space: a new one reserves 256 sectors */
        if (adfs_open_already(m, path, mode)) {
            raise(BBC_MOS_E_ALREADY_OPEN);
            return;
        }
        obj = adfs_obj(&m->adfs, path) + 1;
        if (!obj && mode == 0x80) {
            struct adfs_where w;
            uint32_t start;
            uint16_t e = adfs_where(m, name, 0, &w);
            if (!e) e = adfs_take(m, w.drive, BBC_ADFS_RESERVE, &start);
            if (e) {
                raise(e);
                return;
            }
            adfs_created(m, &w);
            obj = adfs_add(&m->adfs, path, w.drive, start, BBC_ADFS_RESERVE) + 1;
        }
    }
    FILE *f = NULL;
    if (type != 2)
        f = fopen(path, mode == 0x40 ? "rb" : mode == 0x80 ? "w+b" : "r+b");
    if (!f) {
        a = 0;   /* not found: A = 0, no error */
        return;
    }
    m->files[slot] = (struct bbc_file){ f, mode, 0, 0, obj };
    m->files_opened++;
    uint64_t open = 0, writing = 0;
    for (int i = 0; i < BBC_MAX_FILES; i++) {
        open += m->files[i].f != NULL;
        writing += m->files[i].f && m->files[i].mode != 0x40;
    }
    if (open > m->most_open) m->most_open = open;
    if (writing > m->most_writing) m->most_writing = writing;
    a = (uint8_t)(first_handle(m) + slot);
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
        raise(m->cfg.adfs ? BBC_MOS_E_NOT_OPEN_FOR_UPDATE : BBC_MOS_E_READ_ONLY);
        return;
    }
    uint16_t e = adfs_grow(m, bf, (uint32_t)ftell(bf->f) + 1);
    if (e) {
        raise(e);
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
        if (a == 0) a = m->cfg.adfs ? 8 : 4;
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
    case 1: {
        uint32_t ptr = peek32(m, zp);
        if (m->cfg.adfs && bf->mode == 0x40 && ptr > (uint32_t)file_ext(bf)) {
            raise(BBC_MOS_E_OUTSIDE_FILE);
            return;
        }
        uint16_t e = bf->mode == 0x40 ? 0 : adfs_grow(m, bf, ptr);
        if (e) {
            raise(e);
            return;
        }
        file_seek(bf, ptr);
        break;
    }
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
        raise(m->cfg.adfs ? BBC_MOS_E_NOT_OPEN_FOR_UPDATE : BBC_MOS_E_READ_ONLY);
        return;
    }
    if (a == 1 || a == 3) file_seek(bf, peek32(m, (uint16_t)(blk + 9)));
    uint32_t addr = peek32(m, (uint16_t)(blk + 1)), count = peek32(m, (uint16_t)(blk + 5));
    if (writing) {
        uint16_t e = adfs_grow(m, bf, (uint32_t)ftell(bf->f) + count);
        if (e) {
            raise(e);
            return;
        }
    }
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
    char name[256], path[1024], inf_name[256];
    if (!read_name(m, peek16(m, blk), name, sizeof name)) {
        raise(BBC_MOS_E_BAD_NAME);
        return;
    }
    if (!host_path(m, name, 0, path, sizeof path, inf_name, sizeof inf_name)) return;
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
            if (write_inf(path, inf_name, load, exec, length) != 0) {
                raise(BBC_MOS_E_DISC_FAULT);
                return;
            }
        }
        if (a == 6 && type && m->cfg.adfs) {
            struct adfs_where w;
            uint16_t e = adfs_where(m, name, 1, &w);
            if (!e) e = adfs_delete(m, &w);
            if (e) {
                raise(e);
                return;
            }
        } else if (a == 6 && type == 1) {
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
    } else if (m->cfg.adfs && (command_is(m, p, "CDIR", &after) || command_is(m, p, "DIR", &after)
                               || command_is(m, p, "DELETE", &after))) {
        /* ADFS's own commands that the recipe needs (lathe/docs/boards.md) */
        int c0 = toupper(bus_rd(m, p)), c1 = toupper(bus_rd(m, (uint16_t)(p + 1)));
        name[0] = 0;
        if (bus_rd(m, skip_spaces(m, after)) != 0x0D && !read_name(m, after, name, sizeof name)) {
            raise(BBC_MOS_E_BAD_NAME);
            return;
        }
        if (!m->cfg.disk_dir) raise(BBC_MOS_E_NO_DISK);
        else if (c0 == 'D' && c1 == 'I') adfs_dir(m, name);
        else if (!name[0]) raise(BBC_MOS_E_BAD_NAME);
        else if (c0 == 'C') adfs_cdir(m, name);
        else adfs_delete_command(m, name);
    } else {
        y = (uint8_t)(p - line);   /* service call 4, Y the offset from ($F2) */
        pc = BBC_MOS_CLI_SVC;
    }
}

/* No ROM claimed the command: a file of that name is run, else Bad command */
static void os_cli_file(struct bbc_machine *m) {
    uint16_t p = command_start(m, peek16(m, 0xF2));
    char name[256], path[1024], inf_name[256];
    uint16_t end = read_name(m, p, name, sizeof name);
    if (end && m->cfg.disk_dir) {
        if (!file_path(m, name, 0, path, sizeof path, inf_name, sizeof inf_name) && object_type(path, NULL) == 1) {
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
    case 0:     /* the OS version: an error for X = 0, else X = 2 (OS 2.00, the B+; 1, OS 1.20, the B) */
        if (x == 0) raise(m->cfg.model_b ? BBC_MOS_E_OS_120 : BBC_MOS_E_OS);
        else x = m->cfg.model_b ? 1 : 2;
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
        y = m->cfg.shadow ? 0x80 : (uint8_t)(m->cfg.screen >> 8);
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
    adfs_free(&m->adfs);   /* m is static: zero, or a machine this made before */
    memset(m, 0, sizeof *m);
    m->cfg = *cfg;
    if (!m->cfg.out) m->cfg.out = stdout;
    if (!m->cfg.in) m->cfg.in = stdin;
    if (!m->cfg.err) m->cfg.err = stderr;
    if (!m->cfg.page) m->cfg.page = 0x1900;
    if (!m->cfg.screen) m->cfg.screen = bbc_screen_start(7);
    mem->model_b = m->cfg.model_b;
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
