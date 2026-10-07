# 6. The pins: pinmux profiles

## The idea

Each pad of the AM3352 has up to 8 functions (GPIO, UART, I2C, SPI, PWM...). Which one is selected
is decided in the device tree (DTB), which U-Boot loads from NAND mtd6. The kernel and the
initramfs are the same for all boards; only the DTBs differ.

The DTB is generated from a **profile**: a YAML file that states which function each pin has.
There is no `config-pin` and nothing is switched at runtime: the pins are in the correct state
from the moment the kernel starts, and after every restart. Every pad that is not in the profile
is set as a GPIO input with pull-down (the safe state).

## Ready-made profiles

| profile | for | file |
|---|---|---|
| `default` | the original Bitmain board: 4 UARTs to the hash boards, RST0-3, PLUG0-3, LEDs, button, fans, I2C2; plus Q0-3 / I0-3 on the LCD pads. Built into the image | `firmware/pinmux/boards/default.yaml` |
| `breakout` | the test board from `hardware/breakout`: 8 outputs, 8 inputs, 2 x RS-485, ADC, I2C expander and temperature | `.../breakout.yaml` |
| `example-modbus-rtu` | Modbus RTU gateway with 4 RS-485 channels | `.../example-modbus-rtu.yaml` |

Local profiles made on a specific board are stored in `/config/pinmux/` on that board.

Which profile is active: `antminer-dtb current`, or "active on this board" in the editor.

## The visual editor

`http://<ip>/pinmux` → choose a profile → **board editor** (or create a new one by name).

- P9 on the left, P8 on the right, as on the board. The color shows the function; the hatched
  pins with a padlock are used by the system (NAND, Ethernet, console, SD) and cannot be used.
- Click on a pin: function (only those the pad supports), and for GPIO: direction, initial level,
  pull, **line name**, hog, note. The name matters: OpenPLC uses the lines `I0..`, `Q0..`
  (see 07-openplc), and your programs can look them up by name (`gpioset Q0=1`).
- The AIN tiles enable/disable the analog inputs (1.8 V maximum!).
- "Pads outside the headers" are the pads routed to the Bitmain connectors (UART4 etc.).
- "I2C devices": for each enabled I2C bus, the devices (GPIO expanders, temperature sensors)
  with address and line names.
- Yellow dot = changed, red = validation error, orange = incomplete peripheral
  (for example a UART with TX only).
- **Validate & build** generates and compiles the DTB on the board itself (~2 s) and shows the
  errors per pin. **Save** writes to `/config/pinmux/`. **Save + flash to mtd6** writes the DTB to
  NAND; it takes effect from the next restart. **Export YAML** downloads the profile.

"YAML (advanced)" opens the profile as text, for things the editor does not cover (SPI, CAN,
`unused: keep`).

## From the command line

On the board (package `antminer-pinmux`):
```sh
antminer-dtb list                                   # the profiles
antminer-dtb build breakout                         # -> /tmp/am335x-antminer-breakout.dtb (+ .dts, .json)
antminer-dtb build /config/pinmux/my.yaml
antminer-dtb flash /tmp/am335x-antminer-breakout.dtb    # mtd6, with verification
reboot
```

On the PC (WSL/Linux; the kernel tree is taken from the Yocto build or from `~/antminer/linux`, or `KSRC=`):
```sh
cd /mnt/e/Antminer/repo/firmware/pinmux
bash build-dtb.sh boards/breakout.yaml              # -> firmware/out/am335x-antminer-breakout.dtb
```
```sh
python firmware/tools/antminer.py deploy-dtb breakout --netboot-only   # test from RAM
python firmware/tools/antminer.py deploy-dtb breakout                  # write to mtd6 + reboot
```

All paths produce the same DTB (verified byte by byte).

## Profile format

```yaml
name: my-board
pins:
  P9.24: uart1_txd                                    # function only
  P9.26: {func: uart1_rxd, pull: up}
  uart0_ctsn: uart4_rxd                               # pad outside the headers, by name
  P8.43: {func: gpio, dir: out, init: 0, name: Q0}    # output, low at start
  P8.39: {func: gpio, dir: in, pull: up, name: I0, comment: "start button"}
  P9.17: {func: gpio, dir: out, init: 1, name: RS485_DE, hog: true}   # the kernel holds the line
adc: [0, 1, 2, 3]
i2c:
  i2c2:
    clock-frequency: 100000
    devices:
      - {compatible: "nxp,pcf8574", reg: 0x20, props: {gpio-controller: true, "#gpio-cells": 2,
         gpio-line-names: [EXP0, EXP1, EXP2, EXP3, EXP4, EXP5, EXP6, EXP7]}}
      - {compatible: "ti,tmp1075", reg: 0x48}
spi: {spi1: {spidev: [0], max-frequency: 16000000}}
unused: default            # remaining free pads -> GPIO input pull-down; keep = do not touch them
```

Full description of the options and the generator internals: `firmware/pinmux/README.md`.
P8/P9 table with the functions of each pad: web UI → Pinmux → "Header pin table", or
`docs/BBB_Pins.xlsx`.

## Checking on the board

```sh
antminer-dtb current
gpioinfo                                     # the lines with the names from the profile
gpioset -t0 Q0=1 && gpioget I0
cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw     # AIN0, 0..4095 = 0..1.8 V
ls /dev/ttyS* /dev/i2c-*
i2cdetect -y 2
cat /sys/kernel/debug/pinctrl/44e10800.pinmux-pinctrl-single/pins | grep 8a8   # the actual register
```

## Pitfalls

- The `default` profile is also the built-in DTB of the image (`firmware/dts/am335x-antminer.dts`
  is generated from it). A change to `default.yaml` in the repo requires
  `bash build-dtb.sh boards/default.yaml` and a rebuild to get into the images.
- The ADC inputs are **1.8 V**. 3.3 V on an AIN pin damages it.
- The RST lines in `default` start at 0 (hash boards in reset); the LEDs are active low.
- An I2C device without a driver in the kernel gives no error: it simply does not appear. The
  templates in the editor are only for drivers the kernel has (PCF857x, the LM75/TMP1075 family).
