$ErrorActionPreference = "Stop"
$node = & (Join-Path $PSScriptRoot "resolve_node.ps1")
$script = Join-Path $PSScriptRoot "hlsl_selector_server.js"
$port = 8792
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "hlsl_selector_server.log"
$err = Join-Path $root "hlsl_selector_server.err.log"

Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object {
    if ($_ -and $_ -ne $PID) {
      Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
  }

Start-Process -WindowStyle Hidden -FilePath $node -ArgumentList @($script, [string]$port) -RedirectStandardOutput $log -RedirectStandardError $err
Start-Sleep -Milliseconds 600
Write-Host "HLSL Selector: http://127.0.0.1:$port/"
