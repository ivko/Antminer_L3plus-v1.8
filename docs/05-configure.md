# 5. Настройка: мрежа, услуги, достъп

## Достъп до платката

| как | данни |
|---|---|
| конзола | COM порт на USB-serial адаптера, 115200 8N1 (PuTTY). Login `root`, без парола |
| SSH | `ssh root@<ip>`, без парола (по подразбиране) |
| web UI | `http://<ip>/` (SD системата винаги; NAND системата след `opkg install antminer-web`) |
| OpenPLC | `http://<ip>:8080/`, `openplc` / `openplc` |

Hostname-ът е `antminer-<последните 6 hex на MAC>`, например `antminer-731c92`.

## Къде са настройките

Всичко, което е специфично за една платка, е на дяла `/config` (NAND mtd9, jffs2). Той не се
трие при флаш на системата (освен с `--wipe-config` / отметката в UI-а) и е общ за NAND и SD
системите. Файловете се четат при boot от `/etc/init.d/antminer-config`.

| файл | какво | пример |
|---|---|---|
| `/config/hostname` | друг hostname вместо този от MAC | `pump-station-3` |
| `/config/network` | статичен IP; без файла е DHCP | виж по-долу |
| `/config/ntp-server` | NTP сървър (първият ред) | `192.168.200.1` |
| `/config/ssh/authorized_keys` | публични SSH ключове за root | `ssh-ed25519 AAAA...` |
| `/config/ssh/` | SSH host ключът на платката (да не се сменя при всеки флаш) | |
| `/config/web-password` | паролата на web UI-а (хеш); без файла UI-ът е отворен | |
| `/config/pinmux/*.yaml` | локални pinmux профили, записани от редактора | |

Всичко това се настройва и от web UI-а, страница **Services**.

### Статичен IP

`/config/network` (shell синтаксис):
```sh
MODE="static"
ADDRESS="192.168.1.50"
NETMASK="255.255.255.0"
GATEWAY="192.168.1.1"
DNS="192.168.1.1"
```
Прилага се при следващия boot (или `/etc/init.d/antminer-config start && /etc/init.d/networking restart`).
За обратно към DHCP изтрий файла.

### Часовник

Платката няма батерия за RTC: без мрежа часовникът тръгва от последния записан час.
`antminer-ntp` пуска `ntpd` при boot и записва верния час в RTC. Без интернет задай NTP
сървър в локалната мрежа в `/config/ntp-server`. Грешен час чупи login-а в OpenPLC
(cookie-то изтича веднага).

## Услуги

Busybox init + SysV скриптове. Управление: `/etc/init.d/<име> start|stop|restart|status`.

| ред | скрипт | какво прави |
|---|---|---|
| rcS S04 | `mdev` | устройства в /dev |
| rcS S36 | `antminer-early` | директории в /var, **watchdog** демона (60 s таймаут) |
| rcS S41 | `antminer-config` | монтира /config, hostname, мрежа, SSH ключове |
| rc5 S01 | `networking` | eth0 (DHCP или статичен) |
| rc5 S05 | `antminer-ntp` | ntpd + RTC |
| rc5 S10 | `dropbear` | SSH |
| rc5 S20 | `syslog` | `/var/log/messages` (в RAM) |
| rc5 S20 | `antminer-provision` | само на SD картата: монтира /boot, показва банера |
| rc5 S50 | `antminer-web` | web UI на порт 80 (ако е инсталиран) |
| rc5 S90 | `openplc` | OpenPLC (ако е инсталиран) |
| rc5 S99 | `antminer-boot-ok` | маркира успешен boot (нулира брояча на overlay-а) |

Нова услуга на платката: скрипт в `/etc/init.d/`, после `update-rc.d <име> defaults`. В Yocto
рецепта: `inherit update-rc.d` (виж `antminer-web.bb` като пример).

### Watchdog

`/init` включва hardware watchdog-а още преди услугите, а `antminer-early` пуска демона, който
го храни. Ако системата увисне за 60 s, платката се рестартира сама. Не го изключвай: платката
няма Reset бутон. За продължителна работа без демона (дебъг) `/etc/init.d/antminer-early`
може да се редактира, но платката ще рестартира 60 s след спирането му.

## Логове

```sh
dmesg | tail
tail -f /var/log/messages          # syslog, в RAM, губи се при рестарт
cat /var/log/antminer-web.log      # web UI
```

## Сигурност

Образите се билдват с `debug-tweaks`: root без парола по SSH и конзола, web UI-ът без парола.
Това е удобно в лабораторията и неприемливо в реална мрежа. Минимумът преди разгръщане:

1. Сложи SSH ключ в `/config/ssh/authorized_keys` и парола на web UI-а (Services).
2. Смени паролата на OpenPLC (`openplc`/`openplc`) от неговия UI.
3. Махни `debug-tweaks` от `IMAGE_FEATURES` в
   `firmware/yocto/meta-antminer/recipes-core/images/antminer-image.bb` и добави root парола
   през `EXTRA_USERS_PARAMS` (`inherit extrausers`), пребилдвай и флашни. `passwd` на самата
   платка работи само при overlay и не оцелява при `antminer-data wipe`.
4. Feed сървърът е обикновен HTTP без автентикация; дръж го само в доверена мрежа.

Modbus TCP няма автентикация по дизайн: всеки в мрежата може да пише изходи.
