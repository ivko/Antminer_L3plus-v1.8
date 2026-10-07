# 3. Слагане на системата на платка

Четири начина, от най-удобния към най-ниското ниво:

| начин | кога | пише в NAND |
|---|---|---|
| A. Провизираща SD карта + web UI | нова платка, нормалната работа | да, от UI-а |
| B. netboot по TFTP | разработка, проба на нов кернел/DTB | не |
| C. `flash-nand.sh` от работеща платка | без карта, по мрежа | да |
| D. само DTB | смяна на pinmux профил | само mtd6 |

Преди всичко: прочети SYSBOOT на платката (първи ред на конзолата, `Control_status`).
`…13` = тръгва от NAND (нормалният случай). `…17` = тръгва **само** от SD карта, виж края.

## A. Провизираща SD карта

### 1. Запис на картата

Билдът дава `antminer-provision-image-antminer-bbb.rootfs.wic` (~620 MB). Става карта от 1 GB
нагоре; остатъкът от картата не се ползва.

**Windows** (картата в четец):
```powershell
python mainline\tools\antminer.py stage       # слага .wic в mainline\out
powershell -File mainline\tools\write-sd.ps1
```
Скриптът показва USB дисковете между 1 и 64 GB, пита кой е картата и иска `YES`. Пуска се
като администратор (UAC прозорец), изтрива таблицата на картата, пише образа и проверява
първите 70 MB. Windows ще покаже дял 2 като непознат (ext4) и може да предложи да го
форматира: откажи.

Други начини: Rufus / balenaEtcher (режим „DD image“), или на Linux:
```sh
sudo dd if=antminer-provision-image-antminer-bbb.rootfs.wic of=/dev/sdX bs=4M conv=fsync status=progress
```

**От работеща платка** (без четец; кернелът трябва да има MMC, всички от 2026-10 имат):
```sh
wget -O - http://<PC>:8000/images/antminer-bbb/<файлът с датата>.wic | dd of=/dev/mmcblk0 bs=1M
sync
```
После кернелът не вижда новите дялове (mdev е монтирал картата): или reboot, или
`echo mmc0:XXXX > /sys/bus/mmc/drivers/mmcblk/unbind` и същото с `bind`
(`ls /sys/bus/mmc/drivers/mmcblk/` дава името).

### 2. Boot от картата

Изключена платка → карта в слота → включи. U-Boot от NAND вижда `uEnv.txt` на картата и
зарежда системата от нея. След ~20 s на конзолата излиза банер:

```
========================================================
 Antminer provisioning system (running from the SD card)
   board MAC c4:f3:12:73:1c:92   SYSBOOT 0x00420313
   web UI:  http://192.168.200.116/
   ssh:     root@192.168.200.116 (no password)
========================================================
```

IP-то е от DHCP. Без конзола: виж DHCP таблицата на рутера; hostname-ът е
`antminer-<последните 6 hex на MAC>`.

### 3. Флаш на NAND от web UI-а

Отвори `http://<ip>/` → **NAND**:

1. **Scan NAND** показва какво има сега в mtd6/7/8 и дали съвпада с файловете на картата.
2. **Flash**: избери `uImage`, DTB (`am335x-antminer.dtb` = профил default, или `profile-<име>.dtb`),
   `initramfs.cpio.gz.u-boot`. На нова платка (с Bitmain фърмуер) отметни „also erase /config“,
   за да изчезнат старите Bitmain настройки. Всеки дял се проверява по md5 след запис.
3. **Init** (data дяла): форматира mtd10 като UBIFS. Само веднъж за платка; трие всичко там.
4. **Enable overlay**: от следващия boot root-ът става persistent.
5. Изключи платката, извади картата, включи. Платката тръгва от NAND (~12 s до login).

Същото без UI-а, от shell-а на SD системата:
```sh
antminer-flash-nand --wipe-config /boot uImage am335x-antminer.dtb initramfs.cpio.gz.u-boot
antminer-data init && antminer-data enable
```

**Картата се вади само при изключена платка.** Ако я извадиш докато системата работи от нея,
root-ът изчезва и нищо не може да се изпълни; `echo b > /proc/sysrq-trigger` в още отворен
shell рестартира платката.

### 4. След първия boot от NAND

Пакетите (OpenPLC, web UI на NAND системата) → [04-packages.md](04-packages.md).
Мрежа, hostname, SSH ключове → [05-configure.md](05-configure.md).

## B. netboot (нищо не се пише)

PC-то пуска TFTP сървър, скриптът рестартира платката през конзолата, спира U-Boot, тегли
кернел, DTB и initramfs в RAM и ги стартира. Добро за проба на нов кернел или профил.

```powershell
python mainline\tools\antminer.py stage
python mainline\tools\antminer.py netboot                                    # кернел, default DTB, initramfs
python mainline\tools\antminer.py netboot --dtb am335x-antminer-breakout.dtb --log boot.log
```

- Изисква серийният порт да е свободен (затвори PuTTY) и firewall-ът да пуска UDP 69 за python
  (Windows: `netsh advfirewall firewall add rule name="TFTP in" dir=in action=allow protocol=UDP localport=69`).
- Файловете се търсят в `mainline/out/`; портът и IP-то са от `site.conf` (`--port` за друг порт).
- Платката трябва да е включена; инструментът праща `reboot` по конзолата и спира U-Boot.
- `antminer.py uboot "printenv" --then boot` изпълнява произволни U-Boot команди по същия начин.

## C. Флаш от работеща платка по TFTP

На платката (каквато и да е система: Yocto, SD, дори старият Ångström):
```sh
cd /tmp
tftp -g -r flash-nand.sh <PC>
sh flash-nand.sh [--wipe-config] <PC> uImage-yocto.bin am335x-antminer-yocto.dtb antminer-image.cpio.gz.u-boot
reboot
```
TFTP сървърът на PC-то: `python mainline/tools/antminer.py tftp` (сервира `mainline/out/`;
netboot и deploy-dtb го пускат сами). Скриптът отказва, ако дяловете не са на очакваните места, ако
файл не се събира, или ако DTB-то не е DTB.

## D. Само DTB (друг pinmux профил)

- от web UI-а: Pinmux → профил → **Save + flash to mtd6**;
- на платката: `antminer-dtb build <профил> && antminer-dtb flash /tmp/am335x-antminer-<профил>.dtb`;
- от PC-то: `python mainline/tools/antminer.py deploy-dtb <профил>` (`--netboot-only` за проба от RAM).

Подробно в [06-pinmux.md](06-pinmux.md). Ефект след рестарт.

## Връщане към оригиналния Bitmain фърмуер

Оригиналните файлове са в `legacy/bitmain-recovery/`: `uImage.bin`, `initramfs.bin.SD`,
`am335x-boneblack-bitmainer.dtb`. Копирай ги в `mainline\out\` и:
```sh
sh flash-nand.sh <PC> uImage.bin am335x-boneblack-bitmainer.dtb initramfs.bin.SD
```
mtd0-5 не са пипани никога, така че това е пълно връщане (без съдържанието на /config, ако
е изтрит). Не ползвай `runme.sh` от същата папка: той пише и u-boot (виж `legacy/README.md`).

## Платки със SYSBOOT 0x17 (само SD)

ROM-ът на тези платки зарежда MLO и U-Boot от картата, а NAND изобщо не е в списъка.
Без карта не тръгват. С провизиращата карта тръгва провизиращата система, както при другите.

За да работят от NAND системата, картата трябва да остане в слота, но без `uEnv.txt` (само
`MLO` и `u-boot.img` на FAT дял 1): тогава U-Boot от картата не намира `uEnv.txt` и чете
кернела от NAND. **Това не е тествано** на такава платка.
