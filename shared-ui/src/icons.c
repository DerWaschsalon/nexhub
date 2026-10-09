#include "deckbar/icons.h"

#include <stdlib.h>
#include <string.h>

static int cmp(const void *key, const void *elem)
{
    return strcmp((const char *)key, ((const deckbar_icon_t *)elem)->name);
}

const char *deckbar_icon_glyph(const char *name)
{
    if (!name || !*name) return NULL;
    const deckbar_icon_t *hit = bsearch(name, deckbar_icons, deckbar_icons_count, sizeof(deckbar_icon_t), cmp);
    return hit ? hit->glyph : NULL;
}
