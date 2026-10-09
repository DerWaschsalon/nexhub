cmake_minimum_required(VERSION 3.20)
project(deckbar_sim C)

set(CMAKE_C_STANDARD 11)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()

# LVGL in derselben Version wie in den Waveshare-Beispielen (Arduino_Libraries/lvgl9: 9.3.0)
include(FetchContent)
# SOURCE_SUBDIR zeigt ins Leere: nur herunterladen, LVGL-eigenes CMake nicht einbinden
FetchContent_Declare(lvgl_src
    GIT_REPOSITORY https://github.com/lvgl/lvgl.git
    GIT_TAG v9.3.0
    GIT_SHALLOW TRUE
    SOURCE_SUBDIR _none)
FetchContent_MakeAvailable(lvgl_src)

find_package(PkgConfig REQUIRED)
pkg_check_modules(SDL2 REQUIRED IMPORTED_TARGET sdl2)

file(GLOB_RECURSE LVGL_SOURCES CONFIGURE_DEPENDS ${lvgl_src_SOURCE_DIR}/src/*.c)
add_library(lvgl STATIC ${LVGL_SOURCES})
target_include_directories(lvgl PUBLIC
    ${lvgl_src_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}                    # lv_conf.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../shared-ui)      # lv_conf_deckbar.h
target_compile_definitions(lvgl PUBLIC LV_CONF_INCLUDE_SIMPLE)
target_link_libraries(lvgl PUBLIC PkgConfig::SDL2 m)

add_subdirectory(../shared-ui ${CMAKE_BINARY_DIR}/shared-ui)

add_executable(deckbar-sim src/main.c src/ws_client.c)
target_compile_options(deckbar-sim PRIVATE -Wall -Wextra)
target_compile_options(deckbar_ui PRIVATE -Wall -Wextra -Wno-unused-parameter)
target_link_libraries(deckbar-sim PRIVATE deckbar_ui lvgl pthread)
