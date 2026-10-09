#include "theme.h"

#include <string.h>

#include "deckbar/fonts.h"

db_theme_t db_theme;

static lv_color_t accent;
static lv_style_transition_dsc_t trans_press;
static lv_grad_dsc_t grad_highlight;

static const lv_style_prop_t trans_props[] = {
    LV_STYLE_BG_MAIN_OPA, LV_STYLE_BG_GRAD_OPA, LV_STYLE_TRANSFORM_WIDTH, LV_STYLE_TRANSFORM_HEIGHT,
    LV_STYLE_BG_COLOR, LV_STYLE_BG_GRAD_COLOR, LV_STYLE_BORDER_COLOR, LV_STYLE_SHADOW_COLOR,
    LV_STYLE_SHADOW_OPA, 0,
};

lv_color_t db_theme_color(db_style_t s)
{
    switch (s) {
    case DB_STYLE_ACCENT: return accent;
    case DB_STYLE_DANGER: return lv_color_hex(0xFF453A);
    case DB_STYLE_SUCCESS: return lv_color_hex(0x30D158);
    case DB_STYLE_WARNING: return lv_color_hex(0xFF9F0A);
    default: return lv_color_white();
    }
}

db_style_t db_style_parse(const char *name)
{
    if (!name) return DB_STYLE_DEFAULT;
    if (!strcmp(name, "accent")) return DB_STYLE_ACCENT;
    if (!strcmp(name, "danger")) return DB_STYLE_DANGER;
    if (!strcmp(name, "success")) return DB_STYLE_SUCCESS;
    if (!strcmp(name, "warning")) return DB_STYLE_WARNING;
    return DB_STYLE_DEFAULT;
}

static void init_colored(void)
{
    for (int s = 0; s < DB_STYLE_COUNT; s++) {
        lv_color_t c = db_theme_color((db_style_t)s);
        lv_color_t light = lv_color_mix(lv_color_white(), c, 110);

        lv_style_t *t = &db_theme.tint[s];
        lv_style_reset(t);
        lv_style_init(t);
        if (s != DB_STYLE_DEFAULT) {
            lv_style_set_bg_color(t, c);
            lv_style_set_bg_grad_color(t, c);
            lv_style_set_bg_main_opa(t, 78);
            lv_style_set_bg_grad_opa(t, 30);
            lv_style_set_border_color(t, light);
            lv_style_set_border_opa(t, 110);
            lv_style_set_text_color(t, light);
        }

        lv_style_t *a = &db_theme.active[s];
        lv_style_reset(a);
        lv_style_init(a);
        lv_color_t ac = (s == DB_STYLE_DEFAULT) ? accent : c;
        lv_style_set_bg_color(a, ac);
        lv_style_set_bg_grad_color(a, lv_color_mix(lv_color_black(), ac, 60));
        lv_style_set_bg_main_opa(a, 225);
        lv_style_set_bg_grad_opa(a, 190);
        lv_style_set_border_color(a, lv_color_mix(lv_color_white(), ac, 120));
        lv_style_set_border_opa(a, 200);
        lv_style_set_shadow_color(a, ac);
        lv_style_set_shadow_opa(a, 130);
        lv_style_set_shadow_width(a, 24);
        lv_style_set_shadow_offset_y(a, 2);
        lv_style_set_text_color(a, lv_color_white());
    }

    lv_style_reset(&db_theme.fill);
    lv_style_init(&db_theme.fill);
    lv_style_set_bg_color(&db_theme.fill, lv_color_mix(lv_color_white(), accent, 40));
    lv_style_set_bg_grad_color(&db_theme.fill, accent);
    lv_style_set_bg_grad_dir(&db_theme.fill, LV_GRAD_DIR_VER);
    lv_style_set_bg_opa(&db_theme.fill, LV_OPA_COVER);
    lv_style_set_bg_main_opa(&db_theme.fill, 200);
    lv_style_set_bg_grad_opa(&db_theme.fill, 150);
    lv_style_set_radius(&db_theme.fill, 4);
}

void db_theme_set_accent(lv_color_t c)
{
    if (lv_color_eq(c, accent)) return;
    accent = c;
    init_colored();
    lv_obj_report_style_change(NULL);
}

void db_theme_init(void)
{
    accent = lv_color_hex(0x5AC8FA);

    lv_style_transition_dsc_init(&trans_press, trans_props, lv_anim_path_ease_out, 140, 0, NULL);

    lv_style_t *g = &db_theme.glass;
    lv_style_init(g);
    lv_style_set_radius(g, DB_RADIUS);
    lv_style_set_bg_color(g, lv_color_white());
    lv_style_set_bg_grad_color(g, lv_color_white());
    lv_style_set_bg_grad_dir(g, LV_GRAD_DIR_VER);
    lv_style_set_bg_opa(g, LV_OPA_COVER);
    lv_style_set_bg_main_opa(g, 50);  /* oben heller: Licht fällt von oben */
    lv_style_set_bg_grad_opa(g, 16);
    lv_style_set_border_width(g, 1);
    lv_style_set_border_color(g, lv_color_white());
    lv_style_set_border_opa(g, 52);
    lv_style_set_shadow_width(g, 18);
    lv_style_set_shadow_offset_y(g, 5);
    lv_style_set_shadow_color(g, lv_color_black());
    lv_style_set_shadow_opa(g, 70);
    lv_style_set_text_color(g, lv_color_white());
    lv_style_set_text_font(g, &db_font_label);
    lv_style_set_transition(g, &trans_press);

    lv_style_t *p = &db_theme.glass_pressed;
    lv_style_init(p);
    lv_style_set_bg_main_opa(p, 105);
    lv_style_set_bg_grad_opa(p, 55);
    lv_style_set_transform_width(p, -3);
    lv_style_set_transform_height(p, -3);

    /* Lichtkante: horizontal ausgeblendet, in der Mitte hell */
    grad_highlight.dir = LV_GRAD_DIR_HOR;
    grad_highlight.stops_count = 3;
    grad_highlight.stops[0].color = lv_color_white();
    grad_highlight.stops[0].opa = LV_OPA_TRANSP;
    grad_highlight.stops[0].frac = 0;
    grad_highlight.stops[1].color = lv_color_white();
    grad_highlight.stops[1].opa = 170;
    grad_highlight.stops[1].frac = 110;
    grad_highlight.stops[2].color = lv_color_white();
    grad_highlight.stops[2].opa = LV_OPA_TRANSP;
    grad_highlight.stops[2].frac = 255;
    lv_style_init(&db_theme.highlight);
    lv_style_set_bg_opa(&db_theme.highlight, LV_OPA_COVER);
    lv_style_set_bg_grad(&db_theme.highlight, &grad_highlight);

    lv_style_init(&db_theme.fill_muted);
    lv_style_set_bg_color(&db_theme.fill_muted, lv_color_hex(0x8E8E93));
    lv_style_set_bg_grad_color(&db_theme.fill_muted, lv_color_hex(0x636366));
    lv_style_set_bg_main_opa(&db_theme.fill_muted, 120);
    lv_style_set_bg_grad_opa(&db_theme.fill_muted, 90);

    lv_style_t *m = &db_theme.mini;
    lv_style_init(m);
    lv_style_set_radius(m, LV_RADIUS_CIRCLE);
    lv_style_set_bg_color(m, lv_color_white());
    lv_style_set_bg_opa(m, 34);
    lv_style_set_border_width(m, 1);
    lv_style_set_border_color(m, lv_color_white());
    lv_style_set_border_opa(m, 40);
    lv_style_set_text_color(m, lv_color_white());
    lv_style_set_transition(m, &trans_press);

    lv_style_init(&db_theme.mini_pressed);
    lv_style_set_bg_opa(&db_theme.mini_pressed, 110);
    lv_style_set_transform_width(&db_theme.mini_pressed, -3);
    lv_style_set_transform_height(&db_theme.mini_pressed, -3);

    lv_style_init(&db_theme.text);
    lv_style_set_text_color(&db_theme.text, lv_color_white());
    lv_style_set_text_font(&db_theme.text, &db_font_label);

    lv_style_init(&db_theme.text_dim);
    lv_style_set_text_color(&db_theme.text_dim, lv_color_white());
    lv_style_set_text_opa(&db_theme.text_dim, 160);
    lv_style_set_text_font(&db_theme.text_dim, &db_font_small);

    lv_style_t *pl = &db_theme.pill;
    lv_style_init(pl);
    lv_style_set_radius(pl, LV_RADIUS_CIRCLE);
    lv_style_set_bg_color(pl, lv_color_hex(0x1C1C24));
    lv_style_set_bg_opa(pl, 200);
    lv_style_set_border_width(pl, 1);
    lv_style_set_border_color(pl, lv_color_white());
    lv_style_set_border_opa(pl, 50);
    lv_style_set_shadow_width(pl, 16);
    lv_style_set_shadow_opa(pl, 90);
    lv_style_set_shadow_color(pl, lv_color_black());
    lv_style_set_text_color(pl, lv_color_white());
    lv_style_set_text_font(pl, &db_font_small);
    lv_style_set_pad_hor(pl, 12);
    lv_style_set_pad_ver(pl, 5);

    init_colored();
}
