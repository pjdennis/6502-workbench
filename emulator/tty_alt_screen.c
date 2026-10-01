/* Alternate screen + raw terminal mode save/restore (see tty_alt_screen.h). */
#include "tty_alt_screen.h"

#include <termios.h>
#include <unistd.h>

#ifndef STDIN_FILENO
#define STDIN_FILENO  0
#endif
#ifndef STDOUT_FILENO
#define STDOUT_FILENO 1
#endif

static struct termios saved_termios;
static int saved_termios_valid = 0;
static int active = 0;

static void write_seq(const char *s, size_t n) {
    /* Best-effort; ignoring short writes is fine for an escape sequence
     * to a tty. */
    if (write(STDOUT_FILENO, s, n) < 0) { /* ignore */ }
}

void tty_alt_screen_enter(void) {
    if (active) return;
    if (!saved_termios_valid) {
        tcgetattr(STDIN_FILENO, &saved_termios);
        saved_termios_valid = 1;
    }
    const char enter[] = "\x1b[?1049h";
    write_seq(enter, sizeof(enter) - 1);

    struct termios raw = saved_termios;
    cfmakeraw(&raw);
    raw.c_lflag |= ISIG;  /* keep Ctrl-C raising SIGINT */
    raw.c_cc[VMIN] = 1;
    raw.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw);

    active = 1;
}

void tty_alt_screen_leave(void) {
    if (!active) return;
    if (saved_termios_valid) {
        tcsetattr(STDIN_FILENO, TCSAFLUSH, &saved_termios);
    }
    const char leave[] = "\x1b[?1049l\x1b[?25h\x1b[0m";
    write_seq(leave, sizeof(leave) - 1);
    active = 0;
}

int tty_alt_screen_active(void) {
    return active;
}
