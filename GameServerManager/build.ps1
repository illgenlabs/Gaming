param(
    [switch]$Console,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$AppName = "GameServerManager"
$EntryPoint = "main.py"
$IconFile = "app.ico"

if (-not (Test-Path $EntryPoint)) {
    throw "$EntryPoint was not found in $PSScriptRoot"
}

if (-not (Test-Path $IconFile)) {
    throw "$IconFile was not found in $PSScriptRoot"
}

Write-Host "Installing build dependencies..."
py -m pip install --upgrade pip

if (Test-Path "requirements.txt") {
    py -m pip install -r requirements.txt
}

py -m pip install --upgrade pyinstaller

if ($Clean -or (Test-Path "build") -or (Test-Path "dist") -or (Test-Path "$AppName.spec")) {
    Write-Host "Removing previous build output..."
    Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "dist" -ErrorAction SilentlyContinue
    Remove-Item -Force "$AppName.spec" -ErrorAction SilentlyContinue
}

$Arguments = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name", $AppName,
    "--icon", $IconFile
)

if ($Console) {
    $Arguments += "--console"
} else {
    $Arguments += "--windowed"
}

$Arguments += $EntryPoint

Write-Host ""
Write-Host "Building $AppName.exe with icon $IconFile..."
py -m PyInstaller @Arguments

$ExePath = Join-Path $PSScriptRoot "dist\$AppName.exe"

if (-not (Test-Path $ExePath)) {
    throw "Build failed: $ExePath was not created."
}

Write-Host ""
Write-Host "Build completed successfully:"
Write-Host "  $ExePath"
Write-Host ""
Write-Host "For a diagnostic build with a visible console, run:"
Write-Host "  .\build.ps1 -Console -Clean"
