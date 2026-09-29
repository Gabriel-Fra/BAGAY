<#
.SYNOPSIS
    Compiles and runs the Java Command API Parity Check on Windows PowerShell.
.DESCRIPTION
    Requires only a JDK (17+; tested against OpenJDK 21 and Oracle JDK 24).
    No Maven, no network, zero dependencies.
.PARAMETER Vectors
    Path to the hash vectors JSON file (defaults to ..\hash_vectors.json).
#>
param(
    [string]$Vectors = "..\hash_vectors.json"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$OutDir = Join-Path $ScriptDir "out"
if (Test-Path $OutDir) {
    Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$MainFiles = Get-ChildItem -Recurse -Filter "*.java" -Path (Join-Path $ScriptDir "src\main\java") | Select-Object -ExpandProperty FullName
$TestFiles = Get-ChildItem -Recurse -Filter "*.java" -Path (Join-Path $ScriptDir "src\test\java") | Select-Object -ExpandProperty FullName

Write-Host "Compiling Java sources..." -ForegroundColor Cyan
& javac -d $OutDir $MainFiles $TestFiles
if ($LASTEXITCODE -ne 0) {
    Write-Error "javac compilation failed with code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$ResolvedVectors = Resolve-Path -Path $Vectors -ErrorAction SilentlyContinue
if (-not $ResolvedVectors -or -not (Test-Path $ResolvedVectors)) {
    Write-Warning "No vectors file found at $Vectors."
    Write-Host "Generate one first from the repository root:"
    Write-Host "    python -m tools.export_hash_vectors hash_vectors.json"
    exit 1
}

Write-Host "Running ParityCheck against $ResolvedVectors..." -ForegroundColor Cyan
& java -cp $OutDir bagay.chain.ParityCheck "$ResolvedVectors"
exit $LASTEXITCODE
