# pinmux — per-board device tree from a YAML profile

> Reference for the format and the generator. Usage guide (editor, flashing, verification):
> [docs/06-pinmux.md](../../docs/06-pinmux.md).

The idea: the kernel is the same for all boards, and the pin configuration is a **device tree
per board**, which U-Boot loads from the NAND partition `fdt` (mtd6). The profile is a YAML file in `boards/`,
the generator produces a `.dts`, it is compiled with dtc and written to mtd6. There is no runtime pinmux, no
config-pin; the pins are in the correct state from the moment the kernel applies pinctrl.

## Workflow

```sh
# WSL
bash build-dtb.sh boards/default.yaml        # -> dts/am335x-antminer.dts (the image) + out/am335x-antminer-default.dtb
bash build-dtb.sh boards/<name>.yaml         # -> out/am335x-antminer-<name>.dts/.dtb
```
```powershell
# Windows, board on COM3
powershell -File ..\tools\deploy-dtb.ps1 -Profile <name> -NetbootOnly   # trial from RAM, NAND is not touched
powershell -File ..\tools\deploy-dtb.ps1 -Profile <name>                # write to mtd6 + reboot
```

`default.yaml` is special: it generates `dts/am335x-antminer.dts`, which build-kernel.sh and
the Yocto recipe build into the image. Everything else is per-board.

## Profile format

```yaml
name: modbus-rtu-4ch
pins:
  P9.24: uart1_txd                              # function only
  P9.26: {func: uart1_rxd, pull: up}
  uart0_ctsn: uart4_rxd                         # by pad name, for pads outside P8/P9
  P8.43: {func: gpio, dir: out, init: 0, name: Q0}   # pull follows init: 0 -> down, 1 -> up
  P8.39: {func: gpio, dir: in, pull: up, name: I0}
  P9.17: {func: gpio, dir: out, init: 1, name: RS485_DE, hog: true}  # hog = the kernel holds it
adc: [0, 1, 2, 3]                               # AIN0..3, 1.8 V
i2c: {i2c2: {clock-frequency: 400000}}
spi: {spi1: {spidev: [0, 1], max-frequency: 16000000}}
```

Every free pad that is not in the profile is explicitly set as a GPIO input with pulldown
(the reset state). Otherwise, on a warm restart the pad keeps whatever the previous
boot or U-Boot left it in. `unused: keep` disables this.

Pin options: `func`, `pull` (up|down|none), `rx` (true|false), `slew` (fast|slow),
`dir` (in|out, gpio only), `init` (0|1, gpio out), `name` (GPIO line name for libgpiod),
`hog` (true: the kernel claims the line at this level, userspace cannot use it).

Peripherals are enabled automatically from the functions: `uartN_*` → `&uartN`, `i2cN_*` → `&i2cN`,
`spiN_*` → `&spiN` + spidev, `ehrpwmNa/b`, `ecapN_in_pwmN_out` → PWM, `dcanN_rx/tx` → CAN,
`eqepN*` → encoder, `timerN` → mux only. ADC channels have no pinmux.

I2C devices on the bus are described as child nodes (`boards/breakout.yaml`):
```yaml
i2c:
  i2c2:
    clock-frequency: 100000
    devices:
      - {compatible: "nxp,pcf8574", reg: 0x20, label: exp_io,
         props: {gpio-controller: true, "#gpio-cells": 2, gpio-line-names: [EXP0, EXP1]}}
      - {compatible: "ti,tmp1075", reg: 0x48}
```
`props` values: `true` → empty property, number → `<n>`, list → strings/cells, string → string.
The driver must be in the kernel (`kernel/defconfig`: PCF857X and HWMON/LM75 are enabled;
`ti,tmp1075` is handled by the **lm75** driver, not by tmp102). A device without a driver sits in
`/sys/bus/i2c/devices/` without a `driver` link and without a message in dmesg.

## Pad database

`am335x-bbb-pins.json` is extracted from `../../docs/BBB_Pins.xlsx` with `extract-pins.py`: P8/P9
name, pad, offset, the 8 mux modes, GPIO bank/line. Pads outside the headers that the Bitmain
connectors use (uart0_ctsn/rtsn for UART4, gpmc_a4, mcasp0_aclkr/axr1, mii1_col/crs,
xdma_event_intr0) are in `EXTRA_PADS` in gen-dts.py.

Reserved for the fixed part (`dts/am335x-antminer-base.dtsi`) and rejected with a reason:
NAND (gpmc_ad0..7, wait0, wpn, csn0, advn, oen, wen, be0n_cle), Ethernet MII + MDIO, UART0
console, I2C0 to the PMIC, microSD (mmc0 + card detect on spi0_cs1), the user LEDs (gpmc_a5..a8).
On the BBB, P9.11 and P9.13 are UART4; here they are NAND wait0/wpn, which is why UART4 is on uart0_ctsn/rtsn.

## Verification on the board

```sh
gpioinfo                      # the names from the profile
gpioset -t0 Q0=1 Q1=0 && gpioget -a Q0 Q1
gpioget I0 I1
cat /sys/kernel/debug/pinctrl/44e10800.pinmux-pinctrl-single/pins   # the actual pad registers
```
