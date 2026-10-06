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

## Структура

| път | роля |
|---|---|
| `meta-antminer/conf/machine/antminer-bbb.conf` | tune cortexa8hf-neon, uImage @0x80008000, DTB ti/omap/am335x-antminer.dtb, cpio.gz.u-boot |
| `meta-antminer/conf/distro/antminer.conf` | poky + `INIT_MANAGER = "mdev-busybox"`, glibc, ipk, `DISTRO_FEATURES = "ipv4 largefile"` |
| `meta-antminer/recipes-kernel/linux/linux-antminer_6.12.bb` | kernel tarball от cdn.kernel.org, DTS и defconfig от repo/mainline |
| `meta-antminer/recipes-core/images/antminer-image.bb` | initramfs образ, проверява размера срещу 20 MB |
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
