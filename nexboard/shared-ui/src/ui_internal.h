/*
 * Innenleben der NexBoard-UI: Typen, der gemeinsame Zustand und was die Teile voneinander brauchen.
 * Nur für die Dateien unter shared-ui/src; nach außen gilt deckbar/ui.h.
 */
#ifndef DECKBAR_UI_INTERNAL_H
#define DECKBAR_UI_INTERNAL_H

#include "deckbar/ui.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cJSON.h"
#include "deckbar/fonts.h"
#include "deckbar/hal.h"
#include "deckbar/icons.h"
#include "lvgl.h"
#include "theme.h"

#define ID_LEN (DECKBAR_ID_MAX + 1)
#define SLIDER_SEND_MS (1000 / DECKBAR_SLIDER_EVENTS_PER_S)
#define SLIDER_SETTLE_MS 700  /* nach dem Loslassen veraltete Werte vom Daemon ignorieren */
#define TOGGLE_REVERT_MS 1500 /* optimistischer Toggle ohne Bestätigung -> zurück */
#define DRAG_THRESHOLD 6
#define TAP_SLOP 16          /* weiter bewegt = Wischversuch, kein Tippen */
#define SWIPE_MIN 50         /* Wischweg in px, ab dem die Seite wechselt */
#define MARQUEE_MS 20000     /* so lange läuft ein zu langer Titel, danach endet er mit „…“ */
#define CACHE_KEY "layout"
#define BG_KEY "bg"          /* Hintergrund im Flash: nach einem Neustart nicht erneut übertragen */
#define BG_MAGIC "DBG1"
/* Binärframe mit einem Bildteil: "DB", Art ('a' Cover, 'b' Hintergrund), id (16 Byte, mit Nullen
 * aufgefüllt), w, h, y, rows (je uint16 little endian), dann rows*w*2 Byte RGB565 */
#define IMAGE_ID_LEN (DECKBAR_IMAGE_ID_MAX + 1)

typedef struct tile tile_t;

/* Kachel-Schnittstelle: Ein Kacheltyp baut sich aus seinem Eintrag im Layout und zeigt seinen Teil des
 * States. Ein neuer Typ ist eine Datei mit seiner Klasse und eine Zeile in der Tabelle in ui_tiles.c. */
typedef struct {
    const char *name; /* „type“ im Layout */
    void (*build)(tile_t *t, int32_t w, int32_t h, const cJSON *item);
    void (*update)(tile_t *t); /* sein State hat sich geändert; NULL: die Kachel hängt an bind/mute_bind */
    const char *keys[2];       /* State-Schlüssel, bei denen update() gerufen wird */
} tile_class_t;

extern const tile_class_t dbui_tile_button, dbui_tile_toggle, dbui_tile_slider, dbui_tile_media;
extern const tile_class_t dbui_tile_dps, dbui_tile_claude, dbui_tile_guide;

/* Die Klasse zu einem Typnamen; unbekannte Namen sind Knöpfe. */
const tile_class_t *dbui_tile_class(const char *name);


struct tile {
    char id[ID_LEN];
    const tile_class_t *cls;
    db_style_t style;
    char bind[ID_LEN];
    char mute_bind[ID_LEN];
    char nav[ID_LEN];
    const char *glyph;
    const char *glyph_on;
    int32_t min, max;

    lv_obj_t *obj;
    lv_obj_t *icon;
    lv_obj_t *label;
    lv_obj_t *value;   /* Slider: Wert in % */
    lv_obj_t *fill;    /* Slider: Füllung */
    lv_obj_t *title;   /* Media */
    lv_obj_t *artist;  /* Media */
    lv_obj_t *play;    /* Media: Play/Pause-Icon */
    lv_obj_t *cover;   /* Media: Cover-Bild (über dem Platzhalter-Icon in t->icon) */
    int32_t cover_px;  /* Media: Kantenlänge des Covers, 0 = keins */
    bool flat;         /* Media: einzeiliges Layout, Text wird vertikal zentriert */
    void *view;        /* typ-eigene Ansicht (DPS, Claude, Guide), wird mit der Kachel freigegeben */

    bool checked;
    bool muted;
    int32_t value_cur;
    int32_t value_target;

    /* Slider-Interaktion */
    bool dragging, moved, long_fired;
    int32_t press_x, press_value;
    uint32_t last_send;
    int32_t last_sent_value;
    uint32_t settle_until;
    lv_timer_t *timer; /* Slider: Settle-Ende, Toggle: Revert */
};

/* Bild, das zeilenweise in mehreren Nachrichten kommt (`art`, `bg`). Zwei Puffer, damit nie
 * ein halb empfangenes Bild zu sehen ist: empfangen wird in den hinteren, angezeigt der vordere. */
typedef struct {
    lv_image_dsc_t dsc[2];
    uint8_t *buf[2];
    char id[2][IMAGE_ID_LEN];
    int front;          /* angezeigter Puffer, -1 = keins */
    int32_t back_rows;  /* bereits empfangene Zeilen im hinteren Puffer */
} img_rx_t;

typedef struct {
    deckbar_config_t cfg;
    cJSON *state;           /* aktueller State (Objekt) */
    char layout_hash[65];
    bool have_layout;

    tile_t *tiles;
    int tile_count;

    lv_obj_t *bg;
    lv_obj_t *tv;
    lv_obj_t *pages[DECKBAR_MAX_PAGES];
    char page_ids[DECKBAR_MAX_PAGES][ID_LEN];
    int page_count;
    int page_active;
    lv_obj_t *dots;

    lv_obj_t *pill;
    lv_obj_t *pill_dot;
    lv_obj_t *pill_label;
    lv_obj_t *splash;
    lv_obj_t *splash_status;
    lv_obj_t *splash_detail;

    deckbar_net_t net;
    bool ws_open;
    uint32_t last_rx;
    uint32_t hello_at;
    int heartbeat_s;
    char detail[64];

    img_rx_t art; /* Cover der Media-Kacheln */
    img_rx_t bgi; /* Hintergrund vom Daemon (sonst deckbar_bg_default) */
} ui_state_t;

extern ui_state_t ui;

/* ui_tiles.c */
void dbui_apply_full_state(void);
void dbui_apply_state_key(const char *key, const cJSON *val);
void dbui_fill_anim_cb(void *var, int32_t v);
lv_obj_t *dbui_make_tile_obj(lv_obj_t *page, tile_t *t, int32_t x, int32_t y, int32_t w, int32_t h);
lv_obj_t *dbui_mini_button(lv_obj_t *parent, tile_t *t, const char *glyph, const char *part, int32_t size);
void dbui_slider_show(tile_t *t, int32_t v);

/* ui_pages.c */
bool dbui_apply_layout(const cJSON *msg);
void dbui_go_to_page(int idx);
void dbui_touch_cb(lv_event_t *e);

/* ui_images.c */
void dbui_bg_restore(void);
void dbui_handle_art(const cJSON *msg);
void dbui_handle_bg(const cJSON *msg);
void dbui_media_show_cover(tile_t *t);
void dbui_request_art(void);


/* ui_tile_dps.c */
void dbui_set_hidden(lv_obj_t *o, bool hidden);
void dbui_set_text(lv_obj_t *l, const char *txt);


/* ui_status.c */
void dbui_build_status_ui(void);
void dbui_set_net(deckbar_net_t n);
void dbui_update_status_ui(void);

/* ui_util.c */
void dbui_copy_str(char *dst, size_t n, const char *src);
const char *dbui_glyph_or_default(const char *name, const char *fallback);
int dbui_jint(const cJSON *o, const char *key, int def);
const char *dbui_jstr(const cJSON *o, const char *key);
lv_obj_t *dbui_plain_obj(lv_obj_t *parent);
void dbui_send_event(const char *event, const char *item, const char *part, const int32_t *value, int final);
void dbui_send_page_change(const char *page);
void dbui_send_raw(const char *s);
lv_obj_t *dbui_text_label(lv_obj_t *parent, const lv_font_t *font, const char *txt);
bool dbui_truthy(const cJSON *v);
bool dbui_valid_id(const char *s);

#endif
