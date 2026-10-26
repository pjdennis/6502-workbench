/* A client on the network for the W5500's TCP sockets (see net_client.h). */
#include <string.h>
#include "net_client.h"

static void receive(void *ctx, int socket, const uint8_t *data, unsigned len) {
    struct net_client *c = ctx;
    if (socket != c->socket) return;
    if (c->response) fwrite(data, 1, len, c->response);
    c->received += len;
}

static void closed(void *ctx, int socket) {
    struct net_client *c = ctx;
    if (socket != c->socket) return;
    c->socket = -1;
    c->closed++;
}

static void net_client_tick(struct chip *self, struct bus *bus) {
    (void)bus;
    struct net_client *c = self->state;
    if (c->socket < 0) {
        if (c->made == c->connections) return;
        c->socket = w5500_peer_connect(c->w5500, c->port);
        if (c->socket < 0) return;
        c->made++;
        c->wait = c->latency;
        c->sent = 0;
        return;
    }
    if (c->wait && --c->wait) return;
    if (c->sent < c->request_len)
        c->sent += w5500_peer_send(c->w5500, c->socket, c->request + c->sent, c->request_len - c->sent);
}

void net_client_init(struct chip *chip, struct net_client *c, struct w5500_state *w5500, uint16_t port,
                     const uint8_t *request, unsigned request_len, unsigned connections, unsigned latency,
                     FILE *response) {
    static const struct chip_ops ops = { .tick = net_client_tick };
    memset(c, 0, sizeof *c);
    c->w5500 = w5500;
    c->port = port;
    c->request = request;
    c->request_len = request_len;
    c->connections = connections;
    c->latency = latency;
    c->response = response;
    c->socket = -1;
    w5500_attach_peer(w5500, (struct w5500_peer){ c, receive, closed });
    chip->ops = &ops;
    chip->name = "net-client";
    chip->state = c;
}

void net_client_report(FILE *fp, const char *prefix, const struct net_client *c) {
    fprintf(fp, "%s: net client: port %u: %u of %u connections, %u closed by the server, %u bytes received\n",
            prefix, c->port, c->made, c->connections, c->closed, (unsigned)c->received);
}
