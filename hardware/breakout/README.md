# breakout — test board (cape) for the Antminer BB-Black V1.8

KiCad 10 project, **generated** by `gen-sch.py`: the schematic is not drawn by hand but described
in Python by coordinates, with symbols and footprints from the standard KiCad libraries.
This way each of the 8 identical channels is one function, and a design change is a code change
and a regeneration.

The schematic follows `firmware/pinmux/boards/default.yaml` (Q0..3, I0..3, UART1/2/5, I2C2, ADC,
ehrpwm0B) and adds Q4..7 (P8.27-30), I4..7 (P8.31-34), RS485_DE0/1 (P9.17/18), BTN (P9.23),
FAN_TACH (P9.30), SPARE0..8. The profile for the board is `firmware/pinmux/boards/breakout.yaml`
(incl. PCF8574 at 0x20 and TMP1075 at 0x48 as I2C child nodes):
`powershell -File firmware\tools\deploy-dtb.ps1 -Profile breakout`.

## Files

| file | role |
|---|---|
| `gen-sch.py` | the generator: 6 sheets (root + outputs, inputs, analog, serial, i2c_pwm), `breakout.kicad_pro`, `expected-nets.json` |
| `kisym.py` | reader for `.kicad_sym` (S-expression), expands `extends`, gives the pin positions |
| `check.py` | compares the KiCad netlist with the planned connectivity (`expected-nets.json`) |
| `build.ps1` | `gen-sch.py` → ERC → netlist → `check.py` → PDF in `out/` |
| `breakout.kicad_sch` + `*.kicad_sch` | generated sheets (not edited by hand, except for finalization) |
| `breakout.kicad_pcb` | copy of the KiCad BeagleBone cape template: outline, P8/P9, 4 holes. No components or traces |

```powershell
powershell -File build.ps1          # ERC: 0 errors; netlist MATCH; out\breakout.pdf
```

## What is on the board (variant 1, 3.3 V, no isolation)

- **Outputs Q0..Q7**: AO3400A low-side MOSFET (gate pull-down 100k), SS14 flyback to +24V,
  1x10 terminal block (OUT0..7, +24V, GND). Status LED via 74AHCT541 (5 V).
- **Inputs I0..I7**: DIP switch to GND and in parallel a PC817 optocoupler for a 24 V signal
  (4.7k 1206 + 1N4148W antiparallel), 1x10 terminal block (IN0..7, IN_COM, +24V). Button on I4.
  The only pull-up is the processor's internal one (profile `pull: up`).
- **Analog AIN0..6**: 1k + BAT54S clamp to VDD_ADC/GNDA + 100n on each channel.
  AIN0/1 10k potentiometers, AIN2/3 0-10 V divider 47k/10k, AIN4/5 4-20 mA shunt 82R,
  AIN6 NTC 10k/10k. 1x06 terminal block.
- **Serial**: 2x THVD1500 RS-485 (UART1 + DE P9.17, UART2 + DE P9.18) with jumpers for the 120R
  terminator and 680R bias, TX/RX LEDs; UART5 TTL header with a loopback jumper.
- **I2C2**: 4.7k pull-ups on solder jumpers, Qwiic (JST SH) + 1x4 header, PCF8574T (0x20) with
  8 I/O on a header, TMP1075 (0x48).
- **PWM0B**: LED, RC test point (10k/100n), 4-pin fan header (5 V) with tach pull-up.
- **Root**: P8/P9 with the net names, 24 V IN terminal block + SMAJ24A + LED, PWR_FLAG + test
  points for +3V3/+5V/VDD_ADC/+24V/GND/GNDA, RESET button to SYS_RESETn (P9.10), SPARE header
  with 9 free pins, 4x M3.

The NAND pins (P8.3-10, P8.22-26, P9.11, P9.13) are marked NC and are not routed anywhere.

## How it is made and what the limitations are

- Pins are connected with real wires within a block and with global labels between blocks.
  A T-junction works only with a junction (KiCad rule); a pin placed on a wire gets connected.
  `check.py` keeps the generator honest: if a pin lands somewhere else, the netlist does not match.
- All coordinates are on the 1.27 mm grid (otherwise ERC reports `endpoint_off_grid`).
- ERC gives 8 `lib_symbol_mismatch` warnings for AO3400A: a derived symbol
  (`extends Q_NMOS_GSD`) that the generator expands slightly differently from KiCad. Harmless;
  "Update Symbols from Library" in eeschema removes it.
- PCB: open `breakout.kicad_pcb`, "Update PCB from Schematic" (F8) places the footprints;
  placement and routing are manual work (or FreeRouting).
- Viewing without the KiCad GUI: `kicad-cli sch export svg`, then headless Edge
  (`msedge --headless --screenshot`) gives a PNG; see `build.ps1` for the PDF.

## Next steps

- PCB placement and routing, BOM (`kicad-cli sch export bom`).
- Variant 2 with galvanic isolation (ISO1500, optocouplers everywhere, ULN2803) for a DIN-rail enclosure.
