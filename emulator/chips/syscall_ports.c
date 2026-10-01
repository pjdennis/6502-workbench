/* wendy2c host file-I/O port block at $F800-$F80F, enabled by --disk (see syscall_ports.h). */
#include "syscall_ports.h"

#include <stdio.h>
#include <string.h>

/* The chip claims $F800-$F80F and is registered ahead of the RAM chip, so a
 * read/write to those addresses is handled here and never reaches RAM. All
 * other addresses fall through (read/write return false).
 *
 * File I/O is self-contained (a small stdio handle table) so this chip has no
 * link-time dependency on the rest of the emulator -- filenames resolve in the
 * process's cwd, which emu_wendy2c chdir's to the --disk directory. Handles
 * are 1..SYSC_MAX_FILES; 0 means "none/failed". */

#define SYSC_MAX_FILES 16

static FILE *sysc_files[SYSC_MAX_FILES + 1];   /* index 1.., 0 unused */

static uint8_t sysc_open(const char *name, const char *mode) {
    for (uint8_t h = 1; h <= SYSC_MAX_FILES; h++) {
        if (sysc_files[h] == NULL) {
            FILE *f = fopen(name, mode);
            if (!f) return 0;
            sysc_files[h] = f;
            return h;
        }
    }
    return 0;   /* table full */
}

static void name_reset(struct syscall_ports_state *s) {
    s->namelen = 0;
    s->namebuf[0] = '\0';
}

static FILE *cur(struct syscall_ports_state *s) {
    uint8_t h = s->current_handle;
    return (h >= 1 && h <= SYSC_MAX_FILES) ? sysc_files[h] : NULL;
}

static bool syscall_ports_read(struct chip *self, struct bus *bus,
                               uint16_t addr, uint8_t *data_out) {
    (void)bus;
    if (addr < SYSCALL_PORTS_BASE || addr > SYSCALL_PORTS_TOP) return false;
    struct syscall_ports_state *s = (struct syscall_ports_state *)self->state;
    switch (addr) {
    case 0xF802:                            /* open-for-read -> handle */
        s->namebuf[s->namelen] = '\0';
        s->current_handle = sysc_open(s->namebuf, "rb");
        name_reset(s);
        *data_out = s->current_handle;
        return true;
    case 0xF803:                            /* open-for-write -> handle */
        s->namebuf[s->namelen] = '\0';
        s->current_handle = sysc_open(s->namebuf, "wb");
        name_reset(s);
        *data_out = s->current_handle;
        return true;
    case 0xF805: {                          /* read byte from current handle */
        FILE *f = cur(s);
        int b = f ? fgetc(f) : EOF;
        *data_out = (b == EOF) ? 0 : (uint8_t)b;
        return true;
    }
    case 0xF806: {                          /* EOF of current handle (bit7) */
        FILE *f = cur(s);
        *data_out = 0;
        if (f) {
            int b = fgetc(f);
            if (b == EOF) {
                *data_out = 0x80;
                /* Rewind on EOF, matching the nmos machine's read stubs
                 * (emulator.c). A multi-pass reader (e.g. the p1.p8 compiler)
                 * re-scans its input by just clearing its own sticky-EOF flag
                 * and reading again from offset 0 -- no explicit seek port. */
                fseek(f, 0, SEEK_SET);
            } else {
                ungetc(b, f);
            }
        }
        return true;
    }
    default:
        *data_out = 0;                      /* unused read ports read as 0 */
        return true;
    }
}

static bool syscall_ports_write(struct chip *self, struct bus *bus,
                                uint16_t addr, uint8_t data) {
    (void)bus;
    if (addr < SYSCALL_PORTS_BASE || addr > SYSCALL_PORTS_TOP) return false;
    struct syscall_ports_state *s = (struct syscall_ports_state *)self->state;
    switch (addr) {
    case 0xF800:                            /* append filename byte */
        if (s->namelen < (int)sizeof(s->namebuf) - 1)
            s->namebuf[s->namelen++] = (char)data;
        return true;
    case 0xF801:                            /* clear filename buffer */
        name_reset(s);
        return true;
    case 0xF804:                            /* select current handle */
        s->current_handle = data;
        return true;
    case 0xF807: {                          /* write byte to current handle */
        FILE *f = cur(s);
        if (f) fputc(data, f);
        return true;
    }
    case 0xF808: {                          /* close current handle */
        FILE *f = cur(s);
        if (f) { fclose(f); sysc_files[s->current_handle] = NULL; }
        s->current_handle = 0;
        return true;
    }
    case 0xF80F:                            /* power off / halt */
        s->poweroff = 1;
        s->poweroff_code = data;
        return true;
    default:
        return true;                        /* swallow unused write ports */
    }
}

void syscall_ports_init(struct chip *chip, struct syscall_ports_state *state) {
    static const struct chip_ops ops = {
        .tick  = NULL,
        .read  = syscall_ports_read,
        .write = syscall_ports_write,
        .reset = NULL,
    };
    memset(state, 0, sizeof(*state));
    for (int i = 0; i <= SYSC_MAX_FILES; i++) sysc_files[i] = NULL;
    chip->ops = &ops;
    chip->name = "syscall_ports";
    chip->state = state;
}
