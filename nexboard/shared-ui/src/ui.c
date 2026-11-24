/*
 * NexBoard-UI: rendert das vom Daemon geschickte Layout, spiegelt den State und meldet
 * Touch-Ereignisse zurück. Enthält keinerlei Hardware-Code (siehe deckbar/hal.h).
 */
#include "ui_internal.h"

ui_state_t ui;

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
    cJSON_AddNumberToObject(d, "width", DECKBAR_SCREEN_W);
    cJSON_AddNumberToObject(d, "height", DECKBAR_SCREEN_H);
    cJSON_AddBoolToObject(d, "sim", ui.cfg.sim);
    char *s = cJSON_PrintUnformatted(o);
    cJSON_Delete(o);
    if (s) {
        dbui_send_raw(s);
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
        dbui_apply_full_state();
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
        dbui_apply_state_key(it->string, it);
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
    const char *type = dbui_jstr(msg, "type");
    if (dbui_jint(msg, "v", 0) != DECKBAR_PROTO_VERSION || !type) {
        LV_LOG_WARN("Nachricht mit falscher Version ignoriert");
    } else if (!strcmp(type, "ping")) {
        char buf[64];
        const cJSON *t = cJSON_GetObjectItemCaseSensitive(msg, "t");
        snprintf(buf, sizeof buf, "{\"v\":%d,\"type\":\"pong\",\"t\":%.0f}", DECKBAR_PROTO_VERSION,
                 cJSON_IsNumber(t) ? t->valuedouble : 0.0);
        dbui_send_raw(buf);
    } else if (!strcmp(type, "state")) {
        handle_state(msg);
    } else if (!strcmp(type, "art")) {
        dbui_handle_art(msg);
    } else if (!strcmp(type, "bg")) {
        dbui_handle_bg(msg);
    } else if (!strcmp(type, "goto")) {
        const char *page = dbui_jstr(msg, "page");
        for (int i = 0; page && i < ui.page_count; i++)
            if (!strcmp(ui.page_ids[i], page)) dbui_go_to_page(i);
    } else if (!strcmp(type, "layout")) {
        if (dbui_apply_layout(msg)) deckbar_hal_store(CACHE_KEY, text, len);
    } else if (!strcmp(type, "welcome")) {
        ui.heartbeat_s = LV_CLAMP(1, dbui_jint(msg, "heartbeat", 5), 60);
        dbui_set_net(DECKBAR_NET_ONLINE);
        dbui_request_art();
    } else if (!strcmp(type, "error")) {
        const char *code = dbui_jstr(msg, "code");
        LV_LOG_WARN("Daemon meldet Fehler %s: %s", code ? code : "?", dbui_jstr(msg, "message") ? dbui_jstr(msg, "message") : "");
        if (code && !strcmp(code, "auth")) dbui_set_net(DECKBAR_NET_AUTH_FAILED);
    }
    cJSON_Delete(msg);
}

void deckbar_ui_net_connected(void)
{
    ui.ws_open = true;
    ui.last_rx = lv_tick_get();
    ui.hello_at = ui.last_rx;
    if (ui.net != DECKBAR_NET_AUTH_FAILED) ui.net = DECKBAR_NET_SEARCHING;
    dbui_update_status_ui();
    send_hello();
}

void deckbar_ui_net_disconnected(bool no_wifi)
{
    ui.ws_open = false;
    /* "Token abgelehnt" stehen lassen, bis ein neuer Versuch klappt */
    if (ui.net == DECKBAR_NET_AUTH_FAILED && !no_wifi) {
        dbui_update_status_ui();
        return;
    }
    ui.net = no_wifi ? DECKBAR_NET_NO_WIFI : DECKBAR_NET_SEARCHING;
    dbui_update_status_ui();
}

void deckbar_ui_set_detail(const char *detail)
{
    dbui_copy_str(ui.detail, sizeof ui.detail, detail);
    dbui_update_status_ui();
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
                (ui.net == DECKBAR_NET_SEARCHING && lv_tick_elaps(ui.hello_at) > (DECKBAR_HELLO_TIMEOUT_S * 1000));
    if (dead) {
        LV_LOG_WARN("keine Antwort vom Daemon seit %lu ms – verbinde neu", (unsigned long)idle);
        ui.ws_open = false;
        ui.net = DECKBAR_NET_SEARCHING;
        dbui_update_status_ui();
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
    for (lv_indev_t *i = lv_indev_get_next(NULL); i; i = lv_indev_get_next(i))
        if (lv_indev_get_type(i) == LV_INDEV_TYPE_POINTER) lv_indev_add_event_cb(i, dbui_touch_cb, LV_EVENT_ALL, NULL);
    ui.state = cJSON_CreateObject();
    ui.art.front = -1;
    ui.bgi.front = -1;

    db_theme_init();

    /* 600 ms für long_press (Protokoll), gilt für alle Zeigergeräte */
    for (lv_indev_t *i = lv_indev_get_next(NULL); i; i = lv_indev_get_next(i))
        if (lv_indev_get_type(i) == LV_INDEV_TYPE_POINTER) lv_indev_set_long_press_time(i, DECKBAR_LONG_PRESS_MS);

    lv_obj_t *scr = lv_screen_active();
    lv_obj_remove_style_all(scr);
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x0A0D1C), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    ui.bg = lv_image_create(scr);
    lv_image_set_src(ui.bg, &deckbar_bg_default);
    lv_obj_set_pos(ui.bg, 0, 0);
    dbui_bg_restore();

    dbui_build_status_ui();

    char *cached = deckbar_hal_load(CACHE_KEY);
    if (cached) {
        cJSON *msg = cJSON_Parse(cached);
        if (msg && !dbui_apply_layout(msg)) ui.layout_hash[0] = 0;
        cJSON_Delete(msg);
        free(cached);
    }
    dbui_update_status_ui();
    lv_timer_create(watchdog_cb, 1000, NULL);
}
