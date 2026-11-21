/* The bbcbplus machine's MOS (bbc_mos.h): reset, the traps, each MOS call,
 * errors through BRKV, service calls to ROMs, the filing system over a host
 * directory, and the checks. Each test runs a small 6502 program, assembled
 * here by the macros below, at PAGE ($1900). */

#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "greatest.h"
#include "../cpu_core.h"
#include "../bbc_mos.h"
#include "../bbc_mos_rom_generated.h"

uint8_t read6502(uint16_t address) { (void)address; return 0; }
void write6502(uint16_t address, uint8_t value) { (void)address; (void)value; }

/* ---- a few instructions ---- */
#define LO(v) ((uint8_t)((v) & 0xFF))
#define HI(v) ((uint8_t)(((v) >> 8) & 0xFF))
#define LDA_IMM(v) 0xA9, LO(v)
#define LDX_IMM(v) 0xA2, LO(v)
#define LDY_IMM(v) 0xA0, LO(v)
#define LDA_ZP(z) 0xA5, (z)
#define STA_ZP(z) 0x85, (z)
#define STX_ZP(z) 0x86, (z)
#define STY_ZP(z) 0x84, (z)
#define STA_ABS(v) 0x8D, LO(v), HI(v)
#define LDA_ABS(v) 0xAD, LO(v), HI(v)
#define INC_ZP(z) 0xE6, (z)
#define JSR(v) 0x20, LO(v), HI(v)
#define JMP(v) 0x4C, LO(v), HI(v)
#define JMP_IND(v) 0x6C, LO(v), HI(v)
#define PHP 0x08
#define PLA 0x68
#define RTS 0x60
#define BRK 0x00
#define NOP 0xEA

#define OSWRCH 0xFFEE
#define OSASCI 0xFFE3
#define OSNEWL 0xFFE7
#define OSRDCH 0xFFE0
#define OSBYTE 0xFFF4
#define OSWORD 0xFFF1
#define OSCLI 0xFFF7
#define OSFILE 0xFFDD
#define OSFIND 0xFFCE
#define OSBGET 0xFFD7
#define OSBPUT 0xFFD4
#define OSARGS 0xFFDA
#define OSGBPB 0xFFD1
#define WRCHV 0x020E
#define BRKV 0x0202

#define PAGE 0x1900

static struct bbc_memory_state mem;
static struct bbc_module_state mod;
static struct bbc_machine m;
static struct chip mem_chip, mod_chip;
static char *out_text, *err_text;
static size_t out_len, err_len;
static char disk[64];
static int status_code;

static void fresh(void) {
    bbc_memory_init(&mem_chip, &mem);
    free(out_text);
    free(err_text);
    out_text = err_text = NULL;
}

/* Run code at PAGE (or the command) with input; out_text and err_text hold
 * what it printed. */
static int run(const uint8_t *code, size_t n, const char *input, const char *command, struct bbc_config *extra) {
    struct bbc_config cfg = { 0 };
    if (extra) cfg = *extra;
    free(out_text);
    free(err_text);
    out_text = err_text = NULL;
    FILE *out = open_memstream(&out_text, &out_len), *err = open_memstream(&err_text, &err_len);
    FILE *in = fmemopen((void *)(input ? input : ""), input ? strlen(input) : 0, "r");
    if (!input) { fclose(in); in = fopen("/dev/null", "r"); }
    cfg.out = out;
    cfg.err = err;
    cfg.in = in;
    cfg.command = command;
    cfg.entry = PAGE;
    if (!cfg.disk_dir && disk[0]) cfg.disk_dir = disk;
    bbc_machine_init(&m, &cfg, &mem, mem.kind[4] == BBC_SLOT_MODULE ? &mod : NULL);
    for (size_t i = 0; i < n; i++) mem.ram[PAGE + i] = code[i];
    status_code = bbc_machine_run(&m, 10000000);
    bbc_machine_close(&m);
    fclose(out);
    fclose(err);
    fclose(in);
    return status_code;
}

#define RUN(code, input, command) run(code, sizeof code, input, command, NULL)

static void make_disk(void) {
    strcpy(disk, "/tmp/bbc_mos_diskXXXXXX");
    if (!mkdtemp(disk)) disk[0] = 0;
}

static void remove_disk(void) {
    char cmd[128];
    snprintf(cmd, sizeof cmd, "rm -rf %s", disk);
    if (system(cmd) != 0) { /* best effort */ }
    disk[0] = 0;
}

static void write_host(const char *name, const void *data, size_t n) {
    char path[256];
    snprintf(path, sizeof path, "%s/%s", disk, name);
    FILE *f = fopen(path, "wb");
    fwrite(data, 1, n, f);
    fclose(f);
}

static long read_host(const char *name, char *buf, size_t size) {
    char path[256];
    snprintf(path, sizeof path, "%s/%s", disk, name);
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    long n = (long)fread(buf, 1, size - 1, f);
    buf[n] = 0;
    fclose(f);
    return n;
}

static void put_text(uint16_t addr, const char *s) {
    memcpy(mem.ram + addr, s, strlen(s));
    mem.ram[addr + strlen(s)] = 0x0D;
}

/* A sideways ROM image in slot: header, then code at $8020 (the service
 * entry), title "T" */
static void rom_in_slot(int slot, uint8_t type, const uint8_t *service, size_t n) {
    mem.kind[slot] = BBC_SLOT_ROM;
    uint8_t *r = mem.slot[slot];
    memset(r, 0xFF, BBC_SLOT_SIZE);
    r[0] = 0x4C; r[1] = 0x40; r[2] = 0x80;  /* language entry: JMP $8040 */
    r[3] = 0x4C; r[4] = 0x20; r[5] = 0x80;  /* service entry: JMP $8020 */
    r[6] = type;
    r[7] = 0x0B;                             /* copyright offset */
    r[8] = 0x01;                             /* version */
    r[9] = 'T'; r[10] = 0;
    memcpy(r + 0x0B, "\0(C)X", 6);
    memcpy(r + 0x20, service, n);
}

/* ---- reset ---- */

TEST reset_sets_the_vectors_and_returns_with_status_0(void) {
    fresh();
    static const uint8_t code[] = { RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(BBC_END_RETURNED, m.end);
    for (int i = 0; i < 0x36; i++) ASSERT_EQ(bbc_mos_rom[BBC_MOS_VECTAB - 0xC000 + i], mem.ram[0x200 + i]);
    ASSERT_EQ(LO(BBC_MOS_WRCH_DEFAULT), mem.ram[WRCHV]);
    ASSERT_EQ(HI(BBC_MOS_WRCH_DEFAULT), mem.ram[WRCHV + 1]);
    ASSERT(clockticks6502 > 0);
    PASS();
}

TEST reset_fills_the_rom_type_table_from_the_headers(void) {
    fresh();
    static const uint8_t svc[] = { RTS };
    rom_in_slot(3, 0x82, svc, sizeof svc);
    rom_in_slot(9, 0xC2, svc, sizeof svc);
    mem.kind[5] = BBC_SLOT_ROM;              /* no "(C)": not a ROM */
    memset(mem.slot[5], 0x11, BBC_SLOT_SIZE);
    mem.kind[0] = BBC_SLOT_RAM;              /* empty sideways RAM */
    static const uint8_t code[] = { RTS };
    RUN(code, NULL, NULL);
    for (int s = 0; s < 16; s++) ASSERT_EQ_FMT(s == 3 ? 0x82 : s == 9 ? 0xC2 : 0, mem.ram[0x2A1 + s], "%02X");
    ASSERT_EQ(9, mem.ram[0xF4]);             /* the language ROM is selected */
    ASSERT_EQ(9, mem.romsel);
    ASSERT_EQ(9, mem.ram[0x28C]);
    PASS();
}

/* ---- character I/O ---- */

TEST oswrch_osasci_osnewl_write_bytes_unchanged(void) {
    fresh();
    static const uint8_t code[] = {
        LDA_IMM('H'), JSR(OSWRCH), LDA_IMM(0x07), JSR(OSWRCH), LDA_IMM(0x0D), JSR(OSASCI),
        LDA_IMM('i'), JSR(OSASCI), JSR(OSNEWL), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(7, (int)out_len);
    ASSERT_MEM_EQ("H\x07\n\ri\n\r", out_text, 7);
    PASS();
}

TEST a_replaced_vector_is_used_and_can_chain(void) {
    fresh();
    /* WRCHV -> PAGE+$40: INC $70, JMP (old) */
    static const uint8_t code[] = {
        LDA_ABS(WRCHV), STA_ZP(0x72), LDA_ABS(WRCHV + 1), STA_ZP(0x73),
        LDA_IMM(LO(PAGE + 0x40)), STA_ABS(WRCHV), LDA_IMM(HI(PAGE + 0x40)), STA_ABS(WRCHV + 1),
        LDA_IMM('x'), JSR(OSWRCH), JSR(OSNEWL), RTS };
    uint8_t prog[0x50] = { 0 };
    memcpy(prog, code, sizeof code);
    const uint8_t handler[] = { INC_ZP(0x70), JMP_IND(0x0072) };
    memcpy(prog + 0x40, handler, sizeof handler);
    ASSERT_EQ(0, run(prog, sizeof prog, NULL, NULL, NULL));
    ASSERT_EQ(3, mem.ram[0x70]);             /* x, LF, CR */
    ASSERT_MEM_EQ("x\n\r", out_text, 3);
    ASSERT_EQ(0, (int)m.mos_writes);         /* the vectors are the program's to replace */
    PASS();
}

TEST osrdch_reads_standard_input_then_escape_at_its_end(void) {
    fresh();
    static const uint8_t code[] = {
        JSR(OSRDCH), STA_ZP(0x70), PHP, PLA, STA_ZP(0x71),
        JSR(OSRDCH), STA_ZP(0x72), PHP, PLA, STA_ZP(0x73), RTS };
    ASSERT_EQ(0, RUN(code, "A", NULL));
    ASSERT_EQ('A', mem.ram[0x70]);
    ASSERT_EQ(0, mem.ram[0x71] & 1);
    ASSERT_EQ(0x1B, mem.ram[0x72]);
    ASSERT_EQ(1, mem.ram[0x73] & 1);
    ASSERT_EQ(0x80, mem.ram[0xFF] & 0x80);   /* the Escape flag */
    PASS();
}

/* ---- OSBYTE ---- */

TEST osbyte_version_page_himem_and_high_address(void) {
    fresh();
    static const uint8_t code[] = {
        LDA_IMM(0), LDX_IMM(1), JSR(OSBYTE), STX_ZP(0x70),
        LDA_IMM(131), JSR(OSBYTE), STX_ZP(0x71), STY_ZP(0x72),
        LDA_IMM(132), JSR(OSBYTE), STX_ZP(0x73), STY_ZP(0x74),
        LDA_IMM(130), JSR(OSBYTE), STX_ZP(0x75), STY_ZP(0x76),
        LDA_IMM(170), JSR(OSBYTE), STX_ZP(0x77), STY_ZP(0x78), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(2, mem.ram[0x70]);
    ASSERT_EQ(0x00, mem.ram[0x71]);
    ASSERT_EQ(0x19, mem.ram[0x72]);
    ASSERT_EQ(0x00, mem.ram[0x73]);
    ASSERT_EQ(0x7C, mem.ram[0x74]);
    ASSERT_EQ(0xFF, mem.ram[0x75]);
    ASSERT_EQ(0xFF, mem.ram[0x76]);
    ASSERT_EQ(0xA1, mem.ram[0x77]);
    ASSERT_EQ(0x02, mem.ram[0x78]);
    struct bbc_config cfg = { .shadow = 1, .page = 0x0E00 };
    fresh();
    run(code, sizeof code, NULL, NULL, &cfg);
    ASSERT_EQ(0x0E, mem.ram[0x72]);
    ASSERT_EQ(0x80, mem.ram[0x74]);
    PASS();
}

/* The Model B: OSBYTE 0 gives 1 (OS 1.20), and its error for X = 0 says so. HIMEM is the start
 * of the screen of the mode at power on (mode 7 unless the run says otherwise), on the B+ too
 * when the screen is not the shadow one. */
TEST model_b_os_version_and_himem_by_mode(void) {
    fresh();
    static const uint8_t code[] = {
        LDA_IMM(0), LDX_IMM(1), JSR(OSBYTE), STX_ZP(0x70),
        LDA_IMM(132), JSR(OSBYTE), STX_ZP(0x73), STY_ZP(0x74), RTS };
    struct bbc_config b = { .model_b = 1 };
    ASSERT_EQ(0, run(code, sizeof code, NULL, NULL, &b));
    ASSERT_EQ(1, mem.ram[0x70]);
    ASSERT_EQ(0x00, mem.ram[0x73]);
    ASSERT_EQ(0x7C, mem.ram[0x74]);
    static const uint8_t screen[8] = { 0x30, 0x30, 0x30, 0x40, 0x58, 0x58, 0x60, 0x7C };
    for (int mode = 0; mode < 8; mode++) {
        struct bbc_config cfg = { .model_b = mode & 1, .screen = bbc_screen_start(mode) };
        ASSERT_EQ(screen[mode] << 8, bbc_screen_start(mode));
        fresh();
        ASSERT_EQ(0, run(code, sizeof code, NULL, NULL, &cfg));
        ASSERT_EQ(screen[mode], mem.ram[0x74]);
    }
    struct bbc_config shadow = { .shadow = 1, .screen = 0x5800 };
    fresh();
    ASSERT_EQ(0, run(code, sizeof code, NULL, NULL, &shadow));
    ASSERT_EQ(0x80, mem.ram[0x74]);
    static const uint8_t error[] = { LDA_IMM(0), LDX_IMM(0), JSR(OSBYTE), RTS };
    fresh();
    ASSERT_EQ(1, run(error, sizeof error, NULL, NULL, &b));
    ASSERT_STR_EQ("OS 1.20\n", err_text);
    PASS();
}

/* The screen is the MOS's: a program's write from HIMEM to $7FFF is counted, and with strict
 * ends the run, as a write to the MOS's own memory does. Not with the shadow screen. */
TEST writes_to_the_screen_are_counted(void) {
    fresh();
    static const uint8_t code[] = {
        LDA_IMM(1), STA_ABS(0x57FF), STA_ABS(0x5800), STA_ABS(0x7BFF), STA_ABS(0x7C00), STA_ABS(0x7FFF), RTS };
    struct bbc_config seven = { .model_b = 1 };
    ASSERT_EQ(0, run(code, sizeof code, NULL, NULL, &seven));
    ASSERT_EQ(2, (int)m.screen_writes);
    ASSERT_EQ(0x7C00, m.first_screen_writes[0].addr);
    ASSERT_EQ(0, (int)m.mos_writes);
    struct bbc_config four = { .model_b = 1, .screen = 0x5800 };
    fresh();
    ASSERT_EQ(0, run(code, sizeof code, NULL, NULL, &four));
    ASSERT_EQ(4, (int)m.screen_writes);
    ASSERT_EQ(0x5800, m.first_screen_writes[0].addr);
    struct bbc_config strict = { .model_b = 1, .screen = 0x5800, .strict = 1 };
    fresh();
    ASSERT_EQ(1, run(code, sizeof code, NULL, NULL, &strict));
    ASSERT_EQ(BBC_END_STRICT, m.end);
    ASSERT(strstr(m.fault, "screen") != NULL);
    struct bbc_config shadow = { .shadow = 1, .screen = 0x5800, .strict = 1 };
    fresh();
    ASSERT_EQ(0, run(code, sizeof code, NULL, NULL, &shadow));
    ASSERT_EQ(0, (int)m.screen_writes);
    PASS();
}

TEST osbyte_252_reads_and_writes_the_current_language(void) {
    fresh();
    static const uint8_t svc[] = { RTS };
    rom_in_slot(9, 0xC2, svc, sizeof svc);   /* the language: reset selects it */
    static const uint8_t code[] = {
        LDA_IMM(252), LDX_IMM(0), LDY_IMM(0xFF), JSR(OSBYTE), STX_ZP(0x70), STY_ZP(0x71),
        LDA_IMM(252), LDX_IMM(5), LDY_IMM(0), JSR(OSBYTE), STX_ZP(0x72),     /* write 5 */
        LDA_IMM(252), LDX_IMM(0), LDY_IMM(0xFF), JSR(OSBYTE), STX_ZP(0x73), RTS };
    mem.ram[0x28D] = 0x44;
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(9, mem.ram[0x70]);             /* X: the old value, (old AND Y) EOR X the new */
    ASSERT_EQ(0x44, mem.ram[0x71]);          /* Y: the next of the MOS's variables, $028D */
    ASSERT_EQ(9, mem.ram[0x72]);
    ASSERT_EQ(5, mem.ram[0x73]);
    ASSERT_EQ(5, mem.ram[0x28C]);
    mem.kind[9] = BBC_SLOT_EMPTY;
    PASS();
}

TEST osbyte_0_with_x_0_is_an_error_through_brkv(void) {
    fresh();
    static const uint8_t code[] = { LDA_IMM(0), LDX_IMM(0), JSR(OSBYTE), RTS };
    ASSERT_EQ(1, RUN(code, NULL, NULL));
    ASSERT_EQ(BBC_END_ERROR, m.end);
    ASSERT_STR_EQ("OS 2.00\n", err_text);
    ASSERT_EQ(LO(BBC_MOS_E_OS + 1), mem.ram[0xFD]);   /* $FD/$FE: the error number */
    ASSERT_EQ(HI(BBC_MOS_E_OS + 1), mem.ram[0xFE]);
    PASS();
}

TEST osbyte_126_acknowledges_escape(void) {
    fresh();
    static const uint8_t code[] = {
        JSR(OSRDCH),                         /* end of input: Escape */
        LDA_IMM(126), JSR(OSBYTE), STX_ZP(0x70),
        LDA_IMM(126), JSR(OSBYTE), STX_ZP(0x71), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(0xFF, mem.ram[0x70]);
    ASSERT_EQ(0x00, mem.ram[0x71]);
    ASSERT_EQ(0, mem.ram[0xFF] & 0x80);
    PASS();
}

TEST osbyte_unknown_returns_x_ff_with_v_set(void) {
    fresh();
    static const uint8_t code[] = {
        LDA_IMM(99), LDX_IMM(0x12), LDY_IMM(0x34), JSR(OSBYTE),
        STA_ZP(0x70), STX_ZP(0x71), STY_ZP(0x72), PHP, PLA, STA_ZP(0x73), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(99, mem.ram[0x70]);
    ASSERT_EQ(0xFF, mem.ram[0x71]);          /* no ROM claimed it */
    ASSERT_EQ(0x34, mem.ram[0x72]);
    ASSERT_EQ(0x40, mem.ram[0x73] & 0x40);
    ASSERT_EQ(99, mem.ram[0xEF]);            /* A, X, Y kept at $EF-$F1 */
    ASSERT_EQ(0x12, mem.ram[0xF0]);
    ASSERT_EQ(0x34, mem.ram[0xF1]);
    PASS();
}

/* A ROM in slot 6 that counts each service call in $0400+A and claims 254 */
static void counting_rom(void) {
    static const uint8_t svc[] = {
        0xAA,                                /* TAX */
        0xFE, 0x00, 0x04,                    /* INC $0400,X */
        0x8A,                                /* TXA */
        0xA6, 0xF4,                          /* LDX $F4 */
        0xC9, 0xFE,                          /* CMP #254 */
        0xD0, 0x02,                          /* BNE +2 */
        LDA_IMM(0),                          /* claimed */
        RTS };
    rom_in_slot(6, 0x82, svc, sizeof svc);
}

TEST osbyte_143_offers_a_service_call_to_the_roms(void) {
    fresh();
    counting_rom();
    static const uint8_t svc[] = { 0xA6, 0xF4, STX_ZP(0x7E), RTS };   /* slot 2 notes it ran, does not claim */
    rom_in_slot(2, 0x82, svc, sizeof svc);
    static const uint8_t code[] = {
        LDA_IMM(143), LDX_IMM(254), LDY_IMM(0), JSR(OSBYTE), STX_ZP(0x70),
        LDA_IMM(143), LDX_IMM(50), LDY_IMM(0), JSR(OSBYTE), STX_ZP(0x71), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(0, mem.ram[0x70]);             /* claimed */
    ASSERT_EQ(1, mem.ram[0x400 + 254]);
    ASSERT_EQ(50, mem.ram[0x71]);            /* not claimed: X = the call */
    ASSERT_EQ(1, mem.ram[0x400 + 50]);
    ASSERT_EQ(2, mem.ram[0x7E]);             /* slot 2 was offered 50 after slot 6 */
    ASSERT_EQ(15, mem.ram[0xF4]);            /* the ROM selected before, again */
    ASSERT_EQ(15, mem.romsel);
    PASS();
}

TEST osbyte_142_enters_a_language_and_its_return_ends_the_run(void) {
    fresh();
    static const uint8_t svc[] = { RTS };
    rom_in_slot(7, 0xC2, svc, sizeof svc);
    /* the language at $8040: STA $70 (A = 1), print "L", RTS */
    const uint8_t lang[] = { STA_ZP(0x70), LDA_IMM('L'), JSR(OSWRCH), RTS };
    memcpy(mem.slot[7] + 0x40, lang, sizeof lang);
    rom_in_slot(3, 0x82, svc, sizeof svc);
    static const uint8_t code[] = { LDA_IMM(142), LDX_IMM(7), JSR(OSBYTE), LDA_IMM('X'), JSR(OSWRCH), RTS };
    mem.ram[0x28C] = 0;
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(1, mem.ram[0x70]);
    ASSERT_EQ(7, mem.ram[0x28C]);
    ASSERT_EQ(7, mem.ram[0xF4]);
    ASSERT_EQ(7, mem.romsel);
    ASSERT_EQ(1, (int)out_len);
    ASSERT_EQ('L', out_text[0]);
    static const uint8_t not_lang[] = { LDA_IMM(142), LDX_IMM(3), JSR(OSBYTE), RTS };
    ASSERT_EQ(1, RUN(not_lang, NULL, NULL));
    ASSERT_STR_EQ("This is not a language\n", err_text);
    static const uint8_t empty[] = { LDA_IMM(142), LDX_IMM(9), JSR(OSBYTE), LDA_IMM('e'), JSR(OSWRCH), RTS };
    ASSERT_EQ(0, RUN(empty, NULL, NULL));    /* an empty slot: no effect */
    ASSERT_STR_EQ("e", out_text);
    PASS();
}

/* ---- OSWORD ---- */

TEST osword_0_reads_a_line(void) {
    fresh();
    static const uint8_t code[] = {
        LDA_IMM(0x00), STA_ZP(0x70), LDA_IMM(0x04), STA_ZP(0x71),   /* buffer $0400 */
        LDA_IMM(5), STA_ZP(0x72), LDA_IMM(' '), STA_ZP(0x73), LDA_IMM('z'), STA_ZP(0x74),
        LDA_IMM(0), LDX_IMM(0x70), LDY_IMM(0), JSR(OSWORD), STY_ZP(0x75), PHP, PLA, STA_ZP(0x76),
        LDA_IMM(0x00), STA_ZP(0x71), LDA_IMM(0x05), STA_ZP(0x71),
        LDA_IMM(0), LDX_IMM(0x70), LDY_IMM(0), JSR(OSWORD), STY_ZP(0x77), PHP, PLA, STA_ZP(0x78),
        RTS };
    /* "ab~cdefg" with '~' out of range and a 5-character limit */
    ASSERT_EQ(0, RUN(code, "ab~c\x7F" "defgh\n", NULL));
    ASSERT_EQ(5, mem.ram[0x75]);
    ASSERT_MEM_EQ("abdef\r", (char *)mem.ram + 0x400, 6);
    ASSERT_EQ(0, mem.ram[0x76] & 1);
    ASSERT_EQ(1, mem.ram[0x78] & 1);         /* then the end of input: Escape */
    PASS();
}

TEST osword_1_reads_the_clock_and_2_sets_it(void) {
    fresh();
    /* spin about 200000 cycles (10 cs), read the clock into $70 */
    static const uint8_t code[] = {
        LDX_IMM(0), LDY_IMM(160),
        0xCA, 0xD0, 0xFD, 0x88, 0xD0, 0xFA,   /* DEX/BNE, DEY/BNE */
        LDA_IMM(1), LDX_IMM(0x70), LDY_IMM(0), JSR(OSWORD),
        LDA_IMM(0x00), STA_ZP(0x78), STA_ZP(0x79), STA_ZP(0x7A), STA_ZP(0x7B), LDA_IMM(0x10), STA_ZP(0x7C),
        LDA_IMM(2), LDX_IMM(0x78), LDY_IMM(0), JSR(OSWORD),
        LDA_IMM(1), LDX_IMM(0x78), LDY_IMM(0), JSR(OSWORD), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT(mem.ram[0x70] >= 9 && mem.ram[0x70] <= 12);
    ASSERT_EQ(0, mem.ram[0x71]);
    ASSERT_EQ(0x00, mem.ram[0x78]);
    ASSERT_EQ(0x10, mem.ram[0x7C]);          /* set to $10 00000000 and read back */
    PASS();
}

/* ---- errors ---- */

TEST a_program_brk_goes_through_brkv_with_fd_fe_set(void) {
    fresh();
    /* BRKV -> PAGE+$30: LDY #1; LDA ($FD),Y; STA $70; RTS... not allowed: a BRK handler
       never returns; it records and ends by RTS from the program's stack, which we
       don't rely on: it prints "!" and returns to the exit through the stack's top */
    uint8_t prog[0x50] = {
        LDA_IMM(LO(PAGE + 0x30)), STA_ABS(BRKV), LDA_IMM(HI(PAGE + 0x30)), STA_ABS(BRKV + 1),
        BRK, 42, 'N', 'o', 0 };
    const uint8_t handler[] = {
        LDA_ZP(0xFD), STA_ZP(0x70), LDA_ZP(0xFE), STA_ZP(0x71),
        0xA0, 0x01, 0xB1, 0xFD, STA_ZP(0x72),       /* LDY #1; LDA ($FD),Y */
        0xA2, 0xFD, 0x9A,                           /* LDX #$FD; TXS: the exit's return is at $1FE */
        RTS };
    memcpy(prog + 0x30, handler, sizeof handler);
    ASSERT_EQ(0, run(prog, sizeof prog, NULL, NULL, NULL));
    ASSERT_EQ(LO(PAGE + 11), mem.ram[0x70]);   /* the error number's address */
    ASSERT_EQ(HI(PAGE + 11), mem.ram[0x71]);
    ASSERT_EQ('N', mem.ram[0x72]);
    PASS();
}

TEST the_default_brkv_prints_the_message_and_ends_with_status_1(void) {
    fresh();
    static const uint8_t code[] = { LDA_IMM('a'), JSR(OSWRCH), BRK, 17, 'O', 'o', 'p', 's', 0 };
    ASSERT_EQ(1, RUN(code, NULL, NULL));
    ASSERT_STR_EQ("Oops\n", err_text);
    ASSERT_EQ('a', out_text[0]);
    PASS();
}

TEST an_error_in_a_rom_selects_the_language_and_is_reported_from_the_rom(void) {
    fresh();
    /* service call 50: an error (CMP #50; BNE out; BRK ...; out: RTS) */
    static const uint8_t svc[] = { 0xC9, 50, 0xD0, 0x06, BRK, 99, 'R', 'o', 'm', 0, RTS };
    rom_in_slot(6, 0x82, svc, sizeof svc);
    static const uint8_t lang[] = { RTS };
    rom_in_slot(9, 0xC2, lang, sizeof lang);
    static const uint8_t code[] = { LDA_IMM(143), LDX_IMM(50), LDY_IMM(0), JSR(OSBYTE), RTS };
    ASSERT_EQ(1, RUN(code, NULL, NULL));
    ASSERT_STR_EQ("Rom\n", err_text);
    ASSERT_EQ(6, mem.ram[0x24A]);            /* the ROM selected at the BRK */
    ASSERT_EQ(9, mem.romsel);                /* the language, selected again */
    ASSERT_EQ(9, mem.ram[0xF4]);
    ASSERT_EQ(0x25, mem.ram[0xFD]);          /* $8025: the error number */
    ASSERT_EQ(0x80, mem.ram[0xFE]);
    PASS();
}

/* ---- OSCLI ---- */

TEST oscli_unknown_command_is_bad_command(void) {
    fresh();
    ASSERT_EQ(1, run(NULL, 0, NULL, "NOSUCH", NULL));
    ASSERT_STR_EQ("Bad command\n", err_text);
    ASSERT_EQ(254, bbc_mos_rom[(mem.ram[0xFE] << 8 | mem.ram[0xFD]) - 0xC000]);
    fresh();
    ASSERT_EQ(0, run(NULL, 0, NULL, "  *|a comment", NULL));
    ASSERT_EQ(0, run(NULL, 0, NULL, "", NULL));
    PASS();
}

/* A ROM in slot 5 that claims *HI: prints "hi" and, from Y, the rest */
static void hi_rom(void) {
    static const uint8_t svc[] = {
        0xC9, 0x04, 0xD0, 0x1C,              /* CMP #4; BNE out (+28) */
        0xB1, 0xF2, 0xC9, 'H', 0xD0, 0x16,   /* LDA ($F2),Y; CMP #'H'; BNE out */
        0xC8, 0xB1, 0xF2, 0xC9, 'I', 0xD0, 0x0F, /* INY; LDA ($F2),Y; CMP #'I'; BNE out */
        STY_ZP(0x70),
        LDA_IMM('h'), JSR(OSWRCH), LDA_IMM('i'), JSR(OSWRCH),
        LDA_IMM(0), RTS,
        /* out: */ 0xA9, 0x04, RTS };
    rom_in_slot(5, 0x82, svc, sizeof svc);
}

TEST oscli_offers_service_call_4_from_slot_15_down(void) {
    fresh();
    hi_rom();
    counting_rom();                          /* slot 6 sees the call first and does not claim it */
    ASSERT_EQ(0, run(NULL, 0, NULL, " **HI", NULL));
    ASSERT_STR_EQ("hi", out_text);
    ASSERT_EQ(4, mem.ram[0x70]);             /* Y was 3 (the offset from ($F2)), then INY */
    ASSERT_EQ(LO(BBC_COMMAND_BUFFER), mem.ram[0xF2]);
    ASSERT_EQ(HI(BBC_COMMAND_BUFFER), mem.ram[0xF3]);
    ASSERT_EQ(1, mem.ram[0x404]);            /* slot 6 saw call 4 once */
    PASS();
}

/* A ROM in slot 5 that, for service call 9 (*HELP), prints the line from
 * ($F2),Y to its CR and leaves the call unclaimed */
static void help_rom(void) {
    static const uint8_t svc[] = {
        0xC9, 0x09, 0xD0, 0x12,              /* CMP #9; BNE out */
        STY_ZP(0x70),
        0xB1, 0xF2, 0xC9, 0x0D, 0xF0, 0x06,  /* loop: LDA ($F2),Y; CMP #$0D; BEQ done */
        JSR(OSWRCH), 0xC8, 0xD0, 0xF4,       /* JSR OSWRCH; INY; BNE loop */
        0xA4, 0x70, LDA_IMM(9),              /* done: LDY $70; LDA #9 (not claimed) */
        RTS };                               /* out: */
    rom_in_slot(5, 0x82, svc, sizeof svc);
}

TEST oscli_help_offers_service_call_9_with_y_at_its_argument(void) {
    fresh();
    help_rom();
    counting_rom();                          /* slot 6 sees it too */
    ASSERT_EQ(0, run(NULL, 0, NULL, "HELP", NULL));
    ASSERT_STR_EQ("", out_text);
    ASSERT_EQ(1, mem.ram[0x409]);            /* slot 6 saw call 9 once */
    ASSERT_EQ(4, mem.ram[0x70]);             /* Y: the CR after HELP */
    ASSERT_EQ(0, run(NULL, 0, NULL, " *help  LATHE now", NULL));
    ASSERT_STR_EQ("LATHE now", out_text);
    ASSERT_EQ(8, mem.ram[0x70]);             /* Y: after the spaces */
    ASSERT_EQ(1, run(NULL, 0, NULL, "HELPX", NULL));   /* not HELP: service call 4, then Bad command */
    ASSERT_STR_EQ("Bad command\n", err_text);
    PASS();
}

TEST more_commands_run_in_turn_after_each_returns(void) {
    fresh();
    hi_rom();
    static const char *const more[] = { "HI", "*HI" };
    struct bbc_config cfg = { 0 };
    cfg.more_commands = more;
    cfg.more_count = 2;
    ASSERT_EQ(0, run(NULL, 0, NULL, "HI", &cfg));
    ASSERT_STR_EQ("hihihi", out_text);
    ASSERT_EQ(BBC_END_RETURNED, m.end);
    static const char *const after_error[] = { "NOSUCH", "HI" };
    cfg.more_commands = after_error;
    ASSERT_EQ(1, run(NULL, 0, NULL, "HI", &cfg));   /* an error ends the run: no command after it */
    ASSERT_STR_EQ("hi", out_text);
    ASSERT_STR_EQ("Bad command\n", err_text);
    /* after a program that enters a language by OSBYTE 142: the language returns, then the
     * next command runs, from $0700, with the stack reset */
    static const uint8_t svc[] = { RTS };
    rom_in_slot(7, 0xC2, svc, sizeof svc);
    const uint8_t lang[] = { LDA_IMM('L'), JSR(OSWRCH), RTS };
    memcpy(mem.slot[7] + 0x40, lang, sizeof lang);
    static const uint8_t code[] = { LDA_IMM(142), LDX_IMM(7), JSR(OSBYTE), RTS };
    static const char *const one[] = { "HI" };
    cfg.more_commands = one;
    cfg.more_count = 1;
    ASSERT_EQ(0, run(code, sizeof code, NULL, NULL, &cfg));
    ASSERT_STR_EQ("Lhi", out_text);
    ASSERT_MEM_EQ("HI\r", (char *)mem.ram + BBC_COMMAND_BUFFER, 3);
    mem.kind[7] = BBC_SLOT_EMPTY;
    PASS();
}

TEST oscli_run_and_star_name_run_a_file_from_disk(void) {
    fresh();
    make_disk();
    static const uint8_t prog[] = { LDA_IMM('r'), JSR(OSWRCH), RTS };
    write_host("PROG", prog, sizeof prog);
    write_host("PROG.inf", "PROG 00003000 00003000 00000006\n", 32);
    ASSERT_EQ(0, run(NULL, 0, NULL, "RUN PROG  tail", NULL));
    ASSERT_STR_EQ("r", out_text);
    fresh();
    ASSERT_EQ(0, run(NULL, 0, NULL, "PROG", NULL));
    ASSERT_STR_EQ("r", out_text);
    fresh();
    ASSERT_EQ(0, run(NULL, 0, NULL, "*/PROG", NULL));   /* "/" runs a file, as *RUN does */
    ASSERT_STR_EQ("r", out_text);
    fresh();
    ASSERT_EQ(1, run(NULL, 0, NULL, "RUN NONE", NULL));
    ASSERT_STR_EQ("File not found\n", err_text);
    fresh();
    ASSERT_EQ(1, run(NULL, 0, NULL, "NONE", NULL));
    ASSERT_STR_EQ("Bad command\n", err_text);
    remove_disk();
    PASS();
}

TEST oscli_run_passes_the_command_tail_to_osargs(void) {
    fresh();
    make_disk();
    static const uint8_t prog[] = { LDA_IMM(1), LDX_IMM(0x70), LDY_IMM(0), JSR(OSARGS), RTS };
    write_host("T", prog, sizeof prog);
    write_host("T.inf", "T 3000 3000\n", 12);
    ASSERT_EQ(0, run(NULL, 0, NULL, "RUN T  some args", NULL));
    ASSERT_EQ(LO(BBC_COMMAND_BUFFER + 7), mem.ram[0x70]);
    ASSERT_EQ(HI(BBC_COMMAND_BUFFER + 7), mem.ram[0x71]);
    ASSERT_MEM_EQ("some args\r", (char *)mem.ram + BBC_COMMAND_BUFFER + 7, 10);
    remove_disk();
    PASS();
}

TEST oscli_save_and_load(void) {
    fresh();
    make_disk();
    memcpy(mem.ram + 0x3000, "HELLO", 5);
    ASSERT_EQ(0, run(NULL, 0, NULL, "SAVE DATA 3000 +5 3001 2000", NULL));
    char buf[64];
    ASSERT_EQ(5, read_host("DATA", buf, sizeof buf));
    ASSERT_STR_EQ("HELLO", buf);
    read_host("DATA.inf", buf, sizeof buf);
    ASSERT_STR_EQ("DATA 00002000 00003001 00000005\n", buf);
    fresh();
    ASSERT_EQ(0, run(NULL, 0, NULL, "LOAD DATA", NULL));
    ASSERT_MEM_EQ("HELLO", (char *)mem.ram + 0x2000, 5);
    ASSERT_EQ(0, run(NULL, 0, NULL, "LOAD DATA 4100", NULL));
    ASSERT_MEM_EQ("HELLO", (char *)mem.ram + 0x4100, 5);
    ASSERT_EQ(1, run(NULL, 0, NULL, "SAVE X", NULL));
    ASSERT_STR_EQ("Bad address\n", err_text);
    remove_disk();
    PASS();
}

/* ---- OSFILE ---- */

/* The OSFILE block at $0380 is not the program's ($0200-$03FF is the MOS's): use $70 */
static uint8_t osfile_code[] = {
    LDA_ZP(0x6F), LDX_IMM(0x70), LDY_IMM(0x00), JSR(OSFILE), STA_ZP(0x6E), RTS };

static void osfile_block(uint8_t call, uint16_t name, uint32_t load, uint32_t exec, uint32_t s, uint32_t e) {
    mem.ram[0x6F] = call;
    mem.ram[0x70] = LO(name);
    mem.ram[0x71] = HI(name);
    uint32_t v[4] = { load, exec, s, e };
    for (int k = 0; k < 4; k++)
        for (int i = 0; i < 4; i++) mem.ram[0x72 + 4 * k + i] = (uint8_t)(v[k] >> (8 * i));
}

static uint32_t block32(int off) {
    uint32_t v = 0;
    for (int i = 3; i >= 0; i--) v = v << 8 | mem.ram[0x70 + off + i];
    return v;
}

TEST osfile_save_load_info_and_delete(void) {
    make_disk();
    fresh();
    memcpy(mem.ram + 0x5000, "0123456789", 10);
    put_text(0x0400, "F1");
    osfile_block(0x00, 0x0400, 0xFFFF5000, 0xFFFF5002, 0x5000, 0x500A);
    ASSERT_EQ(0, run(osfile_code, sizeof osfile_code, NULL, NULL, NULL));
    ASSERT_EQ(1, mem.ram[0x6E]);
    char buf[64];
    ASSERT_EQ(10, read_host("F1", buf, sizeof buf));
    read_host("F1.inf", buf, sizeof buf);
    ASSERT_STR_EQ("F1 FFFF5000 FFFF5002 0000000A\n", buf);

    fresh();                                 /* load at its own address (exec byte non-zero) */
    put_text(0x0400, "F1");
    osfile_block(0xFF, 0x0400, 0, 1, 0, 0);
    ASSERT_EQ(0, run(osfile_code, sizeof osfile_code, NULL, NULL, NULL));
    ASSERT_EQ(1, mem.ram[0x6E]);
    ASSERT_MEM_EQ("0123456789", (char *)mem.ram + 0x5000, 10);
    ASSERT_EQ(0xFFFF5000u, block32(2));
    ASSERT_EQ(0xFFFF5002u, block32(6));
    ASSERT_EQ(10u, block32(10));

    fresh();                                 /* load at the address given */
    put_text(0x0400, "F1");
    osfile_block(0xFF, 0x0400, 0x6000, 0, 0, 0);
    run(osfile_code, sizeof osfile_code, NULL, NULL, NULL);
    ASSERT_MEM_EQ("0123456789", (char *)mem.ram + 0x6000, 10);

    fresh();                                 /* read the catalogue information */
    put_text(0x0400, "F1");
    osfile_block(5, 0x0400, 0, 0, 0, 0);
    run(osfile_code, sizeof osfile_code, NULL, NULL, NULL);
    ASSERT_EQ(1, mem.ram[0x6E]);
    ASSERT_EQ(0xFFFF5000u, block32(2));
    ASSERT_EQ(10u, block32(10));

    fresh();                                 /* write the load address */
    put_text(0x0400, "F1");
    osfile_block(2, 0x0400, 0x1234, 0, 0, 0);
    run(osfile_code, sizeof osfile_code, NULL, NULL, NULL);
    read_host("F1.inf", buf, sizeof buf);
    ASSERT_STR_EQ("F1 00001234 FFFF5002 0000000A\n", buf);

    fresh();                                 /* delete */
    put_text(0x0400, "F1");
    osfile_block(6, 0x0400, 0, 0, 0, 0);
    run(osfile_code, sizeof osfile_code, NULL, NULL, NULL);
    ASSERT_EQ(1, mem.ram[0x6E]);
    ASSERT_EQ(-1, read_host("F1", buf, sizeof buf));
    ASSERT_EQ(-1, read_host("F1.inf", buf, sizeof buf));
    run(osfile_code, sizeof osfile_code, NULL, NULL, NULL);
    ASSERT_EQ(0, mem.ram[0x6E]);             /* gone: A = 0 */

    fresh();                                 /* a missing file: File not found */
    put_text(0x0400, "F1");
    osfile_block(0xFF, 0x0400, 0x6000, 0, 0, 0);
    ASSERT_EQ(1, run(osfile_code, sizeof osfile_code, NULL, NULL, NULL));
    ASSERT_STR_EQ("File not found\n", err_text);

    fresh();                                 /* no .inf: zero addresses */
    write_host("RAW", "xy", 2);
    put_text(0x0400, "RAW");
    osfile_block(5, 0x0400, 9, 9, 0, 0);
    run(osfile_code, sizeof osfile_code, NULL, NULL, NULL);
    ASSERT_EQ(0u, block32(2));
    ASSERT_EQ(0u, block32(6));
    ASSERT_EQ(2u, block32(10));
    remove_disk();
    PASS();
}

TEST file_names_with_slash_or_dotdot_are_refused(void) {
    make_disk();
    const char *bad[] = { "a/b", "..", "x..y", "/etc", "./a/b", "./", "./../x", "x/./y" };
    for (int i = 0; i < 8; i++) {
        fresh();
        put_text(0x0400, bad[i]);
        osfile_block(5, 0x0400, 0, 0, 0, 0);
        ASSERT_EQ(1, run(osfile_code, sizeof osfile_code, NULL, NULL, NULL));
        ASSERT_STR_EQ("Bad name\n", err_text);
    }
    fresh();                                 /* long names are fine */
    put_text(0x0400, "a_name_much_longer_than_seven_characters");
    osfile_block(5, 0x0400, 0, 0, 0, 0);
    ASSERT_EQ(0, run(osfile_code, sizeof osfile_code, NULL, NULL, NULL));
    remove_disk();
    PASS();
}

TEST a_leading_dot_slash_names_the_disk_itself(void) {
    make_disk();
    write_host("LI", "abc", 3);
    const char *good[] = { "./LI", "././LI" };
    for (int i = 0; i < 2; i++) {
        fresh();
        put_text(0x0400, good[i]);
        osfile_block(5, 0x0400, 0, 0, 0, 0);
        ASSERT_EQ(0, run(osfile_code, sizeof osfile_code, NULL, NULL, NULL));
        ASSERT_EQ(3u, block32(10));          /* the file LI: its length */
    }
    remove_disk();
    PASS();
}

TEST file_calls_without_a_disk_raise_an_error(void) {
    fresh();
    disk[0] = 0;
    put_text(0x0400, "F");
    osfile_block(5, 0x0400, 0, 0, 0, 0);
    ASSERT_EQ(1, run(osfile_code, sizeof osfile_code, NULL, NULL, NULL));
    ASSERT_STR_EQ("No disk (--disk)\n", err_text);
    PASS();
}

/* ---- OSFIND, OSBGET, OSBPUT, OSARGS, OSGBPB ---- */

TEST osfind_bget_bput_copy_a_file_and_report_eof(void) {
    make_disk();
    fresh();
    write_host("IN", "abc", 3);
    put_text(0x0400, "IN");
    put_text(0x0410, "OUT");
    static const uint8_t code[] = {
        LDA_IMM(0x40), LDX_IMM(0x00), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x70),
        LDA_IMM(0x80), LDX_IMM(0x10), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x71),
        /* loop: */ 0xA4, 0x70, JSR(OSBGET), 0xB0, 0x07,     /* LDY $70; JSR OSBGET; BCS done */
        0xA4, 0x71, JSR(OSBPUT), 0x90, 0xF2,                 /* LDY $71; JSR OSBPUT; BCC loop */
        /* done: */ STA_ZP(0x72),
        LDA_IMM(0), LDY_IMM(0), JSR(OSFIND), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(0x11, mem.ram[0x70]);
    ASSERT_EQ(0x12, mem.ram[0x71]);
    ASSERT_EQ(0xFE, mem.ram[0x72]);
    ASSERT_EQ(2u, (unsigned)m.files_opened);   /* the counts --exit-report shows */
    ASSERT_EQ(3u, (unsigned)m.bytes_read);
    ASSERT_EQ(3u, (unsigned)m.bytes_written);
    char buf[16];
    ASSERT_EQ(3, read_host("OUT", buf, sizeof buf));
    ASSERT_STR_EQ("abc", buf);
    remove_disk();
    PASS();
}

TEST osfind_missing_file_returns_0_and_bget_twice_at_eof_is_an_error(void) {
    make_disk();
    fresh();
    put_text(0x0400, "NONE");
    static const uint8_t code[] = { LDA_IMM(0x40), LDX_IMM(0x00), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x70),
                                    LDA_IMM(0xC0), LDX_IMM(0x00), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x71), RTS };
    mem.ram[0x70] = mem.ram[0x71] = 0x55;
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(0, mem.ram[0x70]);
    ASSERT_EQ(0, mem.ram[0x71]);

    fresh();
    write_host("E", "", 0);
    put_text(0x0400, "E");
    static const uint8_t eof[] = { LDA_IMM(0x40), LDX_IMM(0x00), LDY_IMM(0x04), JSR(OSFIND), 0xA8,   /* TAY */
                                   JSR(OSBGET), 0xA0, 0x11, JSR(OSBGET), RTS };
    ASSERT_EQ(1, RUN(eof, NULL, NULL));
    ASSERT_STR_EQ("EOF\n", err_text);

    fresh();
    static const uint8_t channel[] = { LDY_IMM(0x30), JSR(OSBGET), RTS };
    ASSERT_EQ(1, RUN(channel, NULL, NULL));
    ASSERT_STR_EQ("Channel\n", err_text);

    fresh();
    write_host("R", "r", 1);
    put_text(0x0400, "R");
    static const uint8_t ro[] = { LDA_IMM(0x40), LDX_IMM(0x00), LDY_IMM(0x04), JSR(OSFIND), 0xA8,
                                  JSR(OSBPUT), RTS };
    ASSERT_EQ(1, RUN(ro, NULL, NULL));
    ASSERT_STR_EQ("Read only\n", err_text);
    remove_disk();
    PASS();
}

TEST osargs_reads_and_writes_ptr_and_reads_ext(void) {
    make_disk();
    fresh();
    write_host("A", "0123456789", 10);
    put_text(0x0400, "A");
    static const uint8_t code[] = {
        LDA_IMM(0xC0), LDX_IMM(0x00), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x60),
        LDA_IMM(2), LDX_IMM(0x70), 0xA4, 0x60, JSR(OSARGS),          /* EXT -> $70 */
        LDA_IMM(6), STA_ZP(0x74), LDA_IMM(0), STA_ZP(0x75), STA_ZP(0x76), STA_ZP(0x77),
        LDA_IMM(1), LDX_IMM(0x74), 0xA4, 0x60, JSR(OSARGS),          /* PTR = 6 */
        0xA4, 0x60, JSR(OSBGET), STA_ZP(0x78),                       /* '6' */
        LDA_IMM('X'), 0xA4, 0x60, JSR(OSBPUT),                       /* at 7 */
        LDA_IMM(0), LDX_IMM(0x7C), 0xA4, 0x60, JSR(OSARGS),          /* PTR -> $7C: 8 */
        LDA_IMM(0), LDX_IMM(0x6C), LDY_IMM(0), JSR(OSARGS), STA_ZP(0x6B),  /* the filing system */
        LDA_IMM(127), 0xA6, 0x60, JSR(OSBYTE), STX_ZP(0x6A),         /* not at EOF */
        LDA_IMM(0), 0xA4, 0x60, JSR(OSFIND), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(10, mem.ram[0x70]);
    ASSERT_EQ('6', mem.ram[0x78]);
    ASSERT_EQ(8, mem.ram[0x7C]);
    ASSERT_EQ(4, mem.ram[0x6B]);
    ASSERT_EQ(0, mem.ram[0x6A]);
    char buf[16];
    read_host("A", buf, sizeof buf);
    ASSERT_STR_EQ("0123456X89", buf);
    remove_disk();
    PASS();
}

TEST osgbpb_reads_and_writes_blocks(void) {
    make_disk();
    fresh();
    write_host("G", "abcdefghij", 10);
    put_text(0x0400, "G");
    /* block at $70: handle, address $5000, count 4, PTR 3: read (A=3) */
    static const uint8_t code[] = {
        LDA_IMM(0xC0), LDX_IMM(0x00), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x70),
        LDA_IMM(3), LDX_IMM(0x70), LDY_IMM(0), JSR(OSGBPB), PHP, PLA, STA_ZP(0x60),
        /* read 10 more at the current PTR (A=4): only 3 left */
        LDA_IMM(10), STA_ZP(0x75), LDA_IMM(4), LDX_IMM(0x70), LDY_IMM(0), JSR(OSGBPB), PHP, PLA, STA_ZP(0x61),
        /* write "ab" from $5000 at PTR 0 (A=1) */
        LDA_IMM(0x00), STA_ZP(0x71), LDA_IMM(2), STA_ZP(0x75), LDA_IMM(0), STA_ZP(0x79),
        LDA_IMM(1), LDX_IMM(0x70), LDY_IMM(0), JSR(OSGBPB),
        LDA_IMM(0), 0xA4, 0x70, JSR(OSFIND), RTS };
    mem.ram[0x71] = 0x00; mem.ram[0x72] = 0x50; mem.ram[0x73] = 0; mem.ram[0x74] = 0;
    mem.ram[0x75] = 4; mem.ram[0x76] = mem.ram[0x77] = mem.ram[0x78] = 0;
    mem.ram[0x79] = 3; mem.ram[0x7A] = mem.ram[0x7B] = mem.ram[0x7C] = 0;
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_MEM_EQ("defghij", (char *)mem.ram + 0x5000, 7);
    ASSERT_EQ(0, mem.ram[0x60] & 1);         /* all 4 */
    ASSERT_EQ(1, mem.ram[0x61] & 1);         /* not all 10 */
    ASSERT_EQ(0x02, mem.ram[0x71]);          /* the address moved on by 2 */
    ASSERT_EQ(7u, (unsigned)m.bytes_read);    /* 4 and 3 */
    ASSERT_EQ(2u, (unsigned)m.bytes_written);
    ASSERT_EQ(0, mem.ram[0x75]);             /* nothing left */
    ASSERT_EQ(2, mem.ram[0x79]);             /* PTR */
    char buf[16];
    read_host("G", buf, sizeof buf);
    ASSERT_STR_EQ("decdefghij", buf);
    remove_disk();
    PASS();
}

/* ---- --bbc-fs dfs: the names and limits of the Acorn DFS ---- */

static struct bbc_config dfs_cfg = { .dfs = 1 };

/* OSFIND with A = $6F on the name at $0400; the handle in $6E */
static uint8_t find_code[] = {
    LDA_ZP(0x6F), LDX_IMM(0x00), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x6E), RTS };

static int dfs_find(uint8_t mode, const char *name) {
    fresh();
    put_text(0x0400, name);
    mem.ram[0x6F] = mode;
    return run(find_code, sizeof find_code, NULL, NULL, &dfs_cfg);
}

/* OSFILE `call` on the name; a save (0) saves `data` from $5000 */
static int dfs_osfile(uint8_t call, const char *name, const char *data) {
    fresh();
    put_text(0x0400, name);
    uint32_t s = 0x5000, e = 0x5000 + (data ? (uint32_t)strlen(data) : 0);
    if (data) memcpy(mem.ram + 0x5000, data, strlen(data));
    osfile_block(call, 0x0400, 0x1900, 0x1900, s, e);
    return run(osfile_code, sizeof osfile_code, NULL, NULL, &dfs_cfg);
}

TEST dfs_names_are_checked_as_the_dfs_checks_them(void) {
    make_disk();
    const char *good[] = { "A", "ABCDEFG", "L.EXPR", "l.expr", "$.ABC", ":0.A", ":3.O.X", "!.~}|",
                           "_", "L._" };
    for (int i = 0; i < 10; i++) {
        ASSERT_EQ_FMT(0, dfs_osfile(5, good[i], NULL), "%d");
        ASSERT_EQ(0, mem.ram[0x6E]);          /* not there: A = 0, no error */
    }
    const char *bad[] = { "ABCDEFGH", "expr.lth", "./L.X", "A.", ".A", "A#", "A*", "\"A", "L.EX.P",
                          "LL.X", ":1.", ":1", ":1.LONGNAME", "A:B", "../x",
                          "a/b" };   /* a real DFS takes "a/b"; the host directory cannot hold it */
    for (int i = 0; i < 16; i++) {
        ASSERT_EQ_FMT(1, dfs_osfile(5, bad[i], NULL), "%d");
        ASSERT_STR_EQ("Bad name\n", err_text);
    }
    const char *drive[] = { ":4.A", ":A.B", ":.A" };
    for (int i = 0; i < 3; i++) {
        ASSERT_EQ(1, dfs_osfile(5, drive[i], NULL));
        ASSERT_STR_EQ("Bad drive\n", err_text);
    }
    ASSERT_EQ(1, dfs_find(0x40, "expr.lth"));    /* OSFIND too */
    ASSERT_STR_EQ("Bad name\n", err_text);
    fresh();                                     /* and *RUN, *LOAD and *SAVE */
    ASSERT_EQ(1, run(NULL, 0, NULL, "LOAD expr.lth 5000", &dfs_cfg));
    ASSERT_STR_EQ("Bad name\n", err_text);
    fresh();
    ASSERT_EQ(1, run(NULL, 0, NULL, "SAVE TOOLONGX 5000 5001", &dfs_cfg));
    ASSERT_STR_EQ("Bad name\n", err_text);
    remove_disk();
    PASS();
}

TEST dfs_files_are_kept_as_dir_dot_name_and_found_in_any_case(void) {
    make_disk();
    ASSERT_EQ(0, dfs_osfile(0, "l.expr", "abc"));
    char buf[64];
    ASSERT_EQ(3, read_host("l.expr", buf, sizeof buf));   /* the case it was created in */
    read_host("l.expr.inf", buf, sizeof buf);
    ASSERT_STR_EQ("l.expr 00001900 00001900 00000003\n", buf);
    ASSERT_EQ(0, dfs_osfile(0, "A", "a"));
    ASSERT_EQ(1, read_host("$.A", buf, sizeof buf));      /* $ is the directory unless named */
    ASSERT_EQ(0, dfs_osfile(0, ":2.O.X", "ox"));
    ASSERT_EQ(2, read_host(":2/O.X", buf, sizeof buf));   /* drive 2: the subdirectory :2 */
    ASSERT_EQ(0, dfs_osfile(5, "L.EXPR", NULL));          /* found whatever the case */
    ASSERT_EQ(1, mem.ram[0x6E]);
    ASSERT_EQ(3u, block32(10));
    ASSERT_EQ(0, dfs_osfile(5, "$.a", NULL));
    ASSERT_EQ(1, mem.ram[0x6E]);
    ASSERT_EQ(0, dfs_osfile(5, ":0.a", NULL));
    ASSERT_EQ(1, mem.ram[0x6E]);
    ASSERT_EQ(0, dfs_osfile(5, "O.X", NULL));             /* not on drive 0 */
    ASSERT_EQ(0, mem.ram[0x6E]);
    ASSERT_EQ(0, dfs_find(0x40, "L.Expr"));
    ASSERT_EQ(0x11, mem.ram[0x6E]);
    ASSERT_EQ(0, dfs_osfile(0, "L.EXPR", "wxyz"));        /* saving again keeps the one file */
    ASSERT_EQ(4, read_host("l.expr", buf, sizeof buf));
    ASSERT_EQ(-1, read_host("L.EXPR", buf, sizeof buf));
    ASSERT_EQ(0, dfs_find(0x80, "$.NEW"));                /* OSFIND creates as OSFILE saves */
    ASSERT_EQ(0, read_host("$.NEW", buf, sizeof buf));
    fresh();
    write_host("$.PROG", (uint8_t[]){ RTS }, 1);
    write_host("$.PROG.inf", "$.PROG 1900 1900\n", 17);
    ASSERT_EQ(0, run(NULL, 0, NULL, "RUN prog", &dfs_cfg));
    fresh();
    ASSERT_EQ(0, run(NULL, 0, NULL, "LOAD L.EXPR 6000", &dfs_cfg));
    ASSERT_MEM_EQ("wxyz", (char *)mem.ram + 0x6000, 4);
    fresh();                                              /* the host's own names are not seen */
    write_host("HOSTNAME", "h", 1);
    ASSERT_EQ(0, dfs_osfile(5, "HOSTNAM", NULL));
    ASSERT_EQ(0, mem.ram[0x6E]);
    remove_disk();
    PASS();
}

TEST dfs_has_five_files_open_at_most(void) {
    make_disk();
    fresh();
    const char *names[] = { "A", "B", "C", "D", "E", "F" };
    for (int i = 0; i < 6; i++) put_text((uint16_t)(0x0400 + 8 * i), names[i]);
    uint8_t code[6 * 11 + 1];
    size_t n = 0;
    for (int i = 0; i < 6; i++) {
        uint8_t one[] = { LDA_IMM(0x80), LDX_IMM(8 * i), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x60 + i) };
        memcpy(code + n, one, sizeof one);
        n += sizeof one;
    }
    code[n++] = RTS;
    ASSERT_EQ(1, run(code, n, NULL, NULL, &dfs_cfg));
    ASSERT_STR_EQ("Too many open\n", err_text);
    ASSERT_EQ(0x11, mem.ram[0x60]);
    ASSERT_EQ(0x15, mem.ram[0x64]);
    ASSERT_EQ(5u, (unsigned)m.most_open);
    ASSERT_EQ(5u, (unsigned)m.most_writing);
    remove_disk();
    PASS();
}

TEST dfs_catalogue_holds_31_files_a_drive(void) {
    make_disk();
    char name[16];
    for (int i = 0; i < 31; i++) {
        snprintf(name, sizeof name, "%c.F%02d", i < 20 ? '$' : 'O', i);
        write_host(name, "x", 1);
        snprintf(name, sizeof name, "%c.F%02d.inf", i < 20 ? '$' : 'O', i);
        write_host(name, "x 0 0\n", 6);           /* .inf files are not entries */
    }
    write_host("NOT-DFS-NAME", "x", 1);           /* nor are host files of other names */
    ASSERT_EQ(1, dfs_find(0x80, "NEW"));
    ASSERT_STR_EQ("Cat full\n", err_text);
    ASSERT_EQ(1, dfs_osfile(0, "L.NEW", "abc"));
    ASSERT_STR_EQ("Cat full\n", err_text);
    ASSERT_EQ(0, dfs_find(0x80, "O.F25"));        /* a file that is there can be written */
    ASSERT_EQ(0x11, mem.ram[0x6E]);
    ASSERT_EQ(0, dfs_find(0x80, ":1.NEW"));       /* another drive has its own catalogue */
    ASSERT_EQ(0x11, mem.ram[0x6E]);
    ASSERT_EQ(0, dfs_osfile(6, "$.F00", NULL));   /* deleting makes room */
    ASSERT_EQ(0, dfs_find(0x80, "NEW"));
    ASSERT_EQ(0x11, mem.ram[0x6E]);
    remove_disk();
    PASS();
}

/* ---- --bbc-fs adfs: the names, directories, limits and space of ADFS ---- */

static struct bbc_config adfs_cfg = { .adfs = 1 };

static int adfs_find(uint8_t mode, const char *name) {
    fresh();
    put_text(0x0400, name);
    mem.ram[0x6F] = mode;
    return run(find_code, sizeof find_code, NULL, NULL, &adfs_cfg);
}

static int adfs_osfile(uint8_t call, const char *name, const char *data) {
    fresh();
    put_text(0x0400, name);
    uint32_t s = 0x5000, e = 0x5000 + (data ? (uint32_t)strlen(data) : 0);
    if (data) memcpy(mem.ram + 0x5000, data, strlen(data));
    osfile_block(call, 0x0400, 0x1900, 0x1900, s, e);
    return run(osfile_code, sizeof osfile_code, NULL, NULL, &adfs_cfg);
}

/* The commands in turn, as typed one after another */
static int adfs_commands(const char *const *lines, int n, struct bbc_config *cfg) {
    fresh();
    struct bbc_config c = cfg ? *cfg : adfs_cfg;
    c.more_commands = lines + 1;
    c.more_count = n - 1;
    return run(NULL, 0, NULL, lines[0], &c);
}

static int host_is_dir(const char *name) {
    char path[256];
    snprintf(path, sizeof path, "%s/%s", disk, name);
    struct stat st;
    return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}

static void host_mkdir(const char *name) {
    char path[256];
    snprintf(path, sizeof path, "%s/%s", disk, name);
    mkdir(path, 0777);
}

TEST adfs_names_are_checked_as_adfs_checks_them(void) {
    make_disk();
    const char *good[] = { "A", "ABCDEFGHIJ", "lth", "$.A", "&.A", ":0.A", ":1.A", ":4.A", ":E.A", ":b.A",
                           ":0.$.A", "@.A", "^.A", "!~}|_-+", "Y9" };
    for (int i = 0; i < 15; i++) {
        ASSERT_EQ_FMT(0, adfs_osfile(5, good[i], NULL), "%d");
        ASSERT_EQ(0, mem.ram[0x6E]);          /* not there: A = 0, no error */
    }
    const char *bad[] = { "ABCDEFGHIJK", "A..B", ".A", "A.", "$$", "A$B", "FILE:ONE", "A@B", "A^B", "\"A",
                          ":1A", "$A", "A&",
                          "a/b" };   /* ADFS takes "a/b"; the host directory cannot hold it */
    for (int i = 0; i < 14; i++) {
        ASSERT_EQ_FMT(1, adfs_osfile(5, bad[i], NULL), "%d");
        ASSERT_STR_EQ("Bad name\n", err_text);
    }
    ASSERT_EQ(1, adfs_osfile(5, "A#", NULL));
    ASSERT_STR_EQ("Wild cards\n", err_text);
    ASSERT_EQ(1, adfs_osfile(0, "L*", "x"));
    ASSERT_STR_EQ("Wild cards\n", err_text);
    const char *drive[] = { ":2.A", ":3.A", ":C.A", ":7.A" };
    for (int i = 0; i < 4; i++) {
        ASSERT_EQ(1, adfs_osfile(5, drive[i], NULL));
        ASSERT_STR_EQ("Bad drive\n", err_text);
    }
    ASSERT_EQ(1, adfs_find(0x80, "ABCDEFGHIJK"));    /* OSFIND too */
    ASSERT_STR_EQ("Bad name\n", err_text);
    remove_disk();
    PASS();
}

TEST adfs_directories_are_host_directories_and_names_match_in_any_case(void) {
    make_disk();
    const char *mk[] = { "CDIR lth", "CDIR :1.lo", "CDIR lth.sub" };
    ASSERT_EQ(0, adfs_commands(mk, 3, NULL));
    ASSERT(host_is_dir("lth"));
    ASSERT(host_is_dir(":1/lo"));                       /* drive 1: the subdirectory :1 */
    ASSERT(host_is_dir("lth/sub"));
    ASSERT_EQ(0, adfs_osfile(0, "lth.expr", "abc"));
    char buf[64];
    ASSERT_EQ(3, read_host("lth/expr", buf, sizeof buf));
    read_host("lth/expr.inf", buf, sizeof buf);
    ASSERT_STR_EQ("lth.expr 00001900 00001900 00000003\n", buf);
    ASSERT_EQ(0, adfs_osfile(5, "LTH.EXPR", NULL));      /* found whatever the case */
    ASSERT_EQ(1, mem.ram[0x6E]);
    ASSERT_EQ(3u, block32(10));
    ASSERT_EQ(0, adfs_osfile(5, "$.Lth", NULL));          /* a directory */
    ASSERT_EQ(2, mem.ram[0x6E]);
    ASSERT_EQ(0, adfs_osfile(0, "LTH.EXPR", "wxyz"));    /* saving again keeps the one file */
    ASSERT_EQ(4, read_host("lth/expr", buf, sizeof buf));
    ASSERT_EQ(0, adfs_find(0x80, ":1.lo.x"));
    ASSERT_EQ(0x30, mem.ram[0x6E]);                       /* ADFS's first handle */
    ASSERT_EQ(0, read_host(":1/lo/x", buf, sizeof buf));
    ASSERT_EQ(0, adfs_find(0x40, "lo.x"));                /* not on drive 0 */
    ASSERT_EQ(0, mem.ram[0x6E]);
    ASSERT_EQ(0, adfs_find(0x40, "nodir.x"));             /* reading through a missing directory: not there */
    ASSERT_EQ(0, mem.ram[0x6E]);
    ASSERT_EQ(1, adfs_find(0x80, "nodir.x"));             /* creating there: Not found */
    ASSERT_STR_EQ("Not found\n", err_text);
    ASSERT_EQ(1, adfs_osfile(0, "lth.expr.x", "x"));      /* a file is not a directory */
    ASSERT_STR_EQ("Not found\n", err_text);
    const char *again[] = { "CDIR LTH" };
    ASSERT_EQ(1, adfs_commands(again, 1, NULL));
    ASSERT_STR_EQ("Already exists\n", err_text);
    const char *deep[] = { "CDIR no.such" };
    ASSERT_EQ(1, adfs_commands(deep, 1, NULL));
    ASSERT_STR_EQ("Not found\n", err_text);
    /* *DIR: the CSD, which names without $ or a drive start from; ^ its parent */
    const char *dir[] = { "DIR lth", "SAVE inlth 5000 +1", "DIR sub", "SAVE ^.up 5000 +1", "DIR :1",
                          "SAVE one 5000 +1", "DIR", "SAVE root1 5000 +1" };
    ASSERT_EQ_FMT(0, adfs_commands(dir, 8, NULL), "%d");
    ASSERT_EQ(1, read_host("lth/inlth", buf, sizeof buf));
    ASSERT_EQ(1, read_host("lth/up", buf, sizeof buf));
    ASSERT_EQ(1, read_host(":1/one", buf, sizeof buf));
    ASSERT_EQ(1, read_host(":1/root1", buf, sizeof buf));   /* *DIR alone: the root of the current drive */
    const char *nodir[] = { "DIR nosuch" };
    ASSERT_EQ(1, adfs_commands(nodir, 1, NULL));
    ASSERT_STR_EQ("Not found\n", err_text);
    /* *DELETE, and a directory only once it is empty */
    const char *del[] = { "DELETE lth.sub" };
    ASSERT_EQ(0, adfs_commands(del, 1, NULL));
    ASSERT(!host_is_dir("lth/sub"));
    const char *full[] = { "DELETE lth" };
    ASSERT_EQ(1, adfs_commands(full, 1, NULL));
    ASSERT_STR_EQ("Dir not empty\n", err_text);
    const char *gone[] = { "DELETE lth.nothing" };
    ASSERT_EQ(1, adfs_commands(gone, 1, NULL));
    ASSERT_STR_EQ("Not found\n", err_text);
    ASSERT_EQ(0, adfs_osfile(6, "lth.expr", NULL));        /* OSFILE 6 deletes, the .inf too */
    ASSERT_EQ(1, mem.ram[0x6E]);
    ASSERT_EQ(-1, read_host("lth/expr", buf, sizeof buf));
    ASSERT_EQ(-1, read_host("lth/expr.inf", buf, sizeof buf));
    fresh();                                               /* OSARGS: the filing system is 8 */
    uint8_t fs[] = { LDA_IMM(0), LDY_IMM(0), LDX_IMM(0x70), JSR(OSARGS), STA_ZP(0x6E), RTS };
    ASSERT_EQ(0, run(fs, sizeof fs, NULL, NULL, &adfs_cfg));
    ASSERT_EQ(8, mem.ram[0x6E]);
    remove_disk();
    PASS();
}

TEST adfs_has_ten_files_open_and_one_writer_a_file(void) {
    make_disk();
    fresh();
    for (int i = 0; i < 11; i++) {
        char n[4] = { (char)('A' + i), 0 };
        put_text((uint16_t)(0x0400 + 8 * i), n);
    }
    uint8_t code[11 * 11 + 1];
    size_t n = 0;
    for (int i = 0; i < 11; i++) {
        uint8_t one[] = { LDA_IMM(0x80), LDX_IMM(8 * i), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x60 + i) };
        memcpy(code + n, one, sizeof one);
        n += sizeof one;
    }
    code[n++] = RTS;
    struct bbc_config big = adfs_cfg;
    big.adfs_sectors = 7 + 11 * 256;
    ASSERT_EQ(1, run(code, n, NULL, NULL, &big));
    ASSERT_STR_EQ("Too many open files\n", err_text);
    ASSERT_EQ(0x30, mem.ram[0x60]);
    ASSERT_EQ(0x39, mem.ram[0x69]);
    ASSERT_EQ(10u, (unsigned)m.most_open);
    ASSERT_EQ(10u, (unsigned)m.most_writing);
    /* A file open for output cannot be opened again; one open for input can, for input */
    fresh();
    write_host("A", "a", 1);
    put_text(0x0400, "A");
    uint8_t twice[] = { LDA_IMM(0x40), LDX_IMM(0), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x60),
                        LDA_IMM(0x40), LDX_IMM(0), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x61),
                        LDA_IMM(0xC0), LDX_IMM(0), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x62), RTS };
    ASSERT_EQ(1, run(twice, sizeof twice, NULL, NULL, &adfs_cfg));
    ASSERT_STR_EQ("Already open\n", err_text);
    ASSERT_EQ(0x30, mem.ram[0x60]);
    ASSERT_EQ(0x31, mem.ram[0x61]);
    fresh();
    put_text(0x0400, "A");
    uint8_t out_then_in[] = { LDA_IMM(0x80), LDX_IMM(0), LDY_IMM(0x04), JSR(OSFIND),
                              LDA_IMM(0x40), LDX_IMM(0), LDY_IMM(0x04), JSR(OSFIND), RTS };
    ASSERT_EQ(1, run(out_then_in, sizeof out_then_in, NULL, NULL, &adfs_cfg));
    ASSERT_STR_EQ("Already open\n", err_text);
    /* OSBPUT to a file open for input */
    fresh();
    put_text(0x0400, "A");
    uint8_t bput[] = { LDA_IMM(0x40), LDX_IMM(0), LDY_IMM(0x04), JSR(OSFIND), 0xA8 /* TAY */,
                       LDA_IMM('x'), JSR(OSBPUT), RTS };
    ASSERT_EQ(1, run(bput, sizeof bput, NULL, NULL, &adfs_cfg));
    ASSERT_STR_EQ("Not open for update\n", err_text);
    remove_disk();
    PASS();
}

TEST adfs_directory_holds_47_entries(void) {
    make_disk();
    char name[16];
    host_mkdir("d");
    for (int i = 0; i < 47; i++) {
        snprintf(name, sizeof name, "d/F%02d", i);
        write_host(name, "x", 1);
        snprintf(name, sizeof name, "d/F%02d.inf", i);
        write_host(name, "x 0 0\n", 6);           /* .inf files are not entries */
    }
    ASSERT_EQ(1, adfs_find(0x80, "d.NEW"));
    ASSERT_STR_EQ("Dir full\n", err_text);
    ASSERT_EQ(1, adfs_osfile(0, "d.NEW", "abc"));
    ASSERT_STR_EQ("Dir full\n", err_text);
    const char *cdir[] = { "CDIR d.sub" };
    ASSERT_EQ(1, adfs_commands(cdir, 1, NULL));
    ASSERT_STR_EQ("Dir full\n", err_text);
    ASSERT_EQ(0, adfs_find(0x80, "d.F25"));        /* a file that is there can be written */
    ASSERT_EQ(0, adfs_osfile(6, "d.F00", NULL));   /* deleting makes room */
    ASSERT_EQ(0, adfs_find(0x80, "d.NEW"));
    ASSERT_EQ(47u, (unsigned)m.adfs.most_entries);
    remove_disk();
    PASS();
}

/* On a disc without A and B, a program that opens A and B for output and writes `count` bytes
 * to A with OSGBPB from $0000: the block at $70 */
static int adfs_grow(uint32_t sectors, uint32_t count) {
    const char *gone[] = { "A", "A.inf", "B", "B.inf" };
    for (int i = 0; i < 4; i++) {
        char path[256];
        snprintf(path, sizeof path, "%s/%s", disk, gone[i]);
        remove(path);
    }
    fresh();
    put_text(0x0400, "A");
    put_text(0x0408, "B");
    uint8_t code[] = { LDA_IMM(0x80), LDX_IMM(0), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x70),
                       LDA_IMM(0x80), LDX_IMM(8), LDY_IMM(0x04), JSR(OSFIND),
                       LDA_IMM(2), LDX_IMM(0x70), LDY_IMM(0), JSR(OSGBPB), RTS };
    for (int i = 1; i < 13; i++) mem.ram[0x70 + i] = 0;
    mem.ram[0x75] = (uint8_t)count;
    mem.ram[0x76] = (uint8_t)(count >> 8);
    mem.ram[0x77] = (uint8_t)(count >> 16);
    struct bbc_config c = adfs_cfg;
    c.adfs_sectors = sectors;
    return run(code, sizeof code, NULL, NULL, &c);
}

TEST adfs_openout_reserves_64k_and_a_file_that_outgrows_it_moves(void) {
    make_disk();
    /* Two new files at once: 7 + 256 + 256 sectors */
    ASSERT_EQ(0, adfs_grow(7 + 512, 10));
    ASSERT_EQ(1, adfs_grow(7 + 511, 10));
    ASSERT_STR_EQ("Disc full\n", err_text);
    char buf[16];
    ASSERT_EQ(-1, read_host("B", buf, sizeof buf));   /* the file is not created */
    /* Closed, a file keeps its length in whole sectors: A (10 bytes) 1, B (0) none */
    ASSERT_EQ(0, adfs_grow(7 + 512, 10));
    ASSERT_EQ(0, adfs_osfile(5, "A", NULL));
    ASSERT_EQ(1u, m.adfs.in_use[0] - BBC_ADFS_FIRST_FREE);
    /* A grows to 257 sectors: B's reservation follows it, so A moves after B */
    ASSERT_EQ(0, adfs_grow(7 + 512 + 257, 65537));
    ASSERT_EQ(7u + 256 + 256 + 257, (unsigned)m.adfs.peak[0]);   /* both copies while it moves */
    ASSERT_EQ(1, adfs_grow(7 + 512 + 256, 65537));    /* 256 free, but not 257 in one run */
    ASSERT_STR_EQ("Compaction required\n", err_text);
    ASSERT_EQ(1, adfs_grow(7 + 512, 65537));          /* none free */
    ASSERT_EQ_FMT(0, strcmp("Disc full\n", err_text), "%d");
    /* An existing file opened for output keeps the space it has (here 2 sectors, then grows in place) */
    write_host("C", "0123456789", 10);
    fresh();
    struct bbc_config c = adfs_cfg;
    c.adfs_sectors = 7 + 3;                           /* C (1) and two more */
    put_text(0x0400, "C");
    uint8_t code[] = { LDA_IMM(0x80), LDX_IMM(0), LDY_IMM(0x04), JSR(OSFIND), STA_ZP(0x70),
                       LDA_IMM(2), LDX_IMM(0x70), LDY_IMM(0), JSR(OSGBPB), RTS };
    for (int i = 1; i < 13; i++) mem.ram[0x70 + i] = 0;
    mem.ram[0x76] = 3;                                /* 768 bytes: 3 sectors */
    ASSERT_EQ(0, run(code, sizeof code, NULL, NULL, &c));
    ASSERT_EQ(10u, m.adfs.in_use[0]);
    remove_disk();
    PASS();
}

TEST adfs_map_holds_80_free_spaces(void) {
    make_disk();
    char name[16];
    static char lines[90][24];
    static const char *cmds[90];
    for (int d = 0; d < 4; d++) {
        snprintf(name, sizeof name, "D%d", d);
        host_mkdir(name);
        for (int i = 0; i < 45; i++) {
            snprintf(name, sizeof name, "D%d/F%02d", d, i);
            write_host(name, "x", 1);
        }
    }
    /* Every other file deleted: each leaves a free space of its own (one sector). */
    int n = 0;
    for (int d = 0; d < 4 && n < 90; d++)
        for (int i = 0; i < 44 && n < 90; i += 2) {
            snprintf(lines[n], sizeof lines[n], "DELETE D%d.F%02d", d, i);
            cmds[n] = lines[n];
            n++;
        }
    ASSERT_EQ(1, adfs_commands(cmds, n, NULL));
    ASSERT_STR_EQ("Map full\n", err_text);
    ASSERT_EQ(BBC_ADFS_MAP, bbc_adfs_free_spaces(&m, 0));
    remove_disk();
    PASS();
}

/* OSARGS with A = 0 and Y = 0 gives the number of the filing system emulated: 4 the DFS's under
 * --bbc-fs dfs and host, 8 ADFS's under --bbc-fs adfs; --bbc-fs-number gives another, as a
 * filing system the tools do not know would (Lathe's BBCFS 3 asks it: lathe/docs/bbc.md). */
static uint8_t filing_system_number(struct bbc_config *cfg) {
    static const uint8_t fs[] = { LDA_IMM(0), LDY_IMM(0), LDX_IMM(0x70), JSR(OSARGS), STA_ZP(0x6E), RTS };
    fresh();
    mem.ram[0x6E] = 0xEE;
    if (run(fs, sizeof fs, NULL, NULL, cfg) != 0) return 0xEE;
    return mem.ram[0x6E];
}

TEST osargs_gives_the_number_of_the_filing_system(void) {
    make_disk();
    struct bbc_config host = { 0 }, dfs = { .dfs = 1 }, adfs = { .adfs = 1 };
    ASSERT_EQ(4, filing_system_number(&host));
    ASSERT_EQ(4, filing_system_number(&dfs));
    ASSERT_EQ(8, filing_system_number(&adfs));
    struct bbc_config network = { .fs_number_given = 1, .fs_number = 5 };
    ASSERT_EQ(5, filing_system_number(&network));
    struct bbc_config none = { .fs_number_given = 1, .fs_number = 0 };
    ASSERT_EQ(0, filing_system_number(&none));
    struct bbc_config adfs_as_dfs = { .adfs = 1, .fs_number_given = 1, .fs_number = 4 };
    ASSERT_EQ(4, filing_system_number(&adfs_as_dfs));
    remove_disk();
    PASS();
}

TEST without_dfs_names_and_limits_are_as_before(void) {
    make_disk();
    fresh();
    put_text(0x0400, "expr.lth");
    mem.ram[0x6F] = 0x80;
    ASSERT_EQ(0, run(find_code, sizeof find_code, NULL, NULL, NULL));
    ASSERT_EQ(0x11, mem.ram[0x6E]);
    char buf[8];
    ASSERT_EQ(0, read_host("expr.lth", buf, sizeof buf));
    ASSERT_EQ(1u, (unsigned)m.most_open);
    remove_disk();
    PASS();
}

/* ---- the Master-like machine (--bbc-model master) ---- */

/* OSBYTE 0 gives 3 (a Master 128) and its error for X = 0 is "OS 3.20"; PAGE is $0E00 unless
 * given; MOS memory is $0800 up to that PAGE. */
TEST master_os_version_and_page(void) {
    fresh();
    static const uint8_t code[] = {
        LDA_IMM(0), LDX_IMM(1), JSR(OSBYTE), STX_ZP(0x70),
        LDA_IMM(131), JSR(OSBYTE), STX_ZP(0x71), STY_ZP(0x72),
        LDA_IMM(132), JSR(OSBYTE), STX_ZP(0x73), STY_ZP(0x74),
        LDA_IMM(1), STA_ABS(0x0DFF), STA_ABS(0x0E00), RTS };
    struct bbc_config master = { .master = 1, .cmos = 1 };
    ASSERT_EQ(0, run(code, sizeof code, NULL, NULL, &master));
    ASSERT_EQ(3, mem.ram[0x70]);
    ASSERT_EQ(0x00, mem.ram[0x71]);
    ASSERT_EQ(0x0E, mem.ram[0x72]);
    ASSERT_EQ(0x7C, mem.ram[0x74]);
    ASSERT_EQ(1, (int)m.mos_writes);            /* $0DFF, not $0E00 */
    ASSERT_EQ(0x0DFF, m.first_writes[0].addr);
    struct bbc_config shadow = { .master = 1, .cmos = 1, .shadow = 1, .page = 0x1900 };
    fresh();
    ASSERT_EQ(0, run(code, sizeof code, NULL, NULL, &shadow));
    ASSERT_EQ(0x19, mem.ram[0x72]);
    ASSERT_EQ(0x80, mem.ram[0x74]);
    static const uint8_t error[] = { LDA_IMM(0), LDX_IMM(0), JSR(OSBYTE), RTS };
    fresh();
    ASSERT_EQ(1, run(error, sizeof error, NULL, NULL, &master));
    ASSERT_STR_EQ("OS 3.20\n", err_text);
    PASS();
}

/* With cmos the CPU is the emulator's 65C02 core: STZ and BRA run, and JMP ($xxFF) reads its high
 * byte from the next page. The opcodes the 65C12 lacks (the bit instructions $x7 and $xF, WAI and
 * STP) end the run as a fault, as do the NMOS's jam opcodes (a 65C12 runs them as NOPs; no tool
 * should). */
TEST master_cmos_core_and_the_opcodes_a_65c12_lacks(void) {
    fresh();
    static const uint8_t code[] = {
        LDA_IMM(0x55), STA_ZP(0x70), 0x64, 0x70,        /* STZ $70 */
        0x80, 0x02, LDA_IMM(0xEE),                      /* BRA over an LDA */
        STA_ZP(0x71),
        LDA_IMM(LO(PAGE + 0x20)), STA_ABS(0x10FF), LDA_IMM(HI(PAGE + 0x20)), STA_ABS(0x1100),
        LDA_IMM(0x00), STA_ABS(0x1000), JMP_IND(0x10FF) };
    uint8_t prog[0x30];
    memset(prog, NOP, sizeof prog);
    memcpy(prog, code, sizeof code);
    prog[0x20] = RTS;
    struct bbc_config master = { .master = 1, .cmos = 1 };
    ASSERT_EQ(0, run(prog, sizeof prog, NULL, NULL, &master));
    ASSERT_EQ(0x00, mem.ram[0x70]);
    ASSERT_EQ(0x55, mem.ram[0x71]);
    static const uint8_t lacks[] = { 0x07, 0x0F, 0x87, 0xFF, 0xCB, 0xDB, 0x02, 0x12 };
    for (unsigned i = 0; i < sizeof lacks; i++) {
        uint8_t bad[] = { NOP, lacks[i], 0x70, 0x00 };
        fresh();
        ASSERT_EQ(1, run(bad, sizeof bad, NULL, NULL, &master));
        ASSERT_EQ(BBC_END_FAULT, m.end);
        ASSERT(strstr(m.fault, (lacks[i] & 0x0F) == 0x02 ? "jammed" : "65C12") != NULL);
    }
    PASS();
}

/* ---- the trap and the checks ---- */

TEST jumping_straight_to_a_trap_is_a_fault(void) {
    fresh();
    static const uint8_t code[] = { LDA_IMM('x'), JMP(BBC_MOS_T_WRCH) };
    ASSERT_EQ(1, RUN(code, NULL, NULL));
    ASSERT_EQ(BBC_END_FAULT, m.end);
    ASSERT_EQ(0, (int)out_len);
    ASSERT(strstr(m.fault, "trap") != NULL);
    PASS();
}

TEST a_jam_opcode_is_a_fault(void) {
    fresh();
    static const uint8_t code[] = { NOP, 0x02 };
    ASSERT_EQ(1, RUN(code, NULL, NULL));
    ASSERT_EQ(BBC_END_FAULT, m.end);
    ASSERT(strstr(m.fault, "jammed") != NULL);
    PASS();
}

TEST writes_to_mos_memory_are_counted(void) {
    fresh();
    static const uint8_t code[] = {
        LDA_IMM(1), STA_ZP(0x70), STA_ZP(0x8F), STA_ZP(0xF4), STA_ZP(0xA8), STA_ZP(0xF6),   /* allowed */
        STA_ABS(0x0200), STA_ABS(0x02A5), STA_ABS(0x0400), STA_ABS(0x07FF), STA_ABS(0x1900),
        STA_ZP(0x90), STA_ZP(0xFF), STA_ABS(0x0236), STA_ABS(0x03FF), STA_ABS(0x0800), STA_ABS(0x18FF),
        LDA_IMM(15), STA_ZP(0xF4), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(6, (int)m.mos_writes);
    ASSERT_EQ(0x0090, m.first_writes[0].addr);
    ASSERT_EQ(PAGE + 27, m.first_writes[0].pc);
    ASSERT_EQ(0x18FF, m.first_writes[5].addr);
    struct bbc_config strict = { .strict = 1 };
    fresh();
    ASSERT_EQ(1, run(code, sizeof code, NULL, NULL, &strict));
    ASSERT_EQ(BBC_END_STRICT, m.end);
    ASSERT_EQ(1, (int)m.mos_writes);
    PASS();
}

TEST romsel_differing_from_f4_at_a_mos_call_is_counted(void) {
    fresh();
    static const uint8_t code[] = {
        LDA_IMM(3), STA_ABS(0xFE30), LDA_IMM('a'), JSR(OSWRCH),   /* $F4 is 15 */
        LDA_IMM(3), STA_ZP(0xF4), LDA_IMM('b'), JSR(OSWRCH),       /* agreed */
        LDA_IMM(15), STA_ZP(0xF4), STA_ABS(0xFE30), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(1, (int)m.romsel_mismatches);
    ASSERT_EQ(OSWRCH, m.first_mismatches[0].addr);
    ASSERT_STR_EQ("ab", out_text);
    struct bbc_config strict = { .strict = 1 };
    fresh();
    ASSERT_EQ(1, run(code, sizeof code, NULL, NULL, &strict));
    ASSERT_EQ(BBC_END_STRICT, m.end);
    ASSERT_EQ(0, (int)out_len);
    PASS();
}

TEST mos_internal_calls_are_not_checked(void) {
    fresh();
    /* OSNEWL calls OSWRCH from inside the MOS; a service call writes $F4 and ROMSEL */
    counting_rom();
    static const uint8_t code[] = { JSR(OSNEWL), LDA_IMM(143), LDX_IMM(9), LDY_IMM(0), JSR(OSBYTE), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(0, (int)m.romsel_mismatches);
    ASSERT_EQ(0, (int)m.mos_writes);
    PASS();
}

TEST the_cycle_cap_ends_the_run_with_status_2(void) {
    fresh();
    static const uint8_t code[] = { JMP(PAGE) };
    struct bbc_config cfg = { 0 };
    FILE *dn = fopen("/dev/null", "w");
    cfg.out = cfg.err = dn;
    cfg.entry = PAGE;
    bbc_machine_init(&m, &cfg, &mem, NULL);
    memcpy(mem.ram + PAGE, code, sizeof code);
    ASSERT_EQ(2, bbc_machine_run(&m, 1000));
    ASSERT_EQ(BBC_END_CAP, m.end);
    ASSERT(clockticks6502 >= 1000 && clockticks6502 < 1010);
    fclose(dn);
    PASS();
}

/* ---- the module through the machine ---- */

TEST a_module_in_slot_4_switches_banks_under_the_cpu(void) {
    fresh();
    bbc_module_init(&mod_chip, &mod, BBC_MODULE_CC128, 0, 0);
    mem.kind[4] = BBC_SLOT_MODULE;
    mod.data[3 * BBC_MODULE_BANK_SIZE + 0x100] = 0x33;
    static const uint8_t code[] = {
        LDA_IMM(4), STA_ZP(0xF4), STA_ABS(0xFE30),
        LDA_ABS(0xBF80), LDA_ABS(0x8100), STA_ZP(0x70), LDA_ABS(0xBFE0),
        LDA_IMM(15), STA_ZP(0xF4), STA_ABS(0xFE30), RTS };
    ASSERT_EQ(0, RUN(code, NULL, NULL));
    ASSERT_EQ(0x33, mem.ram[0x70]);
    ASSERT_EQ(2, (int)mod.switches);
    ASSERT_EQ(0, mod.bank);
    mem.kind[4] = BBC_SLOT_EMPTY;
    PASS();
}

SUITE(bbc_mos_suite) {
    RUN_TEST(reset_sets_the_vectors_and_returns_with_status_0);
    RUN_TEST(reset_fills_the_rom_type_table_from_the_headers);
    RUN_TEST(oswrch_osasci_osnewl_write_bytes_unchanged);
    RUN_TEST(a_replaced_vector_is_used_and_can_chain);
    RUN_TEST(osrdch_reads_standard_input_then_escape_at_its_end);
    RUN_TEST(osbyte_version_page_himem_and_high_address);
    RUN_TEST(model_b_os_version_and_himem_by_mode);
    RUN_TEST(writes_to_the_screen_are_counted);
    RUN_TEST(osbyte_252_reads_and_writes_the_current_language);
    RUN_TEST(osbyte_0_with_x_0_is_an_error_through_brkv);
    RUN_TEST(osbyte_126_acknowledges_escape);
    RUN_TEST(osbyte_unknown_returns_x_ff_with_v_set);
    RUN_TEST(osbyte_143_offers_a_service_call_to_the_roms);
    RUN_TEST(osbyte_142_enters_a_language_and_its_return_ends_the_run);
    RUN_TEST(osword_0_reads_a_line);
    RUN_TEST(osword_1_reads_the_clock_and_2_sets_it);
    RUN_TEST(a_program_brk_goes_through_brkv_with_fd_fe_set);
    RUN_TEST(the_default_brkv_prints_the_message_and_ends_with_status_1);
    RUN_TEST(an_error_in_a_rom_selects_the_language_and_is_reported_from_the_rom);
    RUN_TEST(oscli_unknown_command_is_bad_command);
    RUN_TEST(oscli_offers_service_call_4_from_slot_15_down);
    RUN_TEST(oscli_help_offers_service_call_9_with_y_at_its_argument);
    RUN_TEST(more_commands_run_in_turn_after_each_returns);
    RUN_TEST(oscli_run_and_star_name_run_a_file_from_disk);
    RUN_TEST(oscli_run_passes_the_command_tail_to_osargs);
    RUN_TEST(oscli_save_and_load);
    RUN_TEST(osfile_save_load_info_and_delete);
    RUN_TEST(file_names_with_slash_or_dotdot_are_refused);
    RUN_TEST(a_leading_dot_slash_names_the_disk_itself);
    RUN_TEST(file_calls_without_a_disk_raise_an_error);
    RUN_TEST(osfind_bget_bput_copy_a_file_and_report_eof);
    RUN_TEST(osfind_missing_file_returns_0_and_bget_twice_at_eof_is_an_error);
    RUN_TEST(osargs_reads_and_writes_ptr_and_reads_ext);
    RUN_TEST(osgbpb_reads_and_writes_blocks);
    RUN_TEST(dfs_names_are_checked_as_the_dfs_checks_them);
    RUN_TEST(dfs_files_are_kept_as_dir_dot_name_and_found_in_any_case);
    RUN_TEST(dfs_has_five_files_open_at_most);
    RUN_TEST(dfs_catalogue_holds_31_files_a_drive);
    RUN_TEST(adfs_names_are_checked_as_adfs_checks_them);
    RUN_TEST(adfs_directories_are_host_directories_and_names_match_in_any_case);
    RUN_TEST(adfs_has_ten_files_open_and_one_writer_a_file);
    RUN_TEST(adfs_directory_holds_47_entries);
    RUN_TEST(adfs_openout_reserves_64k_and_a_file_that_outgrows_it_moves);
    RUN_TEST(adfs_map_holds_80_free_spaces);
    RUN_TEST(osargs_gives_the_number_of_the_filing_system);
    RUN_TEST(without_dfs_names_and_limits_are_as_before);
    RUN_TEST(master_os_version_and_page);
    RUN_TEST(master_cmos_core_and_the_opcodes_a_65c12_lacks);
    RUN_TEST(jumping_straight_to_a_trap_is_a_fault);
    RUN_TEST(a_jam_opcode_is_a_fault);
    RUN_TEST(writes_to_mos_memory_are_counted);
    RUN_TEST(romsel_differing_from_f4_at_a_mos_call_is_counted);
    RUN_TEST(mos_internal_calls_are_not_checked);
    RUN_TEST(the_cycle_cap_ends_the_run_with_status_2);
    RUN_TEST(a_module_in_slot_4_switches_banks_under_the_cpu);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(bbc_mos_suite);
    GREATEST_MAIN_END();
}
