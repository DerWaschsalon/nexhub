#pragma once
/* Icon-Namen (Material Design Icons) -> UTF-8-Glyph in den db_icons_*-Schriften. */

typedef struct {
    const char *name;
    const char *glyph;
} deckbar_icon_t;

extern const deckbar_icon_t deckbar_icons[];
extern const unsigned deckbar_icons_count;

/* Liefert den Glyph oder NULL, wenn der Name unbekannt ist. Tabelle ist sortiert. */
const char *deckbar_icon_glyph(const char *name);
