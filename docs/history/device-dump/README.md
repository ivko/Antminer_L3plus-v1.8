# device-dump — снимка на живото устройство, 2026-10-05

Събрано през серийната конзола (COM3, 115200, login root). Платката е boot-нала от NAND,
без SD карта и без мрежов кабел.

## Какво е в NAND в момента

| mtd | дял        | offset    | размер   | съдържание                                   | md5 съвпада с                                  |
|-----|------------|-----------|----------|----------------------------------------------|------------------------------------------------|
| 0   | spl        | 0x000000  | 128 KiB  | MLO, U-Boot SPL 2013.04-dirty (Aug 04 2014)  | nand/recover-nand/MLO                          |
| 1-3 | spl_backup | 0x020000  | 3x128 KiB| копия на SPL                                 |                                                |
| 4   | u-boot     | 0x080000  | 1792 KiB | U-Boot 2013.04-dirty (Jan 04 2015)           | nand/recover-nand/u-boot.img                   |
| 5   | bootenv    | 0x240000  | 128 KiB  | празен (0xFF) -> default env от binary-то    |                                                |
| 6   | fdt        | 0x260000  | 128 KiB  | DTB 22256 байта, собствена версия            | никой локален файл -> nand-mtd6-fdt.dtb тук    |
| 7   | kernel     | 0x280000  | 5 MiB    | uImage Linux 3.8.13 #22 (Dec 2 2014)         | nand/recover-nand/uImage.bin                   |
| 8   | root       | 0x800000  | 20 MiB   | initramfs 14844103 байта                     | repo/images/initramfs.bin.SD-fixed             |
| 9   | config     | 0x1c00000 | 20 MiB   | jffs2, монтиран на /config                   | config/ (по-стара снимка) + /config/dts        |

Внимание: `nanddump` закръгля дължината нагоре до цяла страница (2048 байта). За md5 сравнение
трябва отрязване до точния размер (busybox `head` няма `-c`, ползвайте dd в две стъпки).

NAND чип: Micron MT29F2G08ABAEAWP, 256 MiB, page 2048, OOB 64, ECC BCH8 hardware + ELM.
При четене се виждат коригирани bit flip-ове (`omap_elm_correct_data`), данните са верни.

## Файлове

- `uboot-default-env.txt` — пълният default env на U-Boot, извлечен от mtd4. Това е реално действащата
  среда, защото bootenv е изтрит. Съдържа bootcmd, nandboot, адресите и mtdparts.
- `nand-mtd6-fdt.dtb` / `.dts` — DTB-то, което реално зарежда кернела, и декомпилацията му (dtc на платката).
- `dmesg.txt` — пълен kernel log от текущия boot.
- `pinctrl-pins.txt`, `pinmux-pins.txt` — реалното състояние на pinmux регистрите (debugfs).
- `opkg-list-installed.txt` — пакетите в initramfs.bin.SD-fixed (106 пакета, вкл. dtc, mc, nano, gdb, i2c-tools, perl, screen).
- `sysinfo.txt` — /proc/iomem, interrupts, gpio exports, tty устройства.
- `init-scripts.txt` — pgnand.sh, cgminer.sh, monitor-recobtn, interfaces, dropbear default.
- `config-dir.txt` — съдържание на /config/dts и /config/.old_config, get_system_info.cgi.

## Наблюдения от dmesg и DTS

- DTB в NAND е ваша модификация на bitmainer DTS: UART1 включен на P9.24/P9.26 (ttyO1 се появява),
  i2c0 изключен (TPS65217 не се probe-ва, затова `cpufreq_cpu0: failed to scale voltage`),
  pruss disabled, добавен възел `gpio-plc` за P8.43-P8.46 (Q0-Q3).
- **Бъг в gpio-plc**: драйверът `gpio-of-helper` в 3.8 кернела очаква свойство `gpio = <...>`, а във
  възела е `gpios = <...>`. Резултат в dmesg: `Failed to get gpio property of 'Q0'`, probe failed -2.
  Пиновете са правилни (gpio3 hwmod = Linux gpiochip64, offsets 8,9,6,7 = GPIO 72,73,70,71).
- `/init` е празен файл, затова `Failed to execute /init` и кернелът пада на `init=/sbin/init`. Безобидно.
- eth0 PHY е SMSC LAN8710/LAN8720 на mdio:00; slave 1 няма PHY. MAC от efuse c4:f3:12:73:1c:92.
- Налични устройства: /dev/ttyO0, /dev/ttyO1, /dev/i2c-0 (това е i2c2 на 0x4819c000, 100 kHz).
- Паметта е 256 MiB, кернелът вижда 255 MiB.

## Boot пътища според default env

- SD: U-Boot чете `uEnv.txt` от mmc0 дял 1 и изпълнява `uenvcmd`. Адресите и файловете са изцяло под
  контрол на uEnv.txt, тоест нов кернел и DTB се тестват от SD без да се пипа NAND.
- NAND: `nand read 0x80200000 0x280000 0x500000` -> кернелът в NAND е ограничен до 5 MiB.
- Няма следа от `bootz`; новият кернел трябва да е legacy uImage (`mkimage -T kernel`).
