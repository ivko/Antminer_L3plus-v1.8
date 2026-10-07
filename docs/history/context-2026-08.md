# DIY from Scrap --- Context dump

Дата: 2026-08-19

## Проект: ANTMINER BB-Black V1.8 / L3+ като общ embedded Linux контролер

### 1. Хардуер

-   Платка: ANTMINER BB-Black V1.8.
-   SoC: TI AM3352 / AM335x, ARM Cortex-A8.
-   Платката е BeagleBone Black-подобна, но не е стандартен BBB.
-   Няма стандартния BeagleBone baseboard EEPROM.
-   Device tree описва 256 MiB RAM: memory { device_type = "memory"; reg
    = \<0x80000000 0x10000000\>; };
-   Използва NAND/GPMC вместо стандартната BBB eMMC конфигурация.
-   Налични/описани периферии: Ethernet, USB, MMC/microSD, NAND, GPIO,
    UART, I2C, SPI, PWM, timers, AES/SHA.
-   Описани, но disabled в разглеждания DT: PRUSS, CAN0, CAN1, ADC, LCD
    и част от PWM блоковете.
-   Има pinmux конфликти: едни и същи AM335x pads могат да бъдат
    UART/I2C/SPI и не могат да се активират едновременно без избор на
    mux.

### 2. Hash boards

-   Налични са Antminer L3+/L3++ hash boards.
-   Свързани са с идеята BB-Black да се използва и извън оригиналната
    mining функция.

### 3. Оригинална ОС

-   Стар Bitmain firmware, базиран на Ångström/OpenEmbedded.
-   Пакетен мениджър: opkg.
-   Старият публичен feeds.angstrom-distribution.org вече не е наличен.
-   Намерен е архив на Ångström v2013.06 binary feeds.
-   Видяна структура: feeds/v2013.06/ipk/eglibc/ sdk/ armv7ahf-vfp-neon/
    all/
-   Това позволява да се направи собствен локален HTTP mirror и да се
    възстанови opkg.

### 4. Скрипт за обезвреждане на mining логиката

Потребителят е автор на скрипт, който: - заменя /sbin/monitorcg с
бездействащ loop; - спира cgminer; - убива monitorcg; - инсталира
angstrom-feed-configs; - изпълнява opkg update; - инсталира
update-alternatives, ca-certificates, wget; - настройва wget CA
certificate; - стартира dropbear; - инсталира dtc/dtc-dev.

Оригиналната зависимост към:
http://feeds.angstrom-distribution.org/feeds/v2013.06/... вече е счупена
и трябва да се замени с локален mirror.

### 5. Native build environment

Потребителят има build-libmodbus.sh, който директно върху Antminer
инсталира: - update-alternatives - wget - autoconf - automake -
libtool - gcc-dev - gcc-symlinks - cpp-symlinks - g++-symlinks -
binutils - make - tar

След това сваля и компилира libmodbus 3.1.10: ./configure --prefix=/usr
--sysconfdir=/etc make && make install

Примерно приложение: gcc test.c -o test -I/usr/include/modbus/ -lmodbus

Цел: BB-Black да може да служи като общ embedded/industrial Linux
controller, включително Modbus.

### 6. Initramfs/NAND repack workflow

Потребителят има собствен Bash repacker.

Вход: - оригинален initramfs.bin.SD; - new-files.tgz; - optional image
name; - optional output filename.

Workflow: 1. Премахва 64-byte U-Boot legacy image header чрез tail
-c+65. 2. Разархивира gzip/cpio. 3. Използва fakeroot. 4. Прилага
delete.list.txt. 5. Наслагва файловете от new-files.tgz. 6. Repack в
newc cpio + gzip. 7. Създава нов U-Boot ramdisk image чрез mkimage -A
arm -O linux -T ramdisk. 8. Git се използва за управление на промените
по filesystem-а.

Важно: този workflow вече работи и засега не е приоритет да бъде
оптимизиран.

### 7. Device Tree workflow

Потребителят компилира собствен DTB: dtc am3352-antminer-next.dts -O dtb
-o am3352-antminer-next.dtb

После го записва директно: flash_erase /dev/mtd6 0x0 0x1 nandwrite -p
/dev/mtd6 am3352-antminer-next.dtb

### 8. NAND layout от DTS

Описани са: - spl: 0x000000, size 0x020000 - spl_backup1: 0x020000, size
0x020000 - spl_backup2: 0x040000, size 0x020000 - spl_backup3: 0x060000,
size 0x020000 - u-boot: 0x080000, size 0x1c0000 - bootenv: 0x240000,
size 0x020000 - fdt: 0x260000, size 0x020000 - kernel: 0x280000, size
0x500000 - root: 0x800000, size 0x1400000 - config: 0x1c00000, size
0x1400000

Следователно /dev/mtd6 е fdt partition.

Boot chain: AM3352 ROM -\> SPL -\> U-Boot -\> FDT -\> kernel -\>
initramfs/rootfs.

### 9. Device tree файлове

Разглеждани са: - am3352-antminer-next.dts - am335x-boneblack.dtsi -
am335x-bone-common.dtsi - am335x-bone-btm.dtsi -
am335x-boneblack-bitmainer.dts

Важно: Не е известно със сигурност кое в локалните DTS/DTSI файлове е
оригинално Bitmain и кое е редактирано от потребителя при стари
експерименти с EEPROM. Не трябва автоматично да се приема всичко за
factory source.

### 10. am3352-antminer-next.dts

Изглежда като експериментален wrapper върху am335x-boneblack.dtsi. Има/е
имало промени около: - disable на i2c0 / internal EEPROM; - активиране
на допълнителен UART. Това вероятно е част от експериментите на
потребителя.

### 11. am335x-bone-btm.dtsi

Съдържа SPI0/SPI1 pinmux и spidev. SPI max frequency: 16 MHz.

Има I2C1 конфигурация върху pads 0x180/0x184 и описан PCA9547 на 0x70 с
до шест канала, всеки с 24c256 EEPROM на 0x50. Самият i2c1 е оставен
disabled. Тази I2C/PCA9547/EEPROM част е подозирана като стара
потребителска експериментална промяна, не е доказано че е Bitmain
оригинал.

### 12. EEPROM проблемът

Трябва да се разграничават две нива:

Kernel/device-tree: - Linux не е задължително да има baseboard EEPROM. -
Хардуерът може да бъде описан директно чрез DT. - Старото BBB tree
съдържа наследена cape/EEPROM инфраструктура, която може да бъде
disabled.

SPL/U-Boot: - Това е по-важният неизвестен слой. - Стандартният BBB boot
flow може да използва EEPROM за board detection и избор на DDR
configuration. - Antminer BB-Black V1.8 очевидно boot-ва без стандартен
BBB EEPROM. - Следователно Bitmain SPL/U-Boot вероятно има hardcoded
board/DDR настройка или друга адаптация.

### 13. Основна посока за модернизация

Най-нискорисков първи вариант: оригинален Bitmain SPL/U-Boot -\>
собствен DTB -\> по-нов Linux kernel -\> Debian/Buildroot/друг rootfs,
вероятно от microSD

Предимство: Не се налага веднага да решаваме DDR initialization и EEPROM
board detection в нов SPL.

Следваща фаза: AM3352 ROM -\> собствен/по-нов SPL -\> нов U-Boot -\>
mainline DTB -\> съвременен Linux

За това трябва първо да се анализира оригиналният Bitmain U-Boot/SPL.

### 14. Какво трябва да се установи в U-Boot/SPL

-   Как се инициализират 256 MiB DDR.
-   Как се заобикаля липсващият BBB EEPROM.
-   NAND geometry.
-   BCH/ECC настройки.
-   bootcmd / environment.
-   Как се зареждат FDT и kernel.
-   Дали старият U-Boot може директно да boot-ва съвременен kernel.
-   Дали може безопасно да се boot-ва от microSD без промяна на NAND.

### 15. BBB_Pins.xlsx

Качен е файл BBB_Pins.xlsx. Съдържа листове: - P8 - P9 - Pin Mode
Register Value - Offsets

Използва се като AM335x/BBB pinmux справочник: - физически P8/P9 pin; -
ZCZ ball; - signal name; - DT offset; - Mode 0-7; - pin control register
values; - pad offsets.

Полезен е за превод: DTS offset/value -\> AM335x pad -\> mux функция -\>
физически pin, както и обратно.

### 16. GitHub repository

Използван е repository: ivko/Antminer_L3plus-v1.8

Споделяни са raw GitHub линкове към DTS/DTSI файловете. Някои URL-и
съдържаха временни token параметри; не трябва да се използват като
постоянен архив.

### 17. Важен принцип за следваща работа

-   Да не се променя работещият initramfs/repack workflow без конкретна
    причина.
-   Да не се приема, че всички DTS/DTSI части са factory Bitmain.
-   Да се използват файловете като hardware map и да се сравняват с
    оригинални източници/история, когато е възможно.
-   Следващият голям обект за reverse engineering е U-Boot/SPL.
-   Крайната DIY цел е платката да се използва като евтин общ
    Linux/industrial controller, с особен интерес към UART, GPIO, SPI,
    I2C и Modbus.

### 18. Свързани налични ресурси

Потребителят разполага поне с: - ANTMINER BB-Black V1.8 платка/платки; -
L3+ hash boards; - стар Bitmain/Ångström firmware; - DTS/DTSI source
collection; - собствен firmware/initramfs modification workflow; -
Git-based filesystem modifications; - Ångström v2013.06 binary feed
archive; - native GCC build setup; - libmodbus build script; - DTB
compile/flash workflow; - BBB_Pins.xlsx pinmux reference.

Този файл е snapshot на текущия разговорен/технически контекст и е
предназначен да може да бъде подаден обратно в бъдеща сесия.
