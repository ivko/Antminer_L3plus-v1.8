<#
.SYNOPSIS
  Serve the Yocto ipk feed (tmp/deploy/ipk inside WSL) over HTTP for the boards' opkg.
  The image's /etc/opkg/*.conf points at http://<PC>:8000/ipk/... (PACKAGE_FEED_URIS in local.conf).

.EXAMPLE
  powershell -File serve-feed.ps1                 # serves \\wsl$\<distro>\home\<user>\antminer\yocto\build\tmp\deploy on :8000
  powershell -File serve-feed.ps1 -Port 8000 -Root "\\wsl$\Ubuntu-24.04\home\pc\antminer\yocto\build\tmp\deploy"
#>
param(
    [int]$Port = 8000,
    [string]$Root = ""
)
if ($Root -eq "") {
    $distro = (wsl -l -q | ForEach-Object { $_ -replace "`0", "" } | Where-Object { $_ -match '\S' } | Select-Object -First 1).Trim()
    $home_ = (wsl bash -c 'echo $HOME' | ForEach-Object { $_ -replace "`0", "" }).Trim()
    $Root = "\\wsl$\$distro$($home_ -replace '/', '\')\antminer\yocto\build\tmp\deploy"
}
if (-not (Test-Path "$Root\ipk")) { throw "no ipk feed at $Root\ipk (run bitbake package-index first)" }
Write-Host "serving $Root on http://0.0.0.0:$Port/  (feed: /ipk/<arch>/Packages.gz)  Ctrl-C to stop"
Write-Host "firewall: netsh advfirewall firewall add rule name=`"opkg feed`" dir=in action=allow protocol=TCP localport=$Port"
python -m http.server $Port --directory $Root --bind 0.0.0.0
