// Simulates Michael running a program, for tests: the 65C02 (emulator/cpu_core.c), RAM,
// the VIA, the 20x4 LCD and the PS/2 keyboard board, modelled at the level the keyboard driver
// (firmware/lib/keyboard/keyboard_driver.inc) sees it:
// - SOLB (PA3) low pulls the keyboard clock low, which the frame detector passes to CA2 as an edge.
// - Releasing SOLB lets the keyboard clock the byte in; CA2 interrupts at the end of that frame.
// - The keyboard replies with a frame: CA2 interrupts at its start and at its end. While SOEB
//   (PA4) is low the receive shift registers drive Port B with the inverted byte.
// - After the 5 start-up commands the keyboard sends the --keys bytes, one frame each. With a
//   --fault, which stops start-up, it sends them after the first command.
// - LCD writes are checked: E must fall with E, RS and RW driven, SOEB high, and Port B driving
//   the data for a write.
// - --ram picks how RAM is decoded below the VIA at $6000:
//     full      (default) RAM at $0000-$5FFF
//     eater     Ben Eater's decoding: 16K at $0000-$3FFF. The RAM's A14 is grounded and address
//               A14 drives its OE, so writes to $4000-$7FFF (the VIA's too) also land in
//               $0000-$3FFF, and reads of $4000-$5FFF see an idle bus (the address's high byte,
//               the last byte an indirect access fetched)
//     mirror8k  8K at $0000-$1FFF, repeated up to $5FFF
// Build: gcc -O2 -I emulator -o michael_keyboard_sim tools/michael_keyboard_sim.c emulator/cpu_core.c
// Usage: michael_keyboard_sim [--keys=E1,14,...] [--fault=noedge|noirq|noack|resend]
//                             [--ram=full|eater|mirror8k]
//                             <program.bin> <load address> <IRQ vector>   (addresses in hex)
// Prints the LCD's 4 lines, then "bad LCD writes: <count>".
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "cpu_core.h"

#define VIA_BASE       0x6000
#define PORTB          0x0
#define PORTA          0x1
#define DDRB           0x2
#define DDRA           0x3
#define IFR            0xd
#define IER            0xe
#define E              0x80
#define RW             0x40
#define RS             0x20
#define SOEB           0x10
#define SOLB           0x08
#define STARTUP_COMMANDS 5
#define FRAME_LENGTH   1000      // Instructions from the start of a frame to its end
#define MAX_EVENTS     256
#define MAX_KEYS       64

static uint8_t mem[65536], via[16];
static uint8_t ddram[128], ddram_address;
static int cgram_mode, bad_lcd_writes;

// CA2 interrupts to deliver; data is the byte on the receive shift registers from then on
static struct { long at; uint8_t data; } events[MAX_EVENTS];
static int n_events, next_event;
static uint8_t received;
static long now;

static uint8_t keys[MAX_KEYS];
static int n_keys, commands;
static const char *fault = "";

// RAM decoding: address bits kept, and where reads and writes stop reaching RAM
static const struct { const char *name; uint16_t mask, read_end, write_end; } ram_maps[] = {
  { "full",     0xffff, VIA_BASE, VIA_BASE },
  { "eater",    0x3fff, 0x4000,   0x8000   },
  { "mirror8k", 0x1fff, VIA_BASE, VIA_BASE },
};
static int ram_map;

static void schedule(long at, uint8_t data) {
  if (n_events == MAX_EVENTS) { fprintf(stderr, "too many events\n"); exit(2); }
  events[n_events].at = at;
  events[n_events++].data = data;
}

static void frame(long at, uint8_t data) {
  schedule(at, received);
  schedule(at + FRAME_LENGTH, data);
}

// The keyboard's response to the host releasing the clock after loading a command byte
static void keyboard_receive_command(void) {
  commands++;
  schedule(now + FRAME_LENGTH, received);                 // Keyboard clocks the command in
  if (strcmp(fault, "noack")) frame(now + 3 * FRAME_LENGTH, !strcmp(fault, "resend") ? 0xfe : 0xfa);
  if (commands == STARTUP_COMMANDS || (commands == 1 && *fault))
    for (int i = 0; i < n_keys; i++) frame(now + 200000 + i * 2 * FRAME_LENGTH, keys[i]);
}

static void lcd_strobe(uint8_t porta) {
  int writing = !(porta & RW);
  if ((via[DDRA] & (E | RW | RS)) != (E | RW | RS) || !(porta & SOEB) ||
      (writing && via[DDRB] != 0xff)) {
    bad_lcd_writes++;
    return;
  }
  if (!writing) return;                                   // Busy flag read
  uint8_t value = via[PORTB];
  if (porta & RS) {
    if (!cgram_mode) ddram[ddram_address++ & 0x7f] = value;
  } else if (value & 0x80) {
    ddram_address = value & 0x7f; cgram_mode = 0;
  } else if (value & 0x40) {
    cgram_mode = 1;
  } else if (value == 0x01) {
    memset(ddram, ' ', sizeof ddram); ddram_address = 0; cgram_mode = 0;
  }
}

uint8_t read6502(uint16_t address) {
  if (address >= 0x8000) return mem[address];
  if (address < ram_maps[ram_map].read_end) return mem[address & ram_maps[ram_map].mask];
  if (address < VIA_BASE) return address >> 8;
  uint8_t reg = address & 0xf;
  if (reg == IFR) return strcmp(fault, "noedge") ? 0x01 : 0x00;  // CA2
  if (reg == PORTB) {                                     // Output bits read back the latch
    uint8_t pins = (via[PORTA] & SOEB) ? 0x00 : (uint8_t)~received;  // LCD never busy
    return (via[PORTB] & via[DDRB]) | (pins & ~via[DDRB]);
  }
  return via[reg];
}

void write6502(uint16_t address, uint8_t value) {
  if (address >= 0x8000) return;
  if (address < ram_maps[ram_map].write_end) mem[address & ram_maps[ram_map].mask] = value;
  if (address < VIA_BASE) return;
  uint8_t reg = address & 0xf, old = via[reg];
  if (reg == IER) value = (value & 0x80) ? (old | (value & 0x7f)) : (old & ~value);
  via[reg] = value;
  if (reg != PORTA) return;
  if ((old & E) && !(value & E)) lcd_strobe(value);
  if (!(old & SOLB) && (value & SOLB) && (via[IER] & 0x01)) keyboard_receive_command();
}

int main(int argc, char **argv) {
  int arg = 1;
  for (; arg < argc && !strncmp(argv[arg], "--", 2); arg++) {
    if (!strncmp(argv[arg], "--keys=", 7)) {
      for (char *p = argv[arg] + 7; *p && n_keys < MAX_KEYS; p += (*p == ',')) keys[n_keys++] = strtol(p, &p, 16);
    } else if (!strncmp(argv[arg], "--fault=", 8)) {
      fault = argv[arg] + 8;
    } else if (!strncmp(argv[arg], "--ram=", 6)) {
      int n = sizeof ram_maps / sizeof *ram_maps;
      for (ram_map = 0; ram_map < n && strcmp(argv[arg] + 6, ram_maps[ram_map].name); ram_map++) {}
      if (ram_map == n) { fprintf(stderr, "unknown RAM map %s\n", argv[arg] + 6); return 2; }
    } else {
      fprintf(stderr, "unknown option %s\n", argv[arg]); return 2;
    }
  }
  if (argc - arg != 3) { fprintf(stderr, "usage: see tools/michael_keyboard_sim.c\n"); return 2; }
  uint16_t load = strtol(argv[arg + 1], 0, 16), irq = strtol(argv[arg + 2], 0, 16);
  FILE *f = fopen(argv[arg], "rb");
  if (!f) { perror(argv[arg]); return 2; }
  size_t length = fread(mem + load, 1, VIA_BASE - load, f);
  fclose(f);
  if (!length) { fprintf(stderr, "empty program\n"); return 2; }
  mem[0xfffe] = irq & 0xff;
  mem[0xffff] = irq >> 8;
  memset(ddram, ' ', sizeof ddram);

  cpu_variant = CPU_65C02;
  reset6502();
  pc = load;
  status |= 0x04;                                         // The loader starts programs with sei
  long stop_at = 3000000;
  for (now = 0; now < stop_at; now++) {
    if (next_event < n_events && events[next_event].at <= now && !(status & 0x04) &&
        (via[IER] & 0x01) && strcmp(fault, "noirq")) {
      received = events[next_event++].data;
      irq6502();
    }
    if (n_events && events[n_events - 1].at + 1000000 > stop_at) stop_at = events[n_events - 1].at + 1000000;
    step6502();
  }

  static const uint8_t lines[] = { 0x00, 0x40, 0x14, 0x54 };
  for (int line = 0; line < 4; line++) {
    for (int column = 0; column < 20; column++) {
      uint8_t c = ddram[lines[line] + column];
      putchar(c >= 0x20 && c < 0x7f ? c : '?');
    }
    putchar('\n');
  }
  printf("bad LCD writes: %d\n", bad_lcd_writes);
  return 0;
}
