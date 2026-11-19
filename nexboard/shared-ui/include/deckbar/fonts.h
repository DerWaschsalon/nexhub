#pragma once
#include "lvgl.h"

LV_FONT_DECLARE(db_font_label);  /* Inter Medium 14 – Button-Beschriftung */
LV_FONT_DECLARE(db_font_small);  /* Inter Medium 12 – Nebentext */
LV_FONT_DECLARE(db_font_title);  /* Inter SemiBold 17 – Tracktitel */
LV_FONT_DECLARE(db_font_value);  /* Inter SemiBold 22 – Slider-Werte */
LV_FONT_DECLARE(db_icons_20);
LV_FONT_DECLARE(db_icons_28);
LV_FONT_DECLARE(db_icons_40);

LV_IMAGE_DECLARE(deckbar_bg_default);
/* Symbole des Leveling-Guides, Index = Zeichen - DECKBAR_GUIDE_ICON_FIRST (proto_gen.h) */
extern const lv_image_dsc_t *const deckbar_guide_icons[];
