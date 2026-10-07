# 8. Проблеми и решения

## Конзола и PC

**COM порт: „Access to the port is denied“.** Друга програма го държи (най-често PuTTY).
Затвори я. Ако няма такава и всеки опит виси, драйверът на USB-serial адаптера (Prolific) е
заклещен: извади адаптера от USB за няколко секунди. Симптом на същото: Task Manager не се
отваря. Причина: принудително спрян процес, който е чакал на порта; не спирай такива процеси,
остави ги да изтекат.

**Нищо на конзолата.** 115200 8N1, без flow control. TX/RX кръстосани, общ GND, 3.3 V
нива (не RS-232).

**netboot не тегли файлове.** Firewall за UDP 69; файловете трябва да са в `mainline/out/`
(`antminer.py stage`); `PC_IP` (`antminer.py config`) трябва да е IP-то на PC-то в мрежата на
платката, иначе го задай в `tools/site.local.conf`.

**antminer.py: „no answer on the serial console“.** Платката е изключена, портът е грешен
(`SERIAL_PORT`) или TX/RX са разменени. **„pyserial is missing“**: `pip install pyserial`.

## Boot

**Платката винаги тръгва от SD картата.** Така е замислено: U-Boot първо търси `uEnv.txt` на
картата. Изключи и извади картата за NAND boot.

**Извадих картата, докато работи, и нищо не става.** Root-ът е бил на картата. В отворен shell:
`echo b > /proc/sysrq-trigger`. Иначе изключи захранването.

**U-Boot: „micro SD card found“, после „Unrecognized filesystem type“ / „No partition table“.**
- Дял 1 трябва да е FAT32 (не exFAT) с MBR таблица. Записвай `.wic`, не копирай файлове.
- Някои карти не работят в 4-bit режим в някои слотове (U-Boot „чете“ нули без грешка).
  Пробвай друга карта. Диагностика от Linux: `dmesg | grep mmc` (`I/O error` = този проблем).

**Платката се рестартира сама след ~60 s.** Hardware watchdog-ът не е захранен: системата е
увиснала преди `antminer-early` (rcS S36) или нещо е спряло `watchdog` демона. Виж конзолата
докъде стига boot-ът.

**Overlay-ът изчезна, всичко инсталирано го няма.** `antminer-data status`. След 3 поредни
недовършени boot-а overlay-ът се изключва сам. Данните са на дяла: оправи причината,
`antminer-data enable`, `reboot`.

**Банерът на SD системата е с удвоени букви.** Стара версия на картата (поправено 2026-10-07);
запиши нов `.wic`.

## Мрежа и пакети

**`opkg update` не може да свали.** Feed сървърът пуснат ли е (`antminer.py feed status`), firewall
за TCP 8000, правилен ли е IP-то в `/etc/opkg/base-feeds.conf` (04-packages).

**opkg: няма място.** `df -h /data`. Изчисти списъците (`rm -rf /var/lib/opkg/lists/*`) и
ненужни пакети; крайната мярка е `antminer-data wipe`.

**Feed файл дава 404, а го има.** Symlink-овете в deploy директорията не се сервират през
`\\wsl$`. Ползвай името с датата.

**Не знам IP-то на платката.** Конзола (`ip addr`), DHCP таблицата на рутера (hostname
`antminer-xxxxxx`), или задай статичен IP в `/config/network`.

## Web UI и OpenPLC

**Login в OpenPLC не прави нищо.** Часовникът на платката е грешен (няма батерия за RTC).
`date`; задай NTP сървър в `/config/ntp-server` или временно `date -s "2026-10-07 12:00"`.

**Web UI-ът иска парола, която не помня.** Изтрий `/config/web-password` по SSH или конзолата.

**OpenPLC не вижда входовете/изходите.** Линиите трябва да се казват точно `I<n>` / `Q<n>`
(`gpioinfo`). Свободни ли са (`gpioinfo` показва consumer)? След смяна на профила е нужен рестарт.

**По Modbus се виждат регистри, които програмата не ползва.** Нормално за OpenPLC (07-openplc).

**ADC показва случайни стойности.** Входът е във въздуха. Свържи го (0..1.8 V!).

## Pinmux и I2C

**Профилът не се компилира.** Грешките са по пин: „reserved for NAND“ = пинът е зает от
системата; „not available“ = pad-ът няма тази функция; „already used“ = два пина с един pad.

**I2C устройството липсва.** Драйверът трябва да е в кернела; иначе устройството стои в
`/sys/bus/i2c/devices/` без `driver`. `i2cdetect -y 2` показва дали чипът отговаря.
`probe ... failed with error -121` = няма чип на този адрес.

## Билд

**Bitbake: липсващи рецепти (python3-flask и др.).** `meta-python` липсва в
`build/conf/bblayers.conf` (стари setup-и). Добави
`~/antminer/yocto/meta-openembedded/meta-python`.

**Билдът спира с „no space“.** Нужни са ~60 GB във WSL. `BB_DISKMON_DIRS` спира билда под 1 GB.

**ParseError: unparsed line.** Bitbake не допуска коментар на реда на присвояване
(`X = "y"  # коментар`); коментарът трябва да е на отделен ред.

**Промяна в кернел конфига не влиза.** Единственият кернел конфиг е `mainline/kernel/defconfig`;
промени го с `bash mainline/build-kernel.sh menuconfig` или `build.sh linux-antminer -c menuconfig`.
Опции като модули (`=m`) не влизат в образа: всичко трябва да е `=y`.
