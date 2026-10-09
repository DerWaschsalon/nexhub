#pragma once
/*
 * Waveshare ESP32-S3-Touch-LCD-3.49 **V2** (PCB-Aufdruck "Rev1.1", QC-Label "V2").
 *
 * Quelle (nicht geraten): https://github.com/waveshareteam/ESP32-S3-Touch-LCD-3.49-V2
 *   Arduino/examples/10_LVGL_V9_Test/user_config.h  (Commit 1c157e6, 2026-06-09)
 *   gegengeprüft mit schematic/ESP32-S3-Touch-LCD-3.49 V2.pdf
 *
 * ACHTUNG: Das Repo ohne "-V2" enthält die V1-Belegung (LCD_RST=GPIO21, BL=GPIO8).
 * Auf V2 ist GPIO21 der TE-*Ausgang* des Displays – nicht als Ausgang treiben!
 */
#include "driver/gpio.h"

/* QSPI-Display (AXS15231B) */
#define BOARD_LCD_HOST       SPI3_HOST
#define BOARD_LCD_CS         GPIO_NUM_9
#define BOARD_LCD_PCLK       GPIO_NUM_10
#define BOARD_LCD_D0         GPIO_NUM_11
#define BOARD_LCD_D1         GPIO_NUM_12
#define BOARD_LCD_D2         GPIO_NUM_13
#define BOARD_LCD_D3         GPIO_NUM_14
#define BOARD_LCD_TE         GPIO_NUM_21  /* V2: TE (Eingang), wird hier nicht genutzt */
#define BOARD_LCD_BL         GPIO_NUM_42  /* V2: Backlight-PWM */
#define BOARD_LCD_PCLK_HZ    (40 * 1000 * 1000)
#define BOARD_LCD_PHYS_W     172          /* Panel nativ hochkant */
#define BOARD_LCD_PHYS_H     640

/* I2C0: RTC, IMU, IO-Expander */
#define BOARD_I2C0_SCL       GPIO_NUM_48
#define BOARD_I2C0_SDA       GPIO_NUM_47
/* I2C1: Touch (Teil des AXS15231B) */
#define BOARD_TOUCH_SCL      GPIO_NUM_18
#define BOARD_TOUCH_SDA      GPIO_NUM_17
#define BOARD_TOUCH_ADDR     0x3B
#define BOARD_I2C_HZ         300000

#define BOARD_EXIO_INT       GPIO_NUM_8   /* V2: Interrupt des TCA9554 */

/* TCA9554 (A0..A2 = GND -> 0x20), Bits laut V2-user_config.h */
#define BOARD_EXIO_TOUCH_INT (1ULL << 0)
#define BOARD_EXIO_BL_EN     (1ULL << 1)
#define BOARD_EXIO_LCD_RST   (1ULL << 5)
#define BOARD_EXIO_SYS_EN    (1ULL << 6)  /* Akku-Selbsthaltung; bei USB-Versorgung egal */
