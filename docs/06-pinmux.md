# 6. Пиновете: pinmux профили

## Идеята

Всеки pad на AM3352 има до 8 функции (GPIO, UART, I2C, SPI, PWM...). Коя е избрана, се решава
в device tree (DTB), който U-Boot зарежда от NAND mtd6. Кернелът и initramfs-ът са еднакви за
всички платки; различни са само DTB-тата.

DTB-то се генерира от **профил**: YAML файл, в който пише кой пин каква функция има. Няма
`config-pin` и нищо не се превключва по време на работа: пиновете са в правилното състояние
от момента, в който кернелът тръгне, и след всеки рестарт. Всеки pad, който не е в профила, се
задава като GPIO вход с pull-down (безопасното състояние).

## Готови профили

| профил | за | файл |
|---|---|---|
| `default` | оригиналната Bitmain платка: 4 UART-а към хеш платките, RST0-3, PLUG0-3, LED-ове, бутон, вентилатори, I2C2; плюс Q0-3 / I0-3 на LCD pad-овете. Вграден в образа | `firmware/pinmux/boards/default.yaml` |
| `breakout` | тестовата платка от `hardware/breakout`: 8 изхода, 8 входа, 2 x RS-485, ADC, I2C експандер и температура | `.../breakout.yaml` |
| `example-modbus-rtu` | Modbus RTU шлюз с 4 RS-485 канала | `.../example-modbus-rtu.yaml` |

Локални профили, правени на конкретна платка, стоят в `/config/pinmux/` на нея.

Кой профил е активен: `antminer-dtb current`, или „active on this board“ в редактора.

## Визуалният редактор

`http://<ip>/pinmux` → избери профил → **board editor** (или създай нов по име).

- P9 вляво, P8 вдясно, както са на платката. Цветът показва функцията; щрихованите с катинар
  са заети от системата (NAND, Ethernet, конзола, SD) и не могат да се ползват.
- Клик на пин: функция (само тези, които pad-ът поддържа), за GPIO посока, начално ниво, pull,
  **име на линията**, hog, бележка. Името е важно: OpenPLC използва линиите `I0..`, `Q0..`
  (виж 07-openplc), а програмите ти могат да ги търсят по име (`gpioset Q0=1`).
- AIN плочките включват/изключват аналоговите входове (1.8 V максимум!).
- „Pads outside the headers“ са pad-овете, изведени към Bitmain конекторите (UART4 и др.).
- „I2C devices“: за всяка включена I2C шина устройства (GPIO експандери, температурни сензори)
  с адрес и имена на линиите.
- Жълта точка = променено, червено = грешка от проверката, оранжево = непълна периферия
  (например UART само с TX).
- **Validate & build** генерира и компилира DTB-то на самата платка (~2 s) и показва грешките
  по пин. **Save** записва в `/config/pinmux/`. **Save + flash to mtd6** записва DTB-то в NAND;
  важи от следващия рестарт. **Export YAML** сваля профила.

„YAML (advanced)“ отваря профила като текст за неща, които редакторът не покрива (SPI, CAN,
`unused: keep`).

## От командния ред

На платката (пакет `antminer-pinmux`):
```sh
antminer-dtb list                                   # профилите
antminer-dtb build breakout                         # -> /tmp/am335x-antminer-breakout.dtb (+ .dts, .json)
antminer-dtb build /config/pinmux/my.yaml
antminer-dtb flash /tmp/am335x-antminer-breakout.dtb    # mtd6, с проверка
reboot
```

На PC-то (WSL/Linux; kernel tree-то се взима от Yocto билда или от `~/antminer/linux`, или `KSRC=`):
```sh
cd /mnt/e/Antminer/repo/firmware/pinmux
bash build-dtb.sh boards/breakout.yaml              # -> firmware/out/am335x-antminer-breakout.dtb
```
```sh
python firmware/tools/antminer.py deploy-dtb breakout --netboot-only   # проба от RAM
python firmware/tools/antminer.py deploy-dtb breakout                  # запис в mtd6 + reboot
```

Всички пътища дават едно и също DTB (проверено байт по байт).

## Формат на профила

```yaml
name: my-board
pins:
  P9.24: uart1_txd                                    # само функция
  P9.26: {func: uart1_rxd, pull: up}
  uart0_ctsn: uart4_rxd                               # pad извън хедърите, по име
  P8.43: {func: gpio, dir: out, init: 0, name: Q0}    # изход, ниско при старт
  P8.39: {func: gpio, dir: in, pull: up, name: I0, comment: "бутон старт"}
  P9.17: {func: gpio, dir: out, init: 1, name: RS485_DE, hog: true}   # кернелът държи линията
adc: [0, 1, 2, 3]
i2c:
  i2c2:
    clock-frequency: 100000
    devices:
      - {compatible: "nxp,pcf8574", reg: 0x20, props: {gpio-controller: true, "#gpio-cells": 2,
         gpio-line-names: [EXP0, EXP1, EXP2, EXP3, EXP4, EXP5, EXP6, EXP7]}}
      - {compatible: "ti,tmp1075", reg: 0x48}
spi: {spi1: {spidev: [0], max-frequency: 16000000}}
unused: default            # останалите свободни pad-ове -> GPIO вход pull-down; keep = не ги пипай
```

Пълното описание на опциите и вътрешността на генератора: `firmware/pinmux/README.md`.
Таблица P8/P9 с функциите на всеки pad: web UI → Pinmux → „Header pin table“, или
`docs/BBB_Pins.xlsx`.

## Проверка на платката

```sh
antminer-dtb current
gpioinfo                                     # линиите с имената от профила
gpioset -t0 Q0=1 && gpioget I0
cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw     # AIN0, 0..4095 = 0..1.8 V
ls /dev/ttyS* /dev/i2c-*
i2cdetect -y 2
cat /sys/kernel/debug/pinctrl/44e10800.pinmux-pinctrl-single/pins | grep 8a8   # реалният регистър
```

## Капани

- Профилът `default` е и вграденото DTB на образа (`firmware/dts/am335x-antminer.dts` се генерира
  от него). Промяна в `default.yaml` в repo-то иска `bash build-dtb.sh boards/default.yaml` и
  пребилд, за да влезе в образите.
- ADC входовете са **1.8 V**. 3.3 V на AIN пин го поврежда.
- RST линиите в `default` тръгват с 0 (хеш платките в reset), LED-овете са активни на ниско ниво.
- I2C устройство без драйвер в кернела не дава грешка: просто не се появява. Шаблоните в
  редактора са само за драйвери, които кернелът има (PCF857x, LM75/TMP1075 семейството).
