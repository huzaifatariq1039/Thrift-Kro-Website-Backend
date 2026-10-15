param(
    [switch]$IncludeAI
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$cacheDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "thrift-kro-uv-cache"
$pythonVersion = (Get-Content (Join-Path $projectRoot ".python-version") -Raw).Trim()
$commonArguments = @(
    "pip", "compile",
    "--python-version", $pythonVersion,
    "--python-platform", "x86_64-unknown-linux-gnu",
    "--generate-hashes",
    "--custom-compile-command", "powershell -File scripts/lock_dependencies.ps1"
)

$env:UV_CACHE_DIR = $cacheDirectory

Push-Location $projectRoot
try {
    & uv @commonArguments requirements.in --output-file requirements.txt --no-emit-index-url
    if ($LASTEXITCODE -ne 0) { throw "Failed to compile requirements.txt" }

    & uv @commonArguments requirements-audit.in --output-file requirements-audit.txt --no-emit-index-url
    if ($LASTEXITCODE -ne 0) { throw "Failed to compile requirements-audit.txt" }

    if ($IncludeAI) {
        & uv @commonArguments requirements-ai.in `
            --output-file requirements-ai.txt `
            --torch-backend cpu `
            --extra-index-url https://download.pytorch.org/whl/cpu `
            --index-strategy unsafe-best-match `
            --emit-index-url
        if ($LASTEXITCODE -ne 0) { throw "Failed to compile requirements-ai.txt" }
    }
}
finally {
    Pop-Location
}
