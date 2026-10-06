param(
    [string]$Cmd = "",
    [int]$MinMs = 1000,
    [int]$IdleMs = 800,
    [int]$MaxMs = 60000,
    [string]$Port = "COM3",
    [string]$OutFile = "",
    [string]$PromptRegex = 'root@antMiner:~# $',
    [switch]$Raw
)
$ErrorActionPreference = "Stop"
$sp = New-Object System.IO.Ports.SerialPort $Port, 115200, None, 8, One
$sp.ReadTimeout = 200
$sp.ReadBufferSize = 4MB
$sp.NewLine = "`n"
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Open()
try {
    Start-Sleep -Milliseconds 100
    $sp.DiscardInBuffer()
    if ($Cmd -ne "") { $sp.Write($Cmd + "`r") } else { $sp.Write("`r") }
    $sb = New-Object System.Text.StringBuilder
    $start = Get-Date
    $lastData = Get-Date
    $tail = ""
    while ($true) {
        try { $chunk = $sp.ReadExisting() } catch { $chunk = "" }
        $now = Get-Date
        if ($chunk.Length -gt 0) {
            [void]$sb.Append($chunk)
            $lastData = $now
            $tail = ($tail + $chunk)
            if ($tail.Length -gt 200) { $tail = $tail.Substring($tail.Length - 200) }
        } else {
            Start-Sleep -Milliseconds 30
        }
        $elapsed = ($now - $start).TotalMilliseconds
        $idle = ($now - $lastData).TotalMilliseconds
        if ($elapsed -gt $MinMs -and $idle -gt $IdleMs) {
            if ($PromptRegex -eq "" -or $tail -match $PromptRegex) { break }
            if ($idle -gt ($IdleMs * 10)) { break }
        }
        if ($elapsed -gt $MaxMs) { break }
    }
    $out = $sb.ToString()
    if (-not $Raw) {
        $lines = $out -split "`r?`n"
        if ($Cmd -ne "" -and $lines.Count -gt 0 -and $lines[0].Trim() -eq $Cmd.Trim()) { $lines = $lines[1..($lines.Count-1)] }
        $out = ($lines -join "`n")
    }
    if ($OutFile -ne "") {
        [System.IO.File]::WriteAllText($OutFile, $out)
        "saved {0} chars to {1} in {2:n1}s" -f $out.Length, $OutFile, ((Get-Date) - $start).TotalSeconds
    } else {
        $out
    }
} finally {
    $sp.Close()
}
