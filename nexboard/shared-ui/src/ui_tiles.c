/* NexBoard-UI · Kacheln: Zustand aus dem State übernehmen, Touch-Ereignisse und der Aufbau von Knopf, Schalter, Regler und Media. */
#include "ui_internal.h"

/* ======================================================================= Kacheln: Zustände */

void dbui_slider_show(tile_t *t, int32_t v)
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

void dbui_fill_anim_cb(void *var, int32_t v)
{
    dbui_slider_show((tile_t *)var, v);
}

static void slider_animate_to(tile_t *t, int32_t v)
{
    t->value_target = v;
    lv_anim_delete(t, dbui_fill_anim_cb);
    if (v == t->value_cur) return;
    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, t);
    lv_anim_set_values(&a, t->value_cur, v);
    lv_anim_set_duration(&a, 220);
    lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
    lv_anim_set_exec_cb(&a, dbui_fill_anim_cb);
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

/* Der Lauftext zeichnet jedes Bild neu, und das Panel nimmt nur ganze Frames (220 KB):
 * Dauerlauf hielt das Gerät mit 45 Bildern/s ständig ausgelastet. Deshalb nur eine Weile. */
static void marquee_stop_cb(lv_timer_t *tm)
{
    tile_t *t = lv_timer_get_user_data(tm);
    t->timer = NULL;
    lv_label_set_long_mode(t->title, LV_LABEL_LONG_DOT);
}

static void media_update(tile_t *t)
{
    const cJSON *track = cJSON_GetObjectItemCaseSensitive(ui.state, "track");
    bool playing = dbui_truthy(cJSON_GetObjectItemCaseSensitive(ui.state, "playing"));
    const char *title = cJSON_IsObject(track) ? dbui_jstr(track, "title") : NULL;
    const char *artist = cJSON_IsObject(track) ? dbui_jstr(track, "artist") : NULL;

    if (title && *title) {
        if (strcmp(lv_label_get_text(t->title), title) != 0) {
            lv_label_set_long_mode(t->title, LV_LABEL_LONG_SCROLL_CIRCULAR);
            lv_label_set_text(t->title, title);
            if (t->timer) lv_timer_delete(t->timer);
            t->timer = lv_timer_create(marquee_stop_cb, MARQUEE_MS, t);
            lv_timer_set_repeat_count(t->timer, 1);
        }
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


static bool wants(const tile_class_t *cls, const char *key)
{
    for (size_t i = 0; i < sizeof cls->keys / sizeof cls->keys[0]; i++)
        if (cls->keys[i] && !strcmp(cls->keys[i], key)) return true;
    return false;
}

void dbui_apply_state_key(const char *key, const cJSON *val)
{
    uint32_t now = lv_tick_get();
    for (int i = 0; i < ui.tile_count; i++) {
        tile_t *t = &ui.tiles[i];
        if (t->cls->update) { /* Kachel mit eigenem State */
            if (wants(t->cls, key)) t->cls->update(t);
            continue;
        }
        if (t->bind[0] && !strcmp(t->bind, key)) {
            if (t->cls == &dbui_tile_toggle) {
                if (t->timer) {
                    lv_timer_delete(t->timer);
                    t->timer = NULL;
                }
                tile_set_checked(t, dbui_truthy(val));
            } else if (t->cls == &dbui_tile_slider && cJSON_IsNumber(val)) {
                int32_t v = (int32_t)val->valuedouble;
                /* Beim Ziehen und kurz danach gewinnt der Finger */
                if (!t->dragging && (int32_t)(now - t->settle_until) >= 0) slider_animate_to(t, v);
            }
        }
        if (t->mute_bind[0] && !strcmp(t->mute_bind, key)) tile_set_muted(t, dbui_truthy(val));
    }
}

void dbui_apply_full_state(void)
{
    const cJSON *it;
    cJSON_ArrayForEach(it, ui.state) dbui_apply_state_key(it->string, it);
    for (int i = 0; i < ui.tile_count; i++)
        if (ui.tiles[i].cls->update) ui.tiles[i].cls->update(&ui.tiles[i]);
}

/* ======================================================================= Kacheln: Events */

static void toggle_revert_cb(lv_timer_t *tm)
{
    tile_t *t = lv_timer_get_user_data(tm);
    t->timer = NULL;
    tile_set_checked(t, dbui_truthy(cJSON_GetObjectItemCaseSensitive(ui.state, t->bind)));
}


static void tile_event_cb(lv_event_t *e)
{
    tile_t *t = lv_event_get_user_data(e);
    lv_event_code_t code = lv_event_get_code(e);

    if (code == LV_EVENT_SHORT_CLICKED) {
        if (t->nav[0]) {
            for (int i = 0; i < ui.page_count; i++)
                if (!strcmp(ui.page_ids[i], t->nav)) dbui_go_to_page(i);
            return;
        }
        if (ui.net != DECKBAR_NET_ONLINE) return;
        if (t->cls == &dbui_tile_toggle) {
            /* optimistisch umschalten; der Daemon bestätigt per state */
            tile_set_checked(t, !t->checked);
            if (t->timer) lv_timer_delete(t->timer);
            t->timer = lv_timer_create(toggle_revert_cb, TOGGLE_REVERT_MS, t);
            lv_timer_set_repeat_count(t->timer, 1);
        }
        dbui_send_event("button_press", t->id, t->cls == &dbui_tile_media ? "toggle" : NULL, NULL, -1);
    } else if (code == LV_EVENT_LONG_PRESSED) {
        if (!t->nav[0]) dbui_send_event("long_press", t->id, NULL, NULL, -1);
    }
}

static void media_part_cb(lv_event_t *e)
{
    tile_t *t = lv_event_get_user_data(e);
    lv_obj_t *btn = lv_event_get_current_target(e);
    const char *part = lv_obj_get_user_data(btn);
    dbui_send_event("button_press", t->id, part, NULL, -1);
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
        lv_anim_delete(t, dbui_fill_anim_cb);
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
        if (v != t->value_cur) dbui_slider_show(t, v);
        if (v != t->last_sent_value && (now - t->last_send) >= SLIDER_SEND_MS && ui.net == DECKBAR_NET_ONLINE) {
            dbui_send_event("slider_change", t->id, NULL, &v, 0);
            t->last_send = now;
            t->last_sent_value = v;
        }
        break;
    }
    case LV_EVENT_LONG_PRESSED:
        if (!t->moved) {
            t->long_fired = true;
            dbui_send_event("long_press", t->id, NULL, NULL, -1);
        }
        break;
    case LV_EVENT_RELEASED:
    case LV_EVENT_PRESS_LOST:
        t->dragging = false;
        if (t->moved && !t->long_fired) {
            int32_t v = t->value_cur;
            dbui_send_event("slider_change", t->id, NULL, &v, 1);
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
    lv_obj_t *h = dbui_plain_obj(tile);
    lv_obj_add_style(h, &db_theme.highlight, 0);
    lv_obj_set_size(h, w - 2 * DB_RADIUS, 1);
    lv_obj_align(h, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_add_flag(h, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_remove_flag(h, LV_OBJ_FLAG_CLICKABLE);
}

lv_obj_t *dbui_make_tile_obj(lv_obj_t *page, tile_t *t, int32_t x, int32_t y, int32_t w, int32_t h)
{
    lv_obj_t *o = dbui_plain_obj(page);
    lv_obj_add_style(o, &db_theme.glass, 0);
    /* Bei Toggles bestimmt style nur den aktiven Zustand */
    if (t->cls != &dbui_tile_toggle) lv_obj_add_style(o, &db_theme.tint[t->style], 0);
    lv_obj_add_style(o, &db_theme.glass_pressed, LV_STATE_PRESSED);
    lv_obj_add_style(o, &db_theme.active[t->style], LV_STATE_CHECKED);
    lv_obj_set_pos(o, x, y);
    lv_obj_set_size(o, w, h);
    lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
    add_highlight(o, w);
    t->obj = o;
    return o;
}

static void build_button(tile_t *t, int32_t w, int32_t h, const cJSON *item)
{
    const char *label = dbui_jstr(item, "label");
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

    if (t->glyph) t->icon = dbui_text_label(o, ifont, t->glyph);
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

static void build_slider(tile_t *t, int32_t w, int32_t h, const cJSON *item)
{
    const char *label = dbui_jstr(item, "label");
    lv_obj_t *o = t->obj;
    /* Wischen auf dem Slider darf nicht die Seite wechseln */
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLL_CHAIN | LV_OBJ_FLAG_GESTURE_BUBBLE);
    lv_obj_add_flag(o, LV_OBJ_FLAG_PRESS_LOCK);

    t->fill = dbui_plain_obj(o);
    lv_obj_add_style(t->fill, &db_theme.fill, 0);
    lv_obj_add_style(t->fill, &db_theme.fill_muted, DB_STATE_MUTED);
    /* gleiche Rundung wie die Kachel statt clip_corner (das zeichnete die Kachel über eine Zwischenebene) */
    lv_obj_set_style_radius(t->fill, DB_RADIUS, 0);
    lv_obj_set_size(t->fill, 0, LV_PCT(100));
    lv_obj_align(t->fill, LV_ALIGN_LEFT_MID, 0, 0);
    lv_obj_remove_flag(t->fill, LV_OBJ_FLAG_CLICKABLE);
    /* Lichtkante über die Füllung legen */
    lv_obj_move_to_index(t->fill, 0);

    bool compact = w < 150;
    const lv_font_t *ifont = h < 60 ? &db_icons_20 : &db_icons_28;
    if (t->glyph) {
        t->icon = dbui_text_label(o, ifont, t->glyph);
        lv_obj_align(t->icon, compact ? LV_ALIGN_TOP_LEFT : LV_ALIGN_LEFT_MID, compact ? 10 : 14, compact ? 8 : 0);
    }
    if (!compact && label && *label && h >= 60) {
        t->label = dbui_text_label(o, &db_font_label, label);
        lv_obj_align(t->label, LV_ALIGN_LEFT_MID, t->glyph ? 52 : 16, 0);
    }
    t->value = dbui_text_label(o, compact ? &db_font_label : &db_font_value, "");
    lv_obj_align(t->value, compact ? LV_ALIGN_BOTTOM_RIGHT : LV_ALIGN_RIGHT_MID, compact ? -10 : -16, compact ? -8 : 0);

    lv_obj_add_event_cb(o, slider_event_cb, LV_EVENT_ALL, t);
    t->value_cur = t->min;
    dbui_slider_show(t, t->min);
}

lv_obj_t *dbui_mini_button(lv_obj_t *parent, tile_t *t, const char *glyph, const char *part, int32_t size)
{
    lv_obj_t *b = dbui_plain_obj(parent);
    lv_obj_add_style(b, &db_theme.mini, 0);
    lv_obj_add_style(b, &db_theme.mini_pressed, LV_STATE_PRESSED);
    lv_obj_set_size(b, size, size);
    lv_obj_add_flag(b, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_user_data(b, (void *)part);
    lv_obj_t *l = dbui_text_label(b, size >= 44 ? &db_icons_28 : &db_icons_20, glyph);
    lv_obj_center(l);
    lv_obj_add_event_cb(b, media_part_cb, LV_EVENT_SHORT_CLICKED, t);
    return l;
}

/* Cover-Kasten mit Platzhalter-Note; das Bild selbst kommt per `art` vom Daemon */
static void build_cover(tile_t *t, int32_t x, int32_t y, int32_t px)
{
    lv_obj_t *box = dbui_plain_obj(t->obj);
    lv_obj_set_size(box, px, px);
    lv_obj_set_pos(box, x, y);
    lv_obj_set_style_radius(box, px >= 60 ? 10 : 7, 0);
    lv_obj_set_style_clip_corner(box, true, 0);
    lv_obj_set_style_bg_color(box, lv_color_white(), 0);
    lv_obj_set_style_bg_opa(box, 22, 0);
    lv_obj_remove_flag(box, LV_OBJ_FLAG_CLICKABLE);

    t->icon = dbui_text_label(box, px >= 56 ? &db_icons_28 : &db_icons_20, deckbar_icon_glyph("music-note"));
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
static void build_media(tile_t *t, int32_t w, int32_t h, const cJSON *item)
{
    (void)item;
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
        t->title = dbui_text_label(o, &db_font_title, "");
        lv_obj_set_size(t->title, text_w, lt);
        lv_obj_set_pos(t->title, text_x, ty);
        t->artist = dbui_text_label(o, &db_font_small, "");
        lv_obj_set_size(t->artist, text_w, ls);
        lv_obj_set_pos(t->artist, text_x, ty + lt + 2);

        lv_obj_t *bar = dbui_plain_obj(o);
        lv_obj_set_size(bar, w - 24, bar_h);
        lv_obj_align(bar, LV_ALIGN_BOTTOM_MID, 0, -m);
        lv_obj_set_flex_flow(bar, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(bar, LV_FLEX_ALIGN_SPACE_EVENLY, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        dbui_mini_button(bar, t, deckbar_icon_glyph("skip-previous"), "prev", 48);
        t->play = dbui_mini_button(bar, t, deckbar_icon_glyph("play"), "toggle", 56);
        dbui_mini_button(bar, t, deckbar_icon_glyph("skip-next"), "next", 48);
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
        lv_obj_t *bar = dbui_plain_obj(o);
        lv_obj_set_size(bar, ctrl_w, ps);
        lv_obj_align(bar, LV_ALIGN_RIGHT_MID, -10, 0);
        lv_obj_set_flex_flow(bar, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(bar, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        if (full) dbui_mini_button(bar, t, deckbar_icon_glyph("skip-previous"), "prev", bs);
        t->play = dbui_mini_button(bar, t, deckbar_icon_glyph("play"), "toggle", ps);
        if (full) dbui_mini_button(bar, t, deckbar_icon_glyph("skip-next"), "next", bs);

        text_w = w - text_x - ctrl_w - 10 - 12;
        t->title = dbui_text_label(o, &db_font_title, "");
        lv_obj_set_size(t->title, text_w, lt);
        lv_obj_set_x(t->title, text_x);
        t->artist = dbui_text_label(o, &db_font_small, "");
        lv_obj_set_size(t->artist, text_w, ls);
        lv_obj_set_x(t->artist, text_x);
    }
    lv_obj_add_style(t->artist, &db_theme.text_dim, 0);
    lv_label_set_long_mode(t->artist, LV_LABEL_LONG_DOT);
    lv_obj_add_event_cb(o, tile_event_cb, LV_EVENT_SHORT_CLICKED, t);
    dbui_media_show_cover(t);
}

/* ======================================================================= Kacheltypen */

const tile_class_t dbui_tile_button = {"button", build_button, NULL, {NULL}};
const tile_class_t dbui_tile_toggle = {"toggle", build_button, NULL, {NULL}};
const tile_class_t dbui_tile_slider = {"slider", build_slider, NULL, {NULL}};
const tile_class_t dbui_tile_media = {"media", build_media, media_update, {"track", "playing"}};

static const tile_class_t *const TILE_CLASSES[] = {
    &dbui_tile_button, &dbui_tile_toggle, &dbui_tile_slider, &dbui_tile_media,
    &dbui_tile_dps,    &dbui_tile_claude, &dbui_tile_guide,
};

const tile_class_t *dbui_tile_class(const char *name)
{
    for (size_t i = 0; name && i < sizeof TILE_CLASSES / sizeof TILE_CLASSES[0]; i++)
        if (!strcmp(TILE_CLASSES[i]->name, name)) return TILE_CLASSES[i];
    return &dbui_tile_button;
}
