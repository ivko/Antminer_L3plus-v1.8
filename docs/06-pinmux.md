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
- `SBn` on a tile = the pin is SYSBOOT bit n (see [SYSBOOT pins](#sysboot-pins-boot-configuration)).
  Red `SBn` = with this function and this board's strap level, the external circuit can change
  the boot configuration; the pin dialog says what to check. The "SYSBOOT pins" card lists all 16
  bits with the board's latched value and what the profile puts on each one.
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

## SYSBOOT pins (boot configuration)

The 16 LCD data pads on P8 are also the SoC's boot configuration inputs SYSBOOT[15:0]
(lcd_dataN = SYSBOOT[N]). Resistors on the board pull each one high or low. The ROM latches them
**once, on the rising edge of PWRONRSTn**, i.e. when power is applied; a `reboot`, the watchdog or
SYS_RESETn do not read them again. The latched value stays in CONTROL_STATUS and is shown on the
start page of the web UI, on the console banner of the SD system and in the pin editor.

After the latch the pads are ordinary pins: the profile can make them GPIO, UART5 etc., and the
pinmux/pull set in the profile has no effect on the boot. What matters is **what is connected to
the pin while the board powers up**.

### The bits

TRM spruh73q, table 26-7. "Test board" = the latched value `0x4213` (CONTROL_STATUS `0x00420313`).

| bit | pin | pad | meaning | test board | effect of a wrong level |
|---|---|---|---|---|---|
| 0 | P8.45 | lcd_data0 | boot order [4:0] | 1 | different boot device list |
| 1 | P8.46 | lcd_data1 | boot order | 1 | " |
| 2 | P8.43 | lcd_data2 | boot order | 0 (1 when P8.43 is held at 3.3 V at power-on) | `10011` NAND first ↔ `10111` SD first |
| 3 | P8.44 | lcd_data3 | boot order | 0 | different boot device list |
| 4 | P8.41 | lcd_data4 | boot order | 1 | e.g. `00011` = UART0, SPI0, XIP, MMC0: no NAND |
| 5 | P8.42 | lcd_data5 | CLKOUT1 enable | 0 | 1 = the ROM outputs CLKOUT1 on xdma_event_intr0; boots |
| 6, 7 | P8.39, P8.40 | lcd_data6/7 | EMAC PHY mode (00 MII, 01 RMII, 11 RGMII) | 00 | only for EMAC boot: none |
| 8 | P8.37 | lcd_data8 | GPMC bus width (0 = 8 bit) | 0 | don't care for the ROM in our sequences |
| 9 | P8.38 | lcd_data9 | NAND ECC: 0 = by the ROM, 1 = by the NAND | 1 | NAND boot reads the SPL with the wrong ECC |
| 10, 11 | P8.36, P8.34 | lcd_data10/11 | GPMC addr/data mux, **00 for NAND** | 00 | NAND boot fails |
| 12, 13 | P8.35, P8.33 | lcd_data12/13 | reserved, **must be 00** | 00 | undefined |
| 14, 15 | P8.31, P8.32 | lcd_data14/15 | crystal: 00 19.2, **01 24**, 10 25, 11 26 MHz | 01 | the ROM sets up its clocks for the wrong crystal |

CONTROL_STATUS (`devmem 0x44E10040`) is not SYSBOOT itself: bits [7:0] = SYSBOOT[7:0],
[10:8] = device type (3 = GP), [16] = SYSBOOT8, [17] = SYSBOOT9, [19:18] = [11:10],
[21:20] = [13:12], [23:22] = [15:14]. `0x00420313` → SYSBOOT `0x4213`; `0x00420317` → `0x4217`.

The boot orders that matter here (the full 32-row table is in `firmware/web/antminer_web/board.py`):

| [4:0] | order | where |
|---|---|---|
| `10011` | NAND, NANDI2C, MMC0, UART0 | most boards |
| `10111` | MMC0, SPI0, UART0, USB0 | P8.43 held high at power-on: ROM boots from the SD card (03-install) |
| `10010` | NAND, NANDI2C, USB0, UART0 | |
| `11000` | SPI0, MMC0, USB0, UART0 | BeagleBone Black with the Boot button pressed |
| `11100` | MMC1, MMC0, UART0, USB0 | BeagleBone Black default (eMMC; this board has none) |

The ROM goes down the list until one device has a valid image; if all fail, it waits for the
watchdog. Each device it tries drives its own pins: with `10111` and no card, the ROM tries SPI0,
i.e. P9.17/18/21/22, which `default` uses as RST0, RST1 and UART2.

### The boot order can be changed

The order is set by resistors, but it is **not** fixed: anything that holds a SYSBOOT pin at the
other level during power-on overrides the strap. That is exactly how the Boot button of the
BeagleBone Black works (it pulls SYSBOOT2 low). Our boards strap SYSBOOT2 = P8.43 low (`10011`,
NAND first); holding P8.43 **at 3.3 V** while the power is applied latches `10111`: **SD first**,
the ROM loads MLO and U-Boot from the card. **Verified** on a board with a direct wire from
P8.43 to 3.3 V: that is the `Control_status {00420317}` in `logs/nand-write-1kom.txt`. (Earlier
versions of these docs took that reading for a second board variant with a different resistor;
there is no such variant.)

How:
- A direct connection to 3.3 V (P9.3/P9.4) works; a resistor of a few kΩ in series protects
  against a wrong pin. The strap resistor's value is still unknown: measure it (board unpowered,
  P8.43 to GND) if you want to size the override instead of shorting it.
- In a final design gate it with reset, as TI and BeagleBoard recommend: a buffer
  (e.g. 74LVC1G125) that drives the level only while SYS_RESETn (P9.10) is low and is high-Z
  afterwards, so the pin is free as Q0 after the boot.
- Only a power cycle applies the change. Check the result with `devmem 0x44E10040` or the first
  console line.

Nothing else about the boot changes: U-Boot from NAND already looks for `uEnv.txt` on the card
first (01-overview), so the override matters in two cases: a board whose NAND SPL/U-Boot is
broken (recovery), and trying a new SPL/U-Boot from the card without writing mtd0-4 (03-install).

### Rules for circuits on these pins

1. At power-on the pad is a high-impedance input (with the SoC's weak reset pull), so only
   **the load** is seen, whatever the profile says.
2. **Inputs** (I0.., UART RX): the source must not pull the pin to the other level while the board
   powers up. On a pin with strap 1, a contact/DIP switch/optocoupler to GND that is closed at
   power-on flips the bit. A UART RX on a strap-0 pin is wrong (TX idles high).
3. **Outputs** (Q0..): a pull resistor in the load (MOSFET gate pull-down, LED to GND, a driver
   input with bias) works against a strap of the other level. Keep it much weaker than the strap or
   buffer the pin.
4. Do not link two SYSBOOT pins with different strap levels (e.g. a loopback jumper TX↔RX).
5. Bits 5-8 do not affect our boot; prefer them (P8.37, P8.39, P8.40, P8.42) and the non-SYSBOOT
   pins P8.27-30 for inputs that may be active at power-on.

**Check with real hardware**: connect the cape, put every input in its worst state (switches
closed, sensors active), power-cycle, read `devmem 0x44E10040` and compare with the value without
the cape.

### What the current profiles and the breakout cape do

From `boards/*.yaml` and the `hardware/breakout` schematics, against the test board's straps:

| pin | bit / strap | profile | circuit on the cape | risk |
|---|---|---|---|---|
| P8.45, P8.46 | 0, 1 / 1 | Q2, Q3 | 100k gate pull-down | **fights the pull-up**: verify |
| P8.43 | 2 / 0 | Q0 | 100k gate pull-down | none (strap is 0 too); a wire to 3.3 V for the SD-boot override still wins over 100k |
| P8.44 | 3 / 0 | Q1 | 100k gate pull-down | none |
| P8.41 | 4 / 1 | I2 | DIP switch / PC817 to GND | **closed at power-on → `00011`, no NAND in the list** |
| P8.31 | 14 / 1 | I4 | DIP / PC817 / push button to GND | **active at power-on → crystal read as 19.2 MHz** |
| P8.32, P8.33, P8.34 | 15, 13, 11 / 0 | I5, I6, I7 | to GND | none (already 0) |
| P8.39, P8.40, P8.42 | 6, 7, 5 / 0 | I0, I1, I3 | to GND | none |
| P8.37 ↔ P8.38 | 8 / 0 ↔ 9 / 1 | UART5 | loopback jumper | **the jumper ties a 0 strap to a 1 strap (bit 9 = NAND ECC)**: remove it for power-on |
| P8.38 | 9 / 1 | UART5 RX (`default`) | hash board TX, idles high | none while the hash board is powered |

The `default` and `example-modbus-rtu` profiles use the same LCD pins for Q0-3/I0-3; the risk
depends on what is wired to them. A revision of the breakout should move I2 and I4 off
SYSBOOT4/14, and use weaker gate pull-downs (or the non-SYSBOOT P8.27-30) for Q2/Q3.

`gen-dts.py` prints a warning for every pin of a profile on a boot-relevant SYSBOOT bit
(0-4, 9-15); the editor additionally knows the board's strap levels and flags the risky ones.

## Pitfalls

- The `default` profile is also the built-in DTB of the image (`firmware/dts/am335x-antminer.dts`
  is generated from it). A change to `default.yaml` in the repo requires
  `bash build-dtb.sh boards/default.yaml` and a rebuild to get into the images.
- The ADC inputs are **1.8 V**. 3.3 V on an AIN pin damages it.
- The RST lines in `default` start at 0 (hash boards in reset); the LEDs are active low.
- An I2C device without a driver in the kernel gives no error: it simply does not appear. The
  templates in the editor are only for drivers the kernel has (PCF857x, the LM75/TMP1075 family).
