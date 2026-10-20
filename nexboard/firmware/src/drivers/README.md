# Treiber aus dem Waveshare-V2-Repo

Unverändert übernommen aus
https://github.com/waveshareteam/ESP32-S3-Touch-LCD-3.49-V2 (Commit 1c157e6, 2026-06-09),
`Arduino/examples/10_LVGL_V9_Test/src/{axs15231b,tca9554}`.

Beide stammen ursprünglich von Espressif (SPDX: Apache-2.0, siehe Dateiköpfe):
- `esp_lcd_axs15231b.*` – Paneltreiber AXS15231B (QSPI); `../touch/` wird nur für dessen Header gebraucht
- `esp_io_expander*.*`, `esp_io_expander_tca9554.*` – IO-Expander TCA9554 (LCD-Reset, Backlight-Enable)
