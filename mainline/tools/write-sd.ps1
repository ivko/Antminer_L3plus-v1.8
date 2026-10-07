<#
.SYNOPSIS
  Write the provisioning SD card image (.wic) to a microSD card in a card reader on Windows.

.DESCRIPTION
  Lists the removable USB disks, asks which one (unless -Disk is given), clears its partition
  table and writes the image raw, then verifies the first 70 MB (partition table + boot
  partition) by MD5. Needs administrator rights: the script re-launches itself elevated (UAC).
  Refuses disks that are not USB, smaller than 1 GB or larger than 64 GB, or the system disk.

.EXAMPLE
  powershell -File write-sd.ps1                                   # image = ..\out\antminer-provision.wic, asks for the disk
  powershell -File write-sd.ps1 -Image D:\x.wic -Disk 4 -Yes      # no questions
#>
param(
    [string]$Image = "",
    [int]$Disk = -1,
    [switch]$Yes,
    [string]$Log = ""
)
$ErrorActionPreference = "Stop"
if ($Image -eq "") { $Image = Join-Path (Split-Path $PSScriptRoot -Parent) "out\antminer-provision.wic" }
$Image = (Resolve-Path $Image).Path

function Candidates { Get-Disk | Where-Object { $_.BusType -eq "USB" -and $_.Size -gt 1GB -and $_.Size -le 64GB -and -not $_.IsBoot -and -not $_.IsSystem } }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    if ($Disk -lt 0) {
        $c = @(Candidates)
        if ($c.Count -eq 0) { throw "no removable USB disk between 1 and 64 GB found - is the card in the reader?" }
        $c | Select-Object Number, FriendlyName, @{n = 'GB'; e = { [math]::Round($_.Size / 1GB, 1) } } | Format-Table -AutoSize | Out-String | Write-Host
        $Disk = [int](Read-Host "Disk number of the SD card")
    }
    if (-not $Yes) {
        $d = Get-Disk -Number $Disk
        $a = Read-Host ("ERASE Disk {0} ({1}, {2} GB) and write {3}? type YES" -f $Disk, $d.FriendlyName, [math]::Round($d.Size / 1GB, 1), (Split-Path $Image -Leaf))
        if ($a -ne "YES") { Write-Host "cancelled"; return }
    }
    $Log = Join-Path $env:TEMP "write-sd.log"
    Remove-Item $Log -ErrorAction SilentlyContinue
    $p = Start-Process powershell -Verb RunAs -PassThru -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Image `"$Image`" -Disk $Disk -Yes -Log `"$Log`""
    $p.WaitForExit()
    if (Test-Path $Log) { Get-Content $Log | Where-Object { $_ -match '^(target|image|written|verify|DONE|ERROR)' } }
    return
}

# ---- elevated part ----------------------------------------------------------------------
if ($Log) { Start-Transcript -Path $Log -Force | Out-Null }
try {
    $d = Get-Disk -Number $Disk
    if (-not (Candidates | Where-Object Number -eq $Disk)) { throw "Disk $Disk ($($d.FriendlyName)) is not a removable USB disk of 1..64 GB - refusing" }
    "target: Disk $Disk $($d.FriendlyName) $([math]::Round($d.Size / 1GB, 1)) GB"
    $img = Get-Item $Image
    "image: $($img.FullName) $($img.Length) bytes"
    Clear-Disk -Number $Disk -RemoveData -RemoveOEM -Confirm:$false -ErrorAction SilentlyContinue
    Start-Sleep 2
    $in = [IO.File]::OpenRead($img.FullName)
    $out = New-Object IO.FileStream("\\.\PhysicalDrive$Disk", [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
    $buf = New-Object byte[] (4MB); $total = 0
    while (($n = $in.Read($buf, 0, $buf.Length)) -gt 0) {
        if ($n % 512) { [Array]::Clear($buf, $n, 512 - ($n % 512)); $n += 512 - ($n % 512) }
        $out.Write($buf, 0, $n); $total += $n
    }
    $out.Flush(); $out.Close(); $in.Close()
    "written $total bytes"
    $len = [int][Math]::Min(70MB, $img.Length)
    $md5 = [Security.Cryptography.MD5]::Create()
    $a = New-Object byte[] $len; $s = [IO.File]::OpenRead($img.FullName); [void]$s.Read($a, 0, $len); $s.Close()
    $r = New-Object IO.FileStream("\\.\PhysicalDrive$Disk", [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    $b = New-Object byte[] $len; [void]$r.Read($b, 0, $len); $r.Close()
    if ([BitConverter]::ToString($md5.ComputeHash($a)) -eq [BitConverter]::ToString($md5.ComputeHash($b))) { "verify first 70 MB: OK" } else { "verify first 70 MB: MISMATCH" }
    Update-Disk -Number $Disk
    "DONE"
} catch { "ERROR: $_" }
if ($Log) { Stop-Transcript | Out-Null }
