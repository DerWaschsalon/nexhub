/*
 * NexBoard-UI: rendert das vom Daemon geschickte Layout, spiegelt den State und meldet
 * Touch-Ereignisse zurück. Enthält keinerlei Hardware-Code (siehe deckbar/hal.h).
 */
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

#define MAX_PAGES 8
#define MAX_ITEMS_PER_PAGE 24
#define ID_LEN 33
#define LONG_PRESS_MS 600
#define SLIDER_SEND_MS 50     /* max. 20 Slider-Events pro Sekunde */
#define SLIDER_SETTLE_MS 700  /* nach dem Loslassen veraltete Werte vom Daemon ignorieren */
#define TOGGLE_REVERT_MS 1500 /* optimistischer Toggle ohne Bestätigung -> zurück */
#define DRAG_THRESHOLD 6
#define HELLO_TIMEOUT_MS 5000
#define CACHE_KEY "layout"
#define BG_KEY "bg"          /* Hintergrund im Flash: nach einem Neustart nicht erneut übertragen */
#define BG_MAGIC "DBG1"
/* Binärframe mit einem Bildteil: "DB", Art ('a' Cover, 'b' Hintergrund), id (16 Byte, mit Nullen
 * aufgefüllt), w, h, y, rows (je uint16 little endian), dann rows*w*2 Byte RGB565 */
#define BIN_HEAD 27

typedef enum { IT_BUTTON, IT_TOGGLE, IT_SLIDER, IT_MEDIA, IT_DPS, IT_CLAUDE } it_type_t;

#define DPS_MAX_ROWS 8

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
    dps_row_t rows[DPS_MAX_ROWS];
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
    char id[2][17];
    int front;          /* angezeigter Puffer, -1 = keins */
    int32_t back_rows;  /* bereits empfangene Zeilen im hinteren Puffer */
} img_rx_t;

static struct {
    deckbar_config_t cfg;
    cJSON *state;           /* aktueller State (Objekt) */
    char layout_hash[65];
    bool have_layout;

    tile_t *tiles;
    int tile_count;

    lv_obj_t *bg;
    lv_obj_t *tv;
    lv_obj_t *pages[MAX_PAGES];
    char page_ids[MAX_PAGES][ID_LEN];
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
} ui;

/* ======================================================================= Hilfen */

static void copy_str(char *dst, size_t n, const char *src)
{
    if (!src) src = "";
    size_t l = strlen(src);
    if (l >= n) l = n - 1;
    memcpy(dst, src, l);
    dst[l] = 0;
}

static bool valid_id(const char *s)
{
    if (!s || !*s || strlen(s) >= ID_LEN) return false;
    for (; *s; s++) {
        char c = *s;
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-'))
            return false;
    }
    return true;
}

static const char *jstr(const cJSON *o, const char *key)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, key);
    return cJSON_IsString(v) ? v->valuestring : NULL;
}

static int jint(const cJSON *o, const char *key, int def)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, key);
    return cJSON_IsNumber(v) ? (int)v->valuedouble : def;
}

static bool truthy(const cJSON *v)
{
    if (!v || cJSON_IsNull(v)) return false;
    if (cJSON_IsBool(v)) return cJSON_IsTrue(v);
    if (cJSON_IsNumber(v)) return v->valuedouble != 0;
    if (cJSON_IsString(v)) return v->valuestring[0] != 0;
    return true;
}

static const char *glyph_or_default(const char *name, const char *fallback)
{
    const char *g = deckbar_icon_glyph(name);
    if (!g && name && *name) LV_LOG_WARN("unbekanntes Icon '%s'", name);
    return g ? g : deckbar_icon_glyph(fallback);
}

static lv_obj_t *plain_obj(lv_obj_t *parent)
{
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_style_all(o);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    return o;
}

static lv_obj_t *text_label(lv_obj_t *parent, const lv_font_t *font, const char *txt)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_obj_remove_style_all(l);
    /* Farbe wird von der Kachel geerbt (tint/active) */
    lv_obj_set_style_text_font(l, font, 0);
    lv_label_set_text(l, txt ? txt : "");
    return l;
}

/* ======================================================================= Senden */

static void send_raw(const char *s)
{
    if (!ui.ws_open) return;
    deckbar_hal_send(s, strlen(s));
}

static void send_event(const char *event, const char *item, const char *part, const int32_t *value, int final)
{
    char buf[192];
    int n = snprintf(buf, sizeof buf, "{\"v\":%d,\"type\":\"event\",\"event\":\"%s\"", DECKBAR_PROTO_VERSION, event);
    if (item) n += snprintf(buf + n, sizeof buf - n, ",\"item\":\"%s\"", item);
    if (part) n += snprintf(buf + n, sizeof buf - n, ",\"part\":\"%s\"", part);
    if (value) n += snprintf(buf + n, sizeof buf - n, ",\"value\":%ld", (long)*value);
    if (final >= 0) n += snprintf(buf + n, sizeof buf - n, ",\"final\":%s", final ? "true" : "false");
    snprintf(buf + n, sizeof buf - n, "}");
    send_raw(buf);
}

static void send_page_change(const char *page)
{
    char buf[96];
    snprintf(buf, sizeof buf, "{\"v\":%d,\"type\":\"event\",\"event\":\"page_change\",\"page\":\"%s\"}",
             DECKBAR_PROTO_VERSION, page);
    send_raw(buf);
}

/* ======================================================================= Status-Anzeige */

static void update_status_ui(void)
{
    const char *txt = "";
    lv_color_t dot = lv_color_hex(0xFF9F0A);
    switch (ui.net) {
    case DECKBAR_NET_NO_WIFI: txt = "Kein WLAN"; dot = lv_color_hex(0xFF453A); break;
    case DECKBAR_NET_SEARCHING: txt = ui.ws_open ? "Verbinde …" : "Suche Daemon …"; break;
    case DECKBAR_NET_AUTH_FAILED: txt = "Token abgelehnt"; dot = lv_color_hex(0xFF453A); break;
    case DECKBAR_NET_ONLINE: txt = "Verbunden"; dot = lv_color_hex(0x30D158); break;
    }
    bool online = ui.net == DECKBAR_NET_ONLINE;

    lv_label_set_text(ui.pill_label, txt);
    lv_obj_set_style_bg_color(ui.pill_dot, dot, 0);
    if (online || !ui.have_layout) lv_obj_add_flag(ui.pill, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_remove_flag(ui.pill, LV_OBJ_FLAG_HIDDEN);

    if (ui.have_layout) {
        lv_obj_add_flag(ui.splash, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_remove_flag(ui.splash, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(ui.splash_status, online ? "Warte auf Layout …" : txt);
        lv_label_set_text(ui.splash_detail, ui.detail);
    }
}

static void set_net(deckbar_net_t n)
{
    if (ui.net == n) return;
    ui.net = n;
    update_status_ui();
}

static void build_status_ui(void)
{
    lv_obj_t *top = lv_layer_top();

    ui.pill = plain_obj(top);
    lv_obj_add_style(ui.pill, &db_theme.pill, 0);
    lv_obj_set_size(ui.pill, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_align(ui.pill, LV_ALIGN_TOP_RIGHT, -10, 6);
    lv_obj_set_flex_flow(ui.pill, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(ui.pill, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(ui.pill, 6, 0);
    lv_obj_remove_flag(ui.pill, LV_OBJ_FLAG_CLICKABLE);
    ui.pill_dot = plain_obj(ui.pill);
    lv_obj_set_size(ui.pill_dot, 8, 8);
    lv_obj_set_style_radius(ui.pill_dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(ui.pill_dot, LV_OPA_COVER, 0);
    ui.pill_label = text_label(ui.pill, &db_font_small, "");

    ui.splash = plain_obj(top);
    lv_obj_add_style(ui.splash, &db_theme.glass, 0);
    lv_obj_set_size(ui.splash, 380, 120);
    lv_obj_center(ui.splash);
    lv_obj_remove_flag(ui.splash, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_flex_flow(ui.splash, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(ui.splash, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_row(ui.splash, 4, 0);
    lv_obj_t *icon = text_label(ui.splash, &db_icons_28, deckbar_icon_glyph("view-grid"));
    lv_obj_set_style_text_color(icon, db_theme_color(DB_STYLE_ACCENT), 0);
    text_label(ui.splash, &db_font_title, "NexBoard");
    ui.splash_status = text_label(ui.splash, &db_font_label, "");
    ui.splash_detail = text_label(ui.splash, &db_font_small, "");
    lv_obj_add_style(ui.splash_detail, &db_theme.text_dim, 0);
}

/* ======================================================================= Cover */

static int b64_val(unsigned char c)
{
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

/* dekodiert höchstens max Bytes, liefert die Anzahl oder -1 bei ungültigen Zeichen */
static int32_t b64_decode(const char *in, uint8_t *out, int32_t max)
{
    int32_t n = 0;
    uint32_t acc = 0;
    int bits = 0;
    for (; *in && *in != '='; in++) {
        int v = b64_val((unsigned char)*in);
        if (v < 0) return -1;
        acc = (acc << 6) | (uint32_t)v;
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            if (n >= max) return -1;
            out[n++] = (uint8_t)(acc >> bits);
        }
    }
    return n;
}

static void media_show_cover(tile_t *t)
{
    if (!t->cover) return;
    int f = ui.art.front;
    if (f < 0) {
        lv_obj_add_flag(t->cover, LV_OBJ_FLAG_HIDDEN);
        if (t->icon) lv_obj_remove_flag(t->icon, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    const lv_image_dsc_t *d = &ui.art.dsc[f];
    lv_image_set_src(t->cover, d);
    /* Daemon liefert die Größe der größten Media-Kachel; kleinere skalieren herunter */
    if ((int32_t)d->header.w != t->cover_px) lv_image_set_scale(t->cover, (uint32_t)(256 * t->cover_px / d->header.w));
    else lv_image_set_scale(t->cover, LV_SCALE_NONE);
    lv_obj_remove_flag(t->cover, LV_OBJ_FLAG_HIDDEN);
    if (t->icon) lv_obj_add_flag(t->icon, LV_OBJ_FLAG_HIDDEN);
}

static void art_apply_all(void)
{
    for (int i = 0; i < ui.tile_count; i++)
        if (ui.tiles[i].type == IT_MEDIA) media_show_cover(&ui.tiles[i]);
}

/* Fordert das Cover in der Größe der größten Media-Kachel an (nach Layout und welcome). */
static void request_art(void)
{
    int32_t px = 0;
    for (int i = 0; i < ui.tile_count; i++)
        if (ui.tiles[i].type == IT_MEDIA && ui.tiles[i].cover_px > px) px = ui.tiles[i].cover_px;
    if (!px || ui.net != DECKBAR_NET_ONLINE) return;
    char buf[96];
    int f = ui.art.front;
    /* have: dieses Cover in dieser Größe ist schon da, der Daemon schickt es dann nicht nochmal */
    if (f >= 0 && (int32_t)ui.art.dsc[f].header.w == px)
        snprintf(buf, sizeof buf, "{\"v\":%d,\"type\":\"art_request\",\"size\":%ld,\"have\":\"%s\"}",
                 DECKBAR_PROTO_VERSION, (long)px, ui.art.id[f]);
    else
        snprintf(buf, sizeof buf, "{\"v\":%d,\"type\":\"art_request\",\"size\":%ld}", DECKBAR_PROTO_VERSION,
                 (long)px);
    send_raw(buf);
}

/*
 * Prüft einen Teil eines RGB565-Bilds und liefert die Stelle im hinteren Puffer, an die seine
 * Zeilen gehören (NULL = verwerfen). Danach img_rx_done().
 */
static uint8_t *img_rx_target(img_rx_t *rx, const char *id, int32_t w, int32_t h, int32_t y, int32_t rows,
                              int32_t min_w, int32_t max_w, int32_t max_h)
{
    if (w < min_w || w > max_w || h < 1 || h > max_h || y < 0 || rows <= 0 || y + rows > h) return NULL;

    int f = rx->front;
    /* dasselbe Bild nochmal (z. B. nach Neuverbindung): nichts tun */
    if (f >= 0 && !strcmp(rx->id[f], id) && (int32_t)rx->dsc[f].header.w == w && (int32_t)rx->dsc[f].header.h == h)
        return NULL;

    int b = f == 0 ? 1 : 0;
    lv_image_dsc_t *d = &rx->dsc[b];
    uint32_t bytes = (uint32_t)(w * h * 2);
    if (strcmp(rx->id[b], id) || d->header.w != (uint32_t)w || d->header.h != (uint32_t)h || y == 0) {
        if (d->data_size != bytes || !rx->buf[b]) {
            lv_free(rx->buf[b]);
            rx->buf[b] = lv_malloc(bytes);
        }
        lv_image_cache_drop(d);
        memset(d, 0, sizeof *d);
        rx->id[b][0] = 0;
        if (!rx->buf[b]) return NULL;
        d->header.magic = LV_IMAGE_HEADER_MAGIC;
        d->header.cf = LV_COLOR_FORMAT_RGB565;
        d->header.w = (uint32_t)w;
        d->header.h = (uint32_t)h;
        d->header.stride = (uint32_t)(w * 2);
        d->data_size = bytes;
        d->data = rx->buf[b];
        copy_str(rx->id[b], sizeof rx->id[b], id);
        rx->back_rows = 0;
    }
    return rx->buf[b] + y * w * 2;
}

/* Nach dem Schreiben eines Teils: 1, wenn das Bild damit vollständig ist (vorderer Puffer
 * gewechselt), sonst 0. */
static int img_rx_done(img_rx_t *rx, int32_t y, int32_t rows, int32_t h)
{
    int b = rx->front == 0 ? 1 : 0;
    rx->back_rows += rows;
    if (y + rows == h && rx->back_rows >= h) {
        rx->front = b;
        return 1;
    }
    return 0;
}

/*
 * Nimmt einen Teil eines RGB565-Bilds als JSON (`art`, `bg`, Daten in base64) an. Liefert 1, wenn
 * das Bild damit vollständig ist, -1 bei `id: ""` (kein Bild mehr), sonst 0.
 */
static int img_rx_chunk(img_rx_t *rx, const cJSON *msg, int32_t min_w, int32_t max_w, int32_t max_h)
{
    const char *id = jstr(msg, "id");
    if (!id || !*id) {
        rx->front = -1;
        return -1;
    }
    int32_t w = jint(msg, "w", 0), h = jint(msg, "h", 0);
    int32_t y = jint(msg, "y", -1), rows = jint(msg, "rows", 0);
    const char *data = jstr(msg, "data");
    if (!data || strlen(id) > 16) return 0;
    uint8_t *dst = img_rx_target(rx, id, w, h, y, rows, min_w, max_w, max_h);
    if (!dst) return 0;
    int32_t want = rows * w * 2;
    if (b64_decode(data, dst, want) != want) return 0;
    return img_rx_done(rx, y, rows, h);
}

static uint16_t le16(const uint8_t *p)
{
    return (uint16_t)(p[0] | p[1] << 8);
}

static void bg_store(void)
{
    if (ui.bgi.front < 0) {
        deckbar_hal_store_bin(BG_KEY, NULL, 0, NULL, 0); /* Standardbild: Gespeichertes löschen */
        return;
    }
    const lv_image_dsc_t *d = &ui.bgi.dsc[ui.bgi.front];
    uint8_t head[24] = BG_MAGIC;
    memcpy(head + 4, ui.bgi.id[ui.bgi.front], 16);
    head[20] = (uint8_t)d->header.w;
    head[21] = (uint8_t)(d->header.w >> 8);
    head[22] = (uint8_t)d->header.h;
    head[23] = (uint8_t)(d->header.h >> 8);
    if (!deckbar_hal_store_bin(BG_KEY, head, sizeof head, d->data, d->data_size))
        LV_LOG_WARN("Hintergrund nicht gespeichert");
}

/* Gespeicherten Hintergrund beim Start laden; seine id geht im hello mit. */
static void bg_restore(void)
{
    size_t len = 0;
    uint8_t *raw = deckbar_hal_load_bin(BG_KEY, &len);
    if (!raw) return;
    uint32_t w = 0, h = 0;
    char id[17] = {0};
    if (len >= 24) {
        w = le16(raw + 20);
        h = le16(raw + 22);
        memcpy(id, raw + 4, 16);
    }
    uint8_t *dst = len >= 24 && !memcmp(raw, BG_MAGIC, 4) && len == 24 + w * h * 2 && *id
                       ? img_rx_target(&ui.bgi, id, (int32_t)w, (int32_t)h, 0, (int32_t)h, DECKBAR_W, DECKBAR_W,
                                       DECKBAR_H)
                       : NULL;
    if (dst) {
        memcpy(dst, raw + 24, w * h * 2);
        if (img_rx_done(&ui.bgi, 0, (int32_t)h, (int32_t)h)) lv_image_set_src(ui.bg, &ui.bgi.dsc[ui.bgi.front]);
    } else LV_LOG_WARN("gespeicherter Hintergrund ungültig");
    free(raw);
}

static void handle_art(const cJSON *msg)
{
    if (img_rx_chunk(&ui.art, msg, 8, 160, 160) != 0) art_apply_all();
}

static void bg_apply(int r)
{
    if (r == 0) return;
    lv_image_set_src(ui.bg, r > 0 ? (const void *)&ui.bgi.dsc[ui.bgi.front] : (const void *)&deckbar_bg_default);
    bg_store();
}

static void handle_bg(const cJSON *msg)
{
    bg_apply(img_rx_chunk(&ui.bgi, msg, DECKBAR_W, DECKBAR_W, DECKBAR_H));
}

void deckbar_ui_net_binary(const uint8_t *data, size_t len)
{
    ui.last_rx = lv_tick_get();
    if (len < BIN_HEAD || data[0] != 'D' || data[1] != 'B') return;
    char id[17] = {0};
    memcpy(id, data + 3, 16);
    int32_t w = le16(data + 19), h = le16(data + 21), y = le16(data + 23), rows = le16(data + 25);
    if (!*id || len != BIN_HEAD + (size_t)(rows * w * 2)) return;
    if (data[2] == 'a') {
        uint8_t *dst = img_rx_target(&ui.art, id, w, h, y, rows, 8, 160, 160);
        if (!dst) return;
        memcpy(dst, data + BIN_HEAD, (size_t)(rows * w * 2));
        if (img_rx_done(&ui.art, y, rows, h)) art_apply_all();
    } else if (data[2] == 'b') {
        uint8_t *dst = img_rx_target(&ui.bgi, id, w, h, y, rows, DECKBAR_W, DECKBAR_W, DECKBAR_H);
        if (!dst) return;
        memcpy(dst, data + BIN_HEAD, (size_t)(rows * w * 2));
        bg_apply(img_rx_done(&ui.bgi, y, rows, h));
    }
}

/* ======================================================================= Kacheln: Zustände */

static void slider_show(tile_t *t, int32_t v)
{
    t->value_cur = v;
    int32_t range = t->max - t->min;
    int32_t pct = range > 0 ? (v - t->min) * 100 / range : 0;
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    int32_t w = lv_obj_get_width(t->obj);
    lv_obj_set_width(t->fill, (w * pct) / 100);
    if (t->value) lv_label_set_text_fmt(t->value, "%ld%%", (long)v);
}

static void fill_anim_cb(void *var, int32_t v)
{
    slider_show((tile_t *)var, v);
}

static void slider_animate_to(tile_t *t, int32_t v)
{
    t->value_target = v;
    lv_anim_delete(t, fill_anim_cb);
    if (v == t->value_cur) return;
    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, t);
    lv_anim_set_values(&a, t->value_cur, v);
    lv_anim_set_duration(&a, 220);
    lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
    lv_anim_set_exec_cb(&a, fill_anim_cb);
    lv_anim_start(&a);
}

static void tile_set_checked(tile_t *t, bool on)
{
    t->checked = on;
    if (on) lv_obj_add_state(t->obj, LV_STATE_CHECKED);
    else lv_obj_remove_state(t->obj, LV_STATE_CHECKED);
    if (t->icon && t->glyph_on) lv_label_set_text(t->icon, on ? t->glyph_on : t->glyph);
}

static void tile_set_muted(tile_t *t, bool muted)
{
    t->muted = muted;
    if (muted) {
        lv_obj_add_state(t->obj, DB_STATE_MUTED);
        lv_obj_add_state(t->fill, DB_STATE_MUTED);
    } else {
        lv_obj_remove_state(t->obj, DB_STATE_MUTED);
        lv_obj_remove_state(t->fill, DB_STATE_MUTED);
    }
    if (t->icon && t->glyph_on) lv_label_set_text(t->icon, muted ? t->glyph_on : t->glyph);
    if (t->value) lv_obj_set_style_text_opa(t->value, muted ? 120 : LV_OPA_COVER, 0);
}

static void media_update(tile_t *t)
{
    const cJSON *track = cJSON_GetObjectItemCaseSensitive(ui.state, "track");
    bool playing = truthy(cJSON_GetObjectItemCaseSensitive(ui.state, "playing"));
    const char *title = cJSON_IsObject(track) ? jstr(track, "title") : NULL;
    const char *artist = cJSON_IsObject(track) ? jstr(track, "artist") : NULL;

    if (title && *title) {
        lv_label_set_long_mode(t->title, LV_LABEL_LONG_SCROLL_CIRCULAR);
        lv_label_set_text(t->title, title);
        lv_obj_set_style_text_opa(t->title, LV_OPA_COVER, 0);
    } else {
        lv_label_set_long_mode(t->title, LV_LABEL_LONG_DOT);
        lv_label_set_text(t->title, "Nichts läuft");
        lv_obj_set_style_text_opa(t->title, 150, 0);
    }
    bool has_artist = artist && *artist;
    lv_label_set_text(t->artist, has_artist ? artist : "");
    /* einzeiliges Layout: Titel (+ Interpret) als Block vertikal zentrieren */
    if (t->flat) {
        int32_t h = lv_obj_get_height(t->obj);
        int32_t lt = lv_font_get_line_height(&db_font_title);
        int32_t ls = lv_font_get_line_height(&db_font_small);
        int32_t block = has_artist ? lt + 2 + ls : lt;
        int32_t y = (h - block) / 2;
        lv_obj_set_y(t->title, y);
        lv_obj_set_y(t->artist, y + lt + 2);
    }
    if (t->play) lv_label_set_text(t->play, deckbar_icon_glyph(playing ? "pause" : "play"));
    if (t->icon) lv_obj_set_style_text_opa(t->icon, playing ? LV_OPA_COVER : 140, 0);
}

static void dps_update(tile_t *t);
static void claude_update(tile_t *t);

static void apply_state_key(const char *key, const cJSON *val)
{
    bool media = !strcmp(key, "track") || !strcmp(key, "playing");
    uint32_t now = lv_tick_get();
    for (int i = 0; i < ui.tile_count; i++) {
        tile_t *t = &ui.tiles[i];
        if (t->type == IT_MEDIA) {
            if (media) media_update(t);
            continue;
        }
        if (t->type == IT_DPS) {
            if (!strcmp(key, "dps")) dps_update(t);
            continue;
        }
        if (t->type == IT_CLAUDE) {
            if (!strcmp(key, "claude")) claude_update(t);
            continue;
        }
        if (t->bind[0] && !strcmp(t->bind, key)) {
            if (t->type == IT_TOGGLE) {
                if (t->timer) {
                    lv_timer_delete(t->timer);
                    t->timer = NULL;
                }
                tile_set_checked(t, truthy(val));
            } else if (t->type == IT_SLIDER && cJSON_IsNumber(val)) {
                int32_t v = (int32_t)val->valuedouble;
                /* Beim Ziehen und kurz danach gewinnt der Finger */
                if (!t->dragging && (int32_t)(now - t->settle_until) >= 0) slider_animate_to(t, v);
            }
        }
        if (t->mute_bind[0] && !strcmp(t->mute_bind, key)) tile_set_muted(t, truthy(val));
    }
}

static void apply_full_state(void)
{
    const cJSON *it;
    cJSON_ArrayForEach(it, ui.state) apply_state_key(it->string, it);
    for (int i = 0; i < ui.tile_count; i++) {
        if (ui.tiles[i].type == IT_MEDIA) media_update(&ui.tiles[i]);
        if (ui.tiles[i].type == IT_DPS) dps_update(&ui.tiles[i]);
        if (ui.tiles[i].type == IT_CLAUDE) claude_update(&ui.tiles[i]);
    }
}

/* ======================================================================= Kacheln: Events */

static void toggle_revert_cb(lv_timer_t *tm)
{
    tile_t *t = lv_timer_get_user_data(tm);
    t->timer = NULL;
    tile_set_checked(t, truthy(cJSON_GetObjectItemCaseSensitive(ui.state, t->bind)));
}

static void go_to_page(int idx, bool anim);

static void tile_event_cb(lv_event_t *e)
{
    tile_t *t = lv_event_get_user_data(e);
    lv_event_code_t code = lv_event_get_code(e);

    if (code == LV_EVENT_SHORT_CLICKED) {
        if (t->nav[0]) {
            for (int i = 0; i < ui.page_count; i++)
                if (!strcmp(ui.page_ids[i], t->nav)) go_to_page(i, true);
            return;
        }
        if (ui.net != DECKBAR_NET_ONLINE) return;
        if (t->type == IT_TOGGLE) {
            /* optimistisch umschalten; der Daemon bestätigt per state */
            tile_set_checked(t, !t->checked);
            if (t->timer) lv_timer_delete(t->timer);
            t->timer = lv_timer_create(toggle_revert_cb, TOGGLE_REVERT_MS, t);
            lv_timer_set_repeat_count(t->timer, 1);
        }
        send_event("button_press", t->id, t->type == IT_MEDIA ? "toggle" : NULL, NULL, -1);
    } else if (code == LV_EVENT_LONG_PRESSED) {
        if (!t->nav[0]) send_event("long_press", t->id, NULL, NULL, -1);
    }
}

static void media_part_cb(lv_event_t *e)
{
    tile_t *t = lv_event_get_user_data(e);
    lv_obj_t *btn = lv_event_get_current_target(e);
    const char *part = lv_obj_get_user_data(btn);
    send_event("button_press", t->id, part, NULL, -1);
}

static void settle_done_cb(lv_timer_t *tm)
{
    tile_t *t = lv_timer_get_user_data(tm);
    t->timer = NULL;
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(ui.state, t->bind);
    if (cJSON_IsNumber(v)) slider_animate_to(t, (int32_t)v->valuedouble);
}

static void slider_event_cb(lv_event_t *e)
{
    tile_t *t = lv_event_get_user_data(e);
    lv_event_code_t code = lv_event_get_code(e);
    lv_indev_t *indev = lv_indev_active();
    lv_point_t p = {0, 0};
    if (indev) lv_indev_get_point(indev, &p);
    uint32_t now = lv_tick_get();

    switch (code) {
    case LV_EVENT_PRESSED:
        lv_anim_delete(t, fill_anim_cb);
        t->dragging = true;
        t->moved = false;
        t->long_fired = false;
        t->press_x = p.x;
        t->press_value = t->value_cur;
        t->last_sent_value = t->value_cur;
        if (t->timer) {
            lv_timer_delete(t->timer);
            t->timer = NULL;
        }
        break;
    case LV_EVENT_PRESSING: {
        int32_t dx = p.x - t->press_x;
        if (!t->moved && LV_ABS(dx) > DRAG_THRESHOLD) t->moved = true;
        if (!t->moved || t->long_fired) break;
        /* relatives Ziehen: volle Kachelbreite = voller Wertebereich */
        int32_t w = lv_obj_get_width(t->obj) - 2 * DRAG_THRESHOLD;
        int32_t v = t->press_value + (dx * (t->max - t->min)) / (w > 1 ? w : 1);
        v = LV_CLAMP(t->min, v, t->max);
        if (v != t->value_cur) slider_show(t, v);
        if (v != t->last_sent_value && (now - t->last_send) >= SLIDER_SEND_MS && ui.net == DECKBAR_NET_ONLINE) {
            send_event("slider_change", t->id, NULL, &v, 0);
            t->last_send = now;
            t->last_sent_value = v;
        }
        break;
    }
    case LV_EVENT_LONG_PRESSED:
        if (!t->moved) {
            t->long_fired = true;
            send_event("long_press", t->id, NULL, NULL, -1);
        }
        break;
    case LV_EVENT_RELEASED:
    case LV_EVENT_PRESS_LOST:
        t->dragging = false;
        if (t->moved && !t->long_fired) {
            int32_t v = t->value_cur;
            send_event("slider_change", t->id, NULL, &v, 1);
            t->settle_until = now + SLIDER_SETTLE_MS;
            t->timer = lv_timer_create(settle_done_cb, SLIDER_SETTLE_MS, t);
            lv_timer_set_repeat_count(t->timer, 1);
        }
        break;
    default: break;
    }
}

/* ======================================================================= Kacheln: Aufbau */

static void add_highlight(lv_obj_t *tile, int32_t w)
{
    lv_obj_t *h = plain_obj(tile);
    lv_obj_add_style(h, &db_theme.highlight, 0);
    lv_obj_set_size(h, w - 2 * DB_RADIUS, 1);
    lv_obj_align(h, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_add_flag(h, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_remove_flag(h, LV_OBJ_FLAG_CLICKABLE);
}

static lv_obj_t *make_tile_obj(lv_obj_t *page, tile_t *t, int32_t x, int32_t y, int32_t w, int32_t h)
{
    lv_obj_t *o = plain_obj(page);
    lv_obj_add_style(o, &db_theme.glass, 0);
    /* Bei Toggles bestimmt style nur den aktiven Zustand */
    if (t->type != IT_TOGGLE) lv_obj_add_style(o, &db_theme.tint[t->style], 0);
    lv_obj_add_style(o, &db_theme.glass_pressed, LV_STATE_PRESSED);
    lv_obj_add_style(o, &db_theme.active[t->style], LV_STATE_CHECKED);
    lv_obj_set_pos(o, x, y);
    lv_obj_set_size(o, w, h);
    lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
    add_highlight(o, w);
    t->obj = o;
    return o;
}

static void build_button(tile_t *t, int32_t w, int32_t h, const char *label)
{
    lv_obj_t *o = t->obj;
    bool big = h >= 100;
    bool row = !big && w >= 150;
    const lv_font_t *ifont = big ? &db_icons_40 : (h < 60 ? &db_icons_20 : &db_icons_28);

    lv_obj_set_flex_flow(o, row ? LV_FLEX_FLOW_ROW : LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(o, row ? LV_FLEX_ALIGN_START : LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_hor(o, row ? 16 : 6, 0);
    lv_obj_set_style_pad_row(o, big ? 8 : 3, 0);
    lv_obj_set_style_pad_column(o, 12, 0);

    if (t->glyph) t->icon = text_label(o, ifont, t->glyph);
    /* Beschriftung erbt die Textfarbe der Kachel (tint/active) */
    if (label && *label && h >= 60) {
        t->label = lv_label_create(o);
        lv_obj_remove_style_all(t->label);
        lv_label_set_text(t->label, label);
        lv_label_set_long_mode(t->label, LV_LABEL_LONG_DOT);
        lv_obj_set_style_text_align(t->label, row ? LV_TEXT_ALIGN_LEFT : LV_TEXT_ALIGN_CENTER, 0);
        /* feste Höhe = eine Zeile, sonst bricht LONG_DOT um statt abzuschneiden */
        lv_obj_set_size(t->label, row ? 1 : w - 12, lv_font_get_line_height(&db_font_label));
        if (row) lv_obj_set_flex_grow(t->label, 1);
    }
    lv_obj_add_event_cb(o, tile_event_cb, LV_EVENT_SHORT_CLICKED, t);
    lv_obj_add_event_cb(o, tile_event_cb, LV_EVENT_LONG_PRESSED, t);
}

static void build_slider(tile_t *t, int32_t w, int32_t h, const char *label)
{
    lv_obj_t *o = t->obj;
    lv_obj_set_style_clip_corner(o, true, 0);
    /* Wischen auf dem Slider darf nicht die Seite wechseln */
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLL_CHAIN | LV_OBJ_FLAG_GESTURE_BUBBLE);
    lv_obj_add_flag(o, LV_OBJ_FLAG_PRESS_LOCK);

    t->fill = plain_obj(o);
    lv_obj_add_style(t->fill, &db_theme.fill, 0);
    lv_obj_add_style(t->fill, &db_theme.fill_muted, DB_STATE_MUTED);
    lv_obj_set_style_radius(t->fill, 0, 0);
    lv_obj_set_size(t->fill, 0, LV_PCT(100));
    lv_obj_align(t->fill, LV_ALIGN_LEFT_MID, 0, 0);
    lv_obj_remove_flag(t->fill, LV_OBJ_FLAG_CLICKABLE);
    /* Lichtkante über die Füllung legen */
    lv_obj_move_to_index(t->fill, 0);

    bool compact = w < 150;
    const lv_font_t *ifont = h < 60 ? &db_icons_20 : &db_icons_28;
    if (t->glyph) {
        t->icon = text_label(o, ifont, t->glyph);
        lv_obj_align(t->icon, compact ? LV_ALIGN_TOP_LEFT : LV_ALIGN_LEFT_MID, compact ? 10 : 14, compact ? 8 : 0);
    }
    if (!compact && label && *label && h >= 60) {
        t->label = text_label(o, &db_font_label, label);
        lv_obj_align(t->label, LV_ALIGN_LEFT_MID, t->glyph ? 52 : 16, 0);
    }
    t->value = text_label(o, compact ? &db_font_label : &db_font_value, "");
    lv_obj_align(t->value, compact ? LV_ALIGN_BOTTOM_RIGHT : LV_ALIGN_RIGHT_MID, compact ? -10 : -16, compact ? -8 : 0);

    lv_obj_add_event_cb(o, slider_event_cb, LV_EVENT_ALL, t);
    t->value_cur = t->min;
    slider_show(t, t->min);
}

static lv_obj_t *mini_button(lv_obj_t *parent, tile_t *t, const char *glyph, const char *part, int32_t size)
{
    lv_obj_t *b = plain_obj(parent);
    lv_obj_add_style(b, &db_theme.mini, 0);
    lv_obj_add_style(b, &db_theme.mini_pressed, LV_STATE_PRESSED);
    lv_obj_set_size(b, size, size);
    lv_obj_add_flag(b, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_user_data(b, (void *)part);
    lv_obj_t *l = text_label(b, size >= 44 ? &db_icons_28 : &db_icons_20, glyph);
    lv_obj_center(l);
    lv_obj_add_event_cb(b, media_part_cb, LV_EVENT_SHORT_CLICKED, t);
    return l;
}

/* Cover-Kasten mit Platzhalter-Note; das Bild selbst kommt per `art` vom Daemon */
static void build_cover(tile_t *t, int32_t x, int32_t y, int32_t px)
{
    lv_obj_t *box = plain_obj(t->obj);
    lv_obj_set_size(box, px, px);
    lv_obj_set_pos(box, x, y);
    lv_obj_set_style_radius(box, px >= 60 ? 10 : 7, 0);
    lv_obj_set_style_clip_corner(box, true, 0);
    lv_obj_set_style_bg_color(box, lv_color_white(), 0);
    lv_obj_set_style_bg_opa(box, 22, 0);
    lv_obj_remove_flag(box, LV_OBJ_FLAG_CLICKABLE);

    t->icon = text_label(box, px >= 56 ? &db_icons_28 : &db_icons_20, deckbar_icon_glyph("music-note"));
    lv_obj_set_style_text_color(t->icon, db_theme_color(DB_STYLE_ACCENT), 0);
    lv_obj_center(t->icon);

    t->cover = lv_image_create(box);
    lv_obj_set_size(t->cover, px, px);
    lv_image_set_inner_align(t->cover, LV_IMAGE_ALIGN_CENTER);
    lv_obj_center(t->cover);
    lv_obj_add_flag(t->cover, LV_OBJ_FLAG_HIDDEN);
    t->cover_px = px;
}

/*
 * Media-Kachel
 *   hoch (h >= 140):  [Cover] Titel/Interpret, darunter ⏮ ⏯ ⏭
 *   flach (sonst):    [Cover] Titel/Interpret ........ ⏮ ⏯ ⏭  (schmal: nur ⏯)
 * Alles wird aus w/h berechnet, damit sich nichts überlappt.
 */
static void build_media(tile_t *t, int32_t w, int32_t h)
{
    lv_obj_t *o = t->obj;
    const int32_t m = 8; /* Rand um das Cover */
    int32_t lt = lv_font_get_line_height(&db_font_title);
    int32_t ls = lv_font_get_line_height(&db_font_small);
    bool tall = h >= 140;
    int32_t text_x, text_w, cover;

    if (tall) {
        const int32_t bar_h = 60;
        cover = LV_CLAMP(0, h - bar_h - 3 * m, 96);
        if (cover > w / 3) cover = w / 3;
        if (cover < 32) cover = 0;
        if (cover) build_cover(t, m, m, cover);
        text_x = cover ? m + cover + 12 : 16;
        text_w = w - text_x - 14;
        int32_t block = lt + 2 + ls;
        int32_t ty = cover ? m + (cover - block) / 2 : 14;
        t->title = text_label(o, &db_font_title, "");
        lv_obj_set_size(t->title, text_w, lt);
        lv_obj_set_pos(t->title, text_x, ty);
        t->artist = text_label(o, &db_font_small, "");
        lv_obj_set_size(t->artist, text_w, ls);
        lv_obj_set_pos(t->artist, text_x, ty + lt + 2);

        lv_obj_t *bar = plain_obj(o);
        lv_obj_set_size(bar, w - 24, bar_h);
        lv_obj_align(bar, LV_ALIGN_BOTTOM_MID, 0, -m);
        lv_obj_set_flex_flow(bar, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(bar, LV_FLEX_ALIGN_SPACE_EVENLY, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        mini_button(bar, t, deckbar_icon_glyph("skip-previous"), "prev", 48);
        t->play = mini_button(bar, t, deckbar_icon_glyph("play"), "toggle", 56);
        mini_button(bar, t, deckbar_icon_glyph("skip-next"), "next", 48);
    } else {
        t->flat = true;
        cover = LV_MIN(h - 2 * m, 120);
        if (cover < 24 || w < 3 * cover) cover = 0;
        if (cover) build_cover(t, m, (h - cover) / 2, cover);
        text_x = cover ? m + cover + 12 : 16;

        /* Steuerung rechts: drei Tasten, wenn genug Platz für Text bleibt, sonst nur ⏯ */
        int32_t bs = LV_CLAMP(32, h - 2 * m, 44);    /* ⏮ ⏭ */
        int32_t ps = LV_CLAMP(36, h - 2 * m, 52);    /* ⏯ */
        int32_t three = bs + ps + bs + 2 * 6;
        bool full = w - text_x - three - 22 >= 120;
        int32_t ctrl_w = full ? three : ps;
        lv_obj_t *bar = plain_obj(o);
        lv_obj_set_size(bar, ctrl_w, ps);
        lv_obj_align(bar, LV_ALIGN_RIGHT_MID, -10, 0);
        lv_obj_set_flex_flow(bar, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(bar, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        if (full) mini_button(bar, t, deckbar_icon_glyph("skip-previous"), "prev", bs);
        t->play = mini_button(bar, t, deckbar_icon_glyph("play"), "toggle", ps);
        if (full) mini_button(bar, t, deckbar_icon_glyph("skip-next"), "next", bs);

        text_w = w - text_x - ctrl_w - 10 - 12;
        t->title = text_label(o, &db_font_title, "");
        lv_obj_set_size(t->title, text_w, lt);
        lv_obj_set_x(t->title, text_x);
        t->artist = text_label(o, &db_font_small, "");
        lv_obj_set_size(t->artist, text_w, ls);
        lv_obj_set_x(t->artist, text_x);
    }
    lv_obj_add_style(t->artist, &db_theme.text_dim, 0);
    lv_label_set_long_mode(t->artist, LV_LABEL_LONG_DOT);
    lv_obj_add_event_cb(o, tile_event_cb, LV_EVENT_SHORT_CLICKED, t);
    media_show_cover(t);
}

/* ======================================================================= DPS (AION 2) */

static lv_color_t class_color(const char *cls)
{
    static const struct {
        const char *name;
        uint32_t rgb;
    } map[] = {
        {"gladiator", 0xE8A33D}, {"templar", 0x5B8DEF},      {"ranger", 0x6CCB5F},
        {"assassin", 0xB46AE6},  {"sorcerer", 0x4FC3F7},     {"cleric", 0xF4E07A},
        {"spiritmaster", 0xEC7FB8}, {"chanter", 0x4DD4B0}, {"brawler", 0xF0624D},
    };
    for (size_t i = 0; cls && i < sizeof map / sizeof map[0]; i++)
        if (!strcmp(map[i].name, cls)) return lv_color_hex(map[i].rgb);
    return lv_color_hex(0x8E8E93);
}

/* 8432 · 18,4k · 1,23M (deutsche Schreibweise) */
static void fmt_amount(char *buf, size_t n, double v)
{
    if (v < 0) v = 0;
    if (v >= 1e9) snprintf(buf, n, "%.2fG", v / 1e9);
    else if (v >= 1e6) snprintf(buf, n, "%.2fM", v / 1e6);
    else if (v >= 1e4) snprintf(buf, n, "%.1fk", v / 1e3);
    else snprintf(buf, n, "%.0f", v);
    for (char *c = buf; *c; c++)
        if (*c == '.') *c = ',';
}

/* nur bei Änderung neu setzen: jedes Neuzeichnen ist ein ganzer Frame */
static void set_text(lv_obj_t *l, const char *txt)
{
    if (strcmp(lv_label_get_text(l), txt)) lv_label_set_text(l, txt);
}

static void set_hidden(lv_obj_t *o, bool hidden)
{
    if (hidden) lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_remove_flag(o, LV_OBJ_FLAG_HIDDEN);
}

static void dps_update(tile_t *t)
{
    dps_view_t *v = t->dps;
    if (!v) return;
    const cJSON *d = cJSON_GetObjectItemCaseSensitive(ui.state, "dps");
    const cJSON *rows = cJSON_IsObject(d) ? cJSON_GetObjectItemCaseSensitive(d, "rows") : NULL;
    int count = cJSON_IsArray(rows) ? cJSON_GetArraySize(rows) : 0;
    char buf[48];

    if (v->target) {
        const char *target = cJSON_IsObject(d) ? jstr(d, "target") : NULL;
        set_text(v->target, target && *target ? target : "AION 2");
        int secs = cJSON_IsObject(d) ? jint(d, "time", 0) : 0;
        const cJSON *hp = cJSON_IsObject(d) ? cJSON_GetObjectItemCaseSensitive(d, "hp") : NULL;
        if (!count) buf[0] = 0;
        else if (cJSON_IsNumber(hp))
            snprintf(buf, sizeof buf, "%.0f %% · %d:%02d", hp->valuedouble, secs / 60, secs % 60);
        else snprintf(buf, sizeof buf, "%d:%02d", secs / 60, secs % 60);
        set_text(v->time, buf);
        if (count && cJSON_IsNumber(hp)) {
            int32_t w = LV_MAX((int32_t)(v->hp_w * LV_CLAMP(0.0, hp->valuedouble, 100.0) / 100.0), 1);
            if (w != v->hp_px) {
                lv_obj_set_width(v->hp, w);
                v->hp_px = w;
            }
            set_hidden(v->hp_track, false);
        } else set_hidden(v->hp_track, true);
    }

    set_text(v->msg, !cJSON_IsObject(d) ? "DPS-Meter nicht verbunden" : "Warte auf Kampf …");
    set_hidden(v->msg, count > 0);

    double best = 1;
    for (int i = 0; i < count && i < v->n; i++) {
        const cJSON *x = cJSON_GetObjectItemCaseSensitive(cJSON_GetArrayItem(rows, i), "dps");
        if (cJSON_IsNumber(x) && x->valuedouble > best) best = x->valuedouble;
    }
    for (int i = 0; i < v->n; i++) {
        dps_row_t *r = &v->rows[i];
        const cJSON *jr = i < count ? cJSON_GetArrayItem(rows, i) : NULL;
        set_hidden(r->row, !cJSON_IsObject(jr));
        if (!cJSON_IsObject(jr)) continue;
        const cJSON *dps = cJSON_GetObjectItemCaseSensitive(jr, "dps");
        double x = cJSON_IsNumber(dps) ? dps->valuedouble : 0;
        const char *name = jstr(jr, "name");
        snprintf(buf, sizeof buf, "%d  %s", i + 1, name ? name : "?");
        set_text(r->name, buf);
        fmt_amount(buf, sizeof buf, x);
        set_text(r->val, buf);
        if (r->extra) {
            if (v->extra == 0) {
                const cJSON *pct = cJSON_GetObjectItemCaseSensitive(jr, "pct");
                snprintf(buf, sizeof buf, "%.0f %%", cJSON_IsNumber(pct) ? pct->valuedouble : 0.0);
            } else {
                const cJSON *dmg = cJSON_GetObjectItemCaseSensitive(jr, "dmg");
                fmt_amount(buf, sizeof buf, cJSON_IsNumber(dmg) ? dmg->valuedouble : 0);
            }
            set_text(r->extra, buf);
        }
        int32_t bar_px = LV_MAX((int32_t)(v->bar_w * x / best), 6);
        if (bar_px != r->bar_px) {
            lv_obj_set_width(r->bar, bar_px);
            r->bar_px = bar_px;
        }
        lv_color_t color = class_color(jstr(jr, "cls"));
        if (!r->color_set || !lv_color_eq(color, r->color)) {
            lv_obj_set_style_bg_color(r->bar, color, 0);
            r->color = color;
            r->color_set = true;
        }
        bool you = cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(jr, "you"));
        if (you != r->you) { /* angelegt ohne Rand (you = false) */
            lv_obj_set_style_border_opa(r->row, you ? 230 : LV_OPA_TRANSP, 0);
            r->you = you;
        }
    }
}

/*
 * DPS-Kachel
 *   ab h >= 90: Kopfzeile mit Ziel, HP und Kampfzeit, darunter dünner HP-Balken
 *   dann `players` Zeilen: [Rang Name ......... DPS  Anteil], Balken in Klassenfarbe
 */
static void build_dps(tile_t *t, int32_t w, int32_t h, int players, const char *extra)
{
    lv_obj_t *o = t->obj;
    lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_clip_corner(o, true, 0);
    dps_view_t *v = lv_malloc_zeroed(sizeof *v);
    if (!v) return;
    t->dps = v;
    v->extra = extra && !strcmp(extra, "dmg") ? 1 : extra && !strcmp(extra, "none") ? 2 : 0;

    const int32_t px = 10, gap = 3;
    int32_t y = 7;
    if (h >= 90) {
        int32_t ls = lv_font_get_line_height(&db_font_small);
        v->time = text_label(o, &db_font_small, "");
        lv_obj_add_style(v->time, &db_theme.text_dim, 0);
        lv_obj_align(v->time, LV_ALIGN_TOP_RIGHT, -px - 2, y);
        v->target = text_label(o, &db_font_small, "AION 2");
        lv_obj_add_style(v->target, &db_theme.text_dim, 0);
        lv_label_set_long_mode(v->target, LV_LABEL_LONG_DOT);
        lv_obj_set_size(v->target, w / 2 - px - 20, ls); /* endet vor dem Reset-Knopf */
        lv_obj_set_pos(v->target, px + 2, y);
        /* kleiner Knopf mittig in der Kopfzeile: Meter zurücksetzen */
        lv_obj_t *reset = lv_obj_get_parent(mini_button(o, t, deckbar_icon_glyph("restart"), "reset", 24));
        lv_obj_align(reset, LV_ALIGN_TOP_MID, 0, y - 5);
        y += ls + 3;
        v->hp_w = w - 2 * px;
        v->hp_track = plain_obj(o);
        lv_obj_set_size(v->hp_track, v->hp_w, 2);
        lv_obj_set_pos(v->hp_track, px, y);
        lv_obj_set_style_bg_color(v->hp_track, lv_color_white(), 0);
        lv_obj_set_style_bg_opa(v->hp_track, 28, 0);
        lv_obj_add_flag(v->hp_track, LV_OBJ_FLAG_HIDDEN);
        v->hp = plain_obj(v->hp_track);
        lv_obj_set_size(v->hp, v->hp_w, 2);
        lv_obj_set_style_bg_color(v->hp, lv_color_hex(0xFF453A), 0);
        lv_obj_set_style_bg_opa(v->hp, 210, 0);
        y += 2 + 4;
    }

    int32_t avail = h - y - 7;
    int n = LV_CLAMP(1, players, DPS_MAX_ROWS);
    while (n > 1 && (avail - (n - 1) * gap) / n < 16) n--;
    /* wenige Spieler: höhere Zeilen und größere Schrift */
    int32_t row_h = LV_MIN((avail - (n - 1) * gap) / n, 40);
    const lv_font_t *font = row_h >= 34 ? &db_font_title : row_h >= 20 ? &db_font_label : &db_font_small;
    int32_t extra_w = v->extra == 2 ? 0 : (v->extra == 1 ? 58 : 44);
    v->n = n;
    v->bar_w = w - 2 * px;

    for (int i = 0; i < n; i++) {
        dps_row_t *r = &v->rows[i];
        r->row = plain_obj(o);
        lv_obj_set_size(r->row, v->bar_w, row_h);
        lv_obj_set_pos(r->row, px, y + i * (row_h + gap));
        lv_obj_set_style_radius(r->row, 7, 0);
        lv_obj_set_style_clip_corner(r->row, true, 0);
        lv_obj_set_style_bg_color(r->row, lv_color_white(), 0);
        lv_obj_set_style_bg_opa(r->row, 14, 0);
        /* Rahmen in Akzentfarbe markiert die eigene Zeile */
        lv_obj_set_style_border_width(r->row, 1, 0);
        lv_obj_set_style_border_color(r->row, db_theme_color(DB_STYLE_ACCENT), 0);
        lv_obj_set_style_border_opa(r->row, LV_OPA_TRANSP, 0);

        r->bar = plain_obj(r->row);
        lv_obj_set_size(r->bar, 6, LV_PCT(100));
        lv_obj_set_style_radius(r->bar, 7, 0);
        lv_obj_set_style_bg_opa(r->bar, 120, 0);

        r->name = text_label(r->row, font, "");
        lv_label_set_long_mode(r->name, LV_LABEL_LONG_DOT);
        lv_obj_set_size(r->name, v->bar_w - 16 - extra_w - 64, lv_font_get_line_height(font));
        lv_obj_align(r->name, LV_ALIGN_LEFT_MID, 8, 0);

        if (extra_w) {
            r->extra = text_label(r->row, &db_font_small, "");
            lv_obj_add_style(r->extra, &db_theme.text_dim, 0);
            lv_obj_set_width(r->extra, extra_w);
            lv_obj_set_style_text_align(r->extra, LV_TEXT_ALIGN_RIGHT, 0);
            lv_obj_align(r->extra, LV_ALIGN_RIGHT_MID, -8, 0);
        }
        r->val = text_label(r->row, font, "");
        lv_obj_set_width(r->val, 64);
        lv_obj_set_style_text_align(r->val, LV_TEXT_ALIGN_RIGHT, 0);
        lv_obj_align(r->val, LV_ALIGN_RIGHT_MID, -8 - extra_w - (extra_w ? 6 : 0), 0);
        lv_obj_add_flag(r->row, LV_OBJ_FLAG_HIDDEN);
    }

    v->msg = text_label(o, &db_font_label, "");
    lv_obj_add_style(v->msg, &db_theme.text_dim, 0);
    lv_obj_align(v->msg, LV_ALIGN_CENTER, 0, v->target ? 8 : 0);
    dps_update(t);
}

/* Schlüssel im State `claude` und Beschriftung, in Zeilenreihenfolge (siehe daemon/claude.py) */
static const char *const CLAUDE_KEYS[2] = {"session", "week"};
static const char *const CLAUDE_NAMES[2] = {"5 h", "Woche"};

static void claude_update(tile_t *t)
{
    claude_view_t *v = t->claude;
    if (!v) return;
    const cJSON *c = cJSON_GetObjectItemCaseSensitive(ui.state, "claude");
    char buf[8];
    for (int i = 0; i < 2; i++) {
        usage_row_t *r = &v->rows[i];
        const cJSON *jr = cJSON_IsObject(c) ? cJSON_GetObjectItemCaseSensitive(c, CLAUDE_KEYS[i]) : NULL;
        const cJSON *jp = cJSON_IsObject(jr) ? cJSON_GetObjectItemCaseSensitive(jr, "pct") : NULL;
        if (!cJSON_IsNumber(jp)) {
            lv_obj_set_width(r->fill, 0);
            lv_label_set_text(r->pct, "–");
            if (r->reset) lv_label_set_text(r->reset, "");
            continue;
        }
        int32_t pct = LV_CLAMP(0, (int32_t)jp->valuedouble, 100);
        lv_obj_set_width(r->fill, v->bar_w * pct / 100);
        /* Farbe warnt, bevor das Limit erreicht ist */
        db_style_t s = pct >= 90 ? DB_STYLE_DANGER : pct >= 75 ? DB_STYLE_WARNING : DB_STYLE_ACCENT;
        lv_obj_set_style_bg_color(r->fill, db_theme_color(s), 0);
        lv_snprintf(buf, sizeof buf, "%d %%", (int)pct);
        lv_label_set_text(r->pct, buf);
        const char *reset = jstr(jr, "reset");
        if (r->reset) lv_label_set_text(r->reset, reset ? reset : "");
    }
}

/* Claude-Kachel: Auslastung des Claude-Abos, Werte kommen alle 5 Minuten vom Daemon */
static void build_claude(tile_t *t, int32_t w, int32_t h)
{
    lv_obj_t *o = t->obj;
    lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
    claude_view_t *v = lv_malloc_zeroed(sizeof *v);
    if (!v) return;
    t->claude = v;

    const int32_t px = 12, gap = 8, name_w = 40, pct_w = 36;
    /* Rücksetzzeit („Sa 01:00“) nur, wenn die Kachel breit genug ist */
    const int32_t reset_w = w >= 260 ? 60 : 0;
    const int32_t lh = lv_font_get_line_height(&db_font_small);
    v->bar_w = LV_MAX(w - 2 * px - name_w - pct_w - reset_w - (reset_w ? 3 : 2) * gap, 10);
    const int32_t bar_x = px + name_w + gap;
    const int32_t pct_x = bar_x + v->bar_w + gap;

    for (int i = 0; i < 2; i++) {
        usage_row_t *r = &v->rows[i];
        int32_t mid = h * (2 * i + 1) / 4; /* Mitte der oberen bzw. unteren Hälfte */

        lv_obj_t *name = text_label(o, &db_font_small, CLAUDE_NAMES[i]);
        lv_obj_add_style(name, &db_theme.text_dim, 0);
        lv_obj_set_pos(name, px, mid - lh / 2);

        lv_obj_t *track = plain_obj(o);
        lv_obj_set_size(track, v->bar_w, 6);
        lv_obj_set_pos(track, bar_x, mid - 3);
        lv_obj_set_style_radius(track, 3, 0);
        lv_obj_set_style_bg_color(track, lv_color_white(), 0);
        lv_obj_set_style_bg_opa(track, 28, 0);
        r->fill = plain_obj(track);
        lv_obj_set_size(r->fill, 0, 6);
        lv_obj_set_style_radius(r->fill, 3, 0);
        lv_obj_set_style_bg_opa(r->fill, 220, 0);

        r->pct = text_label(o, &db_font_small, "");
        lv_obj_set_width(r->pct, pct_w);
        lv_obj_set_style_text_align(r->pct, LV_TEXT_ALIGN_RIGHT, 0);
        lv_obj_set_pos(r->pct, pct_x, mid - lh / 2);

        if (reset_w) {
            r->reset = text_label(o, &db_font_small, "");
            lv_obj_add_style(r->reset, &db_theme.text_dim, 0);
            lv_obj_set_width(r->reset, reset_w);
            lv_obj_set_style_text_align(r->reset, LV_TEXT_ALIGN_RIGHT, 0);
            lv_obj_set_pos(r->reset, pct_x + pct_w + gap, mid - lh / 2);
        }
    }
    claude_update(t);
}

/* ======================================================================= Seiten */

static void update_dots(void)
{
    if (!ui.dots) return;
    uint32_t n = lv_obj_get_child_count(ui.dots);
    for (uint32_t i = 0; i < n; i++) {
        lv_obj_t *d = lv_obj_get_child(ui.dots, i);
        bool on = (int)i == ui.page_active;
        lv_obj_set_width(d, on ? 14 : 5);
        lv_obj_set_style_bg_opa(d, on ? 230 : 110, 0);
    }
}

static void go_to_page(int idx, bool anim)
{
    if (idx < 0 || idx >= ui.page_count) return;
    lv_tileview_set_tile(ui.tv, ui.pages[idx], anim ? LV_ANIM_ON : LV_ANIM_OFF);
    if (idx != ui.page_active) {
        ui.page_active = idx;
        update_dots();
        send_page_change(ui.page_ids[idx]);
    }
}

static void tv_event_cb(lv_event_t *e)
{
    (void)e;
    lv_obj_t *act = lv_tileview_get_tile_active(ui.tv);
    for (int i = 0; i < ui.page_count; i++) {
        if (ui.pages[i] == act && i != ui.page_active) {
            ui.page_active = i;
            update_dots();
            send_page_change(ui.page_ids[i]);
        }
    }
}

static void free_tiles(void)
{
    for (int i = 0; i < ui.tile_count; i++) {
        tile_t *t = &ui.tiles[i];
        lv_anim_delete(t, fill_anim_cb);
        if (t->timer) lv_timer_delete(t->timer);
        lv_free(t->dps);
        lv_free(t->claude);
    }
    lv_free(ui.tiles);
    ui.tiles = NULL;
    ui.tile_count = 0;
}

static it_type_t parse_type(const char *s)
{
    if (s && !strcmp(s, "toggle")) return IT_TOGGLE;
    if (s && !strcmp(s, "slider")) return IT_SLIDER;
    if (s && !strcmp(s, "media")) return IT_MEDIA;
    if (s && !strcmp(s, "dps")) return IT_DPS;
    if (s && !strcmp(s, "claude")) return IT_CLAUDE;
    return IT_BUTTON;
}

/* Setzt die Items einer Seite zeilenweise in die erste freie Lücke (auto-flow dense). */
static void build_page(lv_obj_t *page, const cJSON *jp, int page_idx)
{
    int cols = LV_CLAMP(1, jint(jp, "cols", 6), 8);
    int rows = LV_CLAMP(1, jint(jp, "rows", 2), 3);
    bool used[3][8] = {{0}};
    const int32_t aw = DECKBAR_W - 2 * DB_PAD + DB_GAP;
    const int32_t ah = DECKBAR_H - 2 * DB_PAD + DB_GAP;

    const cJSON *items = cJSON_GetObjectItemCaseSensitive(jp, "items");
    const cJSON *ji;
    int count = 0;
    cJSON_ArrayForEach(ji, items)
    {
        if (count++ >= MAX_ITEMS_PER_PAGE) break;
        const char *id = jstr(ji, "id");
        if (!valid_id(id)) continue;
        int w = LV_CLAMP(1, jint(ji, "w", 1), cols);
        int h = LV_CLAMP(1, jint(ji, "h", 1), rows);

        int pr = -1, pc = -1;
        for (int r = 0; r + h <= rows && pr < 0; r++) {
            for (int c = 0; c + w <= cols && pr < 0; c++) {
                bool fits = true;
                for (int rr = r; rr < r + h && fits; rr++)
                    for (int cc = c; cc < c + w && fits; cc++) fits = !used[rr][cc];
                if (fits) {
                    pr = r;
                    pc = c;
                }
            }
        }
        if (pr < 0) {
            LV_LOG_WARN("Item '%s' passt nicht mehr auf die Seite", id);
            continue;
        }
        for (int rr = pr; rr < pr + h; rr++)
            for (int cc = pc; cc < pc + w; cc++) used[rr][cc] = true;

        /* Zellgrenzen ohne Rundungsdrift */
        int32_t x0 = DB_PAD + pc * aw / cols;
        int32_t x1 = DB_PAD + (pc + w) * aw / cols - DB_GAP;
        int32_t y0 = DB_PAD + pr * ah / rows;
        int32_t y1 = DB_PAD + (pr + h) * ah / rows - DB_GAP;
        int32_t pw = x1 - x0, ph = y1 - y0;

        tile_t *t = &ui.tiles[ui.tile_count++];
        memset(t, 0, sizeof *t);
        copy_str(t->id, sizeof t->id, id);
        t->type = parse_type(jstr(ji, "type"));
        t->style = db_style_parse(jstr(ji, "style"));
        copy_str(t->bind, sizeof t->bind, jstr(ji, "bind"));
        copy_str(t->mute_bind, sizeof t->mute_bind, jstr(ji, "mute_bind"));
        const char *nav = jstr(ji, "nav");
        if (valid_id(nav)) copy_str(t->nav, sizeof t->nav, nav);
        t->glyph = jstr(ji, "icon") ? glyph_or_default(jstr(ji, "icon"), "dots-horizontal") : NULL;
        t->glyph_on = jstr(ji, "icon_on") ? glyph_or_default(jstr(ji, "icon_on"), "dots-horizontal") : NULL;
        t->min = jint(ji, "min", 0);
        t->max = jint(ji, "max", 100);
        if (t->max <= t->min) t->max = t->min + 1;
        (void)page_idx;

        make_tile_obj(page, t, x0, y0, pw, ph);
        switch (t->type) {
        case IT_SLIDER: build_slider(t, pw, ph, jstr(ji, "label")); break;
        case IT_MEDIA: build_media(t, pw, ph); break;
        case IT_DPS: build_dps(t, pw, ph, jint(ji, "players", 5), jstr(ji, "extra")); break;
        case IT_CLAUDE: build_claude(t, pw, ph); break;
        default: build_button(t, pw, ph, jstr(ji, "label")); break;
        }
    }
}

static bool apply_layout(const cJSON *msg)
{
    const cJSON *pages = cJSON_GetObjectItemCaseSensitive(msg, "pages");
    int np = cJSON_GetArraySize(pages);
    if (!cJSON_IsArray(pages) || np < 1) {
        LV_LOG_WARN("Layout ohne Seiten verworfen");
        return false;
    }
    if (np > MAX_PAGES) np = MAX_PAGES;

    const cJSON *theme = cJSON_GetObjectItemCaseSensitive(msg, "theme");
    const char *accent = jstr(theme, "accent");
    if (accent && accent[0] == '#' && strlen(accent) == 7)
        db_theme_set_accent(lv_color_hex((uint32_t)strtoul(accent + 1, NULL, 16)));

    /* Seite merken, damit ein Live-Update nicht auf Seite 1 zurückspringt */
    char prev_page[ID_LEN] = "";
    if (ui.page_count) copy_str(prev_page, sizeof prev_page, ui.page_ids[ui.page_active]);

    /* erst Objekte löschen (Event-Callbacks sehen noch gültige tile_t), dann die Structs */
    if (ui.tv) lv_obj_delete(ui.tv);
    if (ui.dots) lv_obj_delete(ui.dots);
    free_tiles();
    ui.tv = NULL;
    ui.dots = NULL;
    ui.page_count = 0;
    ui.page_active = 0;
    ui.tiles = lv_malloc_zeroed(sizeof(tile_t) * np * MAX_ITEMS_PER_PAGE);

    ui.tv = lv_tileview_create(lv_screen_active());
    lv_obj_set_size(ui.tv, DECKBAR_W, DECKBAR_H);
    lv_obj_set_style_bg_opa(ui.tv, LV_OPA_TRANSP, 0);
    lv_obj_set_scrollbar_mode(ui.tv, LV_SCROLLBAR_MODE_OFF);
    lv_obj_add_event_cb(ui.tv, tv_event_cb, LV_EVENT_VALUE_CHANGED, NULL);

    int idx = 0;
    const cJSON *jp;
    cJSON_ArrayForEach(jp, pages)
    {
        if (idx >= np) break;
        const char *pid = jstr(jp, "id");
        if (!valid_id(pid)) continue;
        lv_dir_t dir = (idx > 0 ? LV_DIR_LEFT : 0) | (idx < np - 1 ? LV_DIR_RIGHT : 0);
        lv_obj_t *page = lv_tileview_add_tile(ui.tv, (uint8_t)idx, 0, dir);
        lv_obj_set_style_bg_opa(page, LV_OPA_TRANSP, 0);
        lv_obj_set_scrollbar_mode(page, LV_SCROLLBAR_MODE_OFF);
        lv_obj_remove_flag(page, LV_OBJ_FLAG_SCROLLABLE);
        ui.pages[idx] = page;
        copy_str(ui.page_ids[idx], ID_LEN, pid);
        build_page(page, jp, idx);
        idx++;
    }
    ui.page_count = idx;

    if (ui.page_count > 1) {
        ui.dots = plain_obj(lv_screen_active());
        lv_obj_set_size(ui.dots, LV_SIZE_CONTENT, 5);
        lv_obj_align(ui.dots, LV_ALIGN_BOTTOM_MID, 0, -1);
        lv_obj_set_flex_flow(ui.dots, LV_FLEX_FLOW_ROW);
        lv_obj_set_style_pad_column(ui.dots, 5, 0);
        lv_obj_remove_flag(ui.dots, LV_OBJ_FLAG_CLICKABLE);
        for (int i = 0; i < ui.page_count; i++) {
            lv_obj_t *d = plain_obj(ui.dots);
            lv_obj_set_size(d, 5, 5);
            lv_obj_set_style_radius(d, LV_RADIUS_CIRCLE, 0);
            lv_obj_set_style_bg_color(d, lv_color_white(), 0);
        }
    }

    for (int i = 0; i < ui.page_count; i++)
        if (prev_page[0] && !strcmp(ui.page_ids[i], prev_page)) {
            ui.page_active = i;
            lv_tileview_set_tile(ui.tv, ui.pages[i], LV_ANIM_OFF);
        }
    update_dots();

    lv_obj_update_layout(ui.tv);
    for (int i = 0; i < ui.tile_count; i++)
        if (ui.tiles[i].type == IT_SLIDER) slider_show(&ui.tiles[i], ui.tiles[i].value_cur);
    apply_full_state();

    copy_str(ui.layout_hash, sizeof ui.layout_hash, jstr(msg, "hash"));
    ui.have_layout = true;
    update_status_ui();
    request_art();
    return true;
}

/* ======================================================================= Protokoll */

static void send_hello(void)
{
    cJSON *o = cJSON_CreateObject();
    cJSON_AddNumberToObject(o, "v", DECKBAR_PROTO_VERSION);
    cJSON_AddStringToObject(o, "type", "hello");
    cJSON_AddStringToObject(o, "token", ui.cfg.token ? ui.cfg.token : "");
    if (ui.layout_hash[0]) cJSON_AddStringToObject(o, "layout_hash", ui.layout_hash);
    if (ui.page_count) cJSON_AddStringToObject(o, "page", ui.page_ids[ui.page_active]);
    if (ui.bgi.front >= 0) cJSON_AddStringToObject(o, "bg_id", ui.bgi.id[ui.bgi.front]);
    /* bin: Bildteile auch als Binärframes (deckbar_ui_net_binary) */
    cJSON_AddItemToArray(cJSON_AddArrayToObject(o, "caps"), cJSON_CreateString("bin"));
    cJSON *d = cJSON_AddObjectToObject(o, "device");
    cJSON_AddStringToObject(d, "id", ui.cfg.device_id ? ui.cfg.device_id : "deckbar");
    cJSON_AddStringToObject(d, "model", ui.cfg.model ? ui.cfg.model : "");
    cJSON_AddStringToObject(d, "fw", ui.cfg.fw ? ui.cfg.fw : "");
    cJSON_AddNumberToObject(d, "width", DECKBAR_W);
    cJSON_AddNumberToObject(d, "height", DECKBAR_H);
    cJSON_AddBoolToObject(d, "sim", ui.cfg.sim);
    char *s = cJSON_PrintUnformatted(o);
    cJSON_Delete(o);
    if (s) {
        send_raw(s);
        cJSON_free(s);
    }
}

static void handle_state(const cJSON *msg)
{
    const cJSON *values = cJSON_GetObjectItemCaseSensitive(msg, "values");
    if (!cJSON_IsObject(values)) return;
    bool full = cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(msg, "full"));
    if (full) {
        cJSON_Delete(ui.state);
        ui.state = cJSON_Duplicate(values, true);
        apply_full_state();
        return;
    }
    const cJSON *it;
    cJSON_ArrayForEach(it, values)
    {
        cJSON *dup = cJSON_Duplicate(it, true);
        if (cJSON_GetObjectItemCaseSensitive(ui.state, it->string))
            cJSON_ReplaceItemInObjectCaseSensitive(ui.state, it->string, dup);
        else
            cJSON_AddItemToObject(ui.state, it->string, dup);
        apply_state_key(it->string, it);
    }
}

void deckbar_ui_net_message(const char *text, size_t len)
{
    ui.last_rx = lv_tick_get();
    cJSON *msg = cJSON_ParseWithLength(text, len);
    if (!msg) {
        LV_LOG_WARN("ungültiges JSON empfangen");
        return;
    }
    const char *type = jstr(msg, "type");
    if (jint(msg, "v", 0) != DECKBAR_PROTO_VERSION || !type) {
        LV_LOG_WARN("Nachricht mit falscher Version ignoriert");
    } else if (!strcmp(type, "ping")) {
        char buf[64];
        const cJSON *t = cJSON_GetObjectItemCaseSensitive(msg, "t");
        snprintf(buf, sizeof buf, "{\"v\":%d,\"type\":\"pong\",\"t\":%.0f}", DECKBAR_PROTO_VERSION,
                 cJSON_IsNumber(t) ? t->valuedouble : 0.0);
        send_raw(buf);
    } else if (!strcmp(type, "state")) {
        handle_state(msg);
    } else if (!strcmp(type, "art")) {
        handle_art(msg);
    } else if (!strcmp(type, "bg")) {
        handle_bg(msg);
    } else if (!strcmp(type, "goto")) {
        const char *page = jstr(msg, "page");
        for (int i = 0; page && i < ui.page_count; i++)
            if (!strcmp(ui.page_ids[i], page)) go_to_page(i, true);
    } else if (!strcmp(type, "layout")) {
        if (apply_layout(msg)) deckbar_hal_store(CACHE_KEY, text, len);
    } else if (!strcmp(type, "welcome")) {
        ui.heartbeat_s = LV_CLAMP(1, jint(msg, "heartbeat", 5), 60);
        set_net(DECKBAR_NET_ONLINE);
        request_art();
    } else if (!strcmp(type, "error")) {
        const char *code = jstr(msg, "code");
        LV_LOG_WARN("Daemon meldet Fehler %s: %s", code ? code : "?", jstr(msg, "message") ? jstr(msg, "message") : "");
        if (code && !strcmp(code, "auth")) set_net(DECKBAR_NET_AUTH_FAILED);
    }
    cJSON_Delete(msg);
}

void deckbar_ui_net_connected(void)
{
    ui.ws_open = true;
    ui.last_rx = lv_tick_get();
    ui.hello_at = ui.last_rx;
    if (ui.net != DECKBAR_NET_AUTH_FAILED) ui.net = DECKBAR_NET_SEARCHING;
    update_status_ui();
    send_hello();
}

void deckbar_ui_net_disconnected(bool no_wifi)
{
    ui.ws_open = false;
    /* "Token abgelehnt" stehen lassen, bis ein neuer Versuch klappt */
    if (ui.net == DECKBAR_NET_AUTH_FAILED && !no_wifi) {
        update_status_ui();
        return;
    }
    ui.net = no_wifi ? DECKBAR_NET_NO_WIFI : DECKBAR_NET_SEARCHING;
    update_status_ui();
}

void deckbar_ui_set_detail(const char *detail)
{
    copy_str(ui.detail, sizeof ui.detail, detail);
    update_status_ui();
}

deckbar_net_t deckbar_ui_net_state(void)
{
    return ui.net;
}

/* Heartbeat-Wächter: ohne Nachricht vom Daemon -> neu verbinden */
static void watchdog_cb(lv_timer_t *t)
{
    (void)t;
    if (!ui.ws_open) return;
    uint32_t idle = lv_tick_elaps(ui.last_rx);
    bool dead = (ui.net == DECKBAR_NET_ONLINE && idle > (uint32_t)ui.heartbeat_s * 3000u) ||
                (ui.net == DECKBAR_NET_SEARCHING && lv_tick_elaps(ui.hello_at) > HELLO_TIMEOUT_MS);
    if (dead) {
        LV_LOG_WARN("keine Antwort vom Daemon seit %lu ms – verbinde neu", (unsigned long)idle);
        ui.ws_open = false;
        ui.net = DECKBAR_NET_SEARCHING;
        update_status_ui();
        deckbar_hal_reconnect();
    }
}

/* ======================================================================= Init */

void deckbar_ui_init(const deckbar_config_t *cfg)
{
    memset(&ui, 0, sizeof ui);
    ui.cfg = *cfg;
    ui.heartbeat_s = 5;
    ui.net = DECKBAR_NET_SEARCHING;
    ui.state = cJSON_CreateObject();
    ui.art.front = -1;
    ui.bgi.front = -1;

    db_theme_init();

    /* 600 ms für long_press (Protokoll), gilt für alle Zeigergeräte */
    for (lv_indev_t *i = lv_indev_get_next(NULL); i; i = lv_indev_get_next(i))
        if (lv_indev_get_type(i) == LV_INDEV_TYPE_POINTER) lv_indev_set_long_press_time(i, LONG_PRESS_MS);

    lv_obj_t *scr = lv_screen_active();
    lv_obj_remove_style_all(scr);
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x0A0D1C), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    ui.bg = lv_image_create(scr);
    lv_image_set_src(ui.bg, &deckbar_bg_default);
    lv_obj_set_pos(ui.bg, 0, 0);
    bg_restore();

    build_status_ui();

    char *cached = deckbar_hal_load(CACHE_KEY);
    if (cached) {
        cJSON *msg = cJSON_Parse(cached);
        if (msg && !apply_layout(msg)) ui.layout_hash[0] = 0;
        cJSON_Delete(msg);
        free(cached);
    }
    update_status_ui();
    lv_timer_create(watchdog_cb, 1000, NULL);
}
