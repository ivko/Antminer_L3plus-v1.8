# 2. Билд от нулата

Всичко се билдва с Yocto (scarthgap) в WSL2 на Windows. На обикновен Linux (Ubuntu 22.04/24.04)
работи по същия начин, само Windows инструментите (`*.ps1`) отпадат.

## Какво трябва на PC-то

| | |
|---|---|
| ОС | Windows 10/11 с WSL2 и Ubuntu 24.04 (`wsl --install -d Ubuntu-24.04`) |
| диск | ~60 GB свободни **във WSL** (ext4 диска на дистрибуцията): build ~45 GB, downloads ~2 GB, sstate ~2.5 GB |
| RAM / CPU | 16 GB+ и колкото повече ядра, толкова по-бързо |
| мрежа | интернет при първия билд (сорсове) |
| Windows | Python 3 (за TFTP/HTTP сървърите и тестовете), Git; по желание PuTTY за конзолата |
| хардуер | USB-serial адаптер 3.3 V към конзолата на платката (COM порт, 115200) |

Repo-то се очаква в `E:\Antminer\repo` (във WSL `/mnt/e/Antminer/repo`). Ако е другаде,
задай `REPO=/mnt/<буква>/<път>` при всички WSL команди по-долу.

## Първи билд

```sh
# във WSL
export FEED_HOST=192.168.200.104:8000     # IP на PC-то, от което платките ще теглят пакети
bash /mnt/e/Antminer/repo/mainline/yocto/setup-yocto.sh
```

Скриптът:
1. инсталира host пакетите за Yocto (иска `sudo` веднъж);
2. клонира `poky` и `meta-openembedded` (клон scarthgap) в `~/antminer/yocto`;
3. сваля кернела 6.12.112 и проверява sha256;
4. пише `build/conf/local.conf` и `bblayers.conf` (само ако ги няма);
5. пуска пълния билд във фон.

`FEED_HOST` влиза в `/etc/opkg/base-feeds.conf` на всички образи. Ако PC-то е с друг IP по-късно,
виж [04-packages.md](04-packages.md#feed-адресът).

Първият билд отнема 2-4 часа. Следене:

```sh
bash /mnt/e/Antminer/repo/mainline/yocto/build.sh status      # работи ли + последните редове
tail -f ~/antminer/yocto/build/bitbake.log
```

Последният ред на лога е `BITBAKE_EXIT=0` при успех.

## Следващи билдове

```sh
bash /mnt/e/Antminer/repo/mainline/yocto/build.sh            # всичко, във фон
bash /mnt/e/Antminer/repo/mainline/yocto/build.sh fg         # всичко, на преден план
bash /mnt/e/Antminer/repo/mainline/yocto/build.sh antminer-provision-image   # само един образ
```

„Всичко“ е: `antminer-image`, `antminer-provision-image`, `antminer-feed-image` и
`package-index`. Bitbake пребилдва само променените части; промяна в web UI-а е минута,
промяна в кернела ~10 минути.

## Какво се получава

В `~/antminer/yocto/build/tmp/deploy/images/antminer-bbb/`:

| файл | за |
|---|---|
| `uImage` | кернел → NAND mtd7 |
| `am335x-antminer.dtb` | DTB на профила `default` → NAND mtd6 |
| `profile-<име>.dtb` | DTB на всеки профил от `mainline/pinmux/boards/` |
| `antminer-image-antminer-bbb.rootfs.cpio.gz.u-boot` | initramfs → NAND mtd8 |
| `antminer-provision-image-antminer-bbb.rootfs.wic` | цялата провизираща SD карта |

В `~/antminer/yocto/build/tmp/deploy/ipk/` е feed-ът (виж 04-packages).

Повечето имена са symlink-ове към файлове с дата в името. От Windows (`\\wsl$\...`)
symlink-овете често не се отварят; ползвай файла с датата или копирай с:

```sh
bash /mnt/e/Antminer/repo/mainline/tools/stage-out.sh
```

Той слага последните резултати в `mainline/out/` под постоянни имена (`uImage-yocto.bin`,
`am335x-antminer-<профил>.dtb`, `antminer-image.cpio.gz.u-boot`, `antminer-provision.wic`,
`flash-nand.sh`), които ползват netboot, deploy-dtb и write-sd.

## Възпроизводимост

- Кернелът е фиксиран: 6.12.112, sha256 в `linux-antminer_6.12.bb`.
- `poky` и `meta-openembedded` се клонират като последното от клон scarthgap. Билдът от
  2026-10 е с poky `3a3d07f625ae` и meta-openembedded `0f00f8b9a219`. Ако нова версия
  счупи нещо, `git checkout` на тези commit-и в `~/antminer/yocto/poky` и `meta-openembedded`.
- OpenPLC е фиксиран по commit (`SRCREV` в `openplc-runtime_git.bb`).
- `~/antminer/yocto/downloads` съдържа всички сорсове. Пази го (или го архивирай): с него
  билдът минава без интернет и без риск upstream да е изчезнал.

## Почистване

```sh
bash /mnt/e/Antminer/repo/mainline/yocto/build.sh <рецепта> -c cleansstate   # една рецепта наново
rm -rf ~/antminer/yocto/build/tmp                                            # всичко наново (sstate остава, бързо е)
```
