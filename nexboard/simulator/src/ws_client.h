#pragma once
#include <stddef.h>

typedef struct ws_client ws_client_t;

/* Callbacks laufen im Netzwerk-Thread. */
typedef struct {
    void (*on_open)(void *user);
    void (*on_close)(void *user);
    void (*on_message)(void *user, const char *text, size_t len);
    void (*on_binary)(void *user, const unsigned char *data, size_t len); /* optional */
} ws_callbacks_t;

ws_client_t *ws_client_start(const char *url, const ws_callbacks_t *cb, void *user);
int ws_client_send_text(ws_client_t *c, const char *text, size_t len);
void ws_client_reconnect(ws_client_t *c);
void ws_client_stop(ws_client_t *c);
