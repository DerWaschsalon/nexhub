/*
 * DeckBar-Simulator: derselbe shared-ui-Code wie auf dem Gerät, in einem SDL-Fenster
 * 640x172 (RGB565). Mausklicks = Touch. Verbindet sich per WebSocket mit dem echten Daemon.
 */
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "deckbar/hal.h"
#include "deckbar/ui.h"
#include "lvgl.h"
#include "ws_client.h"

/* ------------------------------------------------------------------ Queue Netz -> LVGL */
typedef enum { Q_OPEN, Q_CLOSE, Q_MSG } qtype_t;
typedef struct qitem {
    qtype_t type;
    char *data;
    size_t len;
    struct qitem *next;
} qitem_t;

static pthread_mutex_t q_lock = PTHREAD_MUTEX_INITIALIZER;
static qitem_t *q_head, *q_tail;
static ws_client_t *ws;

static void q_push(qtype_t type, const char *data, size_t len)
{
    qitem_t *it = calloc(1, sizeof *it);
    it->type = type;
    if (data) {
        it->data = malloc(len + 1);
        memcpy(it->data, data, len);
        it->data[len] = 0;
        it->len = len;
    }
    pthread_mutex_lock(&q_lock);
    if (q_tail) q_tail->next = it;
    else q_head = it;
    q_tail = it;
    pthread_mutex_unlock(&q_lock);
}

static void q_drain(void)
{
    pthread_mutex_lock(&q_lock);
    qitem_t *it = q_head;
    q_head = q_tail = NULL;
    pthread_mutex_unlock(&q_lock);
    while (it) {
        qitem_t *next = it->next;
        if (it->type == Q_OPEN) deckbar_ui_net_connected();
        else if (it->type == Q_CLOSE) deckbar_ui_net_disconnected(false);
        else deckbar_ui_net_message(it->data, it->len);
        free(it->data);
        free(it);
        it = next;
    }
}

static void on_open(void *u) { (void)u; q_push(Q_OPEN, NULL, 0); }
static void on_close(void *u) { (void)u; q_push(Q_CLOSE, NULL, 0); }
static void on_message(void *u, const char *t, size_t l) { (void)u; q_push(Q_MSG, t, l); }

/* ------------------------------------------------------------------ HAL */
static char cache_dir[512];
static int verbose;

bool deckbar_hal_send(const char *text, size_t len)
{
    if (verbose) printf("-> %.*s\n", (int)len, text);
    return ws && ws_client_send_text(ws, text, len) == 0;
}

void deckbar_hal_reconnect(void)
{
    if (ws) ws_client_reconnect(ws);
}

bool deckbar_hal_store(const char *key, const char *data, size_t len)
{
    if (!cache_dir[0]) return false;
    char path[600], tmp[610];
    snprintf(path, sizeof path, "%s/%s.json", cache_dir, key);
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = fopen(tmp, "wb");
    if (!f) return false;
    bool ok = fwrite(data, 1, len, f) == len;
    ok = fclose(f) == 0 && ok;
    return ok && rename(tmp, path) == 0;
}

char *deckbar_hal_load(const char *key)
{
    if (!cache_dir[0]) return NULL;
    char path[600];
    snprintf(path, sizeof path, "%s/%s.json", cache_dir, key);
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = n > 0 && n < 1024 * 1024 ? malloc((size_t)n + 1) : NULL;
    if (buf && fread(buf, 1, (size_t)n, f) == (size_t)n) buf[n] = 0;
    else {
        free(buf);
        buf = NULL;
    }
    fclose(f);
    return buf;
}

/* ------------------------------------------------------------------ Skript-Zeiger (Tests) */
typedef struct {
    uint32_t at;
    int32_t x1, y1, x2, y2;
    uint32_t dur;
} gesture_t;

static gesture_t gestures[32];
static int gesture_count;
static uint32_t t0;

static void script_read(lv_indev_t *indev, lv_indev_data_t *data)
{
    (void)indev;
    uint32_t now = lv_tick_elaps(t0);
    data->state = LV_INDEV_STATE_RELEASED;
    for (int i = 0; i < gesture_count; i++) {
        gesture_t *g = &gestures[i];
        if (now >= g->at && now <= g->at + g->dur) {
            int32_t p = g->dur ? (int32_t)((now - g->at) * 1000 / g->dur) : 1000;
            data->point.x = g->x1 + (g->x2 - g->x1) * p / 1000;
            data->point.y = g->y1 + (g->y2 - g->y1) * p / 1000;
            data->state = LV_INDEV_STATE_PRESSED;
            return;
        }
        if (now > g->at + g->dur) {
            data->point.x = g->x2;
            data->point.y = g->y2;
        }
    }
}

/* "x,y@ms" = Tap, "x,y>x2,y2@ms" = Wischen/Ziehen (300 ms), "x,y@ms+dauer" = Halten */
static int parse_gesture(const char *s, gesture_t *g)
{
    memset(g, 0, sizeof *g);
    unsigned at = 0, dur = 0;
    if (sscanf(s, "%d,%d>%d,%d@%u", &g->x1, &g->y1, &g->x2, &g->y2, &at) == 5) {
        g->at = at;
        g->dur = 300;
        return 0;
    }
    int n = sscanf(s, "%d,%d@%u+%u", &g->x1, &g->y1, &at, &dur);
    if (n >= 3) {
        g->x2 = g->x1;
        g->y2 = g->y1;
        g->at = at;
        g->dur = n == 4 ? dur : 60;
        return 0;
    }
    return -1;
}

/* ------------------------------------------------------------------ Screenshot */
static int write_ppm(lv_display_t *disp, const char *path)
{
    lv_draw_buf_t *buf = lv_display_get_buf_active(disp);
    if (!buf) return -1;
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    int32_t w = lv_display_get_horizontal_resolution(disp);
    int32_t h = lv_display_get_vertical_resolution(disp);
    fprintf(f, "P6\n%d %d\n255\n", (int)w, (int)h);
    for (int32_t y = 0; y < h; y++) {
        const uint16_t *row = (const uint16_t *)(buf->data + y * buf->header.stride);
        for (int32_t x = 0; x < w; x++) {
            uint16_t c = row[x];
            unsigned char rgb[3] = {(unsigned char)(((c >> 11) & 0x1F) * 255 / 31),
                                    (unsigned char)(((c >> 5) & 0x3F) * 255 / 63),
                                    (unsigned char)((c & 0x1F) * 255 / 31)};
            fwrite(rgb, 1, 3, f);
        }
    }
    fclose(f);
    return 0;
}

/* ------------------------------------------------------------------ Hilfen */
static uint32_t tick_cb(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

static void mkdirs(const char *path)
{
    char tmp[512];
    snprintf(tmp, sizeof tmp, "%s", path);
    for (char *p = tmp + 1; *p; p++) {
        if (*p == '/') {
            *p = 0;
            mkdir(tmp, 0755);
            *p = '/';
        }
    }
    mkdir(tmp, 0755);
}

/* Token aus ~/.config/deckbar/config.yaml lesen (Zeile "token: …") */
static char *token_from_config(void)
{
    char path[512];
    const char *dir = getenv("DECKBAR_CONFIG_DIR");
    const char *xdg = getenv("XDG_CONFIG_HOME");
    const char *home = getenv("HOME");
    if (dir) snprintf(path, sizeof path, "%s/config.yaml", dir);
    else if (xdg) snprintf(path, sizeof path, "%s/deckbar/config.yaml", xdg);
    else snprintf(path, sizeof path, "%s/.config/deckbar/config.yaml", home ? home : ".");
    FILE *f = fopen(path, "r");
    if (!f) return NULL;
    char line[256], *tok = NULL;
    while (fgets(line, sizeof line, f)) {
        if (strncmp(line, "token:", 6) != 0) continue;
        char *s = line + 6;
        while (*s == ' ' || *s == '"' || *s == '\'') s++;
        char *e = s;
        while (*e && *e != '\n' && *e != ' ' && *e != '"' && *e != '\'' && *e != '#') e++;
        *e = 0;
        tok = strdup(s);
        break;
    }
    fclose(f);
    return tok;
}

static void usage(void)
{
    puts("deckbar-sim [Optionen]\n"
         "  --url ws://HOST:PORT/ws   Daemon (Standard ws://127.0.0.1:8765/ws)\n"
         "  --token TOKEN             Standard: aus ~/.config/deckbar/config.yaml\n"
         "  --zoom N                  Fenster vergrößern (1–4, Standard 2)\n"
         "  --no-perf                 FPS-/CPU-Anzeige ausblenden\n"
         "  --no-cache                Layout-Cache nicht laden/speichern\n"
         "  --screenshot DATEI.ppm    nach --after ms Bild speichern und beenden\n"
         "  --after MS                Standard 1500\n"
         "  --gesture G               Skript-Eingabe: \"x,y@ms\", \"x,y@ms+halten\", \"x,y>x2,y2@ms\"\n"
         "  -v                        gesendete Nachrichten ausgeben");
}

int main(int argc, char **argv)
{
    const char *url = "ws://127.0.0.1:8765/ws";
    char *token = NULL;
    int zoom = 2, perf = 1, use_cache = 1;
    const char *shot = NULL;
    uint32_t after = 1500;

    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        const char *next = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--url") && next) url = argv[++i];
        else if (!strcmp(a, "--token") && next) token = strdup(argv[++i]);
        else if (!strcmp(a, "--zoom") && next) zoom = atoi(argv[++i]);
        else if (!strcmp(a, "--no-perf")) perf = 0;
        else if (!strcmp(a, "--no-cache")) use_cache = 0;
        else if (!strcmp(a, "--screenshot") && next) shot = argv[++i];
        else if (!strcmp(a, "--after") && next) after = (uint32_t)atoi(argv[++i]);
        else if (!strcmp(a, "--gesture") && next) {
            if (gesture_count < 32 && parse_gesture(argv[++i], &gestures[gesture_count]) == 0) gesture_count++;
            else fprintf(stderr, "ungültige Geste: %s\n", argv[i]);
        } else if (!strcmp(a, "-v")) verbose = 1;
        else {
            usage();
            return !strcmp(a, "-h") || !strcmp(a, "--help") ? 0 : 1;
        }
    }
    if (zoom < 1 || zoom > 4) zoom = 2;
    if (!token) token = getenv("DECKBAR_TOKEN") ? strdup(getenv("DECKBAR_TOKEN")) : token_from_config();
    if (!token) fprintf(stderr, "Hinweis: kein Token gefunden (--token oder ~/.config/deckbar/config.yaml)\n");

    if (use_cache) {
        const char *xdg = getenv("XDG_CACHE_HOME");
        const char *home = getenv("HOME");
        if (xdg) snprintf(cache_dir, sizeof cache_dir, "%s/deckbar-sim", xdg);
        else snprintf(cache_dir, sizeof cache_dir, "%s/.cache/deckbar-sim", home ? home : ".");
        mkdirs(cache_dir);
    }

    lv_init();
    lv_tick_set_cb(tick_cb);
    lv_display_t *disp = lv_sdl_window_create(DECKBAR_W, DECKBAR_H);
    lv_sdl_window_set_zoom(disp, (uint8_t)zoom);
    lv_sdl_window_set_title(disp, "DeckBar Simulator");
    lv_sdl_mouse_create();
    if (gesture_count) {
        lv_indev_t *script = lv_indev_create();
        lv_indev_set_type(script, LV_INDEV_TYPE_POINTER);
        lv_indev_set_read_cb(script, script_read);
    }

    deckbar_config_t cfg = {
        .token = token,
        .device_id = "deckbar-sim",
        .model = "sdl-sim",
        .fw = "0.1.0",
        .sim = true,
    };
    deckbar_ui_init(&cfg);
    if (!perf || shot) {
        lv_sysmon_hide_performance(disp);
    }

    ws_callbacks_t cb = {on_open, on_close, on_message};
    ws = ws_client_start(url, &cb, NULL);
    if (!ws) return 1;
    deckbar_ui_set_detail(url);

    t0 = lv_tick_get();
    for (;;) {
        q_drain();
        uint32_t idle = lv_timer_handler();
        if (shot && lv_tick_elaps(t0) >= after) {
            lv_refr_now(disp);
            int rc = write_ppm(disp, shot);
            printf(rc == 0 ? "Screenshot: %s\n" : "Screenshot fehlgeschlagen: %s\n", shot);
            ws_client_stop(ws);
            return rc == 0 ? 0 : 1;
        }
        if (idle > 5) idle = 5;
        usleep(idle * 1000);
    }
}
