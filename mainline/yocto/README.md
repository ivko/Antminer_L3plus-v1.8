# yocto — Yocto scarthgap образ и ipk feed за Antminer BB-Black V1.8

Слоят `meta-antminer` описва платката като Yocto машина и строи:

- `uImage` на linux-stable 6.12 от `../kernel/defconfig` и `../dts/am335x-antminer.dts` (едни и
  същи файлове с build-kernel.sh, няма втори екземпляр);
- `antminer-image`: initramfs за NAND root дяла (20 MB), busybox init + mdev, glibc, dropbear,
  libgpiod, libmodbus, mtd-utils, i2c-tools, opkg;
- ipk feed в `tmp/deploy/ipk` за платките с повече софтуер.

## Статус: стъпка 3 готова, 2026-10-06

Образът е тестван по netboot (`device-dump/netboot-09-yocto.log`):

| | |
|---|---|
| initramfs cpio.gz.u-boot | 5.6 MB (лимит 20 MB), 52 пакета, без eudev |
| uImage | 2.58 MB (лимит 5 MB), същия defconfig като netboot кернела |
| boot | кернел 2.4 s, login prompt на ~12 s (DHCP и генериране на SSH ключ са по-голямата част) |
| услуги | busybox init, mdev, watchdog -T 60 -t 10, udhcpc на eth0, dropbear, syslogd |
| /config | jffs2 mtd9 монтиран от fstab |
| opkg | `opkg update` и `opkg install libmodbus-dev` от http://PC:8000/ipk, 1659 пакета във feed-а |

Уроци: без `sysvinit` в DISTRO_FEATURES update-rc.d не прави rcS.d връзките и busybox rcS не
стартира нищо; packagegroup-core-boot ползва `?=` за dev_manager и дърпа eudev, затова distro
conf-ът задава VIRTUAL-RUNTIME_* с `=`; poky busybox няма watchdog аплет (bbappend с antminer.cfg);
jffs2 не приема `nofail`.

Известен шум при boot: populate-volatile.sh се оплаква за `/var/volatile/tmp/tmp_volatile.NN`.
Безобидно, за оправяне по-късно.

## Persistent overlay на NAND `data` дяла (стъпка 5a), 2026-10-06

`/init` в initramfs-а (antminer-base) проверява дали data дялът (mtd10, 208 MB) е UBI с
volume `data` и маркер `/data/overlay/.enabled`. Ако да: копира ramfs-а в tmpfs (lower),
монтира overlayfs с upper/work на UBIFS и прави `switch_root`. Всичко, което се пише в `/`
(opkg install, /etc промени, OpenPLC програми), остава на UBIFS; UBIFS компресира (15.7 MB
upper заемат 6.8 MB). Без маркер: обикновен ramfs boot както досега.

Защити: `/init` въоръжава hardware watchdog-а преди всичко друго (ако userspace не стигне до
rcS и `watchdog` daemon-а, платката се рестартира след 60 s); брояч `/data/overlay/.boot_attempts`
се вдига от `/init` и нулира от rc5.d/S99antminer-boot-ok, при 3 неуспешни boot-а overlay-ът
се самоизключва. Броячът е тестван само в посока "успешен boot го нулира".

```sh
antminer-data init      # еднократно: ubiformat + volume "data" (изтрива дяла)
antminer-data enable    # overlay от следващия boot
antminer-data status    # root: overlay on ubi0:data / plain ramfs, заето място, брояч
antminer-data disable   # обратно към чист ramfs, данните остават
antminer-data wipe      # чист upper слой (фабричен образ + persistent data дял)
```
Тестван: netboot-18/19 (RAM) и nandboot-05 (от NAND).

## OpenPLC v3 (стъпка 5b)

Пакет `openplc-runtime` във feed-а (не в initramfs-а): web сървър на :8080, PLC core сорсове,
build скриптове. OpenPLC компилира всяка качена програма на платката с g++, затова пакетът
влачи gcc/g++/binutils/make/libc6-dev/libstdc++-dev (не `packagegroup-core-buildessential`:
той дърпа autoconf/perl, ~60 MB), bash, pkgconfig, libmodbus-dev, libgpiod-dev, Python 3 с
Flask, flask-login, flask-jwt-extended, flask-sqlalchemy, pyserial, pymodbus 2.5.3 (собствена
рецепта, meta-python има 3.x с друг API), python-dotenv (собствена рецепта); pyjwt е без
cryptography (bbappend), иначе влиза rust. `matiec` (iec2c) е отделна рецепта от същия OpenPLC
git. Snap7 се билдва от включените сорсове, OpenDNP3 не се билдва: dnp3_dummy.cpp + премахнати
`-lasiodnp3 ...` от compile_program.sh. Raspberry-Pi RTS извикванията в modbus_master.cpp (има ги
само в libmodbus fork-а на OpenPLC) са оградени с `#ifdef OPLC_LIBMODBUS_RPI`. Postinst трие
lto1/lto-dump/ld.gold/dwp (~50 MB). Резултат на платката: 187 пакета, 86 MB от 185 MB на `data`.

Hardware layer: `files/antminer.cpp` (libgpiod v2 + IIO), в UI остава като "Blank Linux".
Линии с имена `I0..` от device tree → `%IX0.0..`, `Q0..` → `%QX0.0..`, ADC AIN0..7 → `%IW0..7`.
Нищо не е hard-coded: смяната на пинове е нов YAML профил + DTB.

Инсталира се върху overlay-а: `opkg update && opkg install openplc-runtime`, стартира се с
`/etc/init.d/openplc start` (rc5.d S90 при boot). От PC: `tools/openplc-test.py <ip>` влиза с
openplc/openplc, качва (`--program x.st`, двустъпков upload както браузъра) и компилира
програма (~60 s на платката), стартира PLC-то и чете coils/registers по Modbus TCP :502.
Проверено 2026-10-06 с `../openplc/examples/gpio-echo.st`: Q0 "out hi" и Q1 мига на 1 Hz в
`/sys/kernel/debug/gpio`, I0..I3 се четат като discrete inputs, AIN0 се копира в holding 0.
matiec не допуска `AT %..` и обикновени променливи в един VAR блок.
`openplc-test.py <ip> --autostart on --only-settings` включва "Start OpenPLC in RUN mode":
след reboot runtime-ът сам стартира активната програма (проверено, nandboot-11-autostart.log).
Настройките (settings POST) трябва да се пращат целите: липсващо поле за порт изключва този
сървър, а друг device_hostname кара сървъра да вика hostnamectl, който го няма на платката.
Feed-ът се пълни чрез `antminer-feed-image` (фиктивен image), защото bitbake на
packagegroup не записва ipk на runtime зависимостите. Flask login cookie-то изисква верен
часовник (RTC без батерия → 2018 → login мълчаливо не работи): `antminer-base-ntp` пуска
busybox ntpd при boot и записва часа в RTC.

## Провизираща SD карта (стъпка 6)

`bitbake antminer-provision-image` дава `antminer-provision-image-antminer-bbb.rootfs.wic`:
MBR, p1 FAT32 64 MB (MLO, u-boot.img, uEnv.txt, uImage, am335x-antminer.dtb,
initramfs.cpio.gz.u-boot от `IMAGE_BOOT_FILES`), p2 ext4 ~400 MB с rootfs-а. Рецепти:
`antminer-sd-boot` (deploy на Bitmain MLO/u-boot.img от `mainline/boot/bitmain` и
`sdcard/uEnv-sd.txt`), `antminer-pinmux` (gen-dts.py, pad базата, профилите, препроцесираната
база от kernel source-а в do_compile, `antminer-dtb`; билдва и deploy-ва по едно DTB за всеки
профил в `boards/`, които wic слага на картата), `antminer-web` (Flask UI от `mainline/web`),
`antminer-provision` (fstab за /boot, банер с адреса). Кернелът има MMC/ext4/VFAT вградени
(в `kernel/defconfig`, не само във фрагмента: рецептата чете defconfig).
Запис на картата без четец на PC: от netboot-ната платка с MMC кернел
`wget -O - http://<pc>:8000/images/antminer-bbb/<истинското име>.wic | dd of=/dev/mmcblk0 bs=1M`
(feed сървърът сервира tmp/deploy; symlink-овете не се резолвват през \\wsl$, ползвай файла с
timestamp). След dd кернелът не вижда дяловете, защото mdev е автомонтирал суровото устройство:
`echo mmc0:XXXX > /sys/bus/mmc/drivers/mmcblk/unbind; echo mmc0:XXXX > .../bind`.
Проверено 2026-10-06: boot от картата през NAND U-Boot-а, root на ext4, web UI на :80,
`antminer-dtb build default` на платката за 1.6 s дава байт-идентично DTB с билднатото от кернела,
NAND флаш през UI (mtd6/7/8 с md5 проверка). Същият UI се инсталира и на NAND системата:
`opkg install antminer-web` (feed-ът го носи чрез `antminer-feed-extras`), после
`/etc/init.d/antminer-web start`; там е редно да му се сложи парола от страница Services
(HTTP basic, `admin`, `/config/web-password`). Тестовата платка го има инсталиран на overlay-а.

## Структура

| път | роля |
|---|---|
| `meta-antminer/conf/machine/antminer-bbb.conf` | tune cortexa8hf-neon, uImage @0x80008000, DTB ti/omap/am335x-antminer.dtb, cpio.gz.u-boot |
| `meta-antminer/conf/distro/antminer.conf` | poky + `INIT_MANAGER = "mdev-busybox"`, glibc, ipk, `DISTRO_FEATURES = "ipv4 largefile"` |
| `meta-antminer/recipes-kernel/linux/linux-antminer_6.12.bb` | kernel tarball от cdn.kernel.org, DTS и defconfig от repo/mainline |
| `meta-antminer/recipes-core/images/antminer-image.bb` | initramfs образ, проверява размера срещу 20 MB |
| `meta-antminer/recipes-core/images/antminer-feed-image.bb` | фиктивен image: билдва ipk-тата от `antminer-feed-extras` за feed-а |
| `meta-antminer/recipes-core/antminer-base/` | `/init` с overlay, `antminer-data`, rcS скриптове (early/config/boot-ok/ntp), fstab, volatiles, opkg.conf |
| `meta-antminer/recipes-openplc/` | `openplc-runtime` (+ `files/antminer.cpp` hardware layer, init скрипт), `matiec` |
| `meta-antminer/recipes-python/` | pymodbus 2.5.3, python-dotenv, pyjwt без cryptography |
| `../tools/openplc-test.py` | PC: login, upload, compile, start, Modbus TCP четене/запис |
| `../openplc/examples/` | ST примери за платката |
| `setup-yocto.sh` | WSL: host пакети, clone poky/meta-oe, build/conf, bitbake във фон |
| `../tools/serve-feed.ps1` | Windows: HTTP сървър за `tmp/deploy` (ipk feed) на порт 8000 |

Build дървото е в WSL: `~/antminer/yocto/{poky,meta-openembedded,build,downloads,sstate-cache}`.
Лог на фоновия билд: `~/antminer/yocto/build/bitbake.log`.

## Резултати (tmp/deploy/images/antminer-bbb/)

- `uImage` → NAND mtd7 (≤ 5 MB)
- `am335x-antminer.dtb` → NAND mtd6
- `antminer-image-antminer-bbb.rootfs.cpio.gz.u-boot` → NAND mtd8 (≤ 20 MB)

Тестват се с `tools/netboot.ps1 -Kernel uImage -Dtb am335x-antminer.dtb -Initrd <cpio.gz.u-boot>`
след копиране в `mainline/out/`, без да се пипа NAND.

## opkg на платката

`local.conf` слага `PACKAGE_FEED_URIS = "http://192.168.200.104:8000"`, което става
`/etc/opkg/*.conf` в образа. На PC: `powershell -File tools/serve-feed.ps1`, после на платката
`opkg update && opkg install <пакет>`. В чист ramfs инсталацията е до рестарт; за трайност
се ползва UBIFS `data` дялът с overlayfs (стъпка 5).

## Бележки

- `debug-tweaks` в образа означава root без парола. Да се махне преди реално разгръщане.
- Кернелът няма модули, всичко е вградено; `MODULE_TARBALL_DEPLOY = "0"`.
- Ubuntu 24.04 host: `kernel.apparmor_restrict_unprivileged_userns` не съществува в WSL ядрото,
  bitbake работи без промени.
