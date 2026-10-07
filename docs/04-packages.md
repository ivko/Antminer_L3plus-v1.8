# 4. Feed сървър и инсталиране на пакети

Образът в NAND е минимален (~5.6 MB). Всичко по-голямо (OpenPLC с компилатора, Python, web UI-а
на NAND системата, инструменти) се инсталира с `opkg` от feed-а, който билдът прави, и се пази
на data дяла (overlay).

## Предварително условие: overlay

Без overlay root-ът е в RAM и всичко инсталирано изчезва при рестарт.

```sh
antminer-data status        # трябва: "root: overlay on ubi0:data"
```

Ако не е: `antminer-data init` (само на нова платка, трие mtd10), `antminer-data enable`, `reboot`.
Командите на `antminer-data`:

| команда | какво |
|---|---|
| `status` | откъде е root-ът, заето място, брояч на неуспешни boot-ове |
| `init` | форматира mtd10 като UBIFS (трие всичко там) |
| `enable` / `disable` | overlay от следващия boot / обратно към чист RAM (данните остават) |
| `wipe` | изтрива всичко инсталирано (връща фабричния образ); само при изключен overlay |
| `mount` | монтира `/data` при изключен overlay, за преглед |

Защита: ако 3 поредни boot-а с overlay не стигнат до края на стартирането, overlay-ът се
изключва сам и платката тръгва от чистия образ.

## Feed сървърът

Feed-ът е `~/antminer/yocto/build/tmp/deploy/` във WSL, сервиран по HTTP на порт 8000.

```sh
python mainline/tools/antminer.py feed start     # във фон, връща веднага
python mainline/tools/antminer.py feed status
python mainline/tools/antminer.py feed stop
python mainline/tools/antminer.py feed serve     # на преден план, Ctrl-C спира
```

Работи и на Windows (чете feed-а от WSL през `\\wsl$`), и на Linux. Портът е `FEED_PORT` от
`site.conf`. Windows Firewall трябва да пуска TCP 8000:
```powershell
netsh advfirewall firewall add rule name="opkg feed" dir=in action=allow protocol=TCP localport=8000
```
Проверка от браузър: `http://<PC>:8000/ipk/all/Packages.gz` се сваля.

След всеки билд индексът се обновява от `package-index` (част от пълния билд). Ако си
билдвал само една рецепта: `bash mainline/yocto/build.sh package-index`.

### Feed адресът

Платките търсят feed-а на адреса, вграден при билда (`FEED_HOST`, по подразбиране
`192.168.200.104:8000`), в `/etc/opkg/base-feeds.conf`:
```
src/gz uri-all-0 http://192.168.200.104:8000/ipk/all
src/gz uri-cortexa8hf-neon-0 http://192.168.200.104:8000/ipk/cortexa8hf-neon
src/gz uri-antminer_bbb-0 http://192.168.200.104:8000/ipk/antminer_bbb
```
Ако PC-то е с друг IP: редактирай файла на платката (при overlay промяната остава), или
смени `PACKAGE_FEED_URIS` в `~/antminer/yocto/build/conf/local.conf` и пребилдвай образите.

## Инсталиране

```sh
opkg update
opkg install openplc-runtime          # OpenPLC + компилатор + Python (~180 пакета, ~86 MB)
opkg install antminer-web             # web UI-ът и на NAND системата (порт 80)
opkg list | grep -i <нещо>            # търсене
opkg remove <пакет>
```

Полезни пакети от feed-а:

| пакет | какво |
|---|---|
| `openplc-runtime` | OpenPLC v3 с hardware layer за платката, web на 8080, Modbus TCP 502 |
| `antminer-web` | web UI: NAND, pinmux редактор, настройки (порт 80) |
| `antminer-pinmux` | `antminer-dtb` и генераторът на DTB (идва с antminer-web) |
| `libmodbus-dev`, `libgpiod-dev`, `gcc`, `g++`, `make` | за собствени C програми на платката |
| `python3`, `python3-pymodbus` | Python и Modbus |
| `i2c-tools`, `libgpiod-tools`, `mtd-utils` | вече са в образа |

Пълният списък пакети, които билдът гарантира във feed-а, е в
`mainline/yocto/meta-antminer/recipes-core/packagegroups/antminer-feed-extras.bb`. Във feed-а
има и всичко, което билдът е минал по пътя (~2200 пакета), но не всичко е тествано.

## Кешът на opkg

Изтеглените пакети се кешират в RAM (`/var/volatile/cache/opkg`, `volatile_cache 1` в
`/etc/opkg/antminer.conf`) и изчезват при рестарт, за да не пълнят data дяла. Индексите от
`opkg update` са в `/var/lib/opkg/lists` (на overlay-а, няколко MB):
```sh
rm -rf /var/volatile/cache/opkg/*  /var/lib/opkg/lists/*
df -h /data
```

## Място

Data дялът е 185 MB използваеми. OpenPLC заема ~86 MB. При пълен дял `opkg` спира с грешка
за място; `antminer-data wipe` (при изключен overlay) връща чисто състояние.
