/*
 * DeckBar-Firmware: WLAN + mDNS + WebSocket, rendert den gemeinsamen shared-ui-Code.
 *
 * Threads:
 *   - LVGL-Task (Kern 1): lv_timer_handler() unter lvgl_mux, arbeitet die Eingangs-Queue ab.
 *   - loop() (Arduino, Kern 1): WLAN, mDNS-Suche, WebSocketsClient; einzige Stelle, die das
 *     Netzwerk anfasst. Ausgehende Nachrichten kommen über die Ausgangs-Queue.
 *   - lcd_tx (Kern 0): Frame-Übertragung, siehe display.c.
 */
#include <Arduino.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <WebSocketsClient.h>
#include <WiFi.h>

#include "deckbar/hal.h"
#include "deckbar/ui.h"
#include "deckbar_config.h"
#include "display.h"
#include "lvgl.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "include/secrets.h fehlt – secrets.example.h kopieren und ausfüllen"
#endif
#ifndef DECKBAR_PORT
#define DECKBAR_PORT DECKBAR_DEFAULT_PORT
#endif

static const char *TAG = "deckbar";

/* ------------------------------------------------------------------ Queues */
enum { EV_OPEN, EV_CLOSE, EV_CLOSE_NOWIFI, EV_MSG, EV_DETAIL };
struct net_ev_t {
    uint8_t type;
    char *data; /* ps_malloc, Empfänger gibt frei */
    size_t len;
};

static QueueHandle_t q_in;  /* Netz -> LVGL */
static QueueHandle_t q_out; /* LVGL -> Netz (char*, ps_malloc) */
static SemaphoreHandle_t lvgl_mux;
static volatile bool want_reconnect;
static volatile bool ws_connected;

static void push_in(uint8_t type, const char *data = nullptr, size_t len = 0)
{
    net_ev_t ev = {type, nullptr, len};
    if (data) {
        ev.data = (char *)ps_malloc(len + 1);
        if (!ev.data) return;
        memcpy(ev.data, data, len);
        ev.data[len] = 0;
    }
    /* Bilder (art/bg) kommen in Dutzenden Teilen am Stück: lieber die Netzwerkschleife kurz
     * bremsen (TCP puffert), als Nachrichten zu verwerfen – sonst wird ein Bild nie vollständig. */
    if (xQueueSend(q_in, &ev, pdMS_TO_TICKS(2000)) != pdTRUE) {
        log_printf("Eingangs-Queue voll, Nachricht verworfen\n");
        free(ev.data);
    }
}

/* ------------------------------------------------------------------ HAL für shared-ui */
extern "C" bool deckbar_hal_send(const char *text, size_t len)
{
#if DECKBAR_TOUCH_DEBUG
    log_printf("TXM %.*s\n", (int)(len > 120 ? 120 : len), text);
#endif
    if (!ws_connected) return false;
    char *copy = (char *)ps_malloc(len + 1);
    if (!copy) return false;
    memcpy(copy, text, len);
    copy[len] = 0;
    if (xQueueSend(q_out, &copy, 0) != pdTRUE) {
        free(copy);
        return false;
    }
    return true;
}

extern "C" void deckbar_hal_reconnect(void)
{
    want_reconnect = true;
}

static Preferences prefs;

extern "C" bool deckbar_hal_store(const char *key, const char *data, size_t len)
{
    return prefs.putBytes(key, data, len) == len;
}

extern "C" char *deckbar_hal_load(const char *key)
{
    size_t n = prefs.getBytesLength(key);
    if (n == 0) return nullptr;
    char *buf = (char *)malloc(n + 1);
    if (!buf) return nullptr;
    if (prefs.getBytes(key, buf, n) != n) {
        free(buf);
        return nullptr;
    }
    buf[n] = 0;
    return buf;
}

/* ------------------------------------------------------------------ LVGL-Task */
static uint32_t tick_cb(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}

static void lvgl_task(void *arg)
{
    bool backlight = false;
    for (;;) {
        uint32_t delay_ms = 5;
        if (xSemaphoreTake(lvgl_mux, portMAX_DELAY) == pdTRUE) {
            net_ev_t ev;
            while (xQueueReceive(q_in, &ev, 0) == pdTRUE) {
                switch (ev.type) {
                case EV_OPEN: deckbar_ui_net_connected(); break;
                case EV_CLOSE: deckbar_ui_net_disconnected(false); break;
                case EV_CLOSE_NOWIFI: deckbar_ui_net_disconnected(true); break;
                case EV_MSG:
#if DECKBAR_TOUCH_DEBUG
                    log_printf("RX %u %.100s\n", (unsigned)ev.len, ev.data);
#endif
                    deckbar_ui_net_message(ev.data, ev.len);
                    break;
                case EV_DETAIL: deckbar_ui_set_detail(ev.data); break;
                }
                free(ev.data);
            }
            delay_ms = lv_timer_handler();
            xSemaphoreGive(lvgl_mux);
        }
        if (!backlight) {
            /* erst einschalten, wenn der erste Frame im Panel steht */
            vTaskDelay(pdMS_TO_TICKS(60));
            display_backlight_on();
            backlight = true;
        }
        if (delay_ms > 30) delay_ms = 30;
        if (delay_ms < 2) delay_ms = 2;
        vTaskDelay(pdMS_TO_TICKS(delay_ms));
    }
}

/* ------------------------------------------------------------------ Netzwerk */
static WebSocketsClient ws;
static char device_id[24];
static char detail[64];
static IPAddress daemon_ip;
static uint16_t daemon_port = DECKBAR_PORT;
static bool ws_started;
static uint32_t last_mdns_try;
static uint32_t ws_started_at;
static bool wifi_was_up;

static void set_detail(const char *fmt, ...)
{
    char buf[64];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (strcmp(buf, detail) == 0) return;
    strcpy(detail, buf);
    ESP_LOGI(TAG, "%s", buf);
    push_in(EV_DETAIL, buf, strlen(buf));
}

static void ws_event(WStype_t type, uint8_t *payload, size_t len)
{
    switch (type) {
    case WStype_CONNECTED:
        ws_connected = true;
        set_detail("Daemon %s:%u", daemon_ip.toString().c_str(), daemon_port);
        push_in(EV_OPEN);
        break;
    case WStype_DISCONNECTED:
        if (ws_connected) log_printf("WS getrennt (frei: intern %u, PSRAM %u)\n", (unsigned)ESP.getFreeHeap(),
                                     (unsigned)ESP.getFreePsram());
        if (ws_connected) push_in(EV_CLOSE);
        ws_connected = false;
        break;
    case WStype_TEXT:
        push_in(EV_MSG, (const char *)payload, len);
        break;
    case WStype_ERROR: log_printf("WS-Fehler %.*s\n", (int)len, payload ? (const char *)payload : ""); break;
    default: break;
    }
}

static bool resolve_daemon(void)
{
#ifdef DECKBAR_HOST
    if (daemon_ip.fromString(DECKBAR_HOST)) return true;
    IPAddress ip;
    if (WiFi.hostByName(DECKBAR_HOST, ip)) {
        daemon_ip = ip;
        return true;
    }
    set_detail("Host %s nicht auflösbar", DECKBAR_HOST);
    return false;
#else
    set_detail("Suche _deckbar._tcp per mDNS …");
    int n = MDNS.queryService("deckbar", "tcp");
    if (n <= 0) {
        set_detail("Kein Daemon per mDNS gefunden");
        return false;
    }
    daemon_ip = MDNS.address(0);
    daemon_port = MDNS.port(0);
    return true;
#endif
}

static void stop_ws(void)
{
    if (ws_started) ws.disconnect();
    ws_started = false;
    if (ws_connected) push_in(EV_CLOSE);
    ws_connected = false;
}

static void net_loop(void)
{
    bool wifi_up = WiFi.status() == WL_CONNECTED;
    if (!wifi_up) {
        if (wifi_was_up || ws_started) {
            stop_ws();
            push_in(EV_CLOSE_NOWIFI);
        }
        wifi_was_up = false;
        set_detail("WLAN „%s“ …", WIFI_SSID);
        return;
    }
    if (!wifi_was_up) {
        wifi_was_up = true;
        MDNS.end();
        MDNS.begin(device_id);
        push_in(EV_CLOSE); /* Anzeige: "Suche Daemon" */
        set_detail("WLAN ok, IP %s", WiFi.localIP().toString().c_str());
    }

    if (want_reconnect) {
        want_reconnect = false;
        ESP_LOGW(TAG, "Neuverbindung angefordert");
        stop_ws();
    }

    /* Nach 10 s ohne Verbindung neu per mDNS suchen (Daemon evtl. auf anderer IP) */
    if (ws_started && !ws_connected && millis() - ws_started_at > 10000) stop_ws();

    if (!ws_started) {
        if (millis() - last_mdns_try < 3000 && last_mdns_try) return;
        last_mdns_try = millis();
        if (!resolve_daemon()) return;
        set_detail("Verbinde %s:%u", daemon_ip.toString().c_str(), daemon_port);
        ws.begin(daemon_ip, daemon_port, "/ws");
        ws.onEvent(ws_event);
        ws.setReconnectInterval(2000);
        ws_started = true;
        ws_started_at = millis();
    }

    ws.loop();

    char *out;
    while (ws_connected && xQueueReceive(q_out, &out, 0) == pdTRUE) {
        ws.sendTXT(out, strlen(out));
        free(out);
    }
}

/* ------------------------------------------------------------------ Arduino */
void setup()
{
    Serial.begin(115200);
    log_printf("DeckBar %s, Reset-Grund %d\n", DECKBAR_FW_VERSION, (int)esp_reset_reason());
    q_in = xQueueCreate(32, sizeof(net_ev_t));
    q_out = xQueueCreate(32, sizeof(char *));
    lvgl_mux = xSemaphoreCreateMutex();
    prefs.begin("deckbar", false);

    uint8_t mac[6];
    WiFi.macAddress(mac);
    snprintf(device_id, sizeof device_id, "deckbar-%02x%02x%02x", mac[3], mac[4], mac[5]);

    lv_init();
    lv_log_register_print_cb([](lv_log_level_t, const char *buf) { log_printf("%s", buf); });
    lv_tick_set_cb(tick_cb);
    display_init();

    static deckbar_config_t cfg = {
        .token = DECKBAR_TOKEN,
        .device_id = device_id,
        .model = "waveshare-s3-lcd-3.49-v2",
        .fw = DECKBAR_FW_VERSION,
        .sim = false,
    };
    deckbar_ui_init(&cfg);

    xTaskCreatePinnedToCore(lvgl_task, "lvgl", 12 * 1024, NULL, 3, NULL, 1);

    WiFi.mode(WIFI_STA);
    WiFi.setHostname(device_id);
    WiFi.setSleep(false); /* geringere Latenz beim Tippen */
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    ESP_LOGI(TAG, "%s gestartet, PSRAM frei: %u KB", device_id, (unsigned)(ESP.getFreePsram() / 1024));
}

void loop()
{
    net_loop();
    delay(1);
}
