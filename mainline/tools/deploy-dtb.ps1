<#
.SYNOPSIS
  Build a per-board device tree from a pinmux profile and write it to the board's NAND fdt
  partition over the serial console (TFTP for the transfer), then reboot into it.

.EXAMPLE
  powershell -File deploy-dtb.ps1 -Profile modbus-rtu                 # pinmux/boards/modbus-rtu.yaml
  powershell -File deploy-dtb.ps1 -Profile default -NoReboot
  powershell -File deploy-dtb.ps1 -Profile default -NetbootOnly       # try it from RAM first, NAND untouched

  Requires: WSL with the kernel tree (~/antminer/linux), board on COM3 running the antminer image
  (or the netbooted one), Ethernet to the PC.
#>
param(
    [Parameter(Mandatory = $true)][string]$Profile,
    [string]$ServerIp = "192.168.200.104",
    [string]$Port = "COM3",
    [switch]$NoReboot,
    [switch]$NetbootOnly
)
$ErrorActionPreference = "Stop"
$tools = $PSScriptRoot
$main = Split-Path $tools -Parent
$out = Join-Path $main "out"
$serial = Join-Path $tools "serial.ps1"
$e = [string][char]27; $z = [string][char]0

Write-Host "[deploy-dtb] generating + compiling pinmux/boards/$Profile.yaml in WSL"
$dtb = "am335x-antminer-$Profile.dtb"
Remove-Item (Join-Path $out $dtb) -ErrorAction SilentlyContinue
# dtc warnings go to stderr; merge inside bash so PowerShell's strict mode does not abort on them
$ErrorActionPreference = "Continue"
$r = wsl bash -c "cd /mnt/e/Antminer/repo/mainline/pinmux && bash build-dtb.sh boards/$Profile.yaml 2>&1" | Out-String
$ErrorActionPreference = "Stop"
Write-Host (($r -replace $z, '') -split "`r?`n" | Where-Object { $_ -match 'wrote|dts:|dtb:|error' }) -Separator "`n"
if (-not (Test-Path (Join-Path $out $dtb))) { throw "no $dtb in $out (generator or dtc failed, see above)" }

if ($NetbootOnly) {
    & (Join-Path $tools "netboot.ps1") -ServerIp $ServerIp -Port $Port -Kernel uImage-yocto.bin -Dtb $dtb -Initrd antminer-image.cpio.gz.u-boot -BootArgs "console=ttyS0,115200n8" -KernelLogSeconds 45
    return
}

Copy-Item (Join-Path $tools "flash-nand.sh") (Join-Path $out "flash-nand.sh") -Force
$srv = $null
if (-not (Get-NetUDPEndpoint -LocalPort 69 -ErrorAction SilentlyContinue)) {
    $srv = Start-Process python -ArgumentList "`"$tools\tftp-server.py`" --root `"$out`" --bind 0.0.0.0 --port 69" -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
}
try {
    # serial: login if needed, then flash mtd6 only
    $p = & $serial -Cmd "" -MinMs 1000 -IdleMs 800 -PromptRegex '(login: |# )$' -Raw -Port $Port
    if (($p -replace $e, '') -match 'login: $') { & $serial -Cmd "root" -MinMs 1500 -IdleMs 1000 -PromptRegex '# $' -Raw -Port $Port | Out-Null }
    $flash = & $serial -Cmd "cd /tmp && tftp -g -r flash-nand.sh $ServerIp && sh flash-nand.sh --dtb-only $ServerIp $dtb" -MinMs 4000 -IdleMs 4000 -MaxMs 120000 -PromptRegex '# $' -Port $Port
    Write-Host $flash
    if ($flash -notmatch 'verified') { throw "flash did not report 'verified'" }
    if (-not $NoReboot) {
        Write-Host "[deploy-dtb] rebooting into the new device tree"
        $boot = & $serial -Cmd "reboot" -MinMs 30000 -IdleMs 8000 -MaxMs 120000 -PromptRegex 'login: $' -Raw -Port $Port
        Write-Host ((($boot -replace $z, '') -replace $e, '') -split "`r?`n" | Where-Object { $_ -match 'Machine model|hostname|login:|rror' }) -Separator "`n"
    }
} finally {
    if ($srv -and -not $srv.HasExited) { Stop-Process -Id $srv.Id -Force }
}
