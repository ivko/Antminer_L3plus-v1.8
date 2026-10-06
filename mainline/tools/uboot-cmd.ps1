<#
.SYNOPSIS
  Reboot the board over the serial console, break into U-Boot 2013.04, run a list of
  U-Boot commands, then either stay at the prompt or continue booting ("boot" = NAND boot).

.EXAMPLE
  powershell -File uboot-cmd.ps1 -Commands @("nand bad","nand read 0x82000000 0x3000000 0x20000","crc32 0x82000000 0x20000") -Then boot
  powershell -File uboot-cmd.ps1 -Commands @("printenv") -Then stay -OutFile uboot.log
#>
param(
    [Parameter(Mandatory = $true)][string[]]$Commands,
    [ValidateSet("boot", "stay")][string]$Then = "stay",
    [string]$Port = "COM3",
    [string]$OutFile = "",
    [int]$CmdTimeoutSec = 120,
    [int]$BootLogSeconds = 60
)
$ErrorActionPreference = "Stop"
$ESC = [char]27

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
function UBoot([string]$cmd, [int]$timeoutSec) {
    $script:tail = ""
    $sp.Write($cmd + "`r")
    if (-not (WaitFor 'U-Boot# $' $timeoutSec)) { throw "U-Boot: no prompt after '$cmd' within ${timeoutSec}s" }
}

try {
    $sp.Write("`r"); Start-Sleep -Milliseconds 800; [void](Pump)
    if ($tail -notmatch 'U-Boot# $') {
        if ($tail -match 'login: $') {
            $sp.Write("root`r"); Start-Sleep -Milliseconds 800; [void](Pump)
            $sp.Write("admin`r"); Start-Sleep -Milliseconds 1500; [void](Pump)
        }
        Write-Host "`n[uboot-cmd] rebooting and waiting for U-Boot..."
        if ($tail -match 'root@antMiner') { $sp.Write("reboot`r") } else { $sp.Write("reboot -f`r") }
        if (-not (WaitFor 'U-Boot 2013\.04|U-Boot SPL|Press ESC' 120)) { throw "no U-Boot banner seen within 120s" }
        if (-not (WaitFor 'U-Boot# $' 30 { $sp.Write([string]$ESC) })) { throw "could not break into U-Boot" }
        Start-Sleep -Milliseconds 300
        $script:tail = ""; $sp.Write([string][char]3); [void](WaitFor 'U-Boot# $' 5)
        foreach ($i in 1..2) { try { UBoot "" 5 } catch {} }
    }
    Write-Host "`n[uboot-cmd] at U-Boot prompt"
    foreach ($c in $Commands) { UBoot $c $CmdTimeoutSec }
    if ($Then -eq "boot") {
        Write-Host "`n[uboot-cmd] continuing normal boot (bootcmd)..."
        $script:tail = ""
        $sp.Write("boot`r")
        $deadline = (Get-Date).AddSeconds($BootLogSeconds)
        while ((Get-Date) -lt $deadline) { [void](Pump); if ($tail -match 'login: $') { break }; Start-Sleep -Milliseconds 50 }
    } else {
        Write-Host "`n[uboot-cmd] staying at U-Boot prompt"
    }
} finally {
    $sp.Close()
    if ($OutFile -ne "") { [System.IO.File]::WriteAllText($OutFile, $log.ToString()); Write-Host "[uboot-cmd] log saved to $OutFile" }
}
