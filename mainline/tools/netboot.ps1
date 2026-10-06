<#
.SYNOPSIS
  Netboot the Antminer BB-Black over the serial console: reboot, break into U-Boot 2013.04,
  fetch kernel/DTB/initramfs via TFTP into RAM and bootm. Nothing is written to NAND or SD.

.EXAMPLE
  powershell -File netboot.ps1 -ServerIp 192.168.1.50 -OutFile boot.log
  powershell -File netboot.ps1 -ServerIp 192.168.1.50 -BoardIp 192.168.1.77   # no DHCP

  Run tools/tftp-server.py --root repo/mainline/out on the PC first.
#>
param(
    [Parameter(Mandatory = $true)][string]$ServerIp,
    [string]$BoardIp = "",                 # empty -> use DHCP
    [string]$Port = "COM3",
    [string]$Kernel = "uImage.bin",
    [string]$Dtb = "am335x-antminer.dtb",
    [string]$Initrd = "initramfs.bin.SD",
    [string]$BootArgs = "console=ttyS0,115200n8 earlycon init=/bin/sh",
    [string]$OutFile = "",
    [int]$KernelLogSeconds = 90
)
$ErrorActionPreference = "Stop"
$ESC = [char]27

# --- 0. TFTP server: start tools/tftp-server.py on UDP 69 if nothing listens there ----
$tftpProc = $null
$outDir = Join-Path (Split-Path $PSScriptRoot -Parent) "out"
if (-not (Get-NetUDPEndpoint -LocalPort 69 -ErrorAction SilentlyContinue)) {
    $srv = Join-Path $PSScriptRoot "tftp-server.py"
    $tftpProc = Start-Process python -ArgumentList "`"$srv`" --root `"$outDir`" --bind 0.0.0.0 --port 69" `
        -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    if ($tftpProc.HasExited) { throw "tftp-server.py failed to start (python missing? port 69 blocked?)" }
    Write-Host "[netboot] started tftp-server.py (pid $($tftpProc.Id)) serving $outDir"
} else {
    Write-Host "[netboot] something already listens on UDP 69, using it"
}

$sp = New-Object System.IO.Ports.SerialPort $Port, 115200, None, 8, One
$sp.ReadTimeout = 100
$sp.ReadBufferSize = 4MB
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Open()
$log = New-Object System.Text.StringBuilder
$tail = ""

function Pump {
    $c = ""
    try { $c = $sp.ReadExisting() } catch {}
    if ($c.Length -gt 0) {
        [void]$log.Append($c)
        # U-Boot's plain readline echoes ESC bytes; keep them out of the prompt matching
        $script:tail = ($script:tail + $c) -replace '\x1b', ''
        if ($script:tail.Length -gt 4000) { $script:tail = $script:tail.Substring($script:tail.Length - 4000) }
        Write-Host -NoNewline $c
    }
    return $c.Length
}

function WaitFor([string]$regex, [int]$timeoutSec, [scriptblock]$while = $null) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        [void](Pump)
        if ($script:tail -match $regex) { return $true }
        if ($while) { & $while }
        Start-Sleep -Milliseconds 20
    }
    return $false
}

function UBoot([string]$cmd, [int]$timeoutSec = 30) {
    $script:tail = ""
    $sp.Write($cmd + "`r")
    if (-not (WaitFor 'U-Boot# $' $timeoutSec)) { throw "U-Boot: no prompt after '$cmd' within ${timeoutSec}s" }
    if ($script:tail -match 'Retry count exceeded|Not retrying|TFTP error|ERROR|Bad Magic|Wrong Image') {
        throw "U-Boot reported an error after '$cmd' (see log)"
    }
}

try {
    # --- 1. figure out where we are and get into U-Boot -----------------------------
    $sp.Write("`r")
    Start-Sleep -Milliseconds 800
    [void](Pump)
    if ($tail -match 'U-Boot# $') {
        Write-Host "`n[netboot] already at U-Boot prompt"
    } else {
        if ($tail -match 'login: $') {
            $sp.Write("root`r"); Start-Sleep -Milliseconds 800; [void](Pump)
            $sp.Write("admin`r"); Start-Sleep -Milliseconds 1500; [void](Pump)
        }
        Write-Host "`n[netboot] rebooting Linux and waiting for U-Boot..."
        if ($tail -match 'root@antMiner') {
            $sp.Write("reboot`r")
        } else {
            # bare init=/bin/sh shell from a previous netboot (prompt "/ # ", "/tmp # "...):
            # there is no init to talk to, force it
            $sp.Write("reboot -f`r")
        }
        # Spam ESC from the moment the U-Boot banner shows up until we get the prompt.
        $seen = WaitFor 'U-Boot 2013\.04|U-Boot SPL|Press ESC' 120
        if (-not $seen) { throw "no U-Boot banner seen within 120s" }
        $got = WaitFor 'U-Boot# $' 30 { $sp.Write([string]$ESC) }
        if (-not $got) { throw "could not break into U-Boot (autoboot continued?)" }
        Write-Host "`n[netboot] at U-Boot prompt"
        # the ESC bytes typed during autoboot sit in U-Boot's line buffer: Ctrl-C drops the line
        Start-Sleep -Milliseconds 300
        $script:tail = ""
        $sp.Write([string][char]3)
        [void](WaitFor 'U-Boot# $' 5)
        foreach ($i in 1..2) { try { UBoot "" 5 } catch {} }
    }

    # --- 2. network --------------------------------------------------------------------
    UBoot "setenv autoload no"
    UBoot "setenv serverip $ServerIp"
    if ($BoardIp -ne "") {
        UBoot "setenv ipaddr $BoardIp"
    } else {
        UBoot "dhcp" 60
        if ($tail -notmatch 'DHCP client bound to address') { throw "DHCP failed (see log); retry with -BoardIp" }
    }
    UBoot "printenv ipaddr serverip ethaddr"
    # diagnostics: GPMC CS0 CONFIG1..6 as programmed by U-Boot (known-good NAND timings)
    UBoot "md.l 0x50000060 6"

    # --- 3. fetch into RAM (addresses as in sdcard/uEnv.txt) ---------------------------
    UBoot "tftp 0x82000000 $Kernel" 180
    UBoot "tftp 0x88000000 $Dtb" 60
    UBoot "tftp 0x88100000 $Initrd" 300
    UBoot "iminfo 0x82000000" 30

    # --- 4. boot -----------------------------------------------------------------------
    UBoot "setenv bootargs $BootArgs"
    $script:tail = ""
    $sp.Write("bootm 0x82000000 0x88100000 0x88000000`r")
    Write-Host "`n[netboot] bootm sent, capturing kernel log for ${KernelLogSeconds}s..."
    $deadline = (Get-Date).AddSeconds($KernelLogSeconds)
    $lastData = Get-Date
    while ((Get-Date) -lt $deadline) {
        if ((Pump) -gt 0) { $lastData = Get-Date }
        # stop early once we have a shell prompt and 5 s of silence
        if ($tail -match '(/ # |sh-[0-9.]+# |# )$' -and ((Get-Date) - $lastData).TotalSeconds -gt 5) { break }
        Start-Sleep -Milliseconds 30
    }
    Write-Host "`n[netboot] done"
} finally {
    $sp.Close()
    if ($tftpProc -and -not $tftpProc.HasExited) { Stop-Process -Id $tftpProc.Id -Force }
    if ($OutFile -ne "") {
        [System.IO.File]::WriteAllText($OutFile, $log.ToString())
        Write-Host "[netboot] log saved to $OutFile"
    }
}
