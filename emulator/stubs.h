#ifndef STUBS_H
#define STUBS_H

#include <stdint.h>
#include <stddef.h>

// I/O port addresses
#define port_read_b  0xf004
#define port_write_b 0xf001
#define port_write_d 0xf002
#define port_exit    0xf003
#define port_open    0xf005
#define port_close   0xf000
// High I/O ports. Relocated from the $FE80 block up to $FFE0 so that nmos
// binaries can park their read-only string pool in the freed $F0C0..$FE00
// window (above the $F006 stub routines), keeping the low $0200..$F006
// window entirely for code + arenas. No program references these addresses
// directly -- they are reached via the $F006 jmp table -> stub routines --
// so the move is transparent (only stubs.c + emulator.c interception change).
#define port_read    0xffe5
#define port_argc    0xffe0
#define port_argv_l  0xffe1
#define port_argv_h  0xffe2
#define port_openout 0xffe3
#define port_write   0xffe4
#define port_con_read  0xfff0
#define port_con_flush 0xfff1
#define port_term_rows 0xfff2
#define port_term_cols 0xfff3
#define port_con_ready 0xfff4
#define port_serial_ready       0xfff5
#define port_serial_data        0xfff6
#define port_serial_write       0xfff7
#define port_serial_write_ready 0xfff8
#define port_eof_b   0xfff9
#define port_eof     0xfffa
#define port_opendir 0xfffb
#define port_wait_lo    0xffe6    // wait_ready: timeout in ms, low byte
#define port_wait_hi    0xffe7    //             high byte
#define port_wait_ready 0xffe8    //             read: wait, then the result

// Command-line argv strings are written into RAM (growing up) at load time;
// programs fetch each arg's address via the argv stub. Parked above the
// nmos string-pool window and below the relocated high ports.
#define ARGV_BASE    0xfe00
#define ARGV_TOP     0xffe0       // argv strings must stay below this

// Generate I/O stubs at $F006+ in memory, returns address after last stub byte
size_t generate_stubs(uint8_t *memory, int terminal_mode);

#endif
