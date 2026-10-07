# pinmux — per-board device tree от YAML профил

> Справочник за формата и генератора. Ръководство за употреба (редактор, флаш, проверка):
> [docs/06-pinmux.md](../../docs/06-pinmux.md).

Идеята: кернелът е един и същ за всички платки, а конфигурацията на пиновете е **device tree
per платка**, което U-Boot зарежда от NAND дяла `fdt` (mtd6). Профилът е YAML файл в `boards/`,
генераторът прави `.dts`, компилира се с dtc и се записва в mtd6. Няма runtime pinmux, няма
config-pin, пиновете са в правилното състояние от момента, в който кернелът приложи pinctrl.

## Работен поток

```sh
# WSL
bash build-dtb.sh boards/default.yaml        # -> dts/am335x-antminer.dts (образът) + out/am335x-antminer-default.dtb
bash build-dtb.sh boards/<name>.yaml         # -> out/am335x-antminer-<name>.dts/.dtb
```
```powershell
# Windows, платка на COM3
powershell -File ..\tools\deploy-dtb.ps1 -Profile <name> -NetbootOnly   # проба от RAM, NAND не се пипа
powershell -File ..\tools\deploy-dtb.ps1 -Profile <name>                # запис в mtd6 + reboot
```

`default.yaml` е особен: от него се генерира `dts/am335x-antminer.dts`, който build-kernel.sh и
Yocto рецептата вграждат в образа. Всичко друго е per-board.

## Формат на профила

```yaml
name: modbus-rtu-4ch
pins:
  P9.24: uart1_txd                              # само функция
  P9.26: {func: uart1_rxd, pull: up}
  uart0_ctsn: uart4_rxd                         # по име на pad, за pad-ове извън P8/P9
  P8.43: {func: gpio, dir: out, init: 0, name: Q0}   # pull следва init: 0 -> down, 1 -> up
  P8.39: {func: gpio, dir: in, pull: up, name: I0}
  P9.17: {func: gpio, dir: out, init: 1, name: RS485_DE, hog: true}  # hog = кернелът го държи
adc: [0, 1, 2, 3]                               # AIN0..3, 1.8 V
i2c: {i2c2: {clock-frequency: 400000}}
spi: {spi1: {spidev: [0, 1], max-frequency: 16000000}}
```

Всеки свободен pad, който не е в профила, се задава изрично като GPIO вход с pulldown
(reset състоянието). Иначе при топъл рестарт pad-ът пази каквото е оставил предишният
boot или U-Boot. `unused: keep` изключва това.

Опции на пин: `func`, `pull` (up|down|none), `rx` (true|false), `slew` (fast|slow),
`dir` (in|out, само gpio), `init` (0|1, gpio out), `name` (име на GPIO линията за libgpiod),
`hog` (true: кернелът заема линията с това ниво, userspace не може да я ползва).

Периферии се включват автоматично от функциите: `uartN_*` → `&uartN`, `i2cN_*` → `&i2cN`,
`spiN_*` → `&spiN` + spidev, `ehrpwmNa/b`, `ecapN_in_pwmN_out` → PWM, `dcanN_rx/tx` → CAN,
`eqepN*` → енкодер, `timerN` → само mux. ADC каналите нямат pinmux.

I2C устройства на шината се описват като child възли (`boards/breakout.yaml`):
```yaml
i2c:
  i2c2:
    clock-frequency: 100000
    devices:
      - {compatible: "nxp,pcf8574", reg: 0x20, label: exp_io,
         props: {gpio-controller: true, "#gpio-cells": 2, gpio-line-names: [EXP0, EXP1]}}
      - {compatible: "ti,tmp1075", reg: 0x48}
```
`props` стойности: `true` → празно property, число → `<n>`, списък → низове/клетки, низ → низ.
Драйверът трябва да е в кернела (`kernel/defconfig`: PCF857X и HWMON/LM75 са включени;
`ti,tmp1075` се обслужва от драйвера **lm75**, не от tmp102). Устройство без драйвер стои в
`/sys/bus/i2c/devices/` без `driver` линк и без съобщение в dmesg.

## Pad база

`am335x-bbb-pins.json` се извлича от `../../docs/BBB_Pins.xlsx` с `extract-pins.py`: P8/P9
име, pad, offset, 8-те mux режима, GPIO банка/линия. Pad-ове извън хедърите, които Bitmain
конекторите ползват (uart0_ctsn/rtsn за UART4, gpmc_a4, mcasp0_aclkr/axr1, mii1_col/crs,
xdma_event_intr0), са в `EXTRA_PADS` в gen-dts.py.

Запазени за фиксираната част (`dts/am335x-antminer-base.dtsi`) и отказвани с причина:
NAND (gpmc_ad0..7, wait0, wpn, csn0, advn, oen, wen, be0n_cle), Ethernet MII + MDIO, UART0
конзола, I2C0 към PMIC, microSD (mmc0 + card detect на spi0_cs1), user LED-овете (gpmc_a5..a8).
На BBB P9.11 и P9.13 са UART4, тук са NAND wait0/wpn, затова UART4 е на uart0_ctsn/rtsn.

## Проверка на платката

```sh
gpioinfo                      # имената от профила
gpioset -t0 Q0=1 Q1=0 && gpioget -a Q0 Q1
gpioget I0 I1
cat /sys/kernel/debug/pinctrl/44e10800.pinmux-pinctrl-single/pins   # реалните pad регистри
```
