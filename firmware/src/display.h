#pragma once
#include <stdint.h>

#include "lvgl.h"

#ifdef __cplusplus
extern "C" {
#endif

/* I2C, IO-Expander, Panel, LVGL-Display + Touch. lv_init() muss vorher gelaufen sein. */
lv_display_t *display_init(void);
/* Backlight einschalten (erst nach dem ersten gerenderten Frame, sonst sieht man Müll). */
void display_backlight_on(void);
void display_set_brightness(uint8_t level);

#ifdef __cplusplus
}
#endif
