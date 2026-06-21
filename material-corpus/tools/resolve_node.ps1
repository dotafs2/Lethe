$ErrorActionPreference = "Stop"

$Candidates = @()
if ($env:LETHE_NODE) {
    $Candidates += $env:LETHE_NODE
}
if ($env:LOCALAPPDATA) {
    $Candidates += (Join-Path $env:LOCALAPPDATA "codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
}
if ($env:USERPROFILE) {
    $Candidates += (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
}
$Candidates += "node.exe"

foreach ($Candidate in $Candidates) {
    $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
    if ($Command) {
        Write-Output $Command.Source
        exit 0
    }
    if (Test-Path $Candidate) {
        Write-Output (Resolve-Path $Candidate).Path
        exit 0
    }
}

throw "Node.js not found. Install Node.js, set LETHE_NODE, or run inside a Codex runtime."
