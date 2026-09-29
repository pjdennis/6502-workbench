#include "stubs.h"
#include "direct_io.h"

#define save_address(v) uint16_t v = p; p += 2
#define fill_address(v) memory[v] = p & 0xff; memory[v+1] = p >> 8;
#define emit_byte(b) memory[p++] = b;
#define emit_address(v) emit_byte(v & 0xff); emit_byte(v >> 8);

#define inst_jmp 0x4c
#define inst_lda 0xad
#define inst_beq 0xf0
#define inst_clc 0x18
#define inst_rts 0x60
#define inst_sec 0x38
#define inst_sta 0x8d
#define inst_ldx 0xae
#define inst_stx 0x8e
#define inst_pha 0x48
#define inst_pla 0x68
#define inst_bit 0x2c
#define inst_bmi 0x30
#define inst_lda_imm 0xa9
#define inst_php 0x08
#define inst_plp 0x28
#define inst_eor_imm 0x49
#define inst_tya 0x98
#define inst_tay 0xa8

// The flags a call can return: N V Z C (NVZC_NONE: none of them)
#define NVZC_NONE 0xc3
#define NVZC_C    0xc2      // C only: read_b, read, serial_read, serial_write
#define NVZC_N    0x43      // N only: wait_ready

// A --strict-api tail: invert the flags in its mask, keeping A, X and Y
// (the mask is the flags the call does not return)
static size_t emit_strict_tail(uint8_t *memory, size_t p, uint16_t scratch, uint8_t mask) {
    emit_byte(inst_sta);        // sta scratch
    emit_address(scratch);
    emit_byte(inst_php);        // php
    emit_byte(inst_pla);        // pla
    emit_byte(inst_eor_imm);    // eor #mask
    emit_byte(mask);
    emit_byte(inst_pha);        // pha
    emit_byte(inst_lda);        // lda scratch
    emit_address(scratch);
    emit_byte(inst_plp);        // plp
    emit_byte(inst_rts);        // rts
    return p;
}

// A call's return: rts, or with strict_api a jmp to the tail that inverts
// the flags it does not return
#define emit_return(mask) \
    if (strict_api) { emit_byte(inst_jmp); emit_address(tail_for(mask)); } \
    else { emit_byte(inst_rts); }
#define tail_for(mask) ((mask) == NVZC_C ? tail_c : (mask) == NVZC_N ? tail_n : tail_none)
#define ret_size (strict_api ? 3 : 1)

size_t generate_stubs(uint8_t *memory, int terminal_mode, int direct_io, int strict_api) {
    size_t p = 0xf006;
    emit_byte(inst_jmp);        // f006     jmp read_b
    save_address(addr_read_b);
    emit_byte(inst_jmp);        // f009     jmp write_b
    save_address(addr_write_b);
    emit_byte(inst_jmp);        // f00c     jmp write_d
    save_address(addr_write_d);
    emit_byte(inst_jmp);        // f00f     jmp exit
    save_address(addr_exit);
    emit_byte(inst_jmp);        // f012     jmp open
    save_address(addr_open);
    emit_byte(inst_jmp);        // f015     jmp close
    save_address(addr_close);
    emit_byte(inst_jmp);        // f018     jmp read
    save_address(addr_read);
    emit_byte(inst_jmp);        // f01b     jmp argc
    save_address(addr_argc);
    emit_byte(inst_jmp);        // f01e     jmp argv
    save_address(addr_argv);
    emit_byte(inst_jmp);        // f021     jmp openout
    save_address(addr_openout);
    emit_byte(inst_jmp);        // f024     jmp write
    save_address(addr_write);
    emit_byte(inst_jmp);        // f027     jmp con_read
    save_address(addr_con_read);
    emit_byte(inst_jmp);        // f02a     jmp con_flush
    save_address(addr_con_flush);
    emit_byte(inst_jmp);        // f02d     jmp con_ready
    save_address(addr_con_ready);
    emit_byte(inst_jmp);        // f030     jmp term_rows
    save_address(addr_term_rows);
    emit_byte(inst_jmp);        // f033     jmp term_cols
    save_address(addr_term_cols);
    emit_byte(inst_jmp);        // f036     jmp serial_read
    save_address(addr_serial_read);
    emit_byte(inst_jmp);        // f039     jmp serial_write
    save_address(addr_serial_write);
    emit_byte(inst_jmp);        // f03c     jmp opendir
    save_address(addr_opendir);
    emit_byte(inst_jmp);        // f03f     jmp wait_ready
    save_address(addr_wait_ready);
    uint16_t addr_scr = p;      // f042     jmp scr_goto, ... (direct_io only)
    if (direct_io) p += 3 * SCR_OP_COUNT;
    uint16_t tail_none = 0, tail_c = 0, tail_n = 0;
    if (strict_api) {
        uint16_t scratch = (uint16_t)p++;
        tail_none = (uint16_t)p;
        p = emit_strict_tail(memory, p, scratch, NVZC_NONE);
        tail_c = (uint16_t)p;
        p = emit_strict_tail(memory, p, scratch, NVZC_C);
        tail_n = (uint16_t)p;
        p = emit_strict_tail(memory, p, scratch, NVZC_N);
    }
    fill_address(addr_read_b);
    emit_byte(inst_bit);        // read_b:  bit port_eof_b
    emit_address(port_eof_b);
    emit_byte(inst_bmi);        //          bmi .at_end
    emit_byte(3 + 1 + ret_size);
    emit_byte(inst_lda);        //          lda port_read_b
    emit_address(port_read_b);
    emit_byte(inst_clc);        //          clc
    emit_return(NVZC_C);        //          rts
    emit_byte(inst_sec);        // .at_end: sec
    emit_return(NVZC_C);        //          rts
    fill_address(addr_write_b);
    emit_byte(inst_sta);        // write_b: sta $f001
    emit_address(port_write_b);
    emit_return(NVZC_NONE);     //          rts
    fill_address(addr_write_d);
    emit_byte(inst_sta);        // write_d: sta $f002
    emit_address(port_write_d);
    emit_return(NVZC_NONE);     //          rts
    fill_address(addr_exit);
    emit_byte(inst_sta);        // exit:    sta $f003
    emit_address(port_exit);
    fill_address(addr_open);
    emit_byte(inst_lda);        // open:    lda $f005
    emit_address(port_open);
    emit_return(NVZC_NONE);     //          rts
    fill_address(addr_close);
    emit_byte(inst_sta);        // close:   sta $f000
    emit_address(port_close);
    emit_return(NVZC_NONE);     //          rts
    fill_address(addr_read);
    emit_byte(inst_bit);        // read:    bit port_eof
    emit_address(port_eof);
    emit_byte(inst_bmi);        //          bmi .at_end
    emit_byte(3 + 1 + ret_size);
    emit_byte(inst_lda);        //          lda port_read
    emit_address(port_read);
    emit_byte(inst_clc);        //          clc
    emit_return(NVZC_C);        //          rts
    emit_byte(inst_sec);        // .at_end: sec
    emit_return(NVZC_C);        //          rts
    fill_address(addr_argc);
    emit_byte(inst_lda);        // argc:    lda $fe80
    emit_address(port_argc);
    emit_return(NVZC_NONE);     //          rts
    fill_address(addr_argv);
    emit_byte(inst_ldx);        // argv:    ldx $fe82
    emit_address(port_argv_h);
    emit_byte(inst_lda);        //          lda $fe81
    emit_address(port_argv_l);
    emit_return(NVZC_NONE);     //          rts
    fill_address(addr_openout);
    emit_byte(inst_lda);        // openout: lda $fe83
    emit_address(port_openout);
    emit_return(NVZC_NONE);     //          rts
    fill_address(addr_write);
    emit_byte(inst_sta);        // write:   sta $fe84
    emit_address(port_write);
    emit_return(NVZC_NONE);     //          rts
    fill_address(addr_con_read);
    emit_byte(inst_lda);        // con_read: lda $fe90
    emit_address(port_con_read);
    emit_return(NVZC_NONE);     //           rts
    fill_address(addr_con_flush);
    emit_byte(inst_sta);        // con_flush: sta $fe91
    emit_address(port_con_flush);
    emit_return(NVZC_NONE);     //            rts
    fill_address(addr_con_ready);
    emit_byte(inst_lda);        // con_ready: lda $fe94
    emit_address(port_con_ready);
    emit_return(NVZC_NONE);     //            rts
    fill_address(addr_term_rows);
    emit_byte(inst_lda);        // term_rows: lda $fe92
    emit_address(port_term_rows);
    emit_return(NVZC_NONE);     //            rts
    fill_address(addr_term_cols);
    emit_byte(inst_lda);        // term_cols: lda $fe93
    emit_address(port_term_cols);
    emit_return(NVZC_NONE);     //            rts
    fill_address(addr_serial_read);
    emit_byte(inst_lda);        // serial_read: lda $fe95
    emit_address(port_serial_ready);
    emit_byte(inst_beq);        //              beq .no_data
    emit_byte(3 + 1 + ret_size);
    emit_byte(inst_lda);        //              lda $fe96
    emit_address(port_serial_data);
    emit_byte(inst_clc);        //              clc
    emit_return(NVZC_C);        //              rts
    emit_byte(inst_sec);        // .no_data:    sec
    emit_return(NVZC_C);        //              rts
    fill_address(addr_serial_write);
    if (terminal_mode) {
        emit_byte(inst_pha);    // serial_write: pha
        emit_byte(inst_lda);    //               lda $fe98
        emit_address(port_serial_write_ready);
        emit_byte(inst_beq);    //               beq .not_ready
        emit_byte(1 + 3 + 1 + ret_size);
        emit_byte(inst_pla);    //               pla
        emit_byte(inst_sta);    //               sta $fe97
        emit_address(port_serial_write);
        emit_byte(inst_clc);    //               clc (accepted)
        emit_return(NVZC_C);    //               rts
        emit_byte(inst_pla);    // .not_ready:   pla
        emit_byte(inst_sec);    //               sec (not accepted)
        emit_return(NVZC_C);    //               rts
    } else {
        emit_byte(inst_sec);    // serial_write: sec (not accepted, no terminal mode)
        emit_return(NVZC_C);    //               rts
    }
    fill_address(addr_opendir);
    emit_byte(inst_lda);        // opendir: lda port_opendir
    emit_address(port_opendir);
    emit_return(NVZC_NONE);     //          rts
    fill_address(addr_wait_ready);
    emit_byte(inst_sta);        // wait_ready: sta port_wait_lo
    emit_address(port_wait_lo);
    emit_byte(inst_stx);        //             stx port_wait_hi
    emit_address(port_wait_hi);
    emit_byte(inst_lda);        //             lda port_wait_ready
    emit_address(port_wait_ready);
    emit_return(NVZC_N);        //             rts
    for (int op = 0; direct_io && op < SCR_OP_COUNT; op++) {
        uint16_t vec = (uint16_t)(addr_scr + 3 * op);
        memory[vec] = inst_jmp;
        fill_address(vec + 1);
        emit_byte(inst_sta);    // scr_*:   sta port_scr_a
        emit_address(port_scr_a);
        emit_byte(inst_lda_imm);//          lda #op
        emit_byte(op);
        emit_byte(inst_sta);    //          sta port_scr_op
        emit_address(port_scr_op);
        if (strict_api) {       // A and Y may change: they do
            emit_byte(inst_tya);        // tya
            emit_byte(inst_eor_imm);    // eor #$ff
            emit_byte(0xff);
            emit_byte(inst_tay);        // tay
            emit_byte(inst_lda_imm);    // lda #~op
            emit_byte((uint8_t)~op);
        }
        emit_return(NVZC_NONE); //          rts
    }

    return p;
}
