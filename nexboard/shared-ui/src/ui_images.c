/* NexBoard-UI · Bilder vom Daemon: Cover der Media-Kacheln und der Hintergrund, zeilenweise empfangen und im Flash gemerkt. */
#include "ui_internal.h"

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

void dbui_media_show_cover(tile_t *t)
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
        if (ui.tiles[i].type == IT_MEDIA) dbui_media_show_cover(&ui.tiles[i]);
}

/* Fordert das Cover in der Größe der größten Media-Kachel an (nach Layout und welcome). */
void dbui_request_art(void)
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
    dbui_send_raw(buf);
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
        dbui_copy_str(rx->id[b], sizeof rx->id[b], id);
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
    const char *id = dbui_jstr(msg, "id");
    if (!id || !*id) {
        rx->front = -1;
        return -1;
    }
    int32_t w = dbui_jint(msg, "w", 0), h = dbui_jint(msg, "h", 0);
    int32_t y = dbui_jint(msg, "y", -1), rows = dbui_jint(msg, "rows", 0);
    const char *data = dbui_jstr(msg, "data");
    if (!data || strlen(id) > DECKBAR_IMAGE_ID_MAX) return 0;
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
    memcpy(head + 4, ui.bgi.id[ui.bgi.front], DECKBAR_IMAGE_ID_MAX);
    head[20] = (uint8_t)d->header.w;
    head[21] = (uint8_t)(d->header.w >> 8);
    head[22] = (uint8_t)d->header.h;
    head[23] = (uint8_t)(d->header.h >> 8);
    if (!deckbar_hal_store_bin(BG_KEY, head, sizeof head, d->data, d->data_size))
        LV_LOG_WARN("Hintergrund nicht gespeichert");
}

/* Gespeicherten Hintergrund beim Start laden; seine id geht im hello mit. */
void dbui_bg_restore(void)
{
    size_t len = 0;
    uint8_t *raw = deckbar_hal_load_bin(BG_KEY, &len);
    if (!raw) return;
    uint32_t w = 0, h = 0;
    char id[IMAGE_ID_LEN] = {0};
    if (len >= 24) {
        w = le16(raw + 20);
        h = le16(raw + 22);
        memcpy(id, raw + 4, DECKBAR_IMAGE_ID_MAX);
    }
    uint8_t *dst = len >= 24 && !memcmp(raw, BG_MAGIC, 4) && len == 24 + w * h * 2 && *id
                       ? img_rx_target(&ui.bgi, id, (int32_t)w, (int32_t)h, 0, (int32_t)h, DECKBAR_SCREEN_W, DECKBAR_SCREEN_W,
                                       DECKBAR_SCREEN_H)
                       : NULL;
    if (dst) {
        memcpy(dst, raw + 24, w * h * 2);
        if (img_rx_done(&ui.bgi, 0, (int32_t)h, (int32_t)h)) lv_image_set_src(ui.bg, &ui.bgi.dsc[ui.bgi.front]);
    } else LV_LOG_WARN("gespeicherter Hintergrund ungültig");
    free(raw);
}

void dbui_handle_art(const cJSON *msg)
{
    if (img_rx_chunk(&ui.art, msg, DECKBAR_ART_MIN, DECKBAR_ART_MAX, DECKBAR_ART_MAX) != 0) art_apply_all();
}

static void bg_apply(int r)
{
    if (r == 0) return;
    lv_image_set_src(ui.bg, r > 0 ? (const void *)&ui.bgi.dsc[ui.bgi.front] : (const void *)&deckbar_bg_default);
    bg_store();
}

void dbui_handle_bg(const cJSON *msg)
{
    bg_apply(img_rx_chunk(&ui.bgi, msg, DECKBAR_SCREEN_W, DECKBAR_SCREEN_W, DECKBAR_SCREEN_H));
}

void deckbar_ui_net_binary(const uint8_t *data, size_t len)
{
    ui.last_rx = lv_tick_get();
    if (len < DECKBAR_BIN_HEADER_BYTES || data[0] != 'D' || data[1] != 'B') return;
    char id[IMAGE_ID_LEN] = {0};
    memcpy(id, data + 3, DECKBAR_IMAGE_ID_MAX);
    int32_t w = le16(data + 19), h = le16(data + 21), y = le16(data + 23), rows = le16(data + 25);
    if (!*id || len != DECKBAR_BIN_HEADER_BYTES + (size_t)(rows * w * 2)) return;
    if (data[2] == 'a') {
        uint8_t *dst = img_rx_target(&ui.art, id, w, h, y, rows, DECKBAR_ART_MIN, DECKBAR_ART_MAX, DECKBAR_ART_MAX);
        if (!dst) return;
        memcpy(dst, data + DECKBAR_BIN_HEADER_BYTES, (size_t)(rows * w * 2));
        if (img_rx_done(&ui.art, y, rows, h)) art_apply_all();
    } else if (data[2] == 'b') {
        uint8_t *dst = img_rx_target(&ui.bgi, id, w, h, y, rows, DECKBAR_SCREEN_W, DECKBAR_SCREEN_W, DECKBAR_SCREEN_H);
        if (!dst) return;
        memcpy(dst, data + DECKBAR_BIN_HEADER_BYTES, (size_t)(rows * w * 2));
        bg_apply(img_rx_done(&ui.bgi, y, rows, h));
    }
}
