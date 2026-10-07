# mainline — нов кернел за Antminer BB-Black V1.8 върху стария Bitmain U-Boot

> **Дневник на разработката**, не ръководство: какво е пробвано, в какъв ред и защо, с
> резултатите от тестовете. Част от описаното е заменено по-късно. За билд, инсталиране и
> употреба виж [docs/](../docs/) и [README](../README.md) в корена.

Цел на фаза 1: mainline Linux 6.12 LTS да boot-не с оригиналния SPL/U-Boot 2013.04 и
съществуващия Ångström initramfs, без да се пипа NAND.

## Статус: фаза 1 постигната на 2026-10-05

Linux 6.12.112 е зареден по мрежата (U-Boot tftp + bootm, без SD карта) и проверен:

| проверка | резултат |
|---|---|
| NAND mtd0 spl, mtd4 u-boot, mtd6 fdt, mtd7 kernel, mtd8 root | md5 идентично с локалните файлове, 0 ECC failures, 14 коригирани бита на mtd8 |
| Ethernet | SMSC LAN8710 намерен, udhcpc взима адрес, tftp от PC работи |
| UART | ttyS0 конзола, ttyS1/2/4/5 hash board |
| PMIC | TPS65217 ID 0xe на i2c0, cpufreq на 600 MHz |
| LED, GPIO | antminer:red/green:status, gpio-line-names видими в /sys/kernel/debug/gpio |
| PWM | pwmchip с 2 канала (ehrpwm0) |

Логове: `device-dump/netboot-01.log` (първи опит, грешни NAND тайминги), `device-dump/netboot-02.log` (работещ).

## Стъпка 1 (кернел под 5 MB) и стъпка 2 (NAND запис) — готови, 2026-10-05

| | omap2plus + fragment | + antminer-slim.config |
|---|---|---|
| uImage.bin | 5.37 MB, не влиза в NAND | **2.46 MB**, остават 2.66 MB до лимита |
| kernel code в RAM | 11 MB | 4 MB (Thumb-2, -Os, XZ) |
| boot до шел | 5.9 s | 3.5 s |
| махнато | | OMAP2/3/4/5, AM43xx, DRA7, SMP, USB, DRM/FB/VT, звук, IPv6, netfilter, NFS, ext4/vfat, MMC, kprobes/ftrace |
| добавено | | overlayfs, UBIFS, `data` дял 0x3000000..0x10000000 (208 MB, mtd10) |

Проверено на платката: NAND md5 на всички дялове OK, Ethernet, ADC 8 канала, PWM, watchdog,
LED, cpufreq 1 GHz. Лог: `device-dump/netboot-05-slim-thumb2.log`.

NAND запис round-trip върху `data` дяла (нищо от boot дяловете не е пипано):
- Linux 6.12 `nandwrite` блок 0 -> U-Boot `nand read` + `crc32` = 8c47c3b4, без ECC грешки.
- U-Boot `nand write` блок 1 -> Linux `nanddump` md5 съвпада, 0 ECC съобщения.
- OOB байтовете от двата записа са идентични: mainline BCH8+ELM и U-Boot 2013.04 са една и съща
  ECC схема. Провизиране може да става и от U-Boot (tftp + nand write), и от Linux (nandwrite).
- `nand bad` в U-Boot: няма лоши блокове. Лог: `device-dump/uboot-nandtest.log`.

`tools/uboot-cmd.ps1 -Commands @(...) -Then boot|stay` изпълнява произволни U-Boot команди през COM3.

Netboot без SD карта: `powershell -File tools/netboot.ps1 -ServerIp <IP на PC>` стартира
`tools/tftp-server.py`, рестартира платката през COM3, прекъсва U-Boot, тегли `out/` в RAM и
прави bootm. Нищо не се записва в NAND. Ръчните команди са в `sdcard/netboot-commands.txt`.

### Урок за NAND таймингите

Първият DTS носеше таймингите от Bitmain 3.8 DTS (cycle 300 ns, oe-off 150, access 200).
Под 6.12 OOB се четеше вярно, но данните бяха стабилно грешни, изоставащи с 29 до 45 байта
на страница, тоест пропуснати RE импулси. Причина: `gpmc,access-ns` 200 е след `gpmc,oe-off-ns`
150, данните се семплират след като NAND е пуснал шината. Старият кернел най-вероятно изобщо не
е прилагал тези DT стойности, а е работил с регистрите от U-Boot:

```
GPMC CS0 CONFIG1..6 от U-Boot 2013.04 (md.l 0x50000060 6):
00000800 001e1e00 001e1e00 16051807 00151e1e 16000f80
-> 8-bit NAND, cycle 300 ns, OE on 70 / off 240 ns, access 210 ns (преди OE off)
```

Работещото решение е node-ът от mainline `am335x-evm.dts` едно към едно (същият Micron чип):
cycle 82 ns, oe-off 54, access 64, `ti,nand-xfer-type = "prefetch-dma"`.

## Файлове

| път | за какво |
|---|---|
| `dts/am335x-antminer.dts` | mainline DTS за платката, строен върху `am335x-bone-common.dtsi` |
| `kernel/antminer.config` | Kconfig fragment върху `omap2plus_defconfig`, всичко нужно вградено |
| `kernel/antminer-slim.config` | втори fragment: само AM33xx, без USB/видео/звук/IPv6, XZ, Thumb-2, -Os (`SLIM=0` го пропуска) |
| `kernel/antminer_defconfig.generated` | `make savedefconfig` резултат от последния билд, за справка |
| `tools/netboot.ps1`, `tools/tftp-server.py`, `tools/uboot-cmd.ps1` | netboot без SD карта и U-Boot команди през COM3 |
| `sdcard/uEnv.txt` | U-Boot env за SD boot с новите адреси и `console=ttyS0` |
| `build-kernel.sh` | WSL2 скрипт: toolchain, clone linux-6.12.y, config, build, mkimage, копира в `out/` |

## Build (WSL2 Ubuntu)

```sh
bash /mnt/e/Antminer/repo/mainline/build-kernel.sh
```

Сорсовете отиват в `~/antminer/linux` вътре в WSL (ext4). Резултатът е в `repo/mainline/out/`:
`uImage.bin`, `am335x-antminer.dtb`, `uEnv.txt`, `initramfs.bin.SD` (копие на legacy/images/initramfs.bin.SD-fixed).
Всичко от `out/` се копира на FAT дяла на SD картата.

Скриптът печата кои символи от fragment-а не са влезли в .config. Преименувани опции
се оправят в `antminer.config`.

## Първи boot

1. SD в платката, серийна конзола на 115200.
2. U-Boot: `micro SD card found` -> `Loaded environment from uEnv.txt` -> `Running uenvcmd`.
3. Кернелът стартира с `init=/bin/sh`. В шела:

```sh
mount -t proc proc /proc; mount -t sysfs sys /sys
cat /proc/mtd                      # очакваме 10 дяла с размерите от device-dump/README.md
# md5 на kernel дяла до точния размер на uImage.bin (busybox head няма -c):
{ dd bs=2048 count=2150; dd bs=368 count=1; } < /dev/mtd7 2>/dev/null | md5sum
#   очаквано: c68a7b971f6c919dbf34813518bbd6b7  (= nand/recover-nand/uImage.bin)
dmesg | grep -i -E "nand|ecc|elm|mtd|cpsw|phy|mmc"
ls /dev/ttyS*                      # ttyS0 конзола, ttyS1/2/4/5 hash board UART-и
```

Ако md5 на kernel дяла съвпада с `nand/recover-nand/uImage.bin`, GPMC таймингите и
BCH8/ELM в DTS са верни и NAND е безопасен за писане от новия кернел.

## Какво е различно спрямо стария DTB (device-dump/nand-mtd6-fdt.dts)

- UART номерацията е mainline: hwmod uartN на 3.8 е `&uart(N-1)`. Конзолата е ttyS0.
- i2c0 с TPS65217 е включен (bone-common). Старият DTB го изключваше, но U-Boot говори с
  PMIC-а на 0x24, така че той съществува. Без него няма poweroff и cpufreq.
- `baseboard_eeprom` (i2c0 0x50) и `cape_eeprom0..3` (i2c2 0x54..0x57) от bone-common са
  изтрити с `/delete-node/`: няма EEPROM-и на платката, i2c2 показва само това, което профилът добавя.
- `pruss_tm` е disabled, AM3352 няма PRU-ICSS. bone-common го включва за AM3358.
- LED-овете на платката са четирите BeagleBone user LED-а (gpio1 21..24, heartbeat на usr0),
  проверено с мигане. RED=gpio45 и GREEN=gpio23 от Bitmain скриптовете са за LED панел с IP
  Report бутон, какъвто този контролер няма. Зумер също няма.
- `clkout2_pin` от bone-common НЕ се прилага: на тази платка pad xdma_event_intr1 (gpio0_20)
  е зумерът.
- Четирите hash board UART-а (uart1, uart2, uart4, uart5) са включени с pinmux-а от оригиналния
  Bitmain DTS. ehrpwm0B на P9.29 е вентилаторният PWM.
- Възелът gpio-plc (счупен в стария DTB заради `gpios` вместо `gpio`) е заменен с pinmux hog
  на P8.43..46 плюс `gpio-line-names`, за да се ползва с libgpiod: `gpioset -c gpiochip2 8=1`.
- NAND таймингите са тези от mainline am335x-evm (виж урока по-горе). ready/busy е през
  `rb-gpios` на gpmc_wait0, а не през `gpmc,wait-on-read`.
- `davinci_mdio_default` е предефиниран само с MDIO/MDC. bone-common добавя там uart0_ctsn
  като GPIO за PHY reset на BBB rev C, а на тази платка това е uart4_rxd.
- SGX модулът (`/ocp/target-module@56000000`) е disabled, AM3352 няма SGX.

## GPIO карта (от Bitmain init скриптовете)

| функция | GPIO | sysfs # | pad | DTS име |
|---|---|---|---|---|
| RST0..RST3 (hash board reset) | gpio0_5, 0_4, 0_27, 0_22 | 5, 4, 27, 22 | spi0_cs0, spi0_d1, gpmc_ad11, gpmc_ad8 | rst0..rst3 |
| PLUG0..PLUG3 (board present) | gpio1_19, 1_16, 1_15, 1_12 | 51, 48, 47, 44 | gpmc_a3, gpmc_a0, gpmc_ad15, gpmc_ad12 | plug0..plug3 |
| USR0..USR3 LED на платката | gpio1_21..24 | 53..56 | gpmc_a5..a8 | usr0..usr3 (bone-common leds) |
| RED / GREEN LED (панел, липсва) | gpio1_13 / gpio0_23 | 45 / 23 | gpmc_ad13 / gpmc_ad9 | led_red / led_green |
| BEEP (липсва на платката) | gpio0_20 | 20 | xdma_event_intr1 | beep |
| RECOVERY key | gpio1_14 | 46 | gpmc_ad14 | recovery_key |
| FAN_SPEED0 / 1 (tach) | gpio3_16 / gpio3_14 | 112 / 110 | mcasp0_axr0 / mcasp0_aclkx | fan_speed0 / 1 |
| FAN_PWM | ehrpwm0B | pwm1 | mcasp0_fsx P9.29 | &ehrpwm0 |
| PLC Q0..Q3 (ваши) | gpio2_8, 2_9, 2_6, 2_7 | 72, 73, 70, 71 | lcd_data2,3,0,1 P8.43..46 | plc_q0..q3 |

## Известни неясноти, за проверка на хардуера

- gpio0_26 (gpmc_ad10) и gpio1_20 (gpmc_a4) са в Bitmain pinmux-а, но функцията им не е ясна.
- Етикетите `&pruss_tm`, `&baseboard_eeprom`, `&epwmss0`, `&ehrpwm0`, `&tscadc` трябва да
  съществуват в избраната версия на кернела. При грешка от dtc за непознат label, проверете
  `arch/arm/boot/dts/ti/omap/am33xx*.dtsi` и `am335x-bone-common.dtsi`.

## Стъпка 3 (Yocto initramfs + ipk feed) — готова, 2026-10-06

Виж `yocto/README.md`. Резултат: `uImage` 2.58 MB, `antminer-image...cpio.gz.u-boot` 5.6 MB,
DTB, ipk feed с 1659 пакета. Тествано по netboot: watchdog, DHCP, SSH, syslog, /config, opkg.
Старият Ångström initramfs вече не е нужен за нищо.

Провизиране в NAND — направено на тестовата платка на 2026-10-06: `tools/flash-nand.sh` на
netboot-натата платка записа mtd8, mtd7, mtd6 в този ред с md5 проверка, после `reboot` зареди
новата система от NAND за ~12 s (лог `device-dump/nandboot-01-yocto.log`). Bitmain кернелът и
rootfs вече не са на тази платка. Второ флашване с `--wipe-config` изтри и Bitmain файловете от
/config; сега там има само `ssh/dropbear_rsa_host_key`, който оцелява рестарт (nandboot-02/03).
Hostname е `antminer-<последните 3 байта от MAC>`, override през `/config/hostname`. Default env на U-Boot boot-ва новия кернел без промени:
`console=ttyO0` се пренасочва към ttyS0 от CONFIG_SERIAL_8250_OMAP_TTYO_FIXUP, `init=/sbin/init`
е busybox init. mtd0..mtd4 (SPL/U-Boot) не се пипат никога, няма boot бутон за възстановяване.
Връщане назад: същият скрипт с `nand/recover-nand/{uImage.bin,am335x-boneblack-bitmainer.dtb}`
и `repo/images/initramfs.bin.SD-fixed`.

## Стъпка 4 (per-board device tree от YAML) — готова, 2026-10-06

Виж `pinmux/README.md`. `dts/am335x-antminer-base.dtsi` е фиксираната част, `dts/am335x-antminer.dts`
се ГЕНЕРИРА от `pinmux/boards/default.yaml` с `pinmux/gen-dts.py` (не се редактира на ръка).
Per-board профилите дават `out/am335x-antminer-<name>.dtb`, който `tools/deploy-dtb.ps1` записва
в mtd6 (или пробва от RAM с `-NetbootOnly`). Проверено на платката с `default`,
`example-modbus-rtu` (RS485_DE0..3, DI0/1, hog ALIVE, 4 UART, ADC) и `breakout` (профилът на
тестовата платка `hardware/breakout`, с I2C child възли; флашнат в mtd6 на тестовата платка на
2026-10-06, OpenPLC заема Q0..Q7/I0..I7 след boot): имена в gpioinfo, pad
регистри точно по генератора, gpioset/gpioget работят. Всички свободни pad-ове извън профила се
задават изрично в reset състояние (GPIO вход pulldown), иначе топъл рестарт пази стари стойности.
Per-board hostname е от MAC, override в /config/hostname; SSH ключ в /config/ssh.

## Boot ред на ROM-а и microSD слотът, 2026-10-06

SYSBOOT пиновете се четат от CONTROL_STATUS (`devmem 0x44E10040`). Тестовата платка дава
`0x00420313` → SYSBOOT[4:0] = 10011 = **NAND, NANDI2C, MMC0, UART0**: докато SPL-ът в NAND е
валиден, ROM-ът никога не стига до SD карта; U-Boot от NAND обаче пробва SD първи (`bootcmd`).
Платката от `logs/nand-write-1kom.txt` е `0x00420317` → 10111 = **MMC0, SPI0, UART0, USB0**
(само SD, NAND го няма в списъка) – хардуерна разлика в резистора на SYSBOOT2 (= lcd_data2 =
P8.43). Т.е. "вкарвам SD и boot-ва от нея" важи за платките с 0x17, не за тази.

microSD слотът: с една конкретна карта (DDINC 16 GB, старата Bitmain карта) тестовата платка
чете само в 1-bit режим, а в 4-bit (дори на 400 kHz) всяко четене дава `I/O error`; същата
карта работи в 4-bit на другата платка със стария кернел. С друга карта (USD00 16 GB) 4-bit на
50 MHz е без нито една грешка на тестовата платка. Т.е. слотът е здрав, проблемът е маргинален
контакт карта/слот. Bitmain U-Boot ползва 4-bit, затова с лоша комбинация "чете" боклук
(`mmc read` връща OK, без да пипне буфера). Логове: `device-dump/netboot-22..26-*.log`,
`uboot-sdcard-0*.log`. Кернелът има MMC/SDHCI_OMAP/VFAT вградени (+93 KB) – основа за
провизиращата SD карта; `sdcard/uEnv.txt` е готов (FAT32, дял 1). При проблем с карта:
`netboot.ps1 -Dtb am335x-antminer-mmc1bit-fast.dtb` срещу стандартното DTB показва дали е
4-bit проблем.

## Провизираща microSD карта (стъпка 6), 2026-10-06

Една карта за двата типа платки: FAT дял 1 носи Bitmain MLO + u-boot.img (за платките със
SYSBOOT 10111 ROM-ът тръгва от тях), `uEnv.txt`, нашия uImage, DTB и initramfs; ext4 дял 2 е
`antminer-provision-image` (web UI, dtc, генераторът на DTS). `uEnv.txt` подава
`antminer.root=sd` и `/init` прави `switch_root` в дял 2 вместо overlay върху NAND. Самите
файлове от дял 1 са и payload-ът за NAND. Образът на цялата карта е `.wic`
(`yocto/meta-antminer/wic/antminer-sd.wks`), пише се с Rufus/dd или от самата платка.

На платката: `antminer-dtb build <profile>` компилира YAML профил с dtc върху предварително
препроцесирана база (`pinmux/make-base-pp.sh`, `gen-dts.py --flat`; резултатът е байт-идентичен
с cpp build-а), `antminer-dtb flash x.dtb` го записва в mtd6 с проверка;
`antminer-flash-nand /boot uImage x.dtb initramfs.cpio.gz.u-boot` флашва mtd6/7/8 от картата.
Web UI (Flask, порт 80, `mainline/web/`): платка/SYSBOOT, NAND (съдържание срещу payload, флаш,
data дял), pinmux (редактор на YAML, build, запис в mtd6, таблица на пиновете), услуги
(hostname, NTP, статичен IP, SSH ключове в /config), лог. `antminer-config` вече чете
`/config/network` (MODE=static ADDRESS NETMASK GATEWAY DNS) и линква `/config/ssh/authorized_keys`.
Профилът `default` (от него се генерира `dts/am335x-antminer.dts`, вграденото DTB на образа)
отразява разводката на оригиналната Bitmain платка, в която се монтира контролерът:
4 UART-а към хеш платките, RST0..3 (изходи, 0 = в reset), PLUG0..3, LED_RED/LED_GREEN,
RECOVERY, IP_SIG, fan PWM + FAN_SPEED0/1, I2C2, плюс Q0..3/I0..3 на LCD pad-овете. Източник:
`dts/bitmain/am335x-boneblack-bitmainer.dts` (dtc на `nand/recover-nand/*.dtb`); всичките 25
Bitmain pad-а са със същите регистрови стойности. Gpio-leds възелът на Bitmain има грешни номера
на линиите (plug0, fan_speed0); авторитетни са pinmux групата и init скриптовете.

Визуален редактор на пиновете (`/pinmux/<профил>/board`, Lit компонент
`web/antminer_web/static/board-editor.js` с vendor-нат `lit-all.min.js`, без build стъпка): P9 и P8
като физическите хедъри, плочки с цвят по категория (захранване, запазени, GPIO in/out, UART, I2C,
SPI, PWM, CAN, timer, ADC), клик → диалог (функция, посока, init, pull, име на линията, hog,
коментар), AIN плочките превключват ADC каналите, маркери за променени/грешни/непълни периферии.
JSON API: `/api/pads`, `/api/profiles[/<name>[/build|/flash|/yaml]]`; `gen-dts.py --json` дава
грешките по пин. Профилът се пази като YAML (`web/antminer_web/profile.py`, коментарите на пин са
в поле `comment:`). Разработка на PC: `ANTMINER_PINMUX=.../pinmux ANTMINER_CONFIG=/tmp/cfg
ANTMINER_PAYLOAD=.../out/sdcard python3 run.py --port 8088`, `?open=P8.43` отваря диалога.
Тест на хоста: `python3 web/test_smoke.py`. UI-ят е отворен, докато няма парола; парола
(HTTP basic, потребител `admin`) се слага от страница Services и живее в `/config/web-password`.

Внимание: картата се вади **след** reboot/изключване, не докато системата работи от нея
(root-ът изчезва, нищо не може да се изпълни). Ако се случи: `echo b > /proc/sysrq-trigger`
от shell-а (builtin echo) рестартира; проверено 2026-10-06.

## Следващи стъпки

- Старите sysfs GPIO номера не важат в 6.12, всичко е през libgpiod по `gpio-line-names`.
- Стъпка 5 (готова, виж `yocto/README.md`): UBIFS на `data` + overlayfs (`antminer-data`),
  OpenPLC като ipk с hardware layer за I*/Q*/ADC линиите. Пример: `openplc/examples/gpio-echo.st`.
- Непроверено: fallback-ът на boot брояча (3 неуспешни boot-а → overlay off); `debug-tweaks`
  (root без парола) е още в образа.
- Modbus TCP slave daemon върху libgpiod/libmodbus като по-лек заместител на OpenPLC в initramfs-а.
- OpenPLC web UI показва слоя като "Blank Linux"; собствен запис в списъка на hardware слоевете.
