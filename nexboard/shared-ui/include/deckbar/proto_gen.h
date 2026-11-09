/* Erzeugt von proto/nexproto/codegen.py, nicht von Hand ändern. */
#pragma once

#define DECKBAR_PROTO_VERSION 1
#define DECKBAR_DEFAULT_PORT 8765
#define DECKBAR_SCREEN_W 640
#define DECKBAR_SCREEN_H 172
#define DECKBAR_HELLO_TIMEOUT_S 5
#define DECKBAR_MAX_MESSAGE_BYTES 15360
#define DECKBAR_MAX_PAGES 8
#define DECKBAR_MAX_ITEMS_PER_PAGE 24
#define DECKBAR_MAX_COLS 8
#define DECKBAR_MAX_ROWS 3
#define DECKBAR_ID_MAX 32
#define DECKBAR_LABEL_MAX 24
#define DECKBAR_ICON_MAX 48
#define DECKBAR_IMAGE_ID_MAX 16
#define DECKBAR_ART_MIN 8
#define DECKBAR_ART_MAX 160
#define DECKBAR_BIN_HEADER_BYTES 27
#define DECKBAR_DPS_MAX_ROWS 8
#define DECKBAR_DPS_DEFAULT_PLAYERS 5
#define DECKBAR_LONG_PRESS_MS 600
#define DECKBAR_SLIDER_EVENTS_PER_S 20

/* Klassenfarben: { Schlüssel aus state.dps.rows[].cls, RGB } */
#define DECKBAR_CLASS_COLORS \
    {"gladiator", 0x4FD1C5}, \
    {"templar", 0x5F8CFF}, \
    {"assassin", 0x7BE35A}, \
    {"ranger", 0x41D98A}, \
    {"sorcerer", 0x9A6BFF}, \
    {"spiritmaster", 0xE06BFF}, \
    {"cleric", 0xF2C15A}, \
    {"chanter", 0xFF9A3D}, \
    {"brawler", 0xE85D5D}, \

#define DECKBAR_UNKNOWN_CLASS_COLOR 0x8E8E93
