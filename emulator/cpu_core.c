// Fake6502 CPU emulator core v1.1
// (c)2011 Mike Chambers (miker00lz@gmail.com)
// Released into the public domain

#include "cpu_core.h"
#include <stddef.h>

//6502 defines
#define UNDOCUMENTED //when this is defined, undocumented opcodes are handled.
                     //otherwise, they're simply treated as NOPs.

#define NES_CPU      //when this is defined, the binary-coded decimal (BCD)
                     //status flag is not honored by ADC and SBC. the 2A03
                     //CPU in the Nintendo Entertainment System does not
                     //support BCD operation.

#define FLAG_CARRY     0x01
#define FLAG_ZERO      0x02
#define FLAG_INTERRUPT 0x04
#define FLAG_DECIMAL   0x08
#define FLAG_BREAK     0x10
#define FLAG_CONSTANT  0x20
#define FLAG_OVERFLOW  0x40
#define FLAG_SIGN      0x80

#define BASE_STACK     0x100

#define saveaccum(n) a = (uint8_t)((n) & 0x00FF)


//flag modifier macros
#define setcarry() status |= FLAG_CARRY
#define clearcarry() status &= (~FLAG_CARRY)
#define setzero() status |= FLAG_ZERO
#define clearzero() status &= (~FLAG_ZERO)
#define setinterrupt() status |= FLAG_INTERRUPT
#define clearinterrupt() status &= (~FLAG_INTERRUPT)
#define setdecimal() status |= FLAG_DECIMAL
#define cleardecimal() status &= (~FLAG_DECIMAL)
#define setoverflow() status |= FLAG_OVERFLOW
#define clearoverflow() status &= (~FLAG_OVERFLOW)
#define setsign() status |= FLAG_SIGN
#define clearsign() status &= (~FLAG_SIGN)


//flag calculation macros
#define zerocalc(n) {\
    if ((n) & 0x00FF) clearzero();\
        else setzero();\
}

#define signcalc(n) {\
    if ((n) & 0x0080) setsign();\
        else clearsign();\
}

#define carrycalc(n) {\
    if ((n) & 0xFF00) setcarry();\
        else clearcarry();\
}

#define overflowcalc(n, m, o) { /* n = result, m = accumulator, o = memory */ \
    if (((n) ^ (uint16_t)(m)) & ((n) ^ (o)) & 0x0080) setoverflow();\
        else clearoverflow();\
}


//6502 CPU registers
uint16_t pc;
uint8_t sp, a, x, y, status;

//CPU variant selection. Default = NMOS (legacy Fake6502 dispatch).
int cpu_variant = CPU_NMOS;

/* 65C02 WAI / STP pending flags. wai_pending pauses step6502 until an
 * IRQ/NMI clears it; stp_pending pauses indefinitely until reset6502. */
static int wai_pending = 0;
static int stp_pending = 0;

/* Optional bus-transaction taps. Default NULL; the
 * per-access overhead is a null check. */
void (*cpu_bus_read_tap)(uint16_t addr, uint8_t data) = NULL;
void (*cpu_bus_write_tap)(uint16_t addr, uint8_t data) = NULL;

/* Optional external memory hooks (the bus-model machines). When set, the CPU dispatch
 * routes every memory access through these instead of the host's
 * read6502/write6502. The wendy2c bus model installs these. */
uint8_t (*cpu_external_read)(uint16_t addr) = NULL;
void    (*cpu_external_write)(uint16_t addr, uint8_t data) = NULL;

static inline uint8_t cpu_read(uint16_t addr) {
    uint8_t v = cpu_external_read ? cpu_external_read(addr) : read6502(addr);
    if (cpu_bus_read_tap) cpu_bus_read_tap(addr, v);
    return v;
}

static inline void cpu_write(uint16_t addr, uint8_t v) {
    if (cpu_external_write) cpu_external_write(addr, v);
    else write6502(addr, v);
    if (cpu_bus_write_tap) cpu_bus_write_tap(addr, v);
}

int cpu_wai_pending(void) { return wai_pending; }
void cpu_clear_wai(void) { wai_pending = 0; }
int cpu_stp_pending(void) { return stp_pending; }


//helper variables
uint32_t instructions = 0; //keep track of total instructions executed
uint64_t clockticks6502 = 0, clockgoal6502 = 0;
uint16_t oldpc, ea, reladdr, value, result;
uint8_t opcode, oldstatus;

//a few general functions used by various other functions
void push16(uint16_t pushval) {
    cpu_write(BASE_STACK + sp, (pushval >> 8) & 0xFF);
    cpu_write(BASE_STACK + ((sp - 1) & 0xFF), pushval & 0xFF);
    sp -= 2;
}

void push8(uint8_t pushval) {
    cpu_write(BASE_STACK + sp--, pushval);
}

uint16_t pull16() {
    uint16_t temp16;
    temp16 = cpu_read(BASE_STACK + ((sp + 1) & 0xFF)) | ((uint16_t)cpu_read(BASE_STACK + ((sp + 2) & 0xFF)) << 8);
    sp += 2;
    return(temp16);
}

uint8_t pull8() {
    return (cpu_read(BASE_STACK + ++sp));
}

void reset6502() {
    pc = (uint16_t)cpu_read(0xFFFC) | ((uint16_t)cpu_read(0xFFFD) << 8);
    a = 0;
    x = 0;
    y = 0;
    sp = 0xFD;
    status |= FLAG_CONSTANT;
    wai_pending = 0;
    stp_pending = 0;
}


/* Active dispatch tables: pointers set by step6502/exec6502 to one of
 * the addrtable_nmos / addrtable_65c02 etc. arrays below, based on
 * cpu_variant. The deep helpers (getvalue/putvalue) read addrtable[]
 * through this pointer so the same "is this opcode accumulator-mode?"
 * check works for either variant. */
static void (**addrtable)();
static void (**optable)();
static const uint32_t *ticktable;
uint8_t penaltyop, penaltyaddr;

//addressing mode functions, calculates effective addresses
static void imp() { //implied
}

static void acc() { //accumulator
}

static void imm() { //immediate
    ea = pc++;
}

static void zp() { //zero-page
    ea = (uint16_t)cpu_read((uint16_t)pc++);
}

static void zpx() { //zero-page,X
    ea = ((uint16_t)cpu_read((uint16_t)pc++) + (uint16_t)x) & 0xFF; //zero-page wraparound
}

static void zpy() { //zero-page,Y
    ea = ((uint16_t)cpu_read((uint16_t)pc++) + (uint16_t)y) & 0xFF; //zero-page wraparound
}

static void rel() { //relative for branch ops (8-bit immediate value, sign-extended)
    reladdr = (uint16_t)cpu_read(pc++);
    if (reladdr & 0x80) reladdr |= 0xFF00;
}

static void abso() { //absolute
    ea = (uint16_t)cpu_read(pc) | ((uint16_t)cpu_read(pc+1) << 8);
    pc += 2;
}

static void absx() { //absolute,X
    uint16_t startpage;
    ea = ((uint16_t)cpu_read(pc) | ((uint16_t)cpu_read(pc+1) << 8));
    startpage = ea & 0xFF00;
    ea += (uint16_t)x;

    if (startpage != (ea & 0xFF00)) { //one cycle penlty for page-crossing on some opcodes
        penaltyaddr = 1;
    }

    pc += 2;
}

static void absy() { //absolute,Y
    uint16_t startpage;
    ea = ((uint16_t)cpu_read(pc) | ((uint16_t)cpu_read(pc+1) << 8));
    startpage = ea & 0xFF00;
    ea += (uint16_t)y;

    if (startpage != (ea & 0xFF00)) { //one cycle penlty for page-crossing on some opcodes
        penaltyaddr = 1;
    }

    pc += 2;
}

static void ind() { //indirect (NMOS: with page-wrap bug on high-byte read)
    uint16_t eahelp, eahelp2;
    eahelp = (uint16_t)cpu_read(pc) | (uint16_t)((uint16_t)cpu_read(pc+1) << 8);
    eahelp2 = (eahelp & 0xFF00) | ((eahelp + 1) & 0x00FF); //replicate 6502 page-boundary wraparound bug
    ea = (uint16_t)cpu_read(eahelp) | ((uint16_t)cpu_read(eahelp2) << 8);
    pc += 2;
}

static void ind_65c02() { //indirect (65C02: no page-wrap bug; reads eahelp+1 normally)
    uint16_t eahelp;
    eahelp = (uint16_t)cpu_read(pc) | (uint16_t)((uint16_t)cpu_read(pc+1) << 8);
    ea = (uint16_t)cpu_read(eahelp) | ((uint16_t)cpu_read(eahelp + 1) << 8);
    pc += 2;
}

static void ind_zp() { //(zp) indirect: 65C02 LDA (zp), STA (zp), etc.
    uint8_t zp = cpu_read(pc++);
    /* zero-page wrap-around on the +1 fetch */
    ea = (uint16_t)cpu_read(zp) | ((uint16_t)cpu_read((uint8_t)(zp + 1)) << 8);
}

static void ind_absx() { //(abs,X) for 65C02 JMP -- table pre-index then dereference
    uint16_t base = (uint16_t)cpu_read(pc) | ((uint16_t)cpu_read(pc+1) << 8);
    base += (uint16_t)x;
    ea = (uint16_t)cpu_read(base) | ((uint16_t)cpu_read(base + 1) << 8);
    pc += 2;
}

static void indx() { // (indirect,X)
    uint16_t eahelp;
    eahelp = (uint16_t)(((uint16_t)cpu_read(pc++) + (uint16_t)x) & 0xFF); //zero-page wraparound for table pointer
    ea = (uint16_t)cpu_read(eahelp & 0x00FF) | ((uint16_t)cpu_read((eahelp+1) & 0x00FF) << 8);
}

static void indy() { // (indirect),Y
    uint16_t eahelp, eahelp2, startpage;
    eahelp = (uint16_t)cpu_read(pc++);
    eahelp2 = (eahelp & 0xFF00) | ((eahelp + 1) & 0x00FF); //zero-page wraparound
    ea = (uint16_t)cpu_read(eahelp) | ((uint16_t)cpu_read(eahelp2) << 8);
    startpage = ea & 0xFF00;
    ea += (uint16_t)y;

    if (startpage != (ea & 0xFF00)) { //one cycle penlty for page-crossing on some opcodes
        penaltyaddr = 1;
    }
}

static uint16_t getvalue() {
    if (addrtable[opcode] == acc) return((uint16_t)a);
        else return((uint16_t)cpu_read(ea));
}

static uint16_t getvalue16() {
    return((uint16_t)cpu_read(ea) | ((uint16_t)cpu_read(ea+1) << 8));
}

static void putvalue(uint16_t saveval) {
    if (addrtable[opcode] == acc) a = (uint8_t)(saveval & 0x00FF);
        else cpu_write(ea, (saveval & 0x00FF));
}


//instruction handler functions

/* NMOS ADC: full BCD when D=1. NMOS quirk: in decimal mode, N/Z flags
 * reflect the BINARY intermediate result, not the BCD-adjusted one.
 * V is from the binary path in either mode. */
static void adc() {
    penaltyop = 1;
    value = getvalue();
    uint8_t carry_in = (status & FLAG_CARRY) ? 1 : 0;

    if (status & FLAG_DECIMAL) {
        /* Binary intermediate drives N/Z and V on NMOS. */
        uint16_t bin = (uint16_t)a + value + carry_in;
        if (((a ^ value) & 0x80) == 0 && ((a ^ bin) & 0x80)) setoverflow();
        else clearoverflow();
        zerocalc(bin);
        signcalc(bin);

        /* BCD adjust. */
        uint16_t lo = (a & 0x0F) + (value & 0x0F) + carry_in;
        uint16_t hi = (a >> 4) + (value >> 4);
        if (lo > 9) { lo -= 10; hi++; }
        if (hi > 9) { hi -= 10; setcarry(); } else { clearcarry(); }
        a = (uint8_t)(((hi & 0x0F) << 4) | (lo & 0x0F));
    } else {
        result = (uint16_t)a + value + carry_in;
        carrycalc(result);
        zerocalc(result);
        overflowcalc(result, a, value);
        signcalc(result);
        saveaccum(result);
    }
}

/* 65C02 ADC: full BCD with N/Z computed from the BCD-adjusted result
 * (NMOS computes N/Z from the binary intermediate, which is wrong in
 * decimal mode). V flag still comes from the binary path. +1 cycle in
 * decimal mode. */
static void adc_65c02() {
    penaltyop = 1;
    uint8_t carry_in = (status & FLAG_CARRY) ? 1 : 0;
    value = getvalue();

    if (status & FLAG_DECIMAL) {
        /* V flag computed from binary intermediate. */
        uint16_t bin = (uint16_t)a + value + carry_in;
        if (((a ^ value) & 0x80) == 0 && ((a ^ bin) & 0x80)) setoverflow();
        else clearoverflow();

        uint16_t lo = (a & 0x0F) + (value & 0x0F) + carry_in;
        uint16_t hi = (a >> 4) + (value >> 4);
        if (lo > 9) { lo -= 10; hi++; }
        if (hi > 9) { hi -= 10; setcarry(); } else { clearcarry(); }
        uint8_t res = (uint8_t)(((hi & 0x0F) << 4) | (lo & 0x0F));

        if (res == 0) setzero(); else clearzero();
        if (res & 0x80) setsign(); else clearsign();

        a = res;
        clockticks6502++;
    } else {
        result = (uint16_t)a + value + (uint16_t)(status & FLAG_CARRY);
        carrycalc(result);
        zerocalc(result);
        overflowcalc(result, a, value);
        signcalc(result);
        saveaccum(result);
    }
}

static void and() {
    penaltyop = 1;
    value = getvalue();
    result = (uint16_t)a & value;

    zerocalc(result);
    signcalc(result);

    saveaccum(result);
}

static void asl() {
    value = getvalue();
    result = value << 1;

    carrycalc(result);
    zerocalc(result);
    signcalc(result);

    putvalue(result);
}

static void bcc() {
    if ((status & FLAG_CARRY) == 0) {
        oldpc = pc;
        pc += reladdr;
        if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2; //check if jump crossed a page boundary
            else clockticks6502++;
    }
}

static void bcs() {
    if ((status & FLAG_CARRY) == FLAG_CARRY) {
        oldpc = pc;
        pc += reladdr;
        if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2; //check if jump crossed a page boundary
            else clockticks6502++;
    }
}

static void beq() {
    if ((status & FLAG_ZERO) == FLAG_ZERO) {
        oldpc = pc;
        pc += reladdr;
        if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2; //check if jump crossed a page boundary
            else clockticks6502++;
    }
}

static void bit() {
    value = getvalue();
    result = (uint16_t)a & value;

    zerocalc(result);
    status = (status & 0x3F) | (uint8_t)(value & 0xC0);
}

static void bmi() {
    if ((status & FLAG_SIGN) == FLAG_SIGN) {
        oldpc = pc;
        pc += reladdr;
        if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2; //check if jump crossed a page boundary
            else clockticks6502++;
    }
}

static void bne() {
    if ((status & FLAG_ZERO) == 0) {
        oldpc = pc;
        pc += reladdr;
        if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2; //check if jump crossed a page boundary
            else clockticks6502++;
    }
}

static void bpl() {
    if ((status & FLAG_SIGN) == 0) {
        oldpc = pc;
        pc += reladdr;
        if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2; //check if jump crossed a page boundary
            else clockticks6502++;
    }
}

static void brk_insn() {
    pc++;
    push16(pc); //push next instruction address onto stack
    push8(status | FLAG_BREAK); //push CPU status to stack
    setinterrupt(); //set interrupt flag
    pc = (uint16_t)cpu_read(0xFFFE) | ((uint16_t)cpu_read(0xFFFF) << 8);
}

static void brk_insn_65c02() { /* 65C02: clears D after pushing status */
    pc++;
    push16(pc);
    push8(status | FLAG_BREAK);
    setinterrupt();
    cleardecimal();
    pc = (uint16_t)cpu_read(0xFFFE) | ((uint16_t)cpu_read(0xFFFF) << 8);
}

static void bvc() {
    if ((status & FLAG_OVERFLOW) == 0) {
        oldpc = pc;
        pc += reladdr;
        if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2; //check if jump crossed a page boundary
            else clockticks6502++;
    }
}

static void bvs() {
    if ((status & FLAG_OVERFLOW) == FLAG_OVERFLOW) {
        oldpc = pc;
        pc += reladdr;
        if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2; //check if jump crossed a page boundary
            else clockticks6502++;
    }
}

static void clc() {
    clearcarry();
}

static void cld() {
    cleardecimal();
}

static void cli() {
    clearinterrupt();
}

static void clv() {
    clearoverflow();
}

static void cmp() {
    penaltyop = 1;
    value = getvalue();
    result = (uint16_t)a - value;

    if (a >= (uint8_t)(value & 0x00FF)) setcarry();
        else clearcarry();
    if (a == (uint8_t)(value & 0x00FF)) setzero();
        else clearzero();
    signcalc(result);
}

static void cpx() {
    value = getvalue();
    result = (uint16_t)x - value;

    if (x >= (uint8_t)(value & 0x00FF)) setcarry();
        else clearcarry();
    if (x == (uint8_t)(value & 0x00FF)) setzero();
        else clearzero();
    signcalc(result);
}

static void cpy() {
    value = getvalue();
    result = (uint16_t)y - value;

    if (y >= (uint8_t)(value & 0x00FF)) setcarry();
        else clearcarry();
    if (y == (uint8_t)(value & 0x00FF)) setzero();
        else clearzero();
    signcalc(result);
}

static void dec() {
    value = getvalue();
    result = value - 1;

    zerocalc(result);
    signcalc(result);

    putvalue(result);
}

static void dex() {
    x--;

    zerocalc(x);
    signcalc(x);
}

static void dey() {
    y--;

    zerocalc(y);
    signcalc(y);
}

static void eor() {
    penaltyop = 1;
    value = getvalue();
    result = (uint16_t)a ^ value;

    zerocalc(result);
    signcalc(result);

    saveaccum(result);
}

static void inc() {
    value = getvalue();
    result = value + 1;

    zerocalc(result);
    signcalc(result);

    putvalue(result);
}

static void inx() {
    x++;

    zerocalc(x);
    signcalc(x);
}

static void iny() {
    y++;

    zerocalc(y);
    signcalc(y);
}

static void jmp() {
    pc = ea;
}

static void jsr() {
    push16(pc - 1);
    pc = ea;
}

static void lda() {
    penaltyop = 1;
    value = getvalue();
    a = (uint8_t)(value & 0x00FF);

    zerocalc(a);
    signcalc(a);
}

static void ldx() {
    penaltyop = 1;
    value = getvalue();
    x = (uint8_t)(value & 0x00FF);

    zerocalc(x);
    signcalc(x);
}

static void ldy() {
    penaltyop = 1;
    value = getvalue();
    y = (uint8_t)(value & 0x00FF);

    zerocalc(y);
    signcalc(y);
}

static void lsr() {
    value = getvalue();
    result = value >> 1;

    if (value & 1) setcarry();
        else clearcarry();
    zerocalc(result);
    signcalc(result);

    putvalue(result);
}

static void nop() {
    switch (opcode) {
        case 0x1C:
        case 0x3C:
        case 0x5C:
        case 0x7C:
        case 0xDC:
        case 0xFC:
            penaltyop = 1;
            break;
    }
}

static void ora() {
    penaltyop = 1;
    value = getvalue();
    result = (uint16_t)a | value;

    zerocalc(result);
    signcalc(result);

    saveaccum(result);
}

static void pha() {
    push8(a);
}

static void php() {
    push8(status | FLAG_BREAK);
}

static void pla() {
    a = pull8();

    zerocalc(a);
    signcalc(a);
}

static void plp() {
    /* Real 6502: B flag (bit 4) is not a physical CPU bit; the pulled
     * value's bit 4 is ignored. Bit 5 (constant) always reads as 1. */
    status = (pull8() & ~FLAG_BREAK) | FLAG_CONSTANT;
}

static void rol() {
    value = getvalue();
    result = (value << 1) | (status & FLAG_CARRY);

    carrycalc(result);
    zerocalc(result);
    signcalc(result);

    putvalue(result);
}

static void ror() {
    value = getvalue();
    result = (value >> 1) | ((status & FLAG_CARRY) << 7);

    if (value & 1) setcarry();
        else clearcarry();
    zerocalc(result);
    signcalc(result);

    putvalue(result);
}

static void rti() {
    /* Same B/constant treatment as PLP. */
    status = (pull8() & ~FLAG_BREAK) | FLAG_CONSTANT;
    value = pull16();
    pc = value;
}

static void rts() {
    value = pull16();
    pc = value + 1;
}

/* NMOS SBC: full BCD when D=1. NMOS quirks: in decimal mode, N/Z
 * reflect the binary intermediate; V is from binary in either mode. */
static void sbc() {
    penaltyop = 1;
    uint16_t mval = getvalue();
    uint8_t carry_in = (status & FLAG_CARRY) ? 1 : 0;

    if (status & FLAG_DECIMAL) {
        uint16_t bin_m = mval ^ 0x00FF;
        uint16_t bin = (uint16_t)a + bin_m + carry_in;
        if (((a ^ bin_m) & 0x80) == 0 && ((a ^ bin) & 0x80)) setoverflow();
        else clearoverflow();
        zerocalc(bin);
        signcalc(bin);

        int16_t lo = (a & 0x0F) - (mval & 0x0F) - (1 - carry_in);
        int16_t hi = (a >> 4) - (mval >> 4);
        if (lo < 0) { lo += 10; hi--; }
        if (hi < 0) { hi += 10; clearcarry(); } else { setcarry(); }
        a = (uint8_t)(((hi & 0x0F) << 4) | (lo & 0x0F));
    } else {
        value = mval ^ 0x00FF;
        result = (uint16_t)a + value + carry_in;
        carrycalc(result);
        zerocalc(result);
        overflowcalc(result, a, value);
        signcalc(result);
        saveaccum(result);
    }
}

/* ---- 65C02 new opcodes (group A: bra/phx/phy/plx/ply/stz/inc-a/dec-a) ---- */

static void bra() {  /* unconditional relative branch (1 cycle base + page-cross penalty) */
    oldpc = pc;
    pc += reladdr;
    if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2;
    else clockticks6502++;
}

static void phx() { push8(x); }
static void phy() { push8(y); }

static void plx() {
    x = pull8();
    zerocalc(x);
    signcalc(x);
}

static void ply() {
    y = pull8();
    zerocalc(y);
    signcalc(y);
}

/* STZ: store zero. Uses putvalue() so it works with zp/zpx/abso/absx
 * exactly as STA does, but writes 0 instead of A. The 65C02 addrtable
 * slots for STZ are zp/zpx/abso/absx (not acc), so putvalue() takes the
 * memory-write branch. */
static void stz() { putvalue(0); }

/* TRB / TSB: test-and-clear / test-and-set bits using A as the mask.
 * Z is set from (A & M) BEFORE the write, exactly as the W65C02S
 * datasheet specifies. */
static void trb() {
    value = getvalue();
    if ((a & value) == 0) setzero(); else clearzero();
    putvalue(value & (uint16_t)(~a & 0xFF));
}

static void tsb() {
    value = getvalue();
    if ((a & value) == 0) setzero(); else clearzero();
    putvalue(value | a);
}

/* 65C02 BIT immediate ($89): only Z is affected; N and V are
 * unchanged. (The standard `bit` handler used by zp/abs/zpx/abs,X
 * modes copies bits 7 and 6 of the operand into N and V, which is
 * wrong for the immediate form.) */
static void bit_imm() {
    value = getvalue();
    result = (uint16_t)a & value;
    zerocalc(result);
    /* N and V intentionally untouched. */
}

/* RMB n,zp / SMB n,zp: bit-clear/bit-set on a zero-page byte. Bit
 * number (0..7) is encoded in opcode bits 4-6. RMB = $X7 with X in
 * 0..7; SMB = $X7 with X in 8..F. addrtable[opcode] is zp so ea = the
 * zp address. 5 cycles. */
static void rmb() {
    uint8_t bit = (opcode >> 4) & 7;
    uint8_t v = cpu_read(ea);
    v &= (uint8_t)~(1u << bit);
    cpu_write(ea, v);
}

static void smb() {
    uint8_t bit = (opcode >> 4) & 7;
    uint8_t v = cpu_read(ea);
    v |= (uint8_t)(1u << bit);
    cpu_write(ea, v);
}

/* BBR n,zp,rel / BBS n,zp,rel: 3-byte branch-on-bit. addrtable is zp
 * so ea = zp address; we read the rel byte ourselves. 5 cycle base
 * + branch-taken penalty handled inline. */
static void bbr() {
    uint8_t r = cpu_read(pc++);
    uint8_t bit = (opcode >> 4) & 7;
    uint8_t v = cpu_read(ea);
    if ((v & (uint8_t)(1u << bit)) == 0) {
        oldpc = pc;
        pc += (int8_t)r;
        if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2;
        else clockticks6502++;
    }
}

static void bbs() {
    uint8_t r = cpu_read(pc++);
    uint8_t bit = (opcode >> 4) & 7;
    uint8_t v = cpu_read(ea);
    if ((v & (uint8_t)(1u << bit)) != 0) {
        oldpc = pc;
        pc += (int8_t)r;
        if ((oldpc & 0xFF00) != (pc & 0xFF00)) clockticks6502 += 2;
        else clockticks6502++;
    }
}

/* WAI / STP. step6502/exec6502 read these; reset6502 clears both;
 * irq6502/nmi6502 clear wai_pending. Declared at file scope above (with
 * the other CPU globals) so reset6502 can see them. */
static void wai(void) { wai_pending = 1; }
static void stp(void) { stp_pending = 1; }

/* 65C02 INC A / DEC A: re-use the existing inc / dec handlers with the
 * acc addressing mode (addrtable_65c02[$1A] = acc / [$3A] = acc).
 * No separate handler needed -- getvalue/putvalue branch on
 * addrtable[opcode]==acc and operate on A. */

/* ----------------------------------------------------------------- */

/* 65C02 SBC: full BCD with N/Z from the BCD-adjusted result. */
static void sbc_65c02() {
    penaltyop = 1;
    uint16_t mval = getvalue();
    uint8_t carry_in = (status & FLAG_CARRY) ? 1 : 0;

    if (status & FLAG_DECIMAL) {
        /* V flag from binary path: A + ~M + C_in. */
        uint16_t bin_m = mval ^ 0x00FF;
        uint16_t bin = (uint16_t)a + bin_m + carry_in;
        if (((a ^ bin_m) & 0x80) == 0 && ((a ^ bin) & 0x80)) setoverflow();
        else clearoverflow();

        int16_t lo = (a & 0x0F) - (mval & 0x0F) - (1 - carry_in);
        int16_t hi = (a >> 4) - (mval >> 4);
        if (lo < 0) { lo += 10; hi--; }
        if (hi < 0) { hi += 10; clearcarry(); } else { setcarry(); }
        uint8_t res = (uint8_t)(((hi & 0x0F) << 4) | (lo & 0x0F));

        if (res == 0) setzero(); else clearzero();
        if (res & 0x80) setsign(); else clearsign();

        a = res;
        clockticks6502++;
    } else {
        value = mval ^ 0x00FF;
        result = (uint16_t)a + value + (uint16_t)(status & FLAG_CARRY);
        carrycalc(result);
        zerocalc(result);
        overflowcalc(result, a, value);
        signcalc(result);
        saveaccum(result);
    }
}

static void sec() {
    setcarry();
}

static void sed() {
    setdecimal();
}

static void sei() {
    setinterrupt();
}

static void sta() {
    putvalue(a);
}

static void stx() {
    putvalue(x);
}

static void sty() {
    putvalue(y);
}

static void tax() {
    x = a;

    zerocalc(x);
    signcalc(x);
}

static void tay() {
    y = a;

    zerocalc(y);
    signcalc(y);
}

static void tsx() {
    x = sp;

    zerocalc(x);
    signcalc(x);
}

static void txa() {
    a = x;

    zerocalc(a);
    signcalc(a);
}

static void txs() {
    sp = x;
}

static void tya() {
    a = y;

    zerocalc(a);
    signcalc(a);
}

//undocumented instructions
#ifdef UNDOCUMENTED
    static void lax() {
        lda();
        ldx();
    }

    static void sax() {
        sta();
        stx();
        putvalue(a & x);
        if (penaltyop && penaltyaddr) clockticks6502--;
    }

    static void dcp() {
        dec();
        cmp();
        if (penaltyop && penaltyaddr) clockticks6502--;
    }

    static void isb() {
        inc();
        sbc();
        if (penaltyop && penaltyaddr) clockticks6502--;
    }

    static void slo() {
        asl();
        ora();
        if (penaltyop && penaltyaddr) clockticks6502--;
    }

    static void rla() {
        rol();
        and();
        if (penaltyop && penaltyaddr) clockticks6502--;
    }

    static void sre() {
        lsr();
        eor();
        if (penaltyop && penaltyaddr) clockticks6502--;
    }

    static void rra() {
        ror();
        adc();
        if (penaltyop && penaltyaddr) clockticks6502--;
    }
#else
    #define lax nop
    #define sax nop
    #define dcp nop
    #define isb nop
    #define slo nop
    #define rla nop
    #define sre nop
    #define rra nop
#endif


static void (*addrtable_nmos[256])() = {
/*         |  0  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |  9  |  A  |  B  |  C  |  D  |  E  |  F  |     */
/* 0 */      imp, indx,  imp, indx,   zp,   zp,   zp,   zp,  imp,  imm,  acc,  imm, abso, abso, abso, abso, /* 0 */
/* 1 */      rel, indy,  imp, indy,  zpx,  zpx,  zpx,  zpx,  imp, absy,  imp, absy, absx, absx, absx, absx, /* 1 */
/* 2 */     abso, indx,  imp, indx,   zp,   zp,   zp,   zp,  imp,  imm,  acc,  imm, abso, abso, abso, abso, /* 2 */
/* 3 */      rel, indy,  imp, indy,  zpx,  zpx,  zpx,  zpx,  imp, absy,  imp, absy, absx, absx, absx, absx, /* 3 */
/* 4 */      imp, indx,  imp, indx,   zp,   zp,   zp,   zp,  imp,  imm,  acc,  imm, abso, abso, abso, abso, /* 4 */
/* 5 */      rel, indy,  imp, indy,  zpx,  zpx,  zpx,  zpx,  imp, absy,  imp, absy, absx, absx, absx, absx, /* 5 */
/* 6 */      imp, indx,  imp, indx,   zp,   zp,   zp,   zp,  imp,  imm,  acc,  imm,  ind, abso, abso, abso, /* 6 */
/* 7 */      rel, indy,  imp, indy,  zpx,  zpx,  zpx,  zpx,  imp, absy,  imp, absy, absx, absx, absx, absx, /* 7 */
/* 8 */      imm, indx,  imm, indx,   zp,   zp,   zp,   zp,  imp,  imm,  imp,  imm, abso, abso, abso, abso, /* 8 */
/* 9 */      rel, indy,  imp, indy,  zpx,  zpx,  zpy,  zpy,  imp, absy,  imp, absy, absx, absx, absy, absy, /* 9 */
/* A */      imm, indx,  imm, indx,   zp,   zp,   zp,   zp,  imp,  imm,  imp,  imm, abso, abso, abso, abso, /* A */
/* B */      rel, indy,  imp, indy,  zpx,  zpx,  zpy,  zpy,  imp, absy,  imp, absy, absx, absx, absy, absy, /* B */
/* C */      imm, indx,  imm, indx,   zp,   zp,   zp,   zp,  imp,  imm,  imp,  imm, abso, abso, abso, abso, /* C */
/* D */      rel, indy,  imp, indy,  zpx,  zpx,  zpx,  zpx,  imp, absy,  imp, absy, absx, absx, absx, absx, /* D */
/* E */      imm, indx,  imm, indx,   zp,   zp,   zp,   zp,  imp,  imm,  imp,  imm, abso, abso, abso, abso, /* E */
/* F */      rel, indy,  imp, indy,  zpx,  zpx,  zpx,  zpx,  imp, absy,  imp, absy, absx, absx, absx, absx  /* F */
};

static void (*optable_nmos[256])() = {
/*        |  0  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |  9  |  A  |  B  |  C  |  D  |  E  |  F  |      */
/* 0 */ brk_insn,  ora,  nop,  slo,  nop,  ora,  asl,  slo,  php,  ora,  asl,  nop,  nop,  ora,  asl,  slo, /* 0 */
/* 1 */      bpl,  ora,  nop,  slo,  nop,  ora,  asl,  slo,  clc,  ora,  nop,  slo,  nop,  ora,  asl,  slo, /* 1 */
/* 2 */      jsr,  and,  nop,  rla,  bit,  and,  rol,  rla,  plp,  and,  rol,  nop,  bit,  and,  rol,  rla, /* 2 */
/* 3 */      bmi,  and,  nop,  rla,  nop,  and,  rol,  rla,  sec,  and,  nop,  rla,  nop,  and,  rol,  rla, /* 3 */
/* 4 */      rti,  eor,  nop,  sre,  nop,  eor,  lsr,  sre,  pha,  eor,  lsr,  nop,  jmp,  eor,  lsr,  sre, /* 4 */
/* 5 */      bvc,  eor,  nop,  sre,  nop,  eor,  lsr,  sre,  cli,  eor,  nop,  sre,  nop,  eor,  lsr,  sre, /* 5 */
/* 6 */      rts,  adc,  nop,  rra,  nop,  adc,  ror,  rra,  pla,  adc,  ror,  nop,  jmp,  adc,  ror,  rra, /* 6 */
/* 7 */      bvs,  adc,  nop,  rra,  nop,  adc,  ror,  rra,  sei,  adc,  nop,  rra,  nop,  adc,  ror,  rra, /* 7 */
/* 8 */      nop,  sta,  nop,  sax,  sty,  sta,  stx,  sax,  dey,  nop,  txa,  nop,  sty,  sta,  stx,  sax, /* 8 */
/* 9 */      bcc,  sta,  nop,  nop,  sty,  sta,  stx,  sax,  tya,  sta,  txs,  nop,  nop,  sta,  nop,  nop, /* 9 */
/* A */      ldy,  lda,  ldx,  lax,  ldy,  lda,  ldx,  lax,  tay,  lda,  tax,  nop,  ldy,  lda,  ldx,  lax, /* A */
/* B */      bcs,  lda,  nop,  lax,  ldy,  lda,  ldx,  lax,  clv,  lda,  tsx,  lax,  ldy,  lda,  ldx,  lax, /* B */
/* C */      cpy,  cmp,  nop,  dcp,  cpy,  cmp,  dec,  dcp,  iny,  cmp,  dex,  nop,  cpy,  cmp,  dec,  dcp, /* C */
/* D */      bne,  cmp,  nop,  dcp,  nop,  cmp,  dec,  dcp,  cld,  cmp,  nop,  dcp,  nop,  cmp,  dec,  dcp, /* D */
/* E */      cpx,  sbc,  nop,  isb,  cpx,  sbc,  inc,  isb,  inx,  sbc,  nop,  sbc,  cpx,  sbc,  inc,  isb, /* E */
/* F */      beq,  sbc,  nop,  isb,  nop,  sbc,  inc,  isb,  sed,  sbc,  nop,  isb,  nop,  sbc,  inc,  isb  /* F */
};

static const uint32_t ticktable_nmos[256] = {
/*         |  0  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |  9  |  A  |  B  |  C  |  D  |  E  |  F  |     */
/* 0 */       7,    6,    2,    8,    3,    3,    5,    5,    3,    2,    2,    2,    4,    4,    6,    6,  /* 0 */
/* 1 */       2,    5,    2,    8,    4,    4,    6,    6,    2,    4,    2,    7,    4,    4,    7,    7,  /* 1 */
/* 2 */       6,    6,    2,    8,    3,    3,    5,    5,    4,    2,    2,    2,    4,    4,    6,    6,  /* 2 */
/* 3 */       2,    5,    2,    8,    4,    4,    6,    6,    2,    4,    2,    7,    4,    4,    7,    7,  /* 3 */
/* 4 */       6,    6,    2,    8,    3,    3,    5,    5,    3,    2,    2,    2,    3,    4,    6,    6,  /* 4 */
/* 5 */       2,    5,    2,    8,    4,    4,    6,    6,    2,    4,    2,    7,    4,    4,    7,    7,  /* 5 */
/* 6 */       6,    6,    2,    8,    3,    3,    5,    5,    4,    2,    2,    2,    5,    4,    6,    6,  /* 6 */
/* 7 */       2,    5,    2,    8,    4,    4,    6,    6,    2,    4,    2,    7,    4,    4,    7,    7,  /* 7 */
/* 8 */       2,    6,    2,    6,    3,    3,    3,    3,    2,    2,    2,    2,    4,    4,    4,    4,  /* 8 */
/* 9 */       2,    6,    2,    6,    4,    4,    4,    4,    2,    5,    2,    5,    5,    5,    5,    5,  /* 9 */
/* A */       2,    6,    2,    6,    3,    3,    3,    3,    2,    2,    2,    2,    4,    4,    4,    4,  /* A */
/* B */       2,    5,    2,    5,    4,    4,    4,    4,    2,    4,    2,    4,    4,    4,    4,    4,  /* B */
/* C */       2,    6,    2,    8,    3,    3,    5,    5,    2,    2,    2,    2,    4,    4,    6,    6,  /* C */
/* D */       2,    5,    2,    8,    4,    4,    6,    6,    2,    4,    2,    7,    4,    4,    7,    7,  /* D */
/* E */       2,    6,    2,    8,    3,    3,    5,    5,    2,    2,    2,    2,    4,    4,    6,    6,  /* E */
/* F */       2,    5,    2,    8,    4,    4,    6,    6,    2,    4,    2,    7,    4,    4,    7,    7   /* F */
};

/* 65C02 dispatch tables. Initialized close to the NMOS tables with
 * selected entries replaced for the W65C02S differences (JMP indirect
 * page-bug fix at $6C, BCD-aware ADC/SBC, BRK clears D) and the new
 * opcodes (bra/phx/phy/plx/ply/stz/etc., bit ops, wai/stp). */
static void (*addrtable_65c02[256])() = {
/* 0 */      imp, indx,  imm,  imp,   zp,   zp,   zp,   zp,  imp,  imm,  acc,  imp, abso, abso, abso,   zp,
/* 1 */      rel, indy, ind_zp, imp,   zp,  zpx,  zpx,   zp,  imp, absy,  acc,  imp, abso, absx, absx,   zp,
/* 2 */     abso, indx,  imm,  imp,   zp,   zp,   zp,   zp,  imp,  imm,  acc,  imp, abso, abso, abso,   zp,
/* 3 */      rel, indy, ind_zp, imp,  zpx,  zpx,  zpx,   zp,  imp, absy,  acc,  imp, absx, absx, absx,   zp,
/* 4 */      imp, indx,  imm,  imp,   zp,   zp,   zp,   zp,  imp,  imm,  acc,  imp, abso, abso, abso,   zp,
/* 5 */      rel, indy, ind_zp, imp,  zpx,  zpx,  zpx,   zp,  imp, absy,  imp,  imp, abso, absx, absx,   zp,
/* 6 */      imp, indx,  imm,  imp,   zp,   zp,   zp,   zp,  imp,  imm,  acc,  imp, ind_65c02, abso, abso, zp,
/* 7 */      rel, indy, ind_zp, imp,  zpx,  zpx,  zpx,   zp,  imp, absy,  imp,  imp, ind_absx, absx, absx, zp,
/* 8 */      rel, indx,  imm,  imp,   zp,   zp,   zp,   zp,  imp,  imm,  imp,  imp, abso, abso, abso,   zp,
/* 9 */      rel, indy, ind_zp, imp,  zpx,  zpx,  zpy,   zp,  imp, absy,  imp,  imp, abso, absx, absx,   zp,
/* A */      imm, indx,  imm,  imp,   zp,   zp,   zp,   zp,  imp,  imm,  imp,  imp, abso, abso, abso,   zp,
/* B */      rel, indy, ind_zp, imp,  zpx,  zpx,  zpy,   zp,  imp, absy,  imp,  imp, absx, absx, absy,   zp,
/* C */      imm, indx,  imm,  imp,   zp,   zp,   zp,   zp,  imp,  imm,  imp,  imp, abso, abso, abso,   zp,
/* D */      rel, indy, ind_zp, imp,  zpx,  zpx,  zpx,   zp,  imp, absy,  imp,  imp, abso, absx, absx,   zp,
/* E */      imm, indx,  imm,  imp,   zp,   zp,   zp,   zp,  imp,  imm,  imp,  imp, abso, abso, abso,   zp,
/* F */      rel, indy, ind_zp, imp,  zpx,  zpx,  zpx,   zp,  imp, absy,  imp,  imp, abso, absx, absx,   zp
};

static void (*optable_65c02[256])() = {
/* 0 */ brk_insn_65c02, ora, nop, nop, tsb, ora, asl, rmb, php, ora, asl, nop, tsb, ora, asl, bbr,
/* 1 */      bpl,  ora,  ora,  nop,  trb,  ora,  asl,  rmb,  clc,  ora,  inc,  nop,  trb,  ora,  asl,  bbr,
/* 2 */      jsr,  and,  nop,  nop,  bit,  and,  rol,  rmb,  plp,  and,  rol,  nop,  bit,  and,  rol,  bbr,
/* 3 */      bmi,  and,  and,  nop,  bit,  and,  rol,  rmb,  sec,  and,  dec,  nop,  bit,  and,  rol,  bbr,
/* 4 */      rti,  eor,  nop,  nop,  nop,  eor,  lsr,  rmb,  pha,  eor,  lsr,  nop,  jmp,  eor,  lsr,  bbr,
/* 5 */      bvc,  eor,  eor,  nop,  nop,  eor,  lsr,  rmb,  cli,  eor,  phy,  nop,  nop,  eor,  lsr,  bbr,
/* 6 */      rts, adc_65c02, nop, nop, stz, adc_65c02, ror, rmb, pla, adc_65c02, ror, nop, jmp, adc_65c02, ror, bbr,
/* 7 */      bvs, adc_65c02, adc_65c02, nop, stz, adc_65c02, ror, rmb, sei, adc_65c02, ply, nop, jmp, adc_65c02, ror, bbr,
/* 8 */      bra,  sta,  nop,  nop,  sty,  sta,  stx,  smb,  dey, bit_imm,txa,  nop,  sty,  sta,  stx,  bbs,
/* 9 */      bcc,  sta,  sta,  nop,  sty,  sta,  stx,  smb,  tya,  sta,  txs,  nop,  stz,  sta,  stz,  bbs,
/* A */      ldy,  lda,  ldx,  nop,  ldy,  lda,  ldx,  smb,  tay,  lda,  tax,  nop,  ldy,  lda,  ldx,  bbs,
/* B */      bcs,  lda,  lda,  nop,  ldy,  lda,  ldx,  smb,  clv,  lda,  tsx,  nop,  ldy,  lda,  ldx,  bbs,
/* C */      cpy,  cmp,  nop,  nop,  cpy,  cmp,  dec,  smb,  iny,  cmp,  dex,  wai,  cpy,  cmp,  dec,  bbs,
/* D */      bne,  cmp,  cmp,  nop,  nop,  cmp,  dec,  smb,  cld,  cmp,  phx,  stp,  nop,  cmp,  dec,  bbs,
/* E */      cpx, sbc_65c02, nop, nop, cpx, sbc_65c02, inc, smb, inx, sbc_65c02, nop, nop, cpx, sbc_65c02, inc, bbs,
/* F */      beq, sbc_65c02, sbc_65c02, nop, nop, sbc_65c02, inc, smb, sed, sbc_65c02, plx, nop, nop, sbc_65c02, inc, bbs
};

static const uint32_t ticktable_65c02[256] = {
/* 0 */       7,    6,    2,    1,    5,    3,    5,    5,    3,    2,    2,    1,    6,    4,    6,    5,
/* 1 */       2,    5,    5,    1,    5,    4,    6,    5,    2,    4,    2,    1,    6,    4,    7,    5,
/* 2 */       6,    6,    2,    1,    3,    3,    5,    5,    4,    2,    2,    1,    4,    4,    6,    5,
/* 3 */       2,    5,    5,    1,    4,    4,    6,    5,    2,    4,    2,    1,    4,    4,    7,    5,
/* 4 */       6,    6,    2,    1,    3,    3,    5,    5,    3,    2,    2,    1,    3,    4,    6,    5,
/* 5 */       2,    5,    5,    1,    4,    4,    6,    5,    2,    4,    3,    1,    8,    4,    7,    5,
/* 6 */       6,    6,    2,    1,    3,    3,    5,    5,    4,    2,    2,    1,    5,    4,    6,    5,
/* 7 */       2,    5,    5,    1,    4,    4,    6,    5,    2,    4,    4,    1,    6,    4,    7,    5,
/* 8 */       2,    6,    2,    1,    3,    3,    3,    5,    2,    2,    2,    1,    4,    4,    4,    5,
/* 9 */       2,    6,    5,    1,    4,    4,    4,    5,    2,    5,    2,    1,    4,    5,    5,    5,
/* A */       2,    6,    2,    1,    3,    3,    3,    5,    2,    2,    2,    1,    4,    4,    4,    5,
/* B */       2,    5,    5,    1,    4,    4,    4,    5,    2,    4,    2,    1,    4,    4,    4,    5,
/* C */       2,    6,    2,    1,    3,    3,    5,    5,    2,    2,    2,    3,    4,    4,    6,    5,
/* D */       2,    5,    5,    1,    4,    4,    6,    5,    2,    4,    3,    3,    4,    4,    7,    5,
/* E */       2,    6,    2,    1,    3,    3,    5,    5,    2,    2,    2,    1,    4,    4,    6,    5,
/* F */       2,    5,    5,    1,    4,    4,    6,    5,    2,    4,    4,    1,    4,    4,    7,    5
};

/* Set the active dispatch table pointers from cpu_variant. Called at
 * the top of step6502/exec6502 so a mid-run change of cpu_variant
 * takes effect at the next instruction boundary. */
static void cpu_select_tables(void) {
    if (cpu_variant == CPU_65C02) {
        addrtable = addrtable_65c02;
        optable = optable_65c02;
        ticktable = ticktable_65c02;
    } else {
        addrtable = addrtable_nmos;
        optable = optable_nmos;
        ticktable = ticktable_nmos;
    }
}


void nmi6502() {
    wai_pending = 0;
    push16(pc);
    push8(status);
    status |= FLAG_INTERRUPT;
    pc = (uint16_t)cpu_read(0xFFFA) | ((uint16_t)cpu_read(0xFFFB) << 8);
}

void irq6502() {
    wai_pending = 0;
    push16(pc);
    push8(status);
    status |= FLAG_INTERRUPT;
    pc = (uint16_t)cpu_read(0xFFFE) | ((uint16_t)cpu_read(0xFFFF) << 8);
}

uint8_t callexternal = 0;
void (*loopexternal)();

void exec6502(uint64_t tickcount) {
    cpu_select_tables();
    clockgoal6502 += tickcount;

    while (clockticks6502 < clockgoal6502) {
        if (stp_pending || wai_pending) { clockticks6502++; continue; }
        opcode = cpu_read(pc++);
        status |= FLAG_CONSTANT;

        penaltyop = 0;
        penaltyaddr = 0;

        (*addrtable[opcode])();
        (*optable[opcode])();
        clockticks6502 += ticktable[opcode];
        if (penaltyop && penaltyaddr) clockticks6502++;

        instructions++;

        if (callexternal) (*loopexternal)();
    }

}

void step6502() {
    cpu_select_tables();
    if (stp_pending || wai_pending) {
        clockticks6502++;
        clockgoal6502 = clockticks6502;
        return;
    }
    opcode = cpu_read(pc++);
    status |= FLAG_CONSTANT;

    penaltyop = 0;
    penaltyaddr = 0;

    (*addrtable[opcode])();
    (*optable[opcode])();
    clockticks6502 += ticktable[opcode];
    if (penaltyop && penaltyaddr) clockticks6502++;
    clockgoal6502 = clockticks6502;

    instructions++;

    if (callexternal) (*loopexternal)();
}

void hookexternal(void *funcptr) {
    if (funcptr != (void *)NULL) {
        loopexternal = funcptr;
        callexternal = 1;
    } else callexternal = 0;
}
