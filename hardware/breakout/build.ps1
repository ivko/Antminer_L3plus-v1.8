# Regenerate the schematic and run KiCad's checks + exports (Windows, KiCad 10 user install).
#   powershell -File build.ps1            # generate, ERC, netlist compare, PDF
#   powershell -File build.ps1 -NoPdf
param([switch]$NoPdf)
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cli = Join-Path $env:LOCALAPPDATA "Programs\KiCad\10.0\bin\kicad-cli.exe"
if (-not (Test-Path $cli)) { $cli = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" }
Set-Location $here
New-Item -ItemType Directory -Force out | Out-Null

python gen-sch.py
if ($LASTEXITCODE -ne 0) { exit 1 }

& $cli sch erc --severity-all --format report -o out\erc.rpt breakout.kicad_sch | Out-Null
$rpt = Get-Content out\erc.rpt -Raw
$errors = ([regex]::Matches($rpt, "(?m)^\s*; error\s*$")).Count
$warnings = ([regex]::Matches($rpt, "(?m)^\s*; warning\s*$")).Count
"ERC: $errors errors, $warnings warnings (out\erc.rpt)"
Select-String -Path out\erc.rpt -Pattern '^\[(\w+)\]' | ForEach-Object { $_.Matches[0].Groups[1].Value } |
    Group-Object | Sort-Object Count -Descending | ForEach-Object { "   $($_.Count) x $($_.Name)" }

& $cli sch export netlist --format kicadsexpr -o out\breakout.net breakout.kicad_sch | Out-Null
python check.py out\breakout.net

if (-not $NoPdf) {
    & $cli sch export pdf -o out\breakout.pdf breakout.kicad_sch | Out-Null
    "PDF: out\breakout.pdf"
}
