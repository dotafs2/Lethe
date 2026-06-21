$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Node = & (Join-Path $PSScriptRoot "resolve_node.ps1")
$Server = Join-Path $Root "material-corpus\tools\rain_water_gallery_server.js"

Write-Host "Starting Lethe rainy water gallery at http://127.0.0.1:8790/"
& $Node $Server 8790
