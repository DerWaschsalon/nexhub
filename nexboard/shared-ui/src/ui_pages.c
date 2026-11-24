/* NexBoard-UI · Seiten: Layout vom Daemon aufbauen, Wischen zwischen den Seiten, Punkte unten. */
#include "ui_internal.h"

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

void dbui_go_to_page(int idx)
{
    if (idx < 0 || idx >= ui.page_count) return;
    lv_tileview_set_tile(ui.tv, ui.pages[idx], LV_ANIM_OFF);
    if (idx != ui.page_active) {
        ui.page_active = idx;
        update_dots();
        dbui_send_page_change(ui.page_ids[idx]);
    }
}

/* Wischt der Finger über eine Seite (nicht über einen Slider), springt sie beim Loslassen zur Nachbarseite.
 * Die Kette über GESTURE_BUBBLE endet bei Slidern, bei allen anderen Kacheln beim Tileview. */
static bool swipes_page(lv_obj_t *obj)
{
    while (obj && obj != ui.tv && lv_obj_has_flag(obj, LV_OBJ_FLAG_GESTURE_BUBBLE)) obj = lv_obj_get_parent(obj);
    return obj == ui.tv;
}

/*
 * Wischen und Tippen werden am Eingabegerät entschieden, das PRESSED, RELEASED und die Klicks vor der
 * Kachel sieht:
 *   - Seiten folgen nicht dem Finger: Mitziehen zeichnete jedes Bild komplett neu (bis 100 ms), bei so
 *     wenigen Touch-Proben schnappte die Seite oft zurück.
 *   - Die LVGL-Geste taugt nicht: Der Controller meldet nicht bei jeder Abfrage eine neue Position, und
 *     jede Abfrage ohne Bewegung setzt LVGLs Gestensumme zurück. Gezählt wird die Strecke seit PRESSED.
 *   - Wer weiter als TAP_SLOP wischt, löst keinen Klick auf der Kachel darunter aus.
 */
void dbui_touch_cb(lv_event_t *e)
{
    static lv_point_t press;
    lv_indev_t *indev = lv_indev_active();
    lv_event_code_t code = lv_event_get_code(e);
    lv_point_t p;
    lv_indev_get_point(indev, &p);
    int32_t dx = p.x - press.x, dy = p.y - press.y;
    if (code == LV_EVENT_PRESSED) {
        press = p;
    } else if (code == LV_EVENT_RELEASED) {
        if (LV_ABS(dx) >= SWIPE_MIN && LV_ABS(dx) > LV_ABS(dy) && swipes_page(lv_event_get_param(e)))
            dbui_go_to_page(ui.page_active + (dx < 0 ? 1 : -1));
    } else if (code == LV_EVENT_SHORT_CLICKED || code == LV_EVENT_CLICKED || code == LV_EVENT_LONG_PRESSED) {
        if (LV_ABS(dx) + LV_ABS(dy) > TAP_SLOP) lv_indev_stop_processing(indev);
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
            dbui_send_page_change(ui.page_ids[i]);
        }
    }
}

static void free_tiles(void)
{
    for (int i = 0; i < ui.tile_count; i++) {
        tile_t *t = &ui.tiles[i];
        lv_anim_delete(t, dbui_fill_anim_cb);
        if (t->timer) lv_timer_delete(t->timer);
        lv_free(t->view);
    }
    lv_free(ui.tiles);
    ui.tiles = NULL;
    ui.tile_count = 0;
}

/* Setzt die Items einer Seite zeilenweise in die erste freie Lücke (auto-flow dense). */
static void build_page(lv_obj_t *page, const cJSON *jp, int page_idx)
{
    int cols = LV_CLAMP(1, dbui_jint(jp, "cols", 6), 8);
    int rows = LV_CLAMP(1, dbui_jint(jp, "rows", 2), 3);
    bool used[3][8] = {{0}};
    const int32_t aw = DECKBAR_SCREEN_W - 2 * DB_PAD + DB_GAP;
    const int32_t ah = DECKBAR_SCREEN_H - 2 * DB_PAD + DB_GAP;

    const cJSON *items = cJSON_GetObjectItemCaseSensitive(jp, "items");
    const cJSON *ji;
    int count = 0;
    cJSON_ArrayForEach(ji, items)
    {
        if (count++ >= DECKBAR_MAX_ITEMS_PER_PAGE) break;
        const char *id = dbui_jstr(ji, "id");
        if (!dbui_valid_id(id)) continue;
        int w = LV_CLAMP(1, dbui_jint(ji, "w", 1), cols);
        int h = LV_CLAMP(1, dbui_jint(ji, "h", 1), rows);

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
        dbui_copy_str(t->id, sizeof t->id, id);
        t->cls = dbui_tile_class(dbui_jstr(ji, "type"));
        t->style = db_style_parse(dbui_jstr(ji, "style"));
        dbui_copy_str(t->bind, sizeof t->bind, dbui_jstr(ji, "bind"));
        dbui_copy_str(t->mute_bind, sizeof t->mute_bind, dbui_jstr(ji, "mute_bind"));
        const char *nav = dbui_jstr(ji, "nav");
        if (dbui_valid_id(nav)) dbui_copy_str(t->nav, sizeof t->nav, nav);
        t->glyph = dbui_jstr(ji, "icon") ? dbui_glyph_or_default(dbui_jstr(ji, "icon"), "dots-horizontal") : NULL;
        t->glyph_on = dbui_jstr(ji, "icon_on") ? dbui_glyph_or_default(dbui_jstr(ji, "icon_on"), "dots-horizontal") : NULL;
        t->min = dbui_jint(ji, "min", 0);
        t->max = dbui_jint(ji, "max", 100);
        if (t->max <= t->min) t->max = t->min + 1;
        (void)page_idx;

        dbui_make_tile_obj(page, t, x0, y0, pw, ph);
        t->cls->build(t, pw, ph, ji);
    }
}

bool dbui_apply_layout(const cJSON *msg)
{
    const cJSON *pages = cJSON_GetObjectItemCaseSensitive(msg, "pages");
    int np = cJSON_GetArraySize(pages);
    if (!cJSON_IsArray(pages) || np < 1) {
        LV_LOG_WARN("Layout ohne Seiten verworfen");
        return false;
    }
    if (np > DECKBAR_MAX_PAGES) np = DECKBAR_MAX_PAGES;

    const cJSON *theme = cJSON_GetObjectItemCaseSensitive(msg, "theme");
    const char *accent = dbui_jstr(theme, "accent");
    if (accent && accent[0] == '#' && strlen(accent) == 7)
        db_theme_set_accent(lv_color_hex((uint32_t)strtoul(accent + 1, NULL, 16)));

    /* Seite merken, damit ein Live-Update nicht auf Seite 1 zurückspringt */
    char prev_page[ID_LEN] = "";
    if (ui.page_count) dbui_copy_str(prev_page, sizeof prev_page, ui.page_ids[ui.page_active]);

    /* erst Objekte löschen (Event-Callbacks sehen noch gültige tile_t), dann die Structs */
    if (ui.tv) lv_obj_delete(ui.tv);
    if (ui.dots) lv_obj_delete(ui.dots);
    free_tiles();
    ui.tv = NULL;
    ui.dots = NULL;
    ui.page_count = 0;
    ui.page_active = 0;
    ui.tiles = lv_malloc_zeroed(sizeof(tile_t) * np * DECKBAR_MAX_ITEMS_PER_PAGE);

    ui.tv = lv_tileview_create(lv_screen_active());
    lv_obj_set_size(ui.tv, DECKBAR_SCREEN_W, DECKBAR_SCREEN_H);
    lv_obj_set_style_bg_opa(ui.tv, LV_OPA_TRANSP, 0);
    lv_obj_set_scrollbar_mode(ui.tv, LV_SCROLLBAR_MODE_OFF);
    lv_obj_add_event_cb(ui.tv, tv_event_cb, LV_EVENT_VALUE_CHANGED, NULL);
    /* nicht scrollbar: Seiten wechseln per Wisch (dbui_touch_cb); ohne GESTURE_BUBBLE endet die Kette hier */
    lv_obj_remove_flag(ui.tv, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_GESTURE_BUBBLE);

    int idx = 0;
    const cJSON *jp;
    cJSON_ArrayForEach(jp, pages)
    {
        if (idx >= np) break;
        const char *pid = dbui_jstr(jp, "id");
        if (!dbui_valid_id(pid)) continue;
        lv_dir_t dir = (idx > 0 ? LV_DIR_LEFT : 0) | (idx < np - 1 ? LV_DIR_RIGHT : 0);
        lv_obj_t *page = lv_tileview_add_tile(ui.tv, (uint8_t)idx, 0, dir);
        lv_obj_set_style_bg_opa(page, LV_OPA_TRANSP, 0);
        lv_obj_set_scrollbar_mode(page, LV_SCROLLBAR_MODE_OFF);
        lv_obj_remove_flag(page, LV_OBJ_FLAG_SCROLLABLE);
        ui.pages[idx] = page;
        dbui_copy_str(ui.page_ids[idx], ID_LEN, pid);
        build_page(page, jp, idx);
        idx++;
    }
    ui.page_count = idx;

    if (ui.page_count > 1) {
        ui.dots = dbui_plain_obj(lv_screen_active());
        lv_obj_set_size(ui.dots, LV_SIZE_CONTENT, 5);
        lv_obj_align(ui.dots, LV_ALIGN_BOTTOM_MID, 0, -1);
        lv_obj_set_flex_flow(ui.dots, LV_FLEX_FLOW_ROW);
        lv_obj_set_style_pad_column(ui.dots, 5, 0);
        lv_obj_remove_flag(ui.dots, LV_OBJ_FLAG_CLICKABLE);
        for (int i = 0; i < ui.page_count; i++) {
            lv_obj_t *d = dbui_plain_obj(ui.dots);
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
        if (ui.tiles[i].cls == &dbui_tile_slider) dbui_slider_show(&ui.tiles[i], ui.tiles[i].value_cur);
    dbui_apply_full_state();

    dbui_copy_str(ui.layout_hash, sizeof ui.layout_hash, dbui_jstr(msg, "hash"));
    ui.have_layout = true;
    dbui_update_status_ui();
    dbui_request_art();
    return true;
}
