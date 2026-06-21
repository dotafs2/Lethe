$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Node = & (Join-Path $PSScriptRoot "resolve_node.ps1")
$Server = Join-Path $Root "material-corpus\tools\shallow_rain_water_browser_server.js"

Write-Host "Starting shallow rain water browser at http://127.0.0.1:8792/"
& $Node $Server 8792
