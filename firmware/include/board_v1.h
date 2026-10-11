#pragma once
/*
 * Waveshare ESP32-S3-Touch-LCD-3.49 **V1** (ohne "-V2").
 * Pins aus github.com/waveshareteam/ESP32-S3-Touch-LCD-3.49 und am Board geprüft
 * (Navonex PC-Bediendisplay): LCD-Reset GPIO21, Backlight-PWM GPIO8 (invertiert).
 * Bauen mit -DDECKBAR_BOARD_V1=1 (env:deckbar-v1).
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

/* Expander-Bits nur, damit der V2-Code mitkompiliert; auf V1 wird der Expander nicht angesprochen */
#define BOARD_EXIO_TOUCH_INT 0
#define BOARD_EXIO_BL_EN     0
#define BOARD_EXIO_LCD_RST   0
#define BOARD_EXIO_SYS_EN    0

#define BOARD_LCD_RST        GPIO_NUM_21
#define BOARD_LCD_BL         GPIO_NUM_8
