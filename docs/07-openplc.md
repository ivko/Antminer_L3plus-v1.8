# 7. OpenPLC и Modbus

## Инсталиране и старт

На платка с включен overlay (04-packages):
```sh
opkg update && opkg install openplc-runtime
/etc/init.d/openplc start            # после тръгва сам при boot
```
Web интерфейсът е на `http://<ip>:8080`, `openplc` / `openplc`. Modbus TCP сървърът е на порт
502, когато PLC-то е в RUN.

Програмите се компилират на самата платка с gcc (~60 s). Затова пакетът носи компилатора и
заема ~86 MB от data дяла.

## Входове и изходи

Hardware layer-ът (`mainline/yocto/meta-antminer/recipes-openplc/openplc-runtime/files/antminer.cpp`)
не знае нищо за конкретни пинове. При старт търси GPIO линии с имена `I<n>` и `Q<n>` във
всички gpiochip-ове (включително I2C експандери) и ADC каналите:

| в Linux | в PLC програмата | Modbus |
|---|---|---|
| линия `I0`..`I127` | `%IX0.0`..`%IX15.7` (`In` = `%IX(n/8).(n%8)`) | discrete inputs 0.. (1x) |
| линия `Q0`..`Q127` | `%QX0.0`..`%QX15.7` | coils 0.. (0x) |
| AIN0..AIN7 (`in_voltageN_raw`, 0..4095 = 0..1.8 V) | `%IW0`..`%IW7` | input registers 0.. (3x) |
| | `%QW0`.. | holding registers 0.. (4x) |
| | `%MW0`.. | holding registers 1024.. |

Кои физически пинове са `I0`/`Q0` решава pinmux профилът (06-pinmux): преименуваш линия в
редактора, флашваш DTB-то, рестартираш, и същата PLC програма ползва новия пин.

Броят намерени линии се вижда в лога при старт на програмата:
`antminer hardware layer: 8 inputs (I*), 8 outputs (Q*), 7 ADC channels`.

Изходите се управляват всеки цикъл. Линия, заета от друг процес (например `gpioset`), не може
да бъде взета от OpenPLC и обратно.

**Внимание за Modbus:** сървърът на OpenPLC чете и пише буферите на runtime-а директно, не
променливите на програмата. Всички намерени `I*`/`Q*`/ADC се виждат по Modbus, дори да не са
декларирани в програмата, и запис на coil променя изхода, ако програмата не го презаписва.

## Първа програма

Пример: `mainline/openplc/examples/gpio-echo.st` (Q0 = I0 или coil 8, Q1 мига на 1 Hz, AIN0 се
копира в holding register 0).

През UI-а: Programs → Upload → Compile → Dashboard → Start PLC. Или от PC-то:
```powershell
python mainline\tools\openplc-test.py <ip> --program mainline\openplc\examples\gpio-echo.st
python mainline\tools\openplc-test.py <ip> --autostart on --only-settings     # RUN след всеки boot
python mainline\tools\openplc-test.py <ip> --no-compile --no-start --write-coil 8 1
```
`openplc-test.py` влиза, качва, компилира, стартира и чете по Modbus TCP coils, discrete inputs,
holding и input регистрите (само стандартна Python библиотека).

Особеност на компилатора (matiec): в един `VAR` блок не може да има едновременно променливи с
`AT %...` и обикновени (таймери и т.н.); раздели ги в два блока.

## Проверка без OpenPLC

```sh
gpioinfo | grep -E '"(I|Q)[0-9]+"'
gpioset -t0 Q0=1 ; gpioget I0
cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw
```
Спри OpenPLC (`/etc/init.d/openplc stop`), иначе линиите са заети.

Независима проверка на Modbus: всеки Modbus TCP клиент (ModScan, QModMaster, `pymodbus`) към
`<ip>:502`, unit id без значение.

## Modbus RTU

UART-ите (`/dev/ttyS1`, `S2`, `S4`, `S5` в профила default) могат да се ползват от OpenPLC като
Modbus slave устройства (Slave Devices в UI-а) или от собствени програми с libmodbus. За RS-485
трябва линия за посоката (DE): в профила `breakout` това са `RS485_DE0/1`.

## Настройки на OpenPLC

Settings в UI-а: портове (Modbus 502, EtherNet/IP), „Start in RUN mode“. Базата е
`/opt/openplc/webserver/openplc.db`, програмите са в `/opt/openplc/webserver/st_files/`
(на overlay-а).
