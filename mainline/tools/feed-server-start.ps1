<#
.SYNOPSIS
  Start (or report) the persistent HTTP feed server for opkg on port 8000, serving the Yocto
  tmp/deploy directory from WSL. Leaves it running in the background; stop with feed-server-stop.ps1.
#>
param([int]$Port = 8000)
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) { Write-Host "feed server already listening on :$Port (pid $($existing.OwningProcess))"; return }
$distro = (wsl -l -q | ForEach-Object { $_ -replace "`0", "" } | Where-Object { $_ -match '\S' } | Select-Object -First 1).Trim()
$home_ = (wsl bash -c 'echo $HOME' | ForEach-Object { $_ -replace "`0", "" }).Trim()
$root = "\\wsl$\$distro$($home_ -replace '/', '\')\antminer\yocto\build\tmp\deploy"
if (-not (Test-Path "$root\ipk")) { throw "no ipk feed at $root\ipk" }
$p = Start-Process python -ArgumentList "-m http.server $Port --directory `"$root`" --bind 0.0.0.0" -PassThru -WindowStyle Hidden
Start-Sleep 2
Write-Host "feed server pid $($p.Id) serving $root on :$Port"
