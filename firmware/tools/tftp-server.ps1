<#
.SYNOPSIS
  Minimal read-only TFTP server (RFC 1350 + options blksize/tsize/timeout) in pure PowerShell,
  for netbooting the Antminer board from U-Boot 2013.04 on a PC without Python.
  Same behaviour as tftp-server.py: only files inside -Root are served, nothing is written,
  every transfer runs in its own thread (a stale/duplicate RRQ must not block the next one).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tftp-server.ps1 -Root E:\Antminer\repo\firmware\out
  (netboot.ps1 starts it by itself when python is not installed)

  Windows Firewall must allow inbound UDP 69:
    netsh advfirewall firewall add rule name="TFTP in" dir=in action=allow protocol=UDP localport=69
#>
param(
    [string]$Root = (Join-Path (Split-Path $PSScriptRoot -Parent) "out"),
    [string]$Bind = "0.0.0.0",
    [int]$Port = 69,
    [int]$MaxBlksize = 1468,
    [int]$TimeoutMs = 3000,
    [int]$Retries = 6
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path $Root).Path.TrimEnd('\')

function Log([string]$msg) { Write-Host ("{0} {1}" -f (Get-Date -Format HH:mm:ss), $msg) }

# one transfer; runs in a worker runspace, so everything it needs is inside this block
$serve = {
    param([string]$Root, [string]$Bind, [string]$PeerIp, [int]$PeerPort, [string]$Filename,
          [hashtable]$Options, [int]$MaxBlksize, [int]$TimeoutMs, [int]$Retries)
    $OP_DATA = 3; $OP_ACK = 4; $OP_ERROR = 5; $OP_OACK = 6
    $ascii = [System.Text.Encoding]::ASCII
    $addr = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse($PeerIp), $PeerPort)
    $log = New-Object System.Collections.Generic.List[string]
    function U16([byte[]]$b, [int]$off) { return ([int]$b[$off] -shl 8) -bor [int]$b[$off + 1] }
    function Hdr([int]$op, [int]$arg) {
        return [byte[]]@((($op -shr 8) -band 0xff), ($op -band 0xff), (($arg -shr 8) -band 0xff), ($arg -band 0xff))
    }
    $sock = New-Object System.Net.Sockets.UdpClient (New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse($Bind), 0))
    $sock.Client.ReceiveTimeout = $TimeoutMs
    try {
        $rel = $Filename.Replace('/', '\').TrimStart('\')
        $path = [System.IO.Path]::GetFullPath((Join-Path $Root $rel))
        if (-not $path.StartsWith($Root + '\') -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
            $p = (Hdr $OP_ERROR 1) + $ascii.GetBytes("File not found") + [byte]0
            [void]$sock.Send($p, $p.Length, $addr)
            return "$PeerIp`: '$Filename' not found"
        }
        $data = [System.IO.File]::ReadAllBytes($path)
        $size = $data.Length
        $blksize = 512
        $oack = [ordered]@{}
        if ($Options.Contains("blksize")) {
            $blksize = [Math]::Max(8, [Math]::Min([int]$Options["blksize"], $MaxBlksize))
            $oack["blksize"] = "$blksize"
        }
        if ($Options.Contains("tsize")) { $oack["tsize"] = "$size" }
        if ($Options.Contains("timeout")) { $oack["timeout"] = $Options["timeout"] }
        $log.Add("$PeerIp`: RRQ $Filename ($size bytes, blksize $blksize)")

        # $true on the expected ACK, $false on timeout, $null on a client error
        function WaitAck([int]$expect) {
            for ($i = 0; $i -lt $Retries; $i++) {
                $peer = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Any, 0)
                try { $r = $sock.Receive([ref]$peer) } catch { return $false }
                if ($peer.Address.ToString() -ne $PeerIp -or $peer.Port -ne $PeerPort -or $r.Length -lt 4) { continue }
                $op = U16 $r 0; $blk = U16 $r 2
                if ($op -eq $OP_ERROR) {
                    $log.Add("$PeerIp`: client error " + $ascii.GetString($r, 4, $r.Length - 4).TrimEnd([char]0))
                    return $null
                }
                if ($op -eq $OP_ACK -and $blk -eq $expect) { return $true }
            }
            return $false
        }

        if ($oack.Count) {
            $p = [byte[]]@(0, $OP_OACK)
            foreach ($k in $oack.Keys) { $p += $ascii.GetBytes($k) + [byte]0 + $ascii.GetBytes($oack[$k]) + [byte]0 }
            $ok = $false
            for ($i = 0; $i -lt $Retries -and -not $ok; $i++) {
                [void]$sock.Send($p, $p.Length, $addr)
                $ok = WaitAck 0
                if ($null -eq $ok) { return ($log -join "`n") }
            }
            if (-not $ok) { $log.Add("$PeerIp`: no ACK for OACK"); return ($log -join "`n") }
        }

        $block = 1; $off = 0; $t0 = Get-Date
        while ($true) {
            $n = [Math]::Min($blksize, $size - $off)
            $p = New-Object byte[] (4 + $n)
            [Array]::Copy((Hdr $OP_DATA ($block -band 0xffff)), 0, $p, 0, 4)
            if ($n) { [Array]::Copy($data, $off, $p, 4, $n) }
            $ok = $false
            for ($i = 0; $i -lt $Retries -and -not $ok; $i++) {
                [void]$sock.Send($p, $p.Length, $addr)
                $ok = WaitAck ($block -band 0xffff)
                if ($null -eq $ok) { return ($log -join "`n") }
            }
            if (-not $ok) { $log.Add("$PeerIp`: timeout at block $block, giving up"); return ($log -join "`n") }
            $off += $n; $block++
            if ($n -lt $blksize) { break }
        }
        $dt = ((Get-Date) - $t0).TotalSeconds
        $log.Add(("{0}: sent {1} ({2} bytes in {3:N1} s)" -f $PeerIp, $Filename, $size, $dt))
        return ($log -join "`n")
    } finally {
        $sock.Close()
    }
}

$pool = [RunspaceFactory]::CreateRunspacePool(1, 8)
$pool.Open()
$workers = New-Object System.Collections.ArrayList   # @{ps=; handle=; key=}
$ascii = [System.Text.Encoding]::ASCII

function Reap {
    foreach ($w in @($workers)) {
        if ($w.handle.IsCompleted) {
            try { foreach ($line in $w.ps.EndInvoke($w.handle)) { if ($line) { Log $line } } }
            catch { Log "$($w.key): $($_.Exception.Message)" }
            $w.ps.Dispose(); [void]$workers.Remove($w)
        }
    }
}

$listener = New-Object System.Net.Sockets.UdpClient (New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse($Bind), $Port))
$listener.Client.ReceiveTimeout = 500
Log "TFTP server on ${Bind}:$Port serving $Root (read-only)"
try {
    while ($true) {
        Reap
        $peer = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Any, 0)
        try { $req = $listener.Receive([ref]$peer) } catch { continue }
        if ($req.Length -lt 4) { continue }
        $op = ([int]$req[0] -shl 8) -bor [int]$req[1]
        if ($op -ne 1) {
            $s = New-Object System.Net.Sockets.UdpClient
            $p = [byte[]]@(0, 5, 0, 4) + $ascii.GetBytes("Only RRQ supported") + [byte]0
            [void]$s.Send($p, $p.Length, $peer); $s.Close()
            continue
        }
        # filename\0 mode\0 [option\0 value\0]*
        $fields = $ascii.GetString($req, 2, $req.Length - 2).Split([char]0)
        $filename = $fields[0]
        $options = @{}
        for ($i = 2; $i + 1 -lt $fields.Length; $i += 2) {
            if ($fields[$i] -ne "") { $options[$fields[$i].ToLower()] = $fields[$i + 1] }
        }
        $key = "$($peer.Address):$($peer.Port)"
        if ($workers | Where-Object { $_.key -eq $key }) { continue }   # retransmitted RRQ of a running transfer
        $ps = [PowerShell]::Create(); $ps.RunspacePool = $pool
        [void]$ps.AddScript($serve).AddArgument($Root).AddArgument($Bind).AddArgument($peer.Address.ToString()).AddArgument($peer.Port).
            AddArgument($filename).AddArgument($options).AddArgument($MaxBlksize).AddArgument($TimeoutMs).AddArgument($Retries)
        [void]$workers.Add(@{ ps = $ps; handle = $ps.BeginInvoke(); key = $key })
    }
} finally {
    $listener.Close(); $pool.Close()
}
