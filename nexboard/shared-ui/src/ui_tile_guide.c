/* NexBoard-UI · Guide-Kachel (PoE-Leveling): Kopfzeile und die Zeilen des aktuellen Schritts. */
#include "ui_internal.h"

/* Guide-Kachel: Kopfzeile (Akt · Stufe · XP, Schritt, Knöpfe) und die Zeilen des aktuellen Schritts */
typedef struct {
    lv_obj_t *head;
    lv_obj_t *step;
    lv_obj_t *body; /* eine Beschriftung mit Farbbefehlen („#FEC076 Zone#“), Zeilen durch \n getrennt */
    lv_obj_t *msg;
} guide_view_t;

/* Lange auf „weiter“: Schnellvorlauf zur Zone, in der man gerade steht (Daemon: long_press, part next) */
static void guide_long_cb(lv_event_t *e)
{
    tile_t *t = lv_event_get_user_data(e);
    dbui_send_event("long_press", t->id, "next", NULL, -1);
}

static void guide_update(tile_t *t)
{
    guide_view_t *v = t->view;
    if (!v) return;
    const cJSON *g = cJSON_GetObjectItemCaseSensitive(ui.state, "guide");
    if (!cJSON_IsObject(g)) {
        dbui_set_text(v->head, "Leveling-Guide");
        dbui_set_text(v->step, "");
        dbui_set_text(v->body, "");
        dbui_set_text(v->msg, "Modul „Leveling-Guide“ ist aus");
        dbui_set_hidden(v->msg, false);
        return;
    }
    const char *head = dbui_jstr(g, "head");
    const char *step = dbui_jstr(g, "step");
    const char *msg = dbui_jstr(g, "msg");
    dbui_set_text(v->head, head && *head ? head : "Path of Exile");
    dbui_set_text(v->step, step ? step : "");
    /* Zeilen hintereinander; die Kachel kennt keine Zeilenobjekte, nur eine Beschriftung */
    static char body[DECKBAR_GUIDE_MAX_LINES * (DECKBAR_GUIDE_LINE_MAX + 1) + 1];
    size_t n = 0;
    const cJSON *lines = cJSON_GetObjectItemCaseSensitive(g, "lines");
    const cJSON *line;
    body[0] = 0;
    cJSON_ArrayForEach(line, lines) {
        if (!cJSON_IsString(line)) continue;
        n += (size_t)snprintf(body + n, sizeof body - n, "%s%s", n ? "\n" : "", line->valuestring);
        if (n >= sizeof body - 1) break;
    }
    dbui_set_text(v->body, body);
    dbui_set_text(v->msg, msg ? msg : "");
    dbui_set_hidden(v->msg, !(msg && *msg));
}

/* Guide-Symbole (Zeichen ab U+E000) als Bilder; Schrift einmal anlegen, alle Guide-Kacheln teilen sie */
static const void *guide_icon_cb(const lv_font_t *font, uint32_t unicode, uint32_t unicode_next,
                                 int32_t *offset_y, void *user_data)
{
    LV_UNUSED(font); LV_UNUSED(unicode_next); LV_UNUSED(user_data);
    uint32_t i = unicode - DECKBAR_GUIDE_ICON_FIRST;  /* darunter läuft es über und fällt raus */
    if (i >= DECKBAR_GUIDE_ICON_COUNT) return NULL;
    /* mittig in der Zeile statt mit der Unterkante auf der Grundlinie */
    *offset_y = (lv_font_get_line_height(&db_font_title) - DECKBAR_GUIDE_ICON_HEIGHT) / 2 - db_font_title.base_line;
    return deckbar_guide_icons[i];
}

static const lv_font_t *guide_font(void)
{
    static lv_font_t font;
    if (!font.get_glyph_dsc) {
        font = db_font_title;
        font.fallback = lv_imgfont_create(DECKBAR_GUIDE_ICON_HEIGHT, guide_icon_cb, NULL);
    }
    return &font;
}

/*
 * Guide-Kachel (Leveling-Guide für PoE)
 *   Kopfzeile: [Akt · Stufe · XP ........ 12/231  <  >]
 *   darunter die Zeilen des Schritts, Farben vom Daemon; lange auf > = zur aktuellen Zone springen
 */
static void build_guide(tile_t *t, int32_t w, int32_t h, const cJSON *item)
{
    (void)item;
    lv_obj_t *o = t->obj;
    lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
    guide_view_t *v = lv_malloc_zeroed(sizeof *v);
    if (!v) return;
    t->view = v;

    /* große Schrift: auf der Leiste muss man den Schritt im Spiel aus dem Augenwinkel lesen können */
    const int32_t px = 10, btn = 30, gap = 6, head_h = btn + 6, step_w = 70;
    lv_obj_t *next = dbui_mini_button(o, t, deckbar_icon_glyph("chevron-right"), "next", btn);
    lv_obj_t *next_btn = lv_obj_get_parent(next);
    lv_obj_align(next_btn, LV_ALIGN_TOP_RIGHT, -px + 4, 4);
    lv_obj_add_event_cb(next_btn, guide_long_cb, LV_EVENT_LONG_PRESSED, t);
    lv_obj_t *back = dbui_mini_button(o, t, deckbar_icon_glyph("chevron-left"), "back", btn);
    lv_obj_align_to(lv_obj_get_parent(back), next_btn, LV_ALIGN_OUT_LEFT_MID, -gap, 0);

    /* feste Breite: ausgerichtet wird beim Aufbau, der Text („12/231“) kommt erst danach */
    v->step = dbui_text_label(o, &db_font_label, "");
    lv_obj_add_style(v->step, &db_theme.text_dim, 0);
    lv_obj_set_width(v->step, step_w);
    lv_obj_set_style_text_align(v->step, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_align_to(v->step, lv_obj_get_parent(back), LV_ALIGN_OUT_LEFT_MID, -gap, 0);

    v->head = dbui_text_label(o, &db_font_label, "");
    lv_obj_add_style(v->head, &db_theme.text_dim, 0);
    lv_label_set_long_mode(v->head, LV_LABEL_LONG_DOT);
    lv_obj_set_width(v->head, LV_MAX(w - 2 * px - 2 * btn - step_w - 3 * gap, 40));
    lv_obj_set_pos(v->head, px, (head_h - lv_font_get_line_height(&db_font_label)) / 2);

    v->body = dbui_text_label(o, guide_font(), "");
    lv_label_set_recolor(v->body, true);
    lv_label_set_long_mode(v->body, LV_LABEL_LONG_CLIP);
    lv_obj_set_size(v->body, w - 2 * px, LV_MAX(h - head_h - 2, 20));
    lv_obj_set_pos(v->body, px, head_h);

    v->msg = dbui_text_label(o, &db_font_small, "");
    lv_obj_set_style_text_color(v->msg, db_theme_color(DB_STYLE_WARNING), 0);
    lv_obj_align(v->msg, LV_ALIGN_BOTTOM_RIGHT, -px, -6);
    guide_update(t);
}

const tile_class_t dbui_tile_guide = {"guide", build_guide, guide_update, {"guide"}};
