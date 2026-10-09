#pragma once
/* "Liquid Glass"-Styles. Intern für shared-ui. */
#include "lvgl.h"

typedef enum {
    DB_STYLE_DEFAULT,
    DB_STYLE_ACCENT,
    DB_STYLE_DANGER,
    DB_STYLE_SUCCESS,
    DB_STYLE_WARNING,
    DB_STYLE_COUNT
} db_style_t;

#define DB_RADIUS 18
#define DB_PAD 8
#define DB_GAP 8

/* Zustand "stummgeschaltet" bei Slidern */
#define DB_STATE_MUTED LV_STATE_USER_1

typedef struct {
    lv_style_t glass;              /* Grundkachel */
    lv_style_t glass_pressed;      /* LV_STATE_PRESSED */
    lv_style_t tint[DB_STYLE_COUNT];   /* dezente Färbung für style != default */
    lv_style_t active[DB_STYLE_COUNT]; /* LV_STATE_CHECKED (Toggle aktiv) */
    lv_style_t highlight;          /* 1-px-Lichtkante oben */
    lv_style_t fill;               /* Slider-Füllung */
    lv_style_t fill_muted;         /* Slider-Füllung, DB_STATE_MUTED */
    lv_style_t mini;               /* runde Mini-Buttons in der Media-Kachel */
    lv_style_t mini_pressed;
    lv_style_t text;               /* Standardtext */
    lv_style_t text_dim;
    lv_style_t pill;               /* Statuspille / Splash */
} db_theme_t;

extern db_theme_t db_theme;

void db_theme_init(void);
void db_theme_set_accent(lv_color_t accent);
lv_color_t db_theme_color(db_style_t s);
db_style_t db_style_parse(const char *name);
