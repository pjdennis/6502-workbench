#ifndef EMULATOR_CHIPS_SYSCALL_PORTS_H
#define EMULATOR_CHIPS_SYSCALL_PORTS_H

#include "../bus.h"

/* wendy2c "OS-call" port block at $F800-$F80F (only registered when the
 * emulator is given a --disk directory). Provides host-backed file I/O to
 * guest code from any bank (the block is in the fixed high-RAM window, ahead
 * of the RAM chip on the bus). Filenames are pushed byte-by-byte into the
 * chip (no guest-RAM reads needed). See prog8/WENDY2_DISK_BOOT_DESIGN.md.
 *
 * Port map (R=read by guest, W=written by guest):
 *   $F800 W  append a byte to the filename buffer
 *   $F801 W  clear the filename buffer
 *   $F802 R  open filename buffer for reading  -> handle in A (0=fail); resets buffer
 *   $F803 R  open filename buffer for writing  -> handle in A (0=fail); resets buffer
 *   $F804 W  select the current handle
 *   $F805 R  read a byte from the current handle (returns 0 at EOF)
 *   $F806 R  EOF status of the current handle (bit7 set = at end)
 *   $F807 W  write a byte to the current handle
 *   $F808 W  close the current handle
 *   $F80F W  power off / halt the emulator (exit code = byte written)
 */

#define SYSCALL_PORTS_BASE 0xF800
#define SYSCALL_PORTS_TOP  0xF80F

struct syscall_ports_state {
    char    namebuf[256];
    int     namelen;
    uint8_t current_handle;
    int     poweroff;       /* set by a $F80F write; the run loop polls this */
    uint8_t poweroff_code;
};

void syscall_ports_init(struct chip *chip, struct syscall_ports_state *state);

#endif
