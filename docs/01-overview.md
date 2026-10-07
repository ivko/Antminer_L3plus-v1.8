# 1. Платката и системата накратко

## Хардуер

| | |
|---|---|
| SoC | TI AM3352 (Cortex-A8, 600 MHz, без PRU и без GPU) |
| RAM | 256 MB DDR3 |
| NAND | 256 MB Micron MT29F2G08 (BCH8 ECC) |
| Мрежа | 100 Mbit Ethernet (SMSC LAN8710) |
| Хедъри | P8 и P9 като на BeagleBone Black (2 x 46 пина) |
| Конзола | UART0, 115200 8N1, 3.3 V TTL (USB-serial адаптер) |
| microSD | има слот |
| Липсва | eMMC, HDMI, USB порт, EEPROM, Reset и Boot бутони |

Платката се монтира в оригинална Bitmain платка (хеш-контролер) с 4 конектора към хеш
платките, вентилатори, LED-ове и бутон. Тази разводка е описана в профила
`firmware/pinmux/boards/default.yaml`.

Без Reset бутон единственият начин за рестарт е изключване на захранването или софтуерен
reboot. Затова hardware watchdog-ът е винаги включен (виж 05-configure).

## Как тръгва платката

```
AM3352 ROM ─► SPL (MLO) ─► U-Boot 2013.04 (Bitmain) ─► кернел + DTB + initramfs ─► /init ─► busybox init
```

1. **ROM**. Редът на източниците е фиксиран с резистори (SYSBOOT). Повечето платки са
   `0x…13` = NAND, NANDI2C, MMC0, UART0. Срещат се и `0x…17` = MMC0, SPI0, UART0, USB0: те
   тръгват **само** от SD карта, NAND не е в списъка им. Стойността се вижда в първия ред на
   конзолата (`Control_status {00420313}`) и на началната страница на web UI-а.
2. **U-Boot** от NAND (или от картата при `0x17`) първо търси SD карта. Ако на дял 1 има
   `uEnv.txt`, изпълнява го. Иначе чете от NAND:

   | какво | откъде | адрес в RAM |
   |---|---|---|
   | кернел (uImage, ≤ 5 MB) | mtd7 | 0x80200000 |
   | initramfs (≤ 20 MB) | mtd8 | 0x81000000 |
   | DTB (≤ 128 KB) | mtd6 | 0x80F80000 |

   U-Boot няма `bootz`, затова кернелът е legacy uImage. Env дялът (mtd5) е празен и винаги
   важи вграденият env. Autoboot се прекъсва с ESC в рамките на 1 секунда.
3. **/init** в initramfs-а решава какъв да е root-ът:
   - има `antminer.root=sd` в командния ред (SD картата) → root е ext4 дял 2 на картата;
   - data дялът е форматиран и overlay-ът е включен → root е overlayfs (initramfs отдолу,
     UBIFS на mtd10 отгоре), всичко записано остава след рестарт;
   - иначе → root е самият initramfs в RAM; промените изчезват при рестарт.
4. **busybox init** пуска услугите от `/etc/rcS.d` и `/etc/rc5.d`.

## NAND дялове

| mtd | име | размер | съдържание | кой го пише |
|---|---|---|---|---|
| 0-3 | spl, spl_backup1-3 | 4 x 128 KB | Bitmain MLO | **никой** |
| 4 | u-boot | 1.75 MB | Bitmain U-Boot | **никой** |
| 5 | bootenv | 128 KB | празен (вграден env) | **никой** |
| 6 | fdt | 128 KB | DTB (pinmux профил) | flash-nand, antminer-dtb, web UI |
| 7 | kernel | 5 MB | uImage | flash-nand, web UI |
| 8 | root | 20 MB | initramfs | flash-nand, web UI |
| 9 | config | 20 MB | `/config` (jffs2): hostname, SSH ключове, мрежа, локални профили | услугите; `--wipe-config` го трие |
| 10 | data | 208 MB | UBIFS: persistent overlay (инсталирани пакети, OpenPLC програми) | `antminer-data` |

Дял 10 не съществува в оригиналната Bitmain таблица; описан е в нашия DTB и ползва
незаетата част от NAND след 0x3000000.

## Какво работи на платката

| услуга | порт | откъде идва |
|---|---|---|
| SSH (dropbear) | 22 | образа |
| web UI за провизиране и настройка | 80 | пакет `antminer-web` (вграден в SD системата, по желание на NAND) |
| OpenPLC (web) | 8080 | пакет `openplc-runtime` |
| Modbus TCP (OpenPLC) | 502 | пакет `openplc-runtime` |
| hardware watchdog (60 s) | | образа |
| ntpd + запис на часа в RTC | | образа (RTC няма батерия) |

Входовете/изходите се виждат от Linux като GPIO линии с имена (`gpioinfo`), ADC като IIO
(`/sys/bus/iio/devices/iio:device0`), UART-ите като `/dev/ttyS1..5`, I2C като `/dev/i2c-2`.

## Три образа от един билд

| образ | за какво | файл |
|---|---|---|
| `antminer-image` | системата в NAND: initramfs ~5.6 MB + кернел + DTB | `*.rootfs.cpio.gz.u-boot`, `uImage`, `am335x-antminer.dtb` |
| `antminer-provision-image` | провизираща SD карта: boot дял + Linux с web UI, който флашва NAND | `*.rootfs.wic` |
| feed (`tmp/deploy/ipk`) | ~2200 ipk пакета за `opkg install` (OpenPLC, компилатор, Python...) | |

Кернелът и initramfs-ът са едни и същи за NAND и за картата.
