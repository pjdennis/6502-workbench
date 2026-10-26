#ifndef EMULATOR_CHIPS_NET_CLIENT_H
#define EMULATOR_CHIPS_NET_CLIENT_H

#include <stdint.h>
#include <stdio.h>
#include "../bus.h"
#include "w5500.h"

/* A client on the network for the W5500's TCP sockets (w5500.h), to run a server program against: once a socket
 * listens on its port, it connects; latency ticks later it sends its request (as much at a time as the socket's
 * RX buffer takes); it keeps what the server sends (in a file, if it has one) until the server closes the
 * connection; then it waits to connect again, connections times in all.
 *
 * Before its first request it opens idle connections, which never send anything and stay open until the server
 * closes them: as a browser's early ("preconnect") connections, or a phone that went to sleep, leave them. */
struct net_client {
    struct w5500_state *w5500;
    uint16_t port;
    const uint8_t *request;
    unsigned request_len, connections, latency, idle;
    FILE *response;          /* or NULL */
    int socket;              /* the connection's, or -1 */
    unsigned wait, sent;     /* ticks before the request goes; bytes of it sent */
    unsigned made, closed;   /* connections made, and closed by the server */
    uint32_t received;       /* bytes from the server, in every connection */
    int idle_socket[W5500_SOCKETS];   /* the idle connections' sockets (-1 once closed) */
    unsigned idle_made, idle_closed;
};

void net_client_init(struct chip *chip, struct net_client *client, struct w5500_state *w5500, uint16_t port,
                     const uint8_t *request, unsigned request_len, unsigned connections, unsigned idle,
                     unsigned latency, FILE *response);
/* "<prefix>: net client: port P: M of N connections, C closed by the server, B bytes received", then with idle
   connections "; I idle connections, J closed by the server" */
void net_client_report(FILE *fp, const char *prefix, const struct net_client *client);

#endif
