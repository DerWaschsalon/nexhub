/* NexBoard-UI · DPS-Kachel (AION 2): Kopfzeile mit Ziel, HP und Zeit, darunter die Spielerzeilen. */
#include "ui_internal.h"

/* ======================================================================= DPS (AION 2) */

static lv_color_t class_color(const char *cls)
{
    static const struct {
        const char *name;
        uint32_t rgb;
    } map[] = {DECKBAR_CLASS_COLORS};
    for (size_t i = 0; cls && i < sizeof map / sizeof map[0]; i++)
        if (!strcmp(map[i].name, cls)) return lv_color_hex(map[i].rgb);
    return lv_color_hex(DECKBAR_UNKNOWN_CLASS_COLOR);
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
void dbui_set_text(lv_obj_t *l, const char *txt)
{
    if (strcmp(lv_label_get_text(l), txt)) lv_label_set_text(l, txt);
}

void dbui_set_hidden(lv_obj_t *o, bool hidden)
{
    if (hidden) lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_remove_flag(o, LV_OBJ_FLAG_HIDDEN);
}

void dbui_dps_update(tile_t *t)
{
    dps_view_t *v = t->dps;
    if (!v) return;
    const cJSON *d = cJSON_GetObjectItemCaseSensitive(ui.state, "dps");
    const cJSON *rows = cJSON_IsObject(d) ? cJSON_GetObjectItemCaseSensitive(d, "rows") : NULL;
    int count = cJSON_IsArray(rows) ? cJSON_GetArraySize(rows) : 0;
    char buf[48];

    if (v->target) {
        const char *target = cJSON_IsObject(d) ? dbui_jstr(d, "target") : NULL;
        dbui_set_text(v->target, target && *target ? target : "AION 2");
        int secs = cJSON_IsObject(d) ? dbui_jint(d, "time", 0) : 0;
        const cJSON *hp = cJSON_IsObject(d) ? cJSON_GetObjectItemCaseSensitive(d, "hp") : NULL;
        if (!count) buf[0] = 0;
        else if (cJSON_IsNumber(hp))
            snprintf(buf, sizeof buf, "%.0f %% · %d:%02d", hp->valuedouble, secs / 60, secs % 60);
        else snprintf(buf, sizeof buf, "%d:%02d", secs / 60, secs % 60);
        dbui_set_text(v->time, buf);
        if (count && cJSON_IsNumber(hp)) {
            int32_t w = LV_MAX((int32_t)(v->hp_w * LV_CLAMP(0.0, hp->valuedouble, 100.0) / 100.0), 1);
            if (w != v->hp_px) {
                lv_obj_set_width(v->hp, w);
                v->hp_px = w;
            }
            dbui_set_hidden(v->hp_track, false);
        } else dbui_set_hidden(v->hp_track, true);
    }

    dbui_set_text(v->msg, !cJSON_IsObject(d) ? "DPS-Meter nicht verbunden" : "Warte auf Kampf …");
    dbui_set_hidden(v->msg, count > 0);

    double best = 1;
    for (int i = 0; i < count && i < v->n; i++) {
        const cJSON *x = cJSON_GetObjectItemCaseSensitive(cJSON_GetArrayItem(rows, i), "dps");
        if (cJSON_IsNumber(x) && x->valuedouble > best) best = x->valuedouble;
    }
    for (int i = 0; i < v->n; i++) {
        dps_row_t *r = &v->rows[i];
        const cJSON *jr = i < count ? cJSON_GetArrayItem(rows, i) : NULL;
        dbui_set_hidden(r->row, !cJSON_IsObject(jr));
        if (!cJSON_IsObject(jr)) continue;
        const cJSON *dps = cJSON_GetObjectItemCaseSensitive(jr, "dps");
        double x = cJSON_IsNumber(dps) ? dps->valuedouble : 0;
        const char *name = dbui_jstr(jr, "name");
        snprintf(buf, sizeof buf, "%d  %s", i + 1, name ? name : "?");
        dbui_set_text(r->name, buf);
        fmt_amount(buf, sizeof buf, x);
        dbui_set_text(r->val, buf);
        if (r->extra) {
            if (v->extra == 0) {
                const cJSON *pct = cJSON_GetObjectItemCaseSensitive(jr, "pct");
                snprintf(buf, sizeof buf, "%.0f %%", cJSON_IsNumber(pct) ? pct->valuedouble : 0.0);
            } else {
                const cJSON *dmg = cJSON_GetObjectItemCaseSensitive(jr, "dmg");
                fmt_amount(buf, sizeof buf, cJSON_IsNumber(dmg) ? dmg->valuedouble : 0);
            }
            dbui_set_text(r->extra, buf);
        }
        int32_t bar_px = LV_MAX((int32_t)(v->bar_w * x / best), 6);
        if (bar_px != r->bar_px) {
            lv_obj_set_width(r->bar, bar_px);
            r->bar_px = bar_px;
        }
        lv_color_t color = class_color(dbui_jstr(jr, "cls"));
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
void dbui_build_dps(tile_t *t, int32_t w, int32_t h, int players, const char *extra)
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
        v->time = dbui_text_label(o, &db_font_small, "");
        lv_obj_add_style(v->time, &db_theme.text_dim, 0);
        lv_obj_align(v->time, LV_ALIGN_TOP_RIGHT, -px - 2, y);
        v->target = dbui_text_label(o, &db_font_small, "AION 2");
        lv_obj_add_style(v->target, &db_theme.text_dim, 0);
        lv_label_set_long_mode(v->target, LV_LABEL_LONG_DOT);
        lv_obj_set_size(v->target, w / 2 - px - 20, ls); /* endet vor dem Reset-Knopf */
        lv_obj_set_pos(v->target, px + 2, y);
        /* kleiner Knopf mittig in der Kopfzeile: Meter zurücksetzen */
        lv_obj_t *reset = lv_obj_get_parent(dbui_mini_button(o, t, deckbar_icon_glyph("restart"), "reset", 24));
        lv_obj_align(reset, LV_ALIGN_TOP_MID, 0, y - 5);
        y += ls + 3;
        v->hp_w = w - 2 * px;
        v->hp_track = dbui_plain_obj(o);
        lv_obj_set_size(v->hp_track, v->hp_w, 2);
        lv_obj_set_pos(v->hp_track, px, y);
        lv_obj_set_style_bg_color(v->hp_track, lv_color_white(), 0);
        lv_obj_set_style_bg_opa(v->hp_track, 28, 0);
        lv_obj_add_flag(v->hp_track, LV_OBJ_FLAG_HIDDEN);
        v->hp = dbui_plain_obj(v->hp_track);
        lv_obj_set_size(v->hp, v->hp_w, 2);
        lv_obj_set_style_bg_color(v->hp, lv_color_hex(0xFF453A), 0);
        lv_obj_set_style_bg_opa(v->hp, 210, 0);
        y += 2 + 4;
    }

    int32_t avail = h - y - 7;
    int n = LV_CLAMP(1, players, DECKBAR_DPS_MAX_ROWS);
    while (n > 1 && (avail - (n - 1) * gap) / n < 16) n--;
    /* wenige Spieler: höhere Zeilen und größere Schrift */
    int32_t row_h = LV_MIN((avail - (n - 1) * gap) / n, 40);
    const lv_font_t *font = row_h >= 34 ? &db_font_title : row_h >= 20 ? &db_font_label : &db_font_small;
    int32_t extra_w = v->extra == 2 ? 0 : (v->extra == 1 ? 58 : 44);
    v->n = n;
    v->bar_w = w - 2 * px;

    for (int i = 0; i < n; i++) {
        dps_row_t *r = &v->rows[i];
        r->row = dbui_plain_obj(o);
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

        r->bar = dbui_plain_obj(r->row);
        lv_obj_set_size(r->bar, 6, LV_PCT(100));
        lv_obj_set_style_radius(r->bar, 7, 0);
        lv_obj_set_style_bg_opa(r->bar, 120, 0);

        r->name = dbui_text_label(r->row, font, "");
        lv_label_set_long_mode(r->name, LV_LABEL_LONG_DOT);
        lv_obj_set_size(r->name, v->bar_w - 16 - extra_w - 64, lv_font_get_line_height(font));
        lv_obj_align(r->name, LV_ALIGN_LEFT_MID, 8, 0);

        if (extra_w) {
            r->extra = dbui_text_label(r->row, &db_font_small, "");
            lv_obj_add_style(r->extra, &db_theme.text_dim, 0);
            lv_obj_set_width(r->extra, extra_w);
            lv_obj_set_style_text_align(r->extra, LV_TEXT_ALIGN_RIGHT, 0);
            lv_obj_align(r->extra, LV_ALIGN_RIGHT_MID, -8, 0);
        }
        r->val = dbui_text_label(r->row, font, "");
        lv_obj_set_width(r->val, 64);
        lv_obj_set_style_text_align(r->val, LV_TEXT_ALIGN_RIGHT, 0);
        lv_obj_align(r->val, LV_ALIGN_RIGHT_MID, -8 - extra_w - (extra_w ? 6 : 0), 0);
        lv_obj_add_flag(r->row, LV_OBJ_FLAG_HIDDEN);
    }

    v->msg = dbui_text_label(o, &db_font_label, "");
    lv_obj_add_style(v->msg, &db_theme.text_dim, 0);
    lv_obj_align(v->msg, LV_ALIGN_CENTER, 0, v->target ? 8 : 0);
    dbui_dps_update(t);
}
