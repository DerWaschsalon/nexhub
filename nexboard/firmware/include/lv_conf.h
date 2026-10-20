/* LVGL-Konfiguration für die Firmware (ESP32-S3, 8 MB PSRAM) */
#ifndef LV_CONF_H
#define LV_CONF_H

#include "lv_conf_deckbar.h"
#include "deckbar_config.h"

/* malloc() des IDF: große Blöcke landen automatisch im PSRAM */
#define LV_USE_STDLIB_MALLOC LV_STDLIB_CLIB
#define LV_USE_STDLIB_STRING LV_STDLIB_CLIB
#define LV_USE_STDLIB_SPRINTF LV_STDLIB_CLIB
#define LV_USE_OS LV_OS_NONE  /* eigener Mutex in main.cpp, wie im Waveshare-Beispiel */

#define LV_DRAW_LAYER_SIMPLE_BUF_SIZE (32 * 1024)

#if DECKBAR_PERF_MONITOR
#define LV_USE_SYSMON 1
#define LV_USE_PERF_MONITOR 1
#define LV_USE_PERF_MONITOR_POS LV_ALIGN_BOTTOM_LEFT
#endif

#endif
