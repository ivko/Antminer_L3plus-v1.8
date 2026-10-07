# 9. Разработка

## Къде е какво (`mainline/`)

| път | роля |
|---|---|
| `kernel/defconfig` | **единственият** кернел конфиг: ползват го и Yocto, и `build-kernel.sh` |
| `build-kernel.sh` | бърз кернел + DTB без Yocto (клонира linux-6.12.y в `~/antminer/linux`); `menuconfig` режим за промяна на defconfig |
| `dts/am335x-antminer-base.dtsi` | фиксираната част на DTB: NAND и дяловете, Ethernet, конзола, PMIC, SD, LED-ове, изключени блокове |
| `dts/am335x-antminer.dts` | **генериран** от `pinmux/boards/default.yaml`; не се редактира на ръка |
| `dts/bitmain/` | дъмп на оригиналното Bitmain DTB, справочник за разводката |
| `pinmux/gen-dts.py` | генераторът YAML → DTS (pad база, запазени pad-ове, проверки, `--flat`, `--json`) |
| `pinmux/am335x-bbb-pins.json` | pad базата, извлечена от `docs/BBB_Pins.xlsx` с `extract-pins.py` |
| `pinmux/boards/*.yaml` | профилите |
| `pinmux/build-dtb.sh`, `make-base-pp.sh`, `build-dtb-flat.sh` | билд на DTB на PC-то (cpp) / preprocessed база / билд както на платката (само dtc) |
| `web/` | web UI-ът: `antminer_web/` (Flask), `static/board-editor.js` (Lit компонент), `test_smoke.py`, `render_page.py` |
| `yocto/meta-antminer/` | Yocto слоят (виж по-долу) |
| `yocto/setup-yocto.sh`, `build.sh` | настройка и билд |
| `tools/` | инструменти за PC-то (виж по-долу) |
| `sdcard/uEnv-sd.txt` | `uEnv.txt` на провизиращата карта |
| `boot/bitmain/` | оригиналните MLO и u-boot.img (за картата) |
| `openplc/examples/` | ST програми |
| `out/` | билд резултати за TFTP/netboot (в .gitignore) |

### Yocto слоят

| | |
|---|---|
| `conf/machine/antminer-bbb.conf` | cortexa8hf-neon, uImage на 0x80008000, DTB, initramfs формат |
| `conf/distro/antminer.conf` | poky + busybox init/mdev, glibc, ipk, `sysvinit` в DISTRO_FEATURES |
| `recipes-kernel/linux/linux-antminer_6.12.bb` | кернел от tarball + `kernel/defconfig` + DTS-ите от repo-то |
| `recipes-core/images/antminer-image.bb` | NAND образът (проверява лимита от 20 MB) |
| `recipes-core/images/antminer-provision-image.bb` + `wic/antminer-sd.wks` | SD картата |
| `recipes-core/images/antminer-feed-image.bb` | фиктивен образ, кара bitbake да запише ipk-тата на feed пакетите |
| `recipes-core/packagegroups/antminer-feed-extras.bb` | кои пакети гарантирано са във feed-а |
| `recipes-core/antminer-base/` | `/init` (overlay, SD root, watchdog), `antminer-data`, rcS скриптове, fstab, opkg настройки |
| `recipes-core/antminer-pinmux/` | генераторът, профилите и `antminer-dtb` на платката |
| `recipes-core/antminer-web/`, `antminer-provision/` | web UI-ът, банер и /boot на картата |
| `recipes-bsp/antminer-sd-boot/` | MLO, u-boot.img, uEnv.txt за wic |
| `recipes-openplc/` | OpenPLC runtime (с hardware layer-а `files/antminer.cpp`) и matiec |
| `recipes-python/` | pymodbus 2.5.3, python-dotenv, pyjwt без cryptography |
| `recipes-core/{busybox,dropbear,init-ifupdown}` | bbappend-и: busybox аплети (watchdog, ntpd, devmem...), dropbear ключ на /config, interfaces |

Слоят се чете директно от repo-то (`bblayers.conf` сочи към `/mnt/e/.../meta-antminer`), и
рецептите взимат файлове от `mainline/` чрез `ANTMINER_MAINLINE_DIR`: няма копия.

### Инструменти (`tools/`)

| | къде | какво |
|---|---|---|
| `antminer.py` | Windows, Linux | всичко с платката от PC-то: `config`, `console`, `uboot`, `netboot`, `deploy-dtb`, `feed`, `tftp`, `stage` |
| `site.conf` (+ `site.local.conf`) | | настройките на PC-то: IP, сериен порт, feed порт, Yocto път |
| `stage-out.sh` | WSL/Linux | копира резултатите от билда в `out/` (`antminer.py stage` го вика) |
| `write-sd.ps1` | Windows | записва `.wic` на SD карта (на Linux: `dd`) |
| `tftp-server.py` | | TFTP сървърът, който `antminer.py` ползва (може и самостоятелно) |
| `*.ps1` (netboot, deploy-dtb, uboot-cmd, serial, feed-server-*, serve-feed) | Windows | предишните версии на `antminer.py`; ще отпаднат |
| `flash-nand.sh` | платката | флаш на mtd6/7/8 от TFTP или локална директория (= `antminer-flash-nand`) |
| `openplc-test.py` | PC | качва/компилира/стартира OpenPLC програма, чете Modbus |

## Чести промени

**Пакет в NAND образа.** `CORE_IMAGE_EXTRA_INSTALL` в `antminer-image.bb`. Внимавай за лимита
20 MB (билдът спира над него). По-големите неща → feed (`antminer-feed-extras.bb`).

**Кернел опция.** `bash mainline/build-kernel.sh menuconfig` (записва обратно в
`mainline/kernel/defconfig`), после пребилд на `linux-antminer`. Модули не се пакетират:
всичко трябва да е `=y`. Лимитът за кернела в NAND е 5 MB.

**Нов pin профил.** Създай от редактора (записва в `/config/pinmux/` на платката) и го свали
с Export YAML в `mainline/pinmux/boards/`, за да влезе в образите и на картата.

**Промяна на фиксираната част на DTB.** `dts/am335x-antminer-base.dtsi`. Ако заемаш нов pad,
добави го в `RESERVED` в `gen-dts.py`, за да не го дава генераторът на профилите.

**Web UI.** Разработва се на PC-то срещу файловете в repo-то:
```sh
cd /mnt/e/Antminer/repo/mainline/web
ANTMINER_PINMUX=../pinmux ANTMINER_CONFIG=/tmp/cfg ANTMINER_PAYLOAD=../out/sdcard python3 run.py --port 8088
python3 test_smoke.py          # всички страници + YAML кръгово преобразуване на профилите
```
Нужни са `python3-flask` и `python3-yaml` във WSL. NAND страниците и build на профил искат
`antminer-dtb`/`mtd` и работят само на платката. Бързо качване на платка без пребилд:
`scp` на файловете в `/usr/share/antminer/web/antminer_web/` и `/etc/init.d/antminer-web restart`.

## Проверки преди commit

```sh
python3 mainline/web/test_smoke.py
bash mainline/pinmux/build-dtb.sh mainline/pinmux/boards/default.yaml   # регенерира am335x-antminer.dts
bash mainline/yocto/build.sh fg
```
Ако `default.yaml` е променен, `dts/am335x-antminer.dts` трябва да е в същия commit.

## Хардуерни факти, които не се виждат от кода

- 3.8 кернелът на Bitmain номерира `uart1..6` и `gpio1..4`; mainline е `uart0..5`, `gpio0..3`.
- NAND таймингите в DTS са от am335x-evm; тези на Bitmain дават повредени данни с новия драйвер.
- U-Boot 2013.04 няма `bootz`: кернелът е uImage, load адрес 0x80008000.
- ADC е 1.8 V, 12 bit; `ti,am335-sdhci` (не omap_hsmmc) е драйверът за microSD в 6.12.
- Подробната история (какво е пробвано и защо) е в `mainline/README.md` и `mainline/yocto/README.md`.
