# 7. OpenPLC and Modbus

## Installation and start

On a board with the overlay enabled (04-packages):
```sh
opkg update && opkg install openplc-runtime
/etc/init.d/openplc start            # afterwards it starts by itself at boot
```
The web interface is at `http://<ip>:8080`, `openplc` / `openplc`. The Modbus TCP server is on
port 502 when the PLC is in RUN.

Programs are compiled on the board itself with gcc (~60 s). That is why the package includes the
compiler and takes ~86 MB of the data partition.

## Inputs and outputs

The hardware layer (`firmware/yocto/meta-antminer/recipes-openplc/openplc-runtime/files/antminer.cpp`)
knows nothing about specific pins. At start it looks for GPIO lines named `I<n>` and `Q<n>` in
all gpiochips (including I2C expanders), and for the ADC channels:

| in Linux | in the PLC program | Modbus |
|---|---|---|
| line `I0`..`I127` | `%IX0.0`..`%IX15.7` (`In` = `%IX(n/8).(n%8)`) | discrete inputs 0.. (1x) |
| line `Q0`..`Q127` | `%QX0.0`..`%QX15.7` | coils 0.. (0x) |
| AIN0..AIN7 (`in_voltageN_raw`, 0..4095 = 0..1.8 V) | `%IW0`..`%IW7` | input registers 0.. (3x) |
| | `%QW0`.. | holding registers 0.. (4x) |
| | `%MW0`.. | holding registers 1024.. |

Which physical pins are `I0`/`Q0` is decided by the pinmux profile (06-pinmux): you rename a line
in the editor, flash the DTB, restart, and the same PLC program uses the new pin.

The number of lines found is shown in the log when the program starts:
`antminer hardware layer: 8 inputs (I*), 8 outputs (Q*), 7 ADC channels`.

The outputs are driven every cycle. A line held by another process (for example `gpioset`) cannot
be taken by OpenPLC, and vice versa.

**Note on Modbus:** the OpenPLC server reads and writes the runtime buffers directly, not the
program variables. All `I*`/`Q*`/ADC found are visible over Modbus, even if they are not declared
in the program, and writing a coil changes the output if the program does not overwrite it.

## First program

Example: `firmware/openplc/examples/gpio-echo.st` (Q0 = I0 or coil 8, Q1 blinks at 1 Hz, AIN0 is
copied to holding register 0).

Through the UI: Programs → Upload → Compile → Dashboard → Start PLC. Or from the PC:
```powershell
python firmware\tools\openplc-test.py <ip> --program firmware\openplc\examples\gpio-echo.st
python firmware\tools\openplc-test.py <ip> --autostart on --only-settings     # RUN after every boot
python firmware\tools\openplc-test.py <ip> --no-compile --no-start --write-coil 8 1
```
`openplc-test.py` logs in, uploads, compiles, starts, and reads coils, discrete inputs, holding
and input registers over Modbus TCP (standard Python library only).

A quirk of the compiler (matiec): one `VAR` block cannot contain both variables with `AT %...`
and ordinary ones (timers etc.); split them into two blocks.

## Checking without OpenPLC

```sh
gpioinfo | grep -E '"(I|Q)[0-9]+"'
gpioset -t0 Q0=1 ; gpioget I0
cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw
```
Stop OpenPLC (`/etc/init.d/openplc stop`), otherwise the lines are busy.

Independent Modbus check: any Modbus TCP client (ModScan, QModMaster, `pymodbus`) to
`<ip>:502`; the unit id does not matter.

## Modbus RTU

The UARTs (`/dev/ttyS1`, `S2`, `S4`, `S5` in the default profile) can be used by OpenPLC as
Modbus slave devices (Slave Devices in the UI) or by your own programs with libmodbus. RS-485
needs a direction line (DE): in the `breakout` profile these are `RS485_DE0/1`.

## OpenPLC settings

Settings in the UI: ports (Modbus 502, EtherNet/IP), "Start in RUN mode". The database is
`/opt/openplc/webserver/openplc.db`, the programs are in `/opt/openplc/webserver/st_files/`
(on the overlay).
