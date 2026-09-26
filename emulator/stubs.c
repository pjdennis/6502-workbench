#include "stubs.h"

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

size_t generate_stubs(uint8_t *memory, int terminal_mode) {
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
    fill_address(addr_read_b);
    emit_byte(inst_bit);        // read_b:  bit port_eof_b
    emit_address(port_eof_b);
    emit_byte(inst_bmi);        //          bmi .at_end (+5)
    emit_byte(0x05);
    emit_byte(inst_lda);        //          lda port_read_b
    emit_address(port_read_b);
    emit_byte(inst_clc);        //          clc
    emit_byte(inst_rts);        //          rts
    emit_byte(inst_sec);        // .at_end: sec
    emit_byte(inst_rts);        //          rts
    fill_address(addr_write_b);
    emit_byte(inst_sta);        // write_b: sta $f001
    emit_address(port_write_b);
    emit_byte(inst_rts);        //          rts
    fill_address(addr_write_d);
    emit_byte(inst_sta);        // write_d: sta $f002
    emit_address(port_write_d);
    emit_byte(inst_rts);        //          rts
    fill_address(addr_exit);
    emit_byte(inst_sta);        // exit:    sta $f003
    emit_address(port_exit);
    fill_address(addr_open);
    emit_byte(inst_lda);        // open:    lda $f005
    emit_address(port_open);
    emit_byte(inst_rts);        //          rts
    fill_address(addr_close);
    emit_byte(inst_sta);        // close:   sta $f000
    emit_address(port_close);
    emit_byte(inst_rts);        //          rts
    fill_address(addr_read);
    emit_byte(inst_bit);        // read:    bit port_eof
    emit_address(port_eof);
    emit_byte(inst_bmi);        //          bmi .at_end (+5)
    emit_byte(0x05);
    emit_byte(inst_lda);        //          lda port_read
    emit_address(port_read);
    emit_byte(inst_clc);        //          clc
    emit_byte(inst_rts);        //          rts
    emit_byte(inst_sec);        // .at_end: sec
    emit_byte(inst_rts);        //          rts
    fill_address(addr_argc);
    emit_byte(inst_lda);        // argc:    lda $fe80
    emit_address(port_argc);
    emit_byte(inst_rts);        //          rts
    fill_address(addr_argv);
    emit_byte(inst_ldx);        // argv:    ldx $fe82
    emit_address(port_argv_h);
    emit_byte(inst_lda);        //          lda $fe81
    emit_address(port_argv_l);
    emit_byte(inst_rts);        //          rts
    fill_address(addr_openout);
    emit_byte(inst_lda);        // openout: lda $fe83
    emit_address(port_openout);
    emit_byte(inst_rts);        //          rts
    fill_address(addr_write);
    emit_byte(inst_sta);        // write:   sta $fe84
    emit_address(port_write);
    emit_byte(inst_rts);        //          rts
    fill_address(addr_con_read);
    emit_byte(inst_lda);        // con_read: lda $fe90
    emit_address(port_con_read);
    emit_byte(inst_rts);        //           rts
    fill_address(addr_con_flush);
    emit_byte(inst_sta);        // con_flush: sta $fe91
    emit_address(port_con_flush);
    emit_byte(inst_rts);        //            rts
    fill_address(addr_con_ready);
    emit_byte(inst_lda);        // con_ready: lda $fe94
    emit_address(port_con_ready);
    emit_byte(inst_rts);        //            rts
    fill_address(addr_term_rows);
    emit_byte(inst_lda);        // term_rows: lda $fe92
    emit_address(port_term_rows);
    emit_byte(inst_rts);        //            rts
    fill_address(addr_term_cols);
    emit_byte(inst_lda);        // term_cols: lda $fe93
    emit_address(port_term_cols);
    emit_byte(inst_rts);        //            rts
    fill_address(addr_serial_read);
    emit_byte(inst_lda);        // serial_read: lda $fe95
    emit_address(port_serial_ready);
    emit_byte(inst_beq);        //              beq .no_data (+5)
    emit_byte(0x05);
    emit_byte(inst_lda);        //              lda $fe96
    emit_address(port_serial_data);
    emit_byte(inst_clc);        //              clc
    emit_byte(inst_rts);        //              rts
    emit_byte(inst_sec);        // .no_data:    sec
    emit_byte(inst_rts);        //              rts
    fill_address(addr_serial_write);
    if (terminal_mode) {
        emit_byte(inst_pha);    // serial_write: pha
        emit_byte(inst_lda);    //               lda $fe98
        emit_address(port_serial_write_ready);
        emit_byte(inst_beq);    //               beq .not_ready (+6)
        emit_byte(0x06);
        emit_byte(inst_pla);    //               pla
        emit_byte(inst_sta);    //               sta $fe97
        emit_address(port_serial_write);
        emit_byte(inst_clc);    //               clc (accepted)
        emit_byte(inst_rts);    //               rts
        emit_byte(inst_pla);    // .not_ready:   pla
        emit_byte(inst_sec);    //               sec (not accepted)
        emit_byte(inst_rts);    //               rts
    } else {
        emit_byte(inst_sec);    // serial_write: sec (not accepted, no terminal mode)
        emit_byte(inst_rts);    //               rts
    }
    fill_address(addr_opendir);
    emit_byte(inst_lda);        // opendir: lda port_opendir
    emit_address(port_opendir);
    emit_byte(inst_rts);        //          rts
    fill_address(addr_wait_ready);
    emit_byte(inst_sta);        // wait_ready: sta port_wait_lo
    emit_address(port_wait_lo);
    emit_byte(inst_stx);        //             stx port_wait_hi
    emit_address(port_wait_hi);
    emit_byte(inst_lda);        //             lda port_wait_ready
    emit_address(port_wait_ready);
    emit_byte(inst_rts);        //             rts

    return p;
}
