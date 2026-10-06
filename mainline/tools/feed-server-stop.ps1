param([int]$Port = 8000)
$c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($c) { Stop-Process -Id $c.OwningProcess -Force; Write-Host "stopped feed server pid $($c.OwningProcess)" } else { Write-Host "no feed server on :$Port" }
