/*
 * Minimaler WebSocket-Client (RFC 6455) für den Simulator: ws:// ohne TLS, Textframes,
 * Ping/Pong/Close. Läuft in einem eigenen Thread und verbindet sich selbstständig neu.
 * Die Sec-WebSocket-Accept-Antwort wird nicht kryptografisch geprüft (nur lokal/LAN).
 */
#include "ws_client.h"

#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#include <sys/socket.h>
#include <unistd.h>

#define MAX_FRAME (256 * 1024)

struct ws_client {
    char host[128];
    char port[8];
    char path[128];
    ws_callbacks_t cb;
    void *user;

    pthread_t thread;
    pthread_mutex_t lock;
    volatile int stop;
    volatile int kick; /* Verbindung trennen und neu aufbauen */
    int fd;
};

static int parse_url(ws_client_t *c, const char *url)
{
    const char *p = url;
    if (strncmp(p, "ws://", 5) != 0) return -1;
    p += 5;
    const char *slash = strchr(p, '/');
    const char *colon = strchr(p, ':');
    size_t hlen = slash ? (size_t)(slash - p) : strlen(p);
    if (colon && (!slash || colon < slash)) {
        hlen = (size_t)(colon - p);
        size_t plen = slash ? (size_t)(slash - colon - 1) : strlen(colon + 1);
        if (plen == 0 || plen >= sizeof c->port) return -1;
        memcpy(c->port, colon + 1, plen);
        c->port[plen] = 0;
    } else {
        strcpy(c->port, "80");
    }
    if (hlen == 0 || hlen >= sizeof c->host) return -1;
    memcpy(c->host, p, hlen);
    c->host[hlen] = 0;
    snprintf(c->path, sizeof c->path, "%s", slash ? slash : "/");
    return 0;
}

static int write_all(int fd, const void *buf, size_t len)
{
    const unsigned char *b = buf;
    while (len) {
        ssize_t n = send(fd, b, len, MSG_NOSIGNAL);
        if (n < 0) {
            if (errno == EINTR) continue;
            if (errno == EAGAIN) {
                struct pollfd pfd = {fd, POLLOUT, 0};
                poll(&pfd, 1, 1000);
                continue;
            }
            return -1;
        }
        b += n;
        len -= (size_t)n;
    }
    return 0;
}

/* Wartet höchstens timeout_ms auf Daten; liest genau len Bytes. */
static int read_exact(ws_client_t *c, void *buf, size_t len)
{
    unsigned char *b = buf;
    while (len) {
        if (c->stop || c->kick) return -1;
        struct pollfd pfd = {c->fd, POLLIN, 0};
        int r = poll(&pfd, 1, 100);
        if (r < 0 && errno != EINTR) return -1;
        if (r <= 0) continue;
        ssize_t n = recv(c->fd, b, len, 0);
        if (n == 0) return -1;
        if (n < 0) {
            if (errno == EINTR || errno == EAGAIN) continue;
            return -1;
        }
        b += n;
        len -= (size_t)n;
    }
    return 0;
}

static int send_frame(ws_client_t *c, int opcode, const void *data, size_t len)
{
    unsigned char hdr[14];
    size_t h = 0;
    hdr[h++] = 0x80 | (opcode & 0x0F);
    if (len < 126) {
        hdr[h++] = 0x80 | (unsigned char)len;
    } else if (len < 65536) {
        hdr[h++] = 0x80 | 126;
        hdr[h++] = (unsigned char)(len >> 8);
        hdr[h++] = (unsigned char)len;
    } else {
        hdr[h++] = 0x80 | 127;
        for (int i = 7; i >= 0; i--) hdr[h++] = (unsigned char)((uint64_t)len >> (8 * i));
    }
    unsigned char mask[4];
    if (getrandom(mask, 4, 0) != 4) memset(mask, 0x5A, 4);
    memcpy(hdr + h, mask, 4);
    h += 4;

    unsigned char *buf = malloc(h + len);
    if (!buf) return -1;
    memcpy(buf, hdr, h);
    const unsigned char *d = data;
    for (size_t i = 0; i < len; i++) buf[h + i] = d[i] ^ mask[i & 3];

    pthread_mutex_lock(&c->lock);
    int rc = c->fd >= 0 ? write_all(c->fd, buf, h + len) : -1;
    pthread_mutex_unlock(&c->lock);
    free(buf);
    return rc;
}

int ws_client_send_text(ws_client_t *c, const char *text, size_t len)
{
    return send_frame(c, 0x1, text, len);
}

void ws_client_reconnect(ws_client_t *c)
{
    c->kick = 1;
}

static int tcp_connect(ws_client_t *c)
{
    struct addrinfo hints = {0}, *res = NULL;
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(c->host, c->port, &hints, &res) != 0) return -1;
    int fd = -1;
    for (struct addrinfo *ai = res; ai; ai = ai->ai_next) {
        fd = socket(ai->ai_family, ai->ai_socktype | SOCK_CLOEXEC, ai->ai_protocol);
        if (fd < 0) continue;
        fcntl(fd, F_SETFL, O_NONBLOCK);
        int r = connect(fd, ai->ai_addr, ai->ai_addrlen);
        if (r < 0 && errno == EINPROGRESS) {
            struct pollfd pfd = {fd, POLLOUT, 0};
            int err = 0;
            socklen_t el = sizeof err;
            if (poll(&pfd, 1, 2000) == 1 && getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &el) == 0 && err == 0) r = 0;
        }
        if (r == 0) break;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    if (fd >= 0) {
        int one = 1;
        setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    }
    return fd;
}

static void b64(const unsigned char *in, size_t n, char *out)
{
    static const char t[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t o = 0;
    for (size_t i = 0; i < n; i += 3) {
        uint32_t v = (uint32_t)in[i] << 16 | (i + 1 < n ? (uint32_t)in[i + 1] << 8 : 0) | (i + 2 < n ? in[i + 2] : 0);
        out[o++] = t[(v >> 18) & 63];
        out[o++] = t[(v >> 12) & 63];
        out[o++] = i + 1 < n ? t[(v >> 6) & 63] : '=';
        out[o++] = i + 2 < n ? t[v & 63] : '=';
    }
    out[o] = 0;
}

static int handshake(ws_client_t *c)
{
    unsigned char key[16];
    char key64[32];
    if (getrandom(key, sizeof key, 0) != sizeof key) return -1;
    b64(key, sizeof key, key64);
    char req[512];
    int n = snprintf(req, sizeof req,
                     "GET %s HTTP/1.1\r\nHost: %s:%s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                     "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n",
                     c->path, c->host, c->port, key64);
    if (write_all(c->fd, req, (size_t)n) < 0) return -1;

    char resp[1024];
    size_t got = 0;
    while (got < sizeof resp - 1) {
        if (read_exact(c, resp + got, 1) < 0) return -1;
        got++;
        if (got >= 4 && !memcmp(resp + got - 4, "\r\n\r\n", 4)) break;
    }
    resp[got] = 0;
    return strstr(resp, " 101 ") ? 0 : -1;
}

static void session(ws_client_t *c)
{
    char *msg = NULL;
    size_t msg_len = 0;
    int msg_op = 0x1; /* Text oder Binär, für Fortsetzungsframes */
    for (;;) {
        unsigned char h[2];
        if (read_exact(c, h, 2) < 0) break;
        int fin = h[0] & 0x80, op = h[0] & 0x0F;
        uint64_t len = h[1] & 0x7F;
        if (h[1] & 0x80) break; /* Server darf nicht maskieren */
        if (len == 126) {
            unsigned char e[2];
            if (read_exact(c, e, 2) < 0) break;
            len = (uint64_t)e[0] << 8 | e[1];
        } else if (len == 127) {
            unsigned char e[8];
            if (read_exact(c, e, 8) < 0) break;
            len = 0;
            for (int i = 0; i < 8; i++) len = len << 8 | e[i];
        }
        if (len > MAX_FRAME || msg_len + len > MAX_FRAME) break;
        char *payload = malloc((size_t)len + 1);
        if (!payload || (len && read_exact(c, payload, (size_t)len) < 0)) {
            free(payload);
            break;
        }
        payload[len] = 0;

        if (op == 0x9) { /* ping -> pong */
            send_frame(c, 0xA, payload, (size_t)len);
        } else if (op == 0x8) { /* close */
            send_frame(c, 0x8, payload, len >= 2 ? 2 : 0);
            free(payload);
            break;
        } else if (op == 0x1 || op == 0x2 || op == 0x0) {
            if (op) msg_op = op;
            char *nm = realloc(msg, msg_len + (size_t)len + 1);
            if (!nm) {
                free(payload);
                break;
            }
            msg = nm;
            memcpy(msg + msg_len, payload, (size_t)len);
            msg_len += (size_t)len;
            msg[msg_len] = 0;
            if (fin) {
                if (msg_op == 0x2) {
                    if (c->cb.on_binary) c->cb.on_binary(c->user, (const unsigned char *)msg, msg_len);
                } else c->cb.on_message(c->user, msg, msg_len);
                free(msg);
                msg = NULL;
                msg_len = 0;
            }
        }
        free(payload);
    }
    free(msg);
}

static void *thread_main(void *arg)
{
    ws_client_t *c = arg;
    int backoff = 500;
    while (!c->stop) {
        c->kick = 0;
        int fd = tcp_connect(c);
        if (fd >= 0) {
            pthread_mutex_lock(&c->lock);
            c->fd = fd;
            pthread_mutex_unlock(&c->lock);
            if (handshake(c) == 0) {
                backoff = 500;
                c->cb.on_open(c->user);
                session(c);
            }
            pthread_mutex_lock(&c->lock);
            close(c->fd);
            c->fd = -1;
            pthread_mutex_unlock(&c->lock);
            c->cb.on_close(c->user);
        }
        for (int waited = 0; waited < backoff && !c->stop; waited += 100) usleep(100 * 1000);
        if (backoff < 5000) backoff *= 2;
    }
    return NULL;
}

ws_client_t *ws_client_start(const char *url, const ws_callbacks_t *cb, void *user)
{
    ws_client_t *c = calloc(1, sizeof *c);
    if (!c) return NULL;
    if (parse_url(c, url) < 0) {
        fprintf(stderr, "ungültige URL (erwartet ws://host:port/pfad): %s\n", url);
        free(c);
        return NULL;
    }
    c->cb = *cb;
    c->user = user;
    c->fd = -1;
    pthread_mutex_init(&c->lock, NULL);
    pthread_create(&c->thread, NULL, thread_main, c);
    return c;
}

void ws_client_stop(ws_client_t *c)
{
    if (!c) return;
    c->stop = 1;
    pthread_join(c->thread, NULL);
    pthread_mutex_destroy(&c->lock);
    free(c);
}
