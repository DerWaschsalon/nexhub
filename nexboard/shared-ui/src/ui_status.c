/* NexBoard-UI · Status-Anzeige: die Pille oben rechts und der Startbildschirm, solange kein Layout da ist. */
#include "ui_internal.h"

/* ======================================================================= Status-Anzeige */

void dbui_update_status_ui(void)
{
    const char *txt = "";
    lv_color_t dot = lv_color_hex(0xFF9F0A);
    switch (ui.net) {
    case DECKBAR_NET_NO_WIFI: txt = "Kein WLAN"; dot = lv_color_hex(0xFF453A); break;
    case DECKBAR_NET_SEARCHING: txt = ui.ws_open ? "Verbinde …" : "Suche Daemon …"; break;
    case DECKBAR_NET_AUTH_FAILED: txt = "Token abgelehnt"; dot = lv_color_hex(0xFF453A); break;
    case DECKBAR_NET_ONLINE: txt = "Verbunden"; dot = lv_color_hex(0x30D158); break;
    }
    bool online = ui.net == DECKBAR_NET_ONLINE;

    lv_label_set_text(ui.pill_label, txt);
    lv_obj_set_style_bg_color(ui.pill_dot, dot, 0);
    if (online || !ui.have_layout) lv_obj_add_flag(ui.pill, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_remove_flag(ui.pill, LV_OBJ_FLAG_HIDDEN);

    if (ui.have_layout) {
        lv_obj_add_flag(ui.splash, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_remove_flag(ui.splash, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(ui.splash_status, online ? "Warte auf Layout …" : txt);
        lv_label_set_text(ui.splash_detail, ui.detail);
    }
}

void dbui_set_net(deckbar_net_t n)
{
    if (ui.net == n) return;
    ui.net = n;
    dbui_update_status_ui();
}

void dbui_build_status_ui(void)
{
    lv_obj_t *top = lv_layer_top();

    ui.pill = dbui_plain_obj(top);
    lv_obj_add_style(ui.pill, &db_theme.pill, 0);
    lv_obj_set_size(ui.pill, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_align(ui.pill, LV_ALIGN_TOP_RIGHT, -10, 6);
    lv_obj_set_flex_flow(ui.pill, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(ui.pill, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(ui.pill, 6, 0);
    lv_obj_remove_flag(ui.pill, LV_OBJ_FLAG_CLICKABLE);
    ui.pill_dot = dbui_plain_obj(ui.pill);
    lv_obj_set_size(ui.pill_dot, 8, 8);
    lv_obj_set_style_radius(ui.pill_dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(ui.pill_dot, LV_OPA_COVER, 0);
    ui.pill_label = dbui_text_label(ui.pill, &db_font_small, "");

    ui.splash = dbui_plain_obj(top);
    lv_obj_add_style(ui.splash, &db_theme.glass, 0);
    lv_obj_set_size(ui.splash, 380, 120);
    lv_obj_center(ui.splash);
    lv_obj_remove_flag(ui.splash, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_flex_flow(ui.splash, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(ui.splash, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_row(ui.splash, 4, 0);
    lv_obj_t *icon = dbui_text_label(ui.splash, &db_icons_28, deckbar_icon_glyph("view-grid"));
    lv_obj_set_style_text_color(icon, db_theme_color(DB_STYLE_ACCENT), 0);
    dbui_text_label(ui.splash, &db_font_title, "NexBoard");
    ui.splash_status = dbui_text_label(ui.splash, &db_font_label, "");
    ui.splash_detail = dbui_text_label(ui.splash, &db_font_small, "");
    lv_obj_add_style(ui.splash_detail, &db_theme.text_dim, 0);
}
