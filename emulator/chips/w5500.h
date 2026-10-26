#ifndef EMULATOR_CHIPS_W5500_H
#define EMULATOR_CHIPS_W5500_H

#include <stdint.h>
#include <stdio.h>
#include "../bus.h"
#include "spi.h"
#include "via_6522.h"

/* The WIZnet W5500 Ethernet controller as an SPI device (chips/spi.h). Its chip select (SCSn, active low) is
 * either a VIA port A pin, which it watches (on Michael, PA0, through the GAL SPI interface, gal_spi.h; the module
 * pulls SCSn up, so it is deselected while the pin is an input), or, with no VIA, set through the SPI device's
 * select by the master that drives it (the FPGA bus's network device, fpga_bus.h), which also resets it.
 *
 * A frame is two address bytes, a control byte -- the block (BSB, bits 7-3: 0 the common registers, 4n+1, 4n+2
 * and 4n+3 socket n's registers, TX buffer and RX buffer), read or write (bit 2: 1 writes) and the mode (bits 1-0:
 * 0 variable length, until SCSn rises; 1, 2 or 3 fixed at 1, 2 or 4 data bytes) -- then data, the address
 * counting up. While the address and control bytes go in, MISO counts them, $01, $02 and $03 (as the board shows):
 * a driver can check them to see the frame was taken whole. MISO is 0 during a write's data.
 *
 * Modelled: the register and buffer memory, with the reset values of the registers a driver reads first
 * (VERSIONR, read-only, is $04), and MR's software reset (RST, bit 7). PHYCFGR reads link up, as if
 * the cable were plugged into a 100 Mbps full duplex port.
 *
 * TCP sockets, toward a peer on the network (w5500_attach_peer; net_client.h): Sn_CR's commands act at once
 * (and it reads 0): OPEN (with Sn_MR TCP; other protocols aren't modelled) to INIT, LISTEN, then a peer's
 * w5500_peer_connect to a socket listening on its port makes it ESTABLISHED; what the peer sends joins the RX
 * buffer at Sn_RX_WR (Sn_RX_RSR counts it, and RECV, after the driver moves Sn_RX_RD past what it took, counts
 * again); SEND gives the peer the TX buffer from Sn_TX_RD to Sn_TX_WR; DISCON and CLOSE close the connection
 * at once (CLOSED; no FIN_WAIT or TIME_WAIT), and the peer closing it leaves CLOSE_WAIT. Sn_IR's CON, DISCON,
 * RECV and SEND_OK are set as on the chip, and a 1 written clears one; Sn_SR and the pointers the W5500 keeps
 * (Sn_TX_FSR, Sn_TX_RD, Sn_RX_RSR, Sn_RX_WR) are read-only. Timeouts, the interrupt pin and IP aren't. */

#define W5500_SOCKETS 8
#define W5500_BUFFER 0x800      /* each socket's TX and RX buffer at their reset size, 2 KB */

/* A peer on the network: told what a socket sends, and when the W5500 closes the connection */
struct w5500_peer {
    void *ctx;
    void (*receive)(void *ctx, int socket, const uint8_t *data, unsigned len);
    void (*closed)(void *ctx, int socket);
};

struct w5500_state {
    const struct via_6522_state *via;
    uint8_t cs_mask;            /* the port A pin of SCSn */
    int selected;
    unsigned cs_delay;          /* ticks before a change of the pin reaches SCSn (a capacitor on it); 0 by default */
    int pin_selected;           /* the pin, and ticks since it last changed */
    unsigned pin_ticks;
    uint8_t in, out, bits;      /* the byte arriving, the one leaving, and bits so far */
    uint8_t phase;              /* 0, 1: the address's bytes; 2: the control byte; 3: data */
    uint16_t addr;
    uint8_t control, data_left; /* fixed length mode: data bytes left in the frame */
    uint32_t frames;
    uint8_t common[0x40];
    uint8_t socket[W5500_SOCKETS][0x30];
    uint8_t tx[W5500_SOCKETS][W5500_BUFFER], rx[W5500_SOCKETS][W5500_BUFFER];
    struct w5500_peer peer;
};

void w5500_init(struct chip *chip, struct w5500_state *state, const struct via_6522_state *via, uint8_t cs_mask);
/* One SCLK pulse (spi.h): the MISO bit the rising edge saw */
int w5500_pulse(void *state, int mosi);
/* A glitch on the chip select (the board's ground bounce): if selected, the frame starts again */
void w5500_cs_glitch(struct w5500_state *state);
/* The network settings: "<prefix>: w5500: ip a.b.c.d mask a.b.c.d gateway a.b.c.d mac xx:xx:xx:xx:xx:xx" */
void w5500_report(FILE *fp, const char *prefix, const struct w5500_state *state);
/* Its chip select, set by a master that drives it (no VIA): deselecting ends a frame */
void w5500_select(void *state, int selected);
/* The W5500 as an SPI device: on the GAL interface, or with select and reset, on the FPGA's net pins */
struct spi_device w5500_spi(struct w5500_state *state);
/* The network side */
void w5500_attach_peer(struct w5500_state *state, struct w5500_peer peer);
/* A TCP connection to the socket listening on port: its number, or -1 if none is */
int w5500_peer_connect(struct w5500_state *state, uint16_t port);
/* Data from the peer into the socket's RX buffer: the bytes it took (as many as fit) */
unsigned w5500_peer_send(struct w5500_state *state, int socket, const uint8_t *data, unsigned len);
/* The peer closing the connection (its FIN) */
void w5500_peer_close(struct w5500_state *state, int socket);

#endif
