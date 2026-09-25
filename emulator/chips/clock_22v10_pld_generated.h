/* GENERATED FROM hardware/wendy2/22V10-wendy2c.pld by pld_to_c.py -- DO NOT EDIT.
 *
 * Each function evaluates one combinational output of the PLD
 * directly from the addr+config bits. Re-run pld_to_c.py to
 * refresh after editing the .pld source.
 */
#ifndef EMULATOR_CHIPS_CLOCK_22V10_PLD_GENERATED_H
#define EMULATOR_CHIPS_CLOCK_22V10_PLD_GENERATED_H

static inline int pld_romcs(int a15, int a14, int a13, int a12, int a11, int c4, int c3, int c2, int c1, int c0) {
    return (((!c4) & (!c3) & (!c2) & (!c1) & (!c0) & a15 & a14 & a13 & a12 & a11) | ((!c4) & (!c3) & (!c2) & (!c1) & (!c0) & a15 & (!a14)) | ((!c4) & (!c3) & (!c2) & (!c1) & (!c0) & a15 & a14 & (!a13)) | ((!c4) & (!c3) & (!c2) & (!c1) & (!c0) & a15 & a14 & a13 & (!a12)) | (c4 & (!c2) & (!c1) & (!c0) & a15 & (!a14)) | (c4 & (!c2) & (!c1) & (!c0) & a15 & a14 & (!a13)) | (c4 & (!c2) & (!c1) & (!c0) & a15 & a14 & a13 & (!a12))) ? 1 : 0;
}

static inline int pld_viacs(int a15, int a14, int a13, int a12, int a11, int c4, int c3, int c2, int c1, int c0) {
    (void)c4; (void)c3; (void)c2; (void)c1; (void)c0;
    return ((a15 & a14 & a13 & a12 & (!a11))) ? 1 : 0;
}

static inline int pld_ramcs(int a15, int a14, int a13, int a12, int a11, int c4, int c3, int c2, int c1, int c0) {
    return (((!c4) & (!c3) & (!c2) & (!c1) & (!c0) & a15 & a14 & a13 & a12 & a11) | ((!c4) & (!c3) & (!c2) & (!c1) & (!c0) & a15 & (!a14)) | ((!c4) & (!c3) & (!c2) & (!c1) & (!c0) & a15 & a14 & (!a13)) | ((!c4) & (!c3) & (!c2) & (!c1) & (!c0) & a15 & a14 & a13 & (!a12)) | (c4 & (!c2) & (!c1) & (!c0) & a15 & (!a14)) | (c4 & (!c2) & (!c1) & (!c0) & a15 & a14 & (!a13)) | (c4 & (!c2) & (!c1) & (!c0) & a15 & a14 & a13 & (!a12)) | (a15 & a14 & a13 & a12 & (!a11))) ? 0 : 1;
}

static inline int pld_r15(int a15, int a14, int a13, int a12, int a11, int c4, int c3, int c2, int c1, int c0) {
    (void)a13; (void)a12; (void)a11;
    return (((!a15) & (!a14) & (!c4) & (!c3) & (!c2) & (!c1) & (!c0)) | ((!a15) & (!a14) & (!c4) & c0) | ((!a15) & (!a14) & c4 & (!c3)) | (a15 & a14)) ? 1 : 0;
}

static inline int pld_r16(int a15, int a14, int a13, int a12, int a11, int c4, int c3, int c2, int c1, int c0) {
    (void)c2;
    return (((!a15) & (!a14) & (!c4) & c1) | ((!a15) & (!a14) & c4 & c3) | (a15 & (!a14) & c4 & c0) | (a15 & (!a13) & c4 & c0) | (a15 & (!a12) & c4 & c0) | (a15 & (!a11) & c4 & c0)) ? 1 : 0;
}

static inline int pld_r17(int a15, int a14, int a13, int a12, int a11, int c4, int c3, int c2, int c1, int c0) {
    (void)c3; (void)c0;
    return (((!a15) & (!a14) & (!c4) & c2) | (a15 & (!a14) & c4 & c1) | (a15 & (!a13) & c4 & c1) | (a15 & (!a12) & c4 & c1) | (a15 & (!a11) & c4 & c1)) ? 1 : 0;
}

static inline int pld_r18(int a15, int a14, int a13, int a12, int a11, int c4, int c3, int c2, int c1, int c0) {
    (void)c1; (void)c0;
    return (((!a15) & (!a14) & (!c4) & c3) | (a15 & (!a14) & c4 & c2) | (a15 & (!a13) & c4 & c2) | (a15 & (!a12) & c4 & c2) | (a15 & (!a11) & c4 & c2)) ? 1 : 0;
}

#endif
