# breakout — тестова платка (cape) за Antminer BB-Black V1.8

KiCad 10 проект, **генериран** от `gen-sch.py`: схемата не се чертае на ръка, а се описва
в Python по координати, със символи и footprint-и от стандартните библиотеки на KiCad.
Така всеки от 8-те еднакви канала е една функция, а промяна в дизайна е промяна в кода
и регенериране.

Схемата следва `firmware/pinmux/boards/default.yaml` (Q0..3, I0..3, UART1/2/5, I2C2, ADC,
ehrpwm0B) и добавя Q4..7 (P8.27-30), I4..7 (P8.31-34), RS485_DE0/1 (P9.17/18), BTN (P9.23),
FAN_TACH (P9.30), SPARE0..8. Профилът за платката е `firmware/pinmux/boards/breakout.yaml`
(вкл. PCF8574 на 0x20 и TMP1075 на 0x48 като I2C child възли):
`powershell -File firmware\tools\deploy-dtb.ps1 -Profile breakout`.

## Файлове

| файл | роля |
|---|---|
| `gen-sch.py` | генераторът: 6 листа (root + outputs, inputs, analog, serial, i2c_pwm), `breakout.kicad_pro`, `expected-nets.json` |
| `kisym.py` | четец на `.kicad_sym` (S-expression), разгъва `extends`, дава позициите на пиновете |
| `check.py` | сравнява netlist-а на KiCad с планираната свързаност (`expected-nets.json`) |
| `build.ps1` | `gen-sch.py` → ERC → netlist → `check.py` → PDF в `out/` |
| `breakout.kicad_sch` + `*.kicad_sch` | генерирани листове (не се редактират на ръка, освен за финал) |
| `breakout.kicad_pcb` | копие на BeagleBone cape шаблона на KiCad: outline, P8/P9, 4 отвора. Без компоненти и трасета |

```powershell
powershell -File build.ps1          # ERC: 0 errors; netlist MATCH; out\breakout.pdf
```

## Какво има на платката (вариант 1, 3.3 V, без изолация)

- **Изходи Q0..Q7**: AO3400A low-side MOSFET (gate pull-down 100k), SS14 flyback към +24V,
  клема 1x10 (OUT0..7, +24V, GND). Статус LED през 74AHCT541 (5 V).
- **Входове I0..I7**: DIP ключ към GND и паралелно PC817 оптрон за 24 V сигнал
  (4.7k 1206 + 1N4148W антипаралелно), клема 1x10 (IN0..7, IN_COM, +24V). Бутон на I4.
  Pull-up е само вътрешният на процесора (профил `pull: up`).
- **Аналог AIN0..6**: 1k + BAT54S клампа към VDD_ADC/GNDA + 100n на всеки канал.
  AIN0/1 потенциометри 10k, AIN2/3 0-10 V делител 47k/10k, AIN4/5 4-20 mA шунт 82R,
  AIN6 NTC 10k/10k. Клема 1x06.
- **Сериен**: 2x THVD1500 RS-485 (UART1 + DE P9.17, UART2 + DE P9.18) с джъмпери за 120R
  терминатор и bias 680R, TX/RX LED; UART5 TTL хедър с loopback джъмпер.
- **I2C2**: pull-up 4.7k на solder jumpers, Qwiic (JST SH) + 1x4 хедър, PCF8574T (0x20) с
  8 I/O на хедър, TMP1075 (0x48).
- **PWM0B**: LED, RC тест точка (10k/100n), 4-пинов фен хедър (5 V) с tach pull-up.
- **Root**: P8/P9 с имената на мрежите, клема 24 V IN + SMAJ24A + LED, PWR_FLAG + тест
  точки за +3V3/+5V/VDD_ADC/+24V/GND/GNDA, бутон RESET към SYS_RESETn (P9.10), хедър SPARE
  с 9 свободни пина, 4x M3.

NAND пиновете (P8.3-10, P8.22-26, P9.11, P9.13) са маркирани NC и не се изкарват никъде.

## Как е направено и какви са ограниченията

- Пиновете се свързват с реални проводници в блока и с глобални етикети между блоковете.
  T-връзка работи само с junction (правило на KiCad), пин върху проводник се свързва.
  `check.py` държи генератора честен: ако пин попадне другаде, netlist-ът не съвпада.
- Всички координати са на 1.27 mm мрежата (иначе ERC дава `endpoint_off_grid`).
- ERC дава 8 предупреждения `lib_symbol_mismatch` за AO3400A: производен символ
  (`extends Q_NMOS_GSD`), който генераторът разгъва малко по-различно от KiCad. Безобидно,
  "Update Symbols from Library" в eeschema го маха.
- PCB: отворете `breakout.kicad_pcb`, "Update PCB from Schematic" (F8) слага footprint-ите;
  разполагане и трасиране са ръчна работа (или FreeRouting).
- Преглед без KiCad GUI: `kicad-cli sch export svg`, после headless Edge
  (`msedge --headless --screenshot`) дава PNG, виж `build.ps1` за PDF.

## Следващи стъпки

- Разполагане и трасиране на PCB, BOM (`kicad-cli sch export bom`).
- Вариант 2 с галванична изолация (ISO1500, оптрони навсякъде, ULN2803) за DIN-rail кутия.
