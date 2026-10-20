/*
 * Gemeinsame LVGL-Einstellungen für Simulator und Firmware.
 * Jede Plattform hat ein eigenes lv_conf.h, das diese Datei einbindet und danach
 * Plattformspezifisches (Speicher, OS, Treiber) setzt. Alles Nicht-Gesetzte nimmt
 * LVGL aus lv_conf_internal.h.
 */
#ifndef LV_CONF_DECKBAR_H
#define LV_CONF_DECKBAR_H

#define LV_COLOR_DEPTH 16            /* RGB565 wie auf der Hardware */

#define LV_DEF_REFR_PERIOD 16        /* bis ~60 fps, Ziel auf der Hardware >= 30 */
#define LV_DPI_DEF 160

#define LV_GRADIENT_MAX_STOPS 3      /* Lichtkante: transparent -> hell -> transparent */
#define LV_DRAW_SW_SHADOW_CACHE_SIZE 32
#define LV_DRAW_SW_CIRCLE_CACHE_SIZE 8

#define LV_TXT_ENC LV_TXT_ENC_UTF8
#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_DEFAULT &lv_font_montserrat_14

#define LV_USE_LOG 1
#define LV_LOG_LEVEL LV_LOG_LEVEL_WARN

/* benötigte Widgets; der Rest bleibt auf LVGL-Standard */
#define LV_USE_LABEL 1
#define LV_USE_IMAGE 1
#define LV_USE_TILEVIEW 1
#define LV_USE_SPINNER 1
#define LV_USE_ARC 1
#define LV_LABEL_LONG_TXT_HINT 1

#define LV_USE_SNAPSHOT 1

#endif
