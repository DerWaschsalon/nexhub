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

typedef enum { IT_BUTTON, IT_TOGGLE, IT_SLIDER, IT_MEDIA, IT_DPS, IT_CLAUDE, IT_GUIDE } it_type_t;


typedef struct {
    lv_obj_t *row;   /* Zeile (Hintergrundspur) */
    lv_obj_t *bar;   /* Balken in Klassenfarbe, Breite = DPS relativ zum Besten */
    lv_obj_t *name;
    lv_obj_t *val;   /* DPS */
    lv_obj_t *extra; /* Anteil oder Gesamtschaden */
    /* zuletzt gesetzte Werte: Style-Setter lassen LVGL immer neu zeichnen, und das Panel nimmt nur
     * ganze Frames an (220 KB über QSPI). Deshalb nur bei Änderung setzen. */
    int32_t bar_px;
    lv_color_t color;
    bool color_set;
    bool you;
} dps_row_t;

/* DPS-Kachel: Kopfzeile (Ziel, HP, Zeit) und bis zu 8 vorab angelegte Zeilen */
typedef struct {
    int n;          /* angelegte Zeilen */
    int extra;      /* 0 = Anteil, 1 = Schaden, 2 = nichts */
    int32_t bar_w;  /* volle Balkenbreite */
    lv_obj_t *target;
    lv_obj_t *time;
    lv_obj_t *hp_track; /* dünne Spur unter der Kopfzeile … */
    lv_obj_t *hp;       /* … mit den Rest-HP des Bosses */
    int32_t hp_w;
    int32_t hp_px;  /* zuletzt gesetzte HP-Breite */
    lv_obj_t *msg;  /* „nicht verbunden“ / „Warte auf Kampf“ */
    dps_row_t rows[DECKBAR_DPS_MAX_ROWS];
} dps_view_t;

/* Claude-Kachel: je Limit (Sitzung, Woche) eine Zeile [Name  Balken  Prozent  Reset] */
typedef struct {
    lv_obj_t *fill;
    lv_obj_t *pct;
    lv_obj_t *reset;
} usage_row_t;

typedef struct {
    int32_t bar_w;
    usage_row_t rows[2];
} claude_view_t;

/* Guide-Kachel: Kopfzeile (Akt · Stufe · XP, Schritt, Knöpfe) und die Zeilen des aktuellen Schritts */
typedef struct {
    lv_obj_t *head;
    lv_obj_t *step;
    lv_obj_t *body; /* eine Beschriftung mit Farbbefehlen („#FEC076 Zone#“), Zeilen durch \n getrennt */
    lv_obj_t *msg;
} guide_view_t;

typedef struct {
    char id[ID_LEN];
    it_type_t type;
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
    dps_view_t *dps;   /* DPS-Kachel */
    claude_view_t *claude;
    guide_view_t *guide;

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
} tile_t;

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
void dbui_build_button(tile_t *t, int32_t w, int32_t h, const char *label);
void dbui_build_media(tile_t *t, int32_t w, int32_t h);
void dbui_build_slider(tile_t *t, int32_t w, int32_t h, const char *label);
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

/* ui_tile_claude.c */
void dbui_build_claude(tile_t *t, int32_t w, int32_t h);
void dbui_claude_update(tile_t *t);

/* ui_tile_dps.c */
void dbui_build_dps(tile_t *t, int32_t w, int32_t h, int players, const char *extra);
void dbui_dps_update(tile_t *t);
void dbui_set_hidden(lv_obj_t *o, bool hidden);
void dbui_set_text(lv_obj_t *l, const char *txt);

/* ui_tile_guide.c */
void dbui_build_guide(tile_t *t, int32_t w, int32_t h);
void dbui_guide_update(tile_t *t);

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
