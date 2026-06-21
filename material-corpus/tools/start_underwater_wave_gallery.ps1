$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Node = & (Join-Path $PSScriptRoot "resolve_node.ps1")
$Server = Join-Path $PSScriptRoot "underwater_wave_gallery_server.js"
$Port = if ($env:PORT) { [int]$env:PORT } else { 8789 }

Set-Location $RepoRoot
& $Node $Server $Port
