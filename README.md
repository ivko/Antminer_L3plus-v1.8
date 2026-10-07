# Antminer BB-Black V1.8 като Modbus / OpenPLC I/O модул

Контролерната платка от Antminer L3+ (TI AM3352, 256 MB RAM, 256 MB NAND, Ethernet) се
превръща в евтин индустриален I/O модул: съвременен Linux (6.12), конфигурируеми пинове,
Modbus TCP/RTU, OpenPLC, web интерфейс за провизиране и настройка. Всичко свързано с
копаене е премахнато; от Bitmain остават само зареждачът в NAND (SPL/U-Boot) и разводката.

## Откъде да започна

| искам да... | чети |
|---|---|
| разбера какво е платката, как boot-ва и какво има в NAND | [docs/01-overview.md](docs/01-overview.md) |
| подготвя PC и билдна всичко от нулата | [docs/02-build.md](docs/02-build.md) |
| сложа системата на платка (SD карта, NAND, netboot) | [docs/03-install.md](docs/03-install.md) |
| пусна feed сървъра и инсталирам пакети (OpenPLC, web UI) | [docs/04-packages.md](docs/04-packages.md) |
| настроя мрежа, hostname, SSH, услуги, web UI | [docs/05-configure.md](docs/05-configure.md) |
| сменя кои пинове какво правят (pinmux профили) | [docs/06-pinmux.md](docs/06-pinmux.md) |
| пусна PLC програма и Modbus | [docs/07-openplc.md](docs/07-openplc.md) |
| оправя нещо, което не работи | [docs/08-troubleshooting.md](docs/08-troubleshooting.md) |
| променя кода, рецептите или UI-а | [docs/09-development.md](docs/09-development.md) |

Най-краткият път до работеща платка:
1. Билд (WSL): `bash mainline/yocto/setup-yocto.sh` (първият път ~2-4 ч).
2. Запиши картата: `powershell -File mainline\tools\write-sd.ps1`.
3. Сложи картата в платката и я включи. Отвори адреса от банера на конзолата (`http://<ip>/`).
4. В web UI-а: NAND → Flash, Init, Enable. Изключи, извади картата, включи.

## Карта на repo-то

| път | какво е |
|---|---|
| `mainline/` | **текущият проект**: кернел конфиг, DTS, Yocto слой, pinmux генератор, web UI, инструменти |
| `mainline/yocto/meta-antminer/` | Yocto слоят: машина, дистро, рецепти, образи |
| `mainline/pinmux/` | YAML профили на пиновете и генераторът им към device tree |
| `mainline/web/` | web UI-ът (Flask + Lit компонент) |
| `mainline/tools/` | инструменти за PC-то: netboot, запис на SD, feed сървър, флаш, OpenPLC тест |
| `mainline/dts/` | device tree: фиксираната част (`am335x-antminer-base.dtsi`), генерираният `am335x-antminer.dts`, дъмп на оригиналния Bitmain DTB |
| `mainline/kernel/` | `defconfig` на кернела (той е източникът за Yocto) |
| `hardware/breakout/` | KiCad проект на тестова платка с входове/изходи |
| `docs/` | тези ръководства + справочници (BBB_Pins.xlsx, pinmux PDF-и) |
| `docs/history/` | бележки от предишни етапи (Ångström 3.8) |
| `dts/`, `images/`, `scripts/`, `packages/`, `diff/` | **legacy**: работа върху оригиналната Ångström 3.8 система (repack на initramfs, стари DTS). Не се ползват от mainline |

`mainline/README.md` и `mainline/yocto/README.md` са дневник на разработката (какво е
пробвано, защо, с какви резултати). Полезни за "защо е така", не за "как да".

## Важни правила

- **Никога не записвай mtd0-mtd5** (Bitmain SPL, U-Boot, env). Платката няма Boot бутон;
  счупен зареждач значи възстановяване по сериен порт или JTAG. Всички инструменти пишат само
  mtd6 (DTB), mtd7 (кернел), mtd8 (initramfs), mtd9 (/config) и mtd10 (data).
- Образите са с `debug-tweaks`: root **без парола** по SSH и конзола. Преди реално
  разгръщане виж [docs/05-configure.md](docs/05-configure.md#сигурност).
- IP адресът на feed сървъра е вграден в образа при билд (по подразбиране `192.168.200.104:8000`).
