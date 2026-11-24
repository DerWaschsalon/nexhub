/* NexBoard-UI · Claude-Kachel: je Limit (Sitzung, Woche) eine Zeile mit Balken, Prozent und Reset. */
#include "ui_internal.h"

/* Schlüssel im State `claude` und Beschriftung, in Zeilenreihenfolge (siehe daemon/claude.py) */
static const char *const CLAUDE_KEYS[2] = {"session", "week"};
static const char *const CLAUDE_NAMES[2] = {"5 h", "Woche"};

void dbui_claude_update(tile_t *t)
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
        const char *reset = dbui_jstr(jr, "reset");
        if (r->reset) lv_label_set_text(r->reset, reset ? reset : "");
    }
}

/* Claude-Kachel: Auslastung des Claude-Abos, Werte kommen alle 5 Minuten vom Daemon */
void dbui_build_claude(tile_t *t, int32_t w, int32_t h)
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

        lv_obj_t *name = dbui_text_label(o, &db_font_small, CLAUDE_NAMES[i]);
        lv_obj_add_style(name, &db_theme.text_dim, 0);
        lv_obj_set_pos(name, px, mid - lh / 2);

        lv_obj_t *track = dbui_plain_obj(o);
        lv_obj_set_size(track, v->bar_w, 6);
        lv_obj_set_pos(track, bar_x, mid - 3);
        lv_obj_set_style_radius(track, 3, 0);
        lv_obj_set_style_bg_color(track, lv_color_white(), 0);
        lv_obj_set_style_bg_opa(track, 28, 0);
        r->fill = dbui_plain_obj(track);
        lv_obj_set_size(r->fill, 0, 6);
        lv_obj_set_style_radius(r->fill, 3, 0);
        lv_obj_set_style_bg_opa(r->fill, 220, 0);

        r->pct = dbui_text_label(o, &db_font_small, "");
        lv_obj_set_width(r->pct, pct_w);
        lv_obj_set_style_text_align(r->pct, LV_TEXT_ALIGN_RIGHT, 0);
        lv_obj_set_pos(r->pct, pct_x, mid - lh / 2);

        if (reset_w) {
            r->reset = dbui_text_label(o, &db_font_small, "");
            lv_obj_add_style(r->reset, &db_theme.text_dim, 0);
            lv_obj_set_width(r->reset, reset_w);
            lv_obj_set_style_text_align(r->reset, LV_TEXT_ALIGN_RIGHT, 0);
            lv_obj_set_pos(r->reset, pct_x + pct_w + gap, mid - lh / 2);
        }
    }
    dbui_claude_update(t);
}
