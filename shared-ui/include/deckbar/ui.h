#pragma once
/* Öffentliche Schnittstelle des gemeinsamen NexBoard-UI-Codes. */
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DECKBAR_PROTO_VERSION 1
#define DECKBAR_W 640
#define DECKBAR_H 172

typedef struct {
    const char *token;     /* Geräte-Token aus der Daemon-Konfiguration */
    const char *device_id; /* z. B. "deckbar-a1b2c3" */
    const char *model;     /* z. B. "waveshare-s3-lcd-3.49" oder "sdl-sim" */
    const char *fw;        /* Firmware-Version */
    bool sim;
} deckbar_config_t;

typedef enum {
    DECKBAR_NET_NO_WIFI,    /* WLAN nicht verbunden */
    DECKBAR_NET_SEARCHING,  /* WLAN ok, Daemon wird gesucht / verbunden */
    DECKBAR_NET_ONLINE,     /* hello/welcome durch */
    DECKBAR_NET_AUTH_FAILED /* Token abgelehnt */
} deckbar_net_t;

/* Nach lv_init() + Display + Indev aufrufen. Lädt das gecachte Layout. */
void deckbar_ui_init(const deckbar_config_t *cfg);

/* WebSocket ist offen -> shared-ui schickt hello. */
void deckbar_ui_net_connected(void);
/* WebSocket ist zu. no_wifi = true, wenn schon das WLAN fehlt. */
void deckbar_ui_net_disconnected(bool no_wifi);
/* Ein empfangener Textframe (muss nicht nullterminiert sein). */
void deckbar_ui_net_message(const char *text, size_t len);

/* Zusatzinfo in der Offline-Anzeige, z. B. IP oder SSID (NULL = keine). */
void deckbar_ui_set_detail(const char *detail);

deckbar_net_t deckbar_ui_net_state(void);

#ifdef __cplusplus
}
#endif
