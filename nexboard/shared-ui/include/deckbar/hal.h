#pragma once
/*
 * Hardware-Abstraktion: Diese Funktionen implementiert jede Plattform (Simulator, Firmware).
 *
 * Display und Touch laufen über LVGLs eigene Treiber-Schnittstelle: Die Plattform legt
 * vor deckbar_ui_init() ein lv_display_t und ein lv_indev_t (POINTER) an. shared-ui
 * ruft niemals Hardware direkt auf.
 *
 * Alle deckbar_ui_*-Funktionen dürfen nur aus dem LVGL-Kontext aufgerufen werden
 * (derselbe Thread/Task, der lv_timer_handler() ausführt, bzw. mit gehaltenem LVGL-Lock).
 * Netzwerk-Callbacks aus anderen Threads muss die Plattform in eine Queue stellen.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Einen WebSocket-Textframe senden. false, wenn gerade keine Verbindung besteht. */
bool deckbar_hal_send(const char *text, size_t len);

/* Verbindung trennen und neu aufbauen (z. B. nach Heartbeat-Timeout). */
void deckbar_hal_reconnect(void);

/* Kleinen Text-Blob dauerhaft speichern (Layout-Cache). */
bool deckbar_hal_store(const char *key, const char *data, size_t len);

/* Gespeicherten Blob laden; Rückgabe mit malloc() allokiert (Aufrufer gibt mit free() frei)
 * oder NULL. */
char *deckbar_hal_load(const char *key);

/* Größeren Binär-Blob dauerhaft speichern (Hintergrundbild, ~220 KB): Kopf und Daten hintereinander.
 * head == NULL und len == 0 löscht ihn. */
bool deckbar_hal_store_bin(const char *key, const void *head, size_t head_len, const void *data, size_t len);
/* Binär-Blob laden; Rückgabe mit malloc() allokiert (Aufrufer gibt mit free() frei) oder NULL. */
uint8_t *deckbar_hal_load_bin(const char *key, size_t *len);

#ifdef __cplusplus
}
#endif
