# Gemeinsamer UI-Code als statische Bibliothek. Erwartet ein Target "lvgl".
add_library(deckbar_ui STATIC
    src/ui.c
    src/ui_util.c
    src/ui_status.c
    src/ui_images.c
    src/ui_tiles.c
    src/ui_tile_dps.c
    src/ui_tile_claude.c
    src/ui_tile_guide.c
    src/ui_pages.c
    src/theme.c
    src/icons.c
    src/icons_table.c
    fonts/db_font_label.c
    fonts/db_font_small.c
    fonts/db_font_title.c
    fonts/db_font_value.c
    fonts/db_icons_20.c
    fonts/db_icons_28.c
    fonts/db_icons_40.c
    assets/bg_default.c
    assets/guide_icons.c
    third_party/cJSON.c
)
target_include_directories(deckbar_ui PUBLIC include third_party)
target_link_libraries(deckbar_ui PUBLIC lvgl)
