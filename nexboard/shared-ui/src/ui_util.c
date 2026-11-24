/* NexBoard-UI · Hilfen für alle Teile der UI: Texte und JSON lesen, schlichte LVGL-Objekte, Ereignisse an den Daemon senden. */
#include "ui_internal.h"

/* ======================================================================= Hilfen */

void dbui_copy_str(char *dst, size_t n, const char *src)
{
    if (!src) src = "";
    size_t l = strlen(src);
    if (l >= n) l = n - 1;
    memcpy(dst, src, l);
    dst[l] = 0;
}

bool dbui_valid_id(const char *s)
{
    if (!s || !*s || strlen(s) >= ID_LEN) return false;
    for (; *s; s++) {
        char c = *s;
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-'))
            return false;
    }
    return true;
}

const char *dbui_jstr(const cJSON *o, const char *key)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, key);
    return cJSON_IsString(v) ? v->valuestring : NULL;
}

int dbui_jint(const cJSON *o, const char *key, int def)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, key);
    return cJSON_IsNumber(v) ? (int)v->valuedouble : def;
}

bool dbui_truthy(const cJSON *v)
{
    if (!v || cJSON_IsNull(v)) return false;
    if (cJSON_IsBool(v)) return cJSON_IsTrue(v);
    if (cJSON_IsNumber(v)) return v->valuedouble != 0;
    if (cJSON_IsString(v)) return v->valuestring[0] != 0;
    return true;
}

const char *dbui_glyph_or_default(const char *name, const char *fallback)
{
    const char *g = deckbar_icon_glyph(name);
    if (!g && name && *name) LV_LOG_WARN("unbekanntes Icon '%s'", name);
    return g ? g : deckbar_icon_glyph(fallback);
}

lv_obj_t *dbui_plain_obj(lv_obj_t *parent)
{
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_style_all(o);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    return o;
}

lv_obj_t *dbui_text_label(lv_obj_t *parent, const lv_font_t *font, const char *txt)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_obj_remove_style_all(l);
    /* Farbe wird von der Kachel geerbt (tint/active) */
    lv_obj_set_style_text_font(l, font, 0);
    lv_label_set_text(l, txt ? txt : "");
    return l;
}

/* ======================================================================= Senden */

void dbui_send_raw(const char *s)
{
    if (!ui.ws_open) return;
    deckbar_hal_send(s, strlen(s));
}

void dbui_send_event(const char *event, const char *item, const char *part, const int32_t *value, int final)
{
    char buf[192];
    int n = snprintf(buf, sizeof buf, "{\"v\":%d,\"type\":\"event\",\"event\":\"%s\"", DECKBAR_PROTO_VERSION, event);
    if (item) n += snprintf(buf + n, sizeof buf - n, ",\"item\":\"%s\"", item);
    if (part) n += snprintf(buf + n, sizeof buf - n, ",\"part\":\"%s\"", part);
    if (value) n += snprintf(buf + n, sizeof buf - n, ",\"value\":%ld", (long)*value);
    if (final >= 0) n += snprintf(buf + n, sizeof buf - n, ",\"final\":%s", final ? "true" : "false");
    snprintf(buf + n, sizeof buf - n, "}");
    dbui_send_raw(buf);
}

void dbui_send_page_change(const char *page)
{
    char buf[96];
    snprintf(buf, sizeof buf, "{\"v\":%d,\"type\":\"event\",\"event\":\"page_change\",\"page\":\"%s\"}",
             DECKBAR_PROTO_VERSION, page);
    dbui_send_raw(buf);
}
